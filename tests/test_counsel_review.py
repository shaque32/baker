"""Counsel review in the app (rules 0.5.0, option B; plans/confirm-rule-b-c.md PR 3).

A named defense lawyer can accept an evidence item (counsel_accepted) or take back their own
acceptance. A claim that rests on it is "Supported (reviewed by counsel)", never confirmed.
Counsel never dismisses and never changes an item an expert decided; an expert overrides
counsel. Every counsel decision is in the audit log and checked by bundle verify like an
expert's."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from core import db, pipeline
from core.bundle import export
from core.bundle.verify import FAIL, verify_bundle
from core.contracts import EvidenceStatus, ReviewerKind, SupportedBasis, Verdict
from core.report.html import render_report
from core.review import actions, activity, audit_log
from core.review.actions import ReviewError
from core.review.redecide import redecide
from core.review.status import verdict_label
from eval import run_pipeline
from tests.test_report_consistency import _audit
from tests.test_review_screen import RUN_TIME, key_items

COUNSEL = "counsel:Pat Lee"
EXPERT = "expert:Test Expert"
CLAIM = "C05"  # a timing claim whose key evidence covers every core assumption


def at(hours: float):  # noqa: ANN201
    return lambda: RUN_TIME + timedelta(hours=hours)


@pytest.fixture(scope="module")
def audited(tmp_path_factory) -> Path:
    """case01 audited with the AI reviewer accepting everything, and no human review."""
    path = tmp_path_factory.mktemp("counsel") / "case01.db"
    conn = run_pipeline.build_case("case01", path)
    _audit(conn, RUN_TIME)
    conn.close()
    return path


@pytest.fixture
def conn(audited, tmp_path):  # noqa: ANN201
    copy = tmp_path / "case01.db"
    copy.write_bytes(audited.read_bytes())
    c = db.connect(copy)
    yield c
    c.close()


def _current(conn: sqlite3.Connection, claim_id: str = CLAIM):  # noqa: ANN202
    return pipeline.load_verdict(conn, claim_id, pipeline.last_run(conn)["run_id"])


def _open(conn: sqlite3.Connection, eid: str, hours: float = 0.5) -> None:
    """Counsel opens the item's record, which an acceptance needs (require_record_opened)."""
    activity.record_view(
        conn, at(hours)(), COUNSEL, "/evidence", session="s-counsel", query={"id": eid}
    )


def _accept_key(conn: sqlite3.Connection, hours: float = 1) -> list[str]:
    items = key_items(conn, CLAIM)
    assert items
    for eid in items:
        _open(conn, eid, hours - 0.5)
        actions.decide_counsel(
            conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "Read the record.", at(hours)
        )
    return items


def _reviews(conn: sqlite3.Connection, eid: str) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT reviewer_kind, status FROM evidence_reviews WHERE evidence_id = ? ORDER BY seq",
        (eid,),
    ).fetchall()


# ---------------------------------------------------------------- what counsel can do


def test_counsel_acceptance_makes_the_claim_supported_reviewed_by_counsel(conn):
    assert _current(conn).verdict is Verdict.UNPROVEN  # AI review alone never supports
    items = _accept_key(conn)
    assert all(_reviews(conn, e)[-1] == ("counsel", "counsel_accepted") for e in items)
    redecide(conn, EXPERT, at(2))
    d = _current(conn)
    assert d.verdict is Verdict.SUPPORTED
    assert d.supported_basis is SupportedBasis.COUNSEL_REVIEWED
    assert verdict_label(d)[0] == "Supported (reviewed by counsel)"
    assert d.confirmed_by is None


def test_counsel_overrides_the_ai_reviewer(conn):
    eid = key_items(conn, CLAIM)[0]
    assert _reviews(conn, eid)[-1] == ("ai", "ai_accepted")
    _open(conn, eid)
    d = actions.decide_counsel(
        conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "Read it.", at(1)
    )
    assert d.reviewer_kind is ReviewerKind.COUNSEL and d.seq == len(_reviews(conn, eid))


@pytest.mark.parametrize(
    "status", [EvidenceStatus.ACCEPTED, EvidenceStatus.DISMISSED, EvidenceStatus.AI_ACCEPTED]
)
def test_counsel_never_accepts_as_an_expert_or_dismisses(conn, status):
    eid = key_items(conn, CLAIM)[0]
    before = _reviews(conn, eid)
    with pytest.raises(ReviewError):
        actions.decide_counsel(conn, eid, status, COUNSEL, "No.", at(1))
    assert _reviews(conn, eid) == before


def test_counsel_never_changes_an_item_an_expert_decided(conn):
    eid = key_items(conn, CLAIM)[0]
    actions.decide_evidence(conn, eid, EvidenceStatus.ACCEPTED, EXPERT, "Matches.", at(1))
    for status in (EvidenceStatus.COUNSEL_ACCEPTED, EvidenceStatus.OPEN):
        with pytest.raises(ReviewError, match="an expert has decided"):
            actions.decide_counsel(conn, eid, status, COUNSEL, "Read it.", at(2))
    actions.decide_evidence(conn, eid, EvidenceStatus.OPEN, EXPERT, "Look again.", at(3))
    with pytest.raises(ReviewError, match="an expert has decided"):  # even after a reopen
        actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "x", at(4))


def test_an_expert_overrides_counsel(conn):
    items = _accept_key(conn)
    actions.decide_evidence(conn, items[0], EvidenceStatus.DISMISSED, EXPERT, "Not it.", at(2))
    assert _reviews(conn, items[0])[-1] == ("expert", "dismissed")
    redecide(conn, EXPERT, at(3))
    assert _current(conn).supported_basis is not SupportedBasis.CONFIRMED


def test_an_expert_acceptance_after_counsel_makes_it_confirmed(conn):
    items = _accept_key(conn)
    for eid in items:
        actions.decide_evidence(conn, eid, EvidenceStatus.ACCEPTED, EXPERT, "Matches.", at(2))
    redecide(conn, EXPERT, at(3))
    d = _current(conn)
    assert d.verdict is Verdict.SUPPORTED and d.supported_basis is SupportedBasis.CONFIRMED


def test_counsel_takes_back_only_their_own_acceptance(conn):
    eid = key_items(conn, CLAIM)[0]
    with pytest.raises(ReviewError, match="only take back"):  # the AI's acceptance is not theirs
        actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, COUNSEL, "Undo.", at(1))
    _open(conn, eid)
    actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "Read.", at(1))
    with pytest.raises(ReviewError, match="already accepted"):
        actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "x", at(2))
    actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, COUNSEL, "Not sure now.", at(2))
    assert _reviews(conn, eid)[-1] == ("counsel", "open")
    with pytest.raises(ReviewError, match="only take back"):
        actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, COUNSEL, "Again.", at(3))


def test_one_lawyer_cannot_take_back_anothers_acceptance(conn):
    """Greptile on #238: the take-back checked only the last row's kind, not who wrote it."""
    eid = key_items(conn, CLAIM)[0]
    _open(conn, eid)
    actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "Read.", at(1))
    other = "counsel:Sam Ortiz"
    with pytest.raises(ReviewError, match="only take back an acceptance of their own"):
        actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, other, "Undo.", at(2))
    with pytest.raises(ReviewError, match="already accepted"):
        actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, other, "Me too.", at(2))
    assert _reviews(conn, eid)[-1] == ("counsel", "counsel_accepted")
    actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, COUNSEL, "Not sure.", at(3))
    assert _reviews(conn, eid)[-1] == ("counsel", "open")


def test_taking_it_back_leaves_the_claim_unproven(conn):
    for eid in _accept_key(conn):
        actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, COUNSEL, "Not sure.", at(2))
    redecide(conn, EXPERT, at(3))
    assert _current(conn).verdict is Verdict.UNPROVEN


@pytest.mark.parametrize("actor", ["expert:Test Expert", "counsel:", "Pat Lee", "ai:model"])
def test_only_a_named_counsel_actor(conn, actor):
    eid = key_items(conn, CLAIM)[0]
    with pytest.raises(ReviewError, match="counsel:<name>"):
        actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, actor, "x", at(1))


def test_a_reason_and_a_real_item_are_required(conn):
    eid = key_items(conn, CLAIM)[0]
    with pytest.raises(ReviewError, match="say why"):
        actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, " ", at(1))
    with pytest.raises(ReviewError, match="no evidence item"):
        actions.decide_counsel(conn, "ev:nope", EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "x")


def test_an_expert_cannot_store_a_counsel_or_ai_status(conn):
    eid = key_items(conn, CLAIM)[0]
    for status in (EvidenceStatus.COUNSEL_ACCEPTED, EvidenceStatus.AI_ACCEPTED):
        with pytest.raises(ReviewError, match="an expert accepts"):
            actions.decide_evidence(conn, eid, status, EXPERT, "x", at(1))


def test_a_precondition_check_can_refuse(conn, monkeypatch):
    seen = []

    def refuse(c, evidence_id, status, actor):  # noqa: ANN001, ANN202
        seen.append((evidence_id, status, actor))
        raise ReviewError("open the cited record first")

    monkeypatch.setattr(actions, "COUNSEL_CHECKS", [refuse])
    eid = key_items(conn, CLAIM)[0]
    before = _reviews(conn, eid)
    logged = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    with pytest.raises(ReviewError, match="open the cited record"):
        actions.decide_counsel(conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "x", at(1))
    assert seen == [(eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL)]
    assert _reviews(conn, eid) == before  # nothing stored, nothing logged
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == logged


# ---------------------------------------------------------------- log, trail, report, bundle


def test_every_counsel_decision_is_logged_and_matches(conn):
    items = _accept_key(conn)
    rows = conn.execute(
        "SELECT actor, action FROM audit_log WHERE actor = ? AND action != 'view' ORDER BY seq",
        (COUNSEL,),
    ).fetchall()
    assert rows == [(COUNSEL, "evidence.decide")] * len(items)
    assert audit_log.verify_chain(conn)
    assert audit_log.decision_problem(conn) is None


def test_a_counsel_review_added_outside_the_app_is_caught(conn):
    eid = key_items(conn, CLAIM)[0]
    seq = len(_reviews(conn, eid)) + 1
    conn.execute(
        "INSERT INTO evidence_reviews (id, evidence_id, seq, reviewer_kind, reviewer, status,"
        " reason, decided_at_utc) VALUES (?, ?, ?, 'counsel', ?, 'counsel_accepted', 'x', 't')",
        (f"rv:{eid}#{seq}", eid, seq, COUNSEL),
    )
    problem = audit_log.decision_problem(conn)
    assert problem is not None and "counsel review" in problem[1]


def test_the_activity_trail_names_counsel(conn):
    _accept_key(conn)
    mine = [s for s in activity.steps(conn) if s.actor == COUNSEL]
    assert mine and all(s.examiner == "Pat Lee (counsel)" for s in mine)
    assert all(s.claim_id == CLAIM for s in mine)


def test_the_report_says_counsel_never_confirmed(conn):
    _accept_key(conn)
    redecide(conn, EXPERT, at(2))
    text = render_report(conn)
    assert "Supported (reviewed by counsel)" in text
    assert "Reviewed by counsel, not an expert." in text
    assert "Counsel accepted, not an expert: counsel:Pat Lee" in text


def test_a_bundle_with_counsel_reviews_verifies(conn, tmp_path):
    items = _accept_key(conn)
    actions.decide_counsel(conn, items[0], EvidenceStatus.OPEN, COUNSEL, "Not sure.", at(1.5))
    redecide(conn, EXPERT, at(2))
    path = export.export_bundle(
        conn, tmp_path / "b.zip", EXPERT, counsel_confirmed=True, clock=at(3), include="all"
    ).path
    findings = verify_bundle(path)
    fails = [f"{f.check}: {f.detail}" for f in findings if f.level == FAIL]
    assert fails == []
    assert any(
        f.check == "expert reviews" and "expert or counsel reviews" in f.detail for f in findings
    )


def test_a_counsel_decision_stored_as_an_experts_is_refused(conn, tmp_path):
    """The log says counsel took an acceptance back; the row, rewritten by hand (dropping the
    append-only trigger), says an expert reopened the item. Status and reason still match the
    log, so only the reviewer kind gives it away, and the export refuses to write the bundle."""
    eid = _accept_key(conn)[0]
    actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, COUNSEL, "Not sure.", at(1.5))
    conn.execute("DROP TRIGGER evidence_reviews_no_update")
    conn.execute(
        "UPDATE evidence_reviews SET reviewer_kind = 'expert'"
        " WHERE evidence_id = ? AND reviewer_kind = 'counsel' AND status = 'open'",
        (eid,),
    )
    conn.commit()
    assert audit_log.decision_problem(conn) is None  # the log comparison alone misses it
    with pytest.raises(ReviewError, match="not the evidence item, reviewer or time"):
        export.export_bundle(
            conn, tmp_path / "b.zip", EXPERT, counsel_confirmed=True, clock=at(3), include="all"
        )


# ---------------------------------------------------------------- cases made before 0.8.0

NEW = (
    "    reviewer_kind  TEXT NOT NULL CHECK (reviewer_kind IN ('ai', 'expert', 'counsel')),\n",
    "    status         TEXT NOT NULL CHECK (status IN ('open', 'ai_accepted', 'accepted',"
    " 'counsel_accepted', 'dismissed')),\n",
    "                AND model_run_id IS NULL)\n"
    "        OR (reviewer_kind = 'counsel' AND status IN ('counsel_accepted', 'open')\n"
    "                AND model_run_id IS NULL))\n",
)
OLD = (
    "    reviewer_kind  TEXT NOT NULL CHECK (reviewer_kind IN ('ai', 'expert')),\n",
    "    status         TEXT NOT NULL CHECK (status IN ('open', 'ai_accepted', 'accepted',"
    " 'dismissed')),\n",
    "                AND model_run_id IS NULL))\n",
)


def _old_case() -> sqlite3.Connection:
    schema = db.SCHEMA_PATH.read_text(encoding="utf-8")
    for new, old in zip(NEW, OLD, strict=True):
        assert schema.count(new) == 1
        schema = schema.replace(new, old)
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema)
    conn.execute("PRAGMA foreign_keys = OFF")  # the evidence and run rows are not the point
    return conn


def _insert(conn, seq, kind, reviewer, status, run=None):  # noqa: ANN001, ANN202
    conn.execute(
        "INSERT INTO evidence_reviews (id, evidence_id, seq, reviewer_kind, reviewer, status,"
        " reason, model_run_id, decided_at_utc) VALUES (?, 'ev:1', ?, ?, ?, ?, 'r', ?, 't')",
        (f"rv:ev:1#{seq}", seq, kind, reviewer, status, run),
    )


def test_an_old_case_stores_counsel_reviews_once_upgraded():
    conn = _old_case()
    _insert(conn, 1, "ai", "ai:m", "ai_accepted", "mr:1")
    with pytest.raises(sqlite3.IntegrityError):
        _insert(conn, 2, "counsel", COUNSEL, "counsel_accepted")
    assert db.upgrade_evidence_reviews(conn) is True
    _insert(conn, 2, "counsel", COUNSEL, "counsel_accepted")
    assert conn.execute(
        "SELECT seq, reviewer_kind, status FROM evidence_reviews ORDER BY seq"
    ).fetchall() == [(1, "ai", "ai_accepted"), (2, "counsel", "counsel_accepted")]
    view = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'evidence_status'").fetchone()
    assert view is not None and "ORDER BY r.seq DESC LIMIT 1" in view[0]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE evidence_reviews SET reason = 'x'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM evidence_reviews")
    with pytest.raises(sqlite3.IntegrityError):  # the new CHECK still refuses a dismissal
        _insert(conn, 3, "counsel", COUNSEL, "dismissed")
    assert db.upgrade_evidence_reviews(conn) is False  # once is enough


def test_a_current_case_is_left_alone(conn):
    before = conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = 'evidence_reviews' ORDER BY name"
    ).fetchall()
    assert db.upgrade_evidence_reviews(conn) is False
    assert (
        conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name = 'evidence_reviews' ORDER BY name"
        ).fetchall()
        == before
    )
