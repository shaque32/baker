"""Verify before accept (plans/lawyer-checker-and-examiner-pilot.md).

Counsel accepts an evidence item only after opening that item's record (its Evidence item page)
under their own name. The view is the audit log's `view` entry (core/review/activity.py); it
shows the page was opened, never that it was read. Taking an acceptance back needs no view."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from core import db
from core.contracts import EvidenceStatus
from core.review import actions, activity, audit_log
from core.review.actions import NOT_OPENED, ReviewError
from eval import run_pipeline
from tests.test_report_consistency import _audit
from tests.test_review_screen import RUN_TIME, key_items

COUNSEL = "counsel:Pat Lee"
CLAIM = "C05"


def at(hours: float):  # noqa: ANN201
    return lambda: RUN_TIME + timedelta(hours=hours)


@pytest.fixture(scope="module")
def audited(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("verify") / "case01.db"
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


def _view(
    conn: sqlite3.Connection,
    actor: str | None,
    page: str,
    ident: str,
    listed: tuple[str, ...] = (),
    hours: float = 0.5,
) -> None:
    activity.record_view(
        conn, at(hours)(), actor, page, session="s1", query={"id": ident}, listed=listed
    )


def _accept(conn: sqlite3.Connection, eid: str, hours: float = 1):  # noqa: ANN202
    return actions.decide_counsel(
        conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "Read the record.", at(hours)
    )


def _counts(conn: sqlite3.Connection, eid: str) -> tuple[int, int]:
    reviews = conn.execute(
        "SELECT COUNT(*) FROM evidence_reviews WHERE evidence_id = ?", (eid,)
    ).fetchone()[0]
    log = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    return reviews, log


def test_the_lock_is_on_by_default():
    assert actions.require_record_opened in actions.COUNSEL_CHECKS
    assert actions.OPENED_PAGE in activity.ID_PAGES and actions.OPENED_PAGE in activity.PAGES


def test_counsel_cannot_accept_an_item_they_never_opened(conn):
    eid = key_items(conn, CLAIM)[0]
    before = _counts(conn, eid)
    with pytest.raises(ReviewError, match="open this item's record first"):
        _accept(conn, eid)
    assert _counts(conn, eid) == before  # nothing stored, nothing logged


def test_after_opening_the_record_counsel_can_accept(conn):
    eid = key_items(conn, CLAIM)[0]
    _view(conn, COUNSEL, "/evidence", eid)
    d = _accept(conn, eid)
    assert d.status is EvidenceStatus.COUNSEL_ACCEPTED
    rows = conn.execute(
        "SELECT action FROM audit_log WHERE actor = ? ORDER BY seq", (COUNSEL,)
    ).fetchall()
    assert rows == [("view",), ("evidence.decide",)]  # the view is on the record, before it
    assert audit_log.verify_chain(conn)
    assert audit_log.decision_problem(conn) is None


@pytest.mark.parametrize(
    "actor",
    [
        "counsel:Sam Ortiz",  # another lawyer opened it
        "expert:Pat Lee",  # the same name, as an expert
        None,  # opened before a name was entered
    ],
)
def test_only_a_view_by_that_counsel_counts(conn, actor):
    eid = key_items(conn, CLAIM)[0]
    _view(conn, actor, "/evidence", eid)
    with pytest.raises(ReviewError, match="open this item's record first"):
        _accept(conn, eid)


def test_opening_another_item_or_a_page_that_lists_it_does_not_count(conn):
    first, second = key_items(conn, CLAIM)[:2]
    _view(conn, COUNSEL, "/evidence", second)
    _view(conn, COUNSEL, "/claim", CLAIM, listed=(first,))  # listed there; its record unopened
    with pytest.raises(ReviewError, match="open this item's record first"):
        _accept(conn, first)
    _accept(conn, second)


def test_taking_an_acceptance_back_needs_no_new_view(conn):
    eid = key_items(conn, CLAIM)[0]
    _view(conn, COUNSEL, "/evidence", eid)
    _accept(conn, eid)
    d = actions.decide_counsel(conn, eid, EvidenceStatus.OPEN, COUNSEL, "Not sure.", at(2))
    assert d.status is EvidenceStatus.OPEN
    _accept(conn, eid, hours=3)  # the earlier view still stands for a second acceptance


def test_the_refusal_says_what_to_do():
    assert "Evidence item page" in NOT_OPENED
    assert "accept" in NOT_OPENED
