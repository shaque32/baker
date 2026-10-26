"""A model rationale with a forbidden word is withheld item by item; it no longer refuses the
whole report. Mabillon's own text still does. Synthetic case01 only; stand-in labels."""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core.audit import stance as stance_mod
from core.audit.invariants import InvariantViolation, check_report_text
from core.bundle import export
from core.bundle.verify import FAIL, verify_bundle
from core.contracts import Stance
from core.db import connect
from core.ingest import forwarded
from core.report import html as report_html
from core.report.html import render_report, write_report
from core.review import actions, audit_log, withheld
from core.review.actions import ReviewError
from core.review.redecide import redecide
from core.review.status import claim_state, claim_states
from eval import run_pipeline
from tests.test_report_consistency import START, _audit
from tests.test_review_screen import PORT, EverythingSupports, get, post
from ui.app import App

EXPERT = "expert:Test Expert"
SAYS = "The model reads this message as deleted later."
IRRELEVANT_SAYS = "Guilty of nothing here; another chat."


class SaysForbiddenWords(EverythingSupports):
    """Every record supports, as in the review-screen tests, except: on C01 each rationale says
    "deleted", and on C08 each record is labeled irrelevant with a rationale that says "Guilty"."""

    def label(self, assumption, candidate):  # noqa: ANN001, ANN201
        out = super().label(assumption, candidate)
        if assumption.claim_id == "C01":
            return out.model_copy(update={"rationale": SAYS})
        if assumption.claim_id == "C08":
            return out.model_copy(
                update={"stance": Stance.IRRELEVANT, "rationale": IRRELEVANT_SAYS}
            )
        return out


class SameLabelsCleanWords(SaysForbiddenWords):
    """The same stances and quotes, with rationales that use no forbidden word."""

    def label(self, assumption, candidate):  # noqa: ANN001, ANN201
        return super().label(assumption, candidate).model_copy(update={"rationale": "test"})


def _case(path: Path, labeler: EverythingSupports) -> Path:
    conn = run_pipeline.build_case("case01", path)
    _audit(conn, START, labeler=labeler)
    conn.close()
    return path


@pytest.fixture(scope="module")
def audited(tmp_path_factory) -> Path:
    return _case(tmp_path_factory.mktemp("withheld") / "case01.db", SaysForbiddenWords())


@pytest.fixture
def db(audited, tmp_path) -> Path:
    copy = tmp_path / "case.db"
    shutil.copy(audited, copy)
    return copy


@pytest.fixture
def conn(db) -> sqlite3.Connection:
    c = connect(db)
    yield c
    c.close()


def _ids(conn: sqlite3.Connection, claim_id: str) -> list[str]:
    st = claim_state(conn, claim_id)
    return [w.evidence_id for w in st.withheld]


# ---------------------------------------------------------------- the report renders


def test_a_rationale_saying_deleted_renders_the_report_with_the_item_flagged(conn, tmp_path):
    out = write_report(conn, tmp_path / "report.html")  # the word check runs before the write
    text = out.read_text(encoding="utf-8")
    check_report_text(text)
    assert SAYS not in text and IRRELEVANT_SAYS not in text
    c01 = claim_state(conn, "C01")
    assert c01.evidence and len(c01.withheld) == len(c01.evidence)
    for w in c01.withheld:
        row = re.search(rf"<tr id='{re.escape(html.escape(w.evidence_id))}'>(.*?)</tr>", text)
        assert row, w.evidence_id
        assert "Rationale withheld; needs expert review." in row.group(1)
        assert '<span class="withheld-word">deleted</span>' in row.group(1)
        assert w.sha256 == hashlib.sha256(SAYS.encode()).hexdigest() in row.group(1)
        assert "Not yet acknowledged by the expert." in row.group(1)
    # an irrelevant item has no row, but the section lists it, with its word in lower case
    c08 = claim_state(conn, "C08")
    assert c08.evidence and {x.stance for x in c08.evidence} == {Stance.IRRELEVANT}
    section = text.split("<h2>Withheld model rationales</h2>", 1)[1].split("<h2>", 1)[0]
    for w in c08.withheld:
        assert w.word == "guilty" and html.escape(w.evidence_id) in section
    # other claims' rationales are shown as before
    c02 = claim_state(conn, "C02")
    assert not c02.withheld and "Model rationale (inferred): test: always supports" in text


def test_withholding_changes_no_stance_quote_or_verdict(conn, tmp_path):
    """No verdict rule reads a rationale: the same labels with clean rationales give the same
    verdicts, labels, stances and quotes."""
    clean = connect(_case(tmp_path / "clean.db", SameLabelsCleanWords()))
    try:
        got = {st.claim.id: st for st in claim_states(conn)}
        want = {st.claim.id: st for st in claim_states(clean)}
        assert got.keys() == want.keys()
        for cid, st in got.items():
            assert (st.label, st.decision.verdict) == (want[cid].label, want[cid].decision.verdict)
            assert [(x.id, x.stance, x.quote) for x in st.evidence] == [
                (x.id, x.stance, x.quote) for x in want[cid].evidence
            ]
            assert not want[cid].withheld
    finally:
        clean.close()


def test_mabillons_own_text_with_deleted_still_refuses_the_report(conn, tmp_path, monkeypatch):
    monkeypatch.setitem(report_html.STANCE_LABEL, Stance.SUPPORTS, "supports (deleted)")
    with pytest.raises(InvariantViolation, match="deleted"):
        write_report(conn, tmp_path / "report.html")
    assert not (tmp_path / "report.html").exists()


def test_the_word_element_lets_only_the_word_itself_through():
    check_report_text('<p>uses the word <span class="withheld-word">deleted</span>.</p>')
    for bad in (
        '<span class="withheld-word">deleted records</span>',
        '<span class="withheld-word">Deleted</span>',  # the notice always writes lower case
        '<span class="withheld-word">x</span> deleted',
        "<span class='withheld-word'>deleted</span>",  # not the element the notice writes
        'dele<span class="withheld-word">guilty</span>ted',
    ):
        with pytest.raises(InvariantViolation):
            check_report_text(bad)


def test_the_check_reads_the_rationale_as_it_would_be_printed():
    assert withheld.forbidden_word("Plainly DELETED.") == "deleted"
    assert withheld.forbidden_word("the leader's phone") == "leader"
    assert withheld.forbidden_word("undeleted, not innocently") is None
    # what Mabillon puts in front of a model's rationale is clean, so only the model's words count
    assert withheld.forbidden_word(stance_mod.NOT_THE_MESSAGE) is None
    assert withheld.forbidden_word(forwarded.STANCE_NOTE + "supports. ok") is None
    assert withheld.forbidden_word(forwarded.BAKER_STANCE_NOTE + "supports. ok") is None


# ---------------------------------------------------------------- screen and report agree


def _overview_items(page: str) -> list[str]:
    card = page.split("<div class='card' id='withheld'>", 1)[1].split("</div></div>", 1)[0]
    return re.findall(r"<span class='mono'>([^<]*)</span>", card)


def _report_items(text: str) -> list[str]:
    section = text.split("<h2>Withheld model rationales</h2>", 1)[1].split("</table>", 1)[0]
    return re.findall(r"<tr><td>[^<]*</td><td class='mono'>([^<]*)</td>", section)


def test_screen_and_report_show_the_same_withheld_items_and_count(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    page = get(app, "/").text
    text = render_report(conn)
    expected = [w for st in claim_states(conn) for w in st.withheld]
    assert len(expected) == len(_ids(conn, "C01")) + len(_ids(conn, "C08")) > 2
    sentence = html.escape(withheld.summary(expected))
    assert sentence in page and sentence in text
    assert f"{len(expected)} model rationales withheld" in sentence
    ids = [html.escape(w.evidence_id) for w in expected]
    assert _overview_items(page) == _report_items(text) == ids
    # each claim page asks for the acknowledgment; the claim with relevant items shows the notice
    claim = get(app, "/claim", id="C01").text
    assert claim.count("badge b-withheld") == len(_ids(conn, "C01"))
    assert "Acknowledge the withheld rationale" in claim and SAYS not in claim
    assert "model rationale(s) withheld" in get(app, "/claim", id="C08").text
    assert "badge b-withheld" in get(app, "/evidence", id=_ids(conn, "C08")[0]).text


# ---------------------------------------------------------------- acknowledgment and sign-off


def test_each_acknowledgment_is_logged_without_the_rationale_text(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    eid = _ids(conn, "C01")[0]
    before = conn.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
    r = post(app, "/rationale/acknowledge", id=eid, next="/claim?id=C01")
    assert r.status == 303
    rows = conn.execute(
        "SELECT seq, actor, action, payload_json FROM audit_log WHERE seq > ?", (before,)
    ).fetchall()
    assert len(rows) == 1
    seq, actor, action, payload = rows[0]
    assert (actor, action) == (EXPERT, withheld.ACTION)
    sha = hashlib.sha256(SAYS.encode("utf-8")).hexdigest()
    assert json.loads(payload) == {"evidence_id": eid, "word": "deleted", "rationale_sha256": sha}
    assert "reads this message" not in payload
    assert audit_log.verify_chain(conn)
    # a second acknowledgment of the same rationale writes nothing
    post(app, "/rationale/acknowledge", id=eid, next="/claim?id=C01")
    assert conn.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0] == seq
    w = next(w for w in claim_state(conn, "C01").withheld if w.evidence_id == eid)
    assert (w.acknowledged_by, w.acknowledged_seq) == (EXPERT, seq)
    assert f"Acknowledged by {EXPERT} (audit log entry {seq})." in render_report(conn)
    # an item whose rationale is shown has nothing to acknowledge
    shown = claim_state(conn, "C02").evidence[0].id
    with pytest.raises(ReviewError, match="not withheld"):
        withheld.acknowledge(conn, shown, EXPERT)


def test_the_verdict_waits_for_every_acknowledgment(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    for cid in ("C01", "C08"):
        with pytest.raises(ReviewError, match="acknowledge the"):
            actions.confirm_verdict(conn, cid, EXPERT)
        with pytest.raises(ReviewError, match="acknowledge the"):
            verdict = claim_state(conn, cid).decision.verdict
            actions.override_verdict(conn, cid, verdict, EXPERT, "x")
    post(app, "/verdict", claim="C01", action="confirm", note="")
    assert "withheld model rationale" in get(app, "/").text  # the screen says why
    assert claim_state(conn, "C01").decision.confirmed_by is None
    assert "verdict.confirm" not in {r[0] for r in conn.execute("SELECT action FROM audit_log")}

    *first, last = _ids(conn, "C01")
    for eid in first:
        post(app, "/rationale/acknowledge", id=eid)
    with pytest.raises(ReviewError, match=re.escape(last)):
        actions.confirm_verdict(conn, "C01", EXPERT)
    assert cli_main(["acknowledge", "--db", str(db), "--id", last, "--by", EXPERT]) == 0
    post(app, "/verdict", claim="C01", action="confirm", note="")
    assert claim_state(conn, "C01").decision.confirmed_by == EXPERT
    st = claim_state(conn, "C01")
    assert st.withheld_waiting == 0 and all("withheld" not in t for _p, t in st.needs())

    # irrelevant items too, from their own page
    for eid in _ids(conn, "C08"):
        assert "Acknowledge the withheld rationale" in get(app, "/evidence", id=eid).text
        post(app, "/rationale/acknowledge", id=eid)
    actions.override_verdict(conn, "C08", claim_state(conn, "C08").decision.verdict, EXPERT, "ok")
    text = render_report(conn)
    assert "not yet acknowledged" not in text and "not yet</td>" not in text
    assert redecide(conn, EXPERT).decisions  # rules-only re-run still works
    assert audit_log.verify_chain(conn)


def test_a_new_rationale_needs_a_new_acknowledgment(conn):
    eid = _ids(conn, "C01")[0]
    withheld.acknowledge(conn, eid, EXPERT)
    assert next(w for w in claim_state(conn, "C01").withheld if w.evidence_id == eid).acknowledged
    with conn:  # what a later run that stores another rationale for the item does
        conn.execute("UPDATE evidence_items SET rationale = ? WHERE id = ?", ("Now innocent.", eid))
    w = next(w for w in claim_state(conn, "C01").withheld if w.evidence_id == eid)
    assert w.word == "innocent" and not w.acknowledged


def test_a_bundle_carries_the_acknowledgments_and_verifies(conn, tmp_path):
    for eid in _ids(conn, "C01"):
        withheld.acknowledge(conn, eid, EXPERT)
    full = export.export_bundle(
        conn, tmp_path / "all.zip", EXPERT, counsel_confirmed=True, include="all"
    )
    assert not [f for f in verify_bundle(full.path) if f.level == FAIL]
    # a scoped bundle leaves out irrelevant items, and the entries about them with them
    for eid in _ids(conn, "C08"):
        withheld.acknowledge(conn, eid, EXPERT)
    scoped = export.export_bundle(conn, tmp_path / "s.zip", EXPERT, counsel_confirmed=True)
    assert not [f for f in verify_bundle(scoped.path) if f.level == FAIL]
    with zipfile.ZipFile(scoped.path) as z:
        report = z.read(export.REPORT).decode("utf-8")
        log = z.read(f"{export.TABLES}audit_log.jsonl").decode("utf-8")
    check_report_text(report)
    assert _report_items(report) == [html.escape(e) for e in _ids(conn, "C01")]
    entries = [json.loads(line) for line in log.splitlines() if line.strip()]
    acks = [json.loads(r["payload_json"]) for r in entries if r["action"] == withheld.ACTION]
    assert [a["evidence_id"] for a in acks] == _ids(conn, "C01")
