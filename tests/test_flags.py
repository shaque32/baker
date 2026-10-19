# ruff: noqa: F811  (the screen fixtures, imported from test_review_screen)
"""Expert flags: a wrong label, a missed record or a verdict disagreement, on synthetic case01.

A flag is feedback for Baker's error log. It lives in the hash-chained audit log, never changes
a verdict or an evidence status, and exports only as a redacted summary with no case content.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from cli.main import main as cli_main
from core.review import audit_log, flags
from core.review.actions import ReviewError
from core.review.redecide import redecide
from core.review.status import claim_state, claim_states
from tests.test_review_screen import (  # noqa: F401 (fixtures)
    EXPERT,
    PORT,
    audited_case,
    conn,
    db,
    get,
    key_items,
    post,
)
from ui.app import App

NOTE = "ZZ-note-only-in-the-case 0111"
RECORD = "item1.xlsx Chats!ZZ412"
WHEN = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _state(conn: sqlite3.Connection) -> list[tuple]:
    """Everything a flag must never touch."""
    verdicts = list(conn.execute("SELECT * FROM verdicts ORDER BY rowid"))
    reviews = list(conn.execute("SELECT * FROM evidence_reviews ORDER BY rowid"))
    claims = list(conn.execute("SELECT * FROM claims ORDER BY id"))
    return [tuple(verdicts), tuple(reviews), tuple(claims)]


def _labels(conn: sqlite3.Connection) -> dict[str, str]:
    return {st.claim.id: st.label for st in claim_states(conn)}


def test_flags_are_stored_in_the_audit_log_and_change_no_verdict(conn):
    before, labels = _state(conn), _labels(conn)
    eid = key_items(conn, "C05")[0]
    f1 = flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, eid, "irrelevant", "", NOTE)
    f2 = flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT, record=RECORD)
    f3 = flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="contradicted")
    assert [f.id for f in flags.active_flags(conn)] == [f1.id, f2.id, f3.id]
    assert _state(conn) == before and _labels(conn) == labels
    assert audit_log.verify_chain(conn)
    snap = flags.flags(conn, "C05")[0].at_flag
    assert snap["stance"] == "supports" and snap["verdict"] == "unproven"
    assert snap["model"]["model"] == "test-stance"

    flags.withdraw_flag(conn, f2.id, EXPERT)
    assert [f.id for f in flags.active_flags(conn)] == [f1.id, f3.id]
    assert len(flags.flags(conn)) == 3  # the withdrawn flag stays in the log
    with pytest.raises(ReviewError):
        flags.withdraw_flag(conn, f2.id, EXPERT)
    # the rules re-run without a model call reads no flag
    redecide(conn, EXPERT)
    assert _labels(conn) == labels


def test_bad_flags_are_refused(conn):
    eid = key_items(conn, "C05")[0]
    with pytest.raises(ReviewError):
        flags.add_flag(conn, "C05", flags.WRONG_LABEL, "system", eid)  # experts only
    with pytest.raises(ReviewError):
        flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT)  # which item?
    with pytest.raises(ReviewError):
        flags.add_flag(conn, "C06", flags.WRONG_LABEL, EXPERT, eid)  # item is on another claim
    with pytest.raises(ReviewError):
        flags.add_flag(conn, "C05", "guess", EXPERT)
    with pytest.raises(ReviewError):
        flags.add_flag(conn, "C05", flags.VERDICT, EXPERT, should_be="maybe")
    with pytest.raises(ReviewError):
        flags.add_flag(conn, "nope", flags.VERDICT, EXPERT)
    assert flags.flags(conn) == []


def test_summary_is_redacted(conn):
    eid = key_items(conn, "C05")[0]
    flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, eid, "contradicts", note=NOTE)
    flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT, record=RECORD, note=NOTE)
    flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="contradicted")
    s = flags.summary(conn, "Pilot A", clock=lambda: WHEN)
    text = json.dumps(s)
    assert s["flag_counts"] == {"missed_record": 1, "verdict": 1, "wrong_label": 1}
    assert s["exported_on"] == "2026-10-15" and s["audit_log_chain_ok"]
    assert s["denominators"]["claims_with_verdict"] > 0
    assert s["denominators"]["evidence_items_labeled"] > 0
    # no case content: notes, records, ids, claim text, quotes, names, file names, hashes
    leaks = [NOTE, "ZZ412", "item1", eid, "C05", "C06", "expert:", "Test Expert"]
    leaks += [c.text for c in (claim_state(conn, "C05").claim, claim_state(conn, "C06").claim)]
    leaks += [x.quote for x in claim_state(conn, "C05").evidence if len(x.quote) > 8]
    leaks += [r[0] for r in conn.execute("SELECT sha256 FROM sources")]
    leaks += [r[0] for r in conn.execute("SELECT file_name FROM sources")]
    leaks += [r[0] for r in conn.execute("SELECT name FROM persons")]
    for leak in leaks:
        assert leak not in text, leak
    w = next(f for f in s["flags"] if f["kind"] == "wrong_label")
    assert w["stance_at_flag"] == "supports" and w["should_be"] == "contradicts"
    assert w["has_note"] and not w["names_a_record"]


def test_error_log_combines_pilots(conn):
    eid = key_items(conn, "C05")[0]
    flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, eid, "irrelevant")
    flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="contradicted")
    a = flags.summary(conn, "Pilot A")
    b = flags.summary(conn, "Pilot B | x")
    log = flags.error_log([a, a, b, {**b, "audit_log_chain_ok": False}])
    rows = log.rows
    assert log.left_out == 1
    assert [r.pilot for r in rows] == ["Pilot A", "Pilot B | x"]
    assert rows[0].cases == 2 and rows[0].wrong_label == 2 and rows[0].verdict == 2
    md = flags.error_log_markdown(log)
    assert "lower bound" in md and "| Pilot B / x |" in md
    assert (
        "Label supports flagged, expert says irrelevant (model test-stance, prompt none): 2" in md
    )
    assert "Left out: 1 summary" in md and "stance test-stance prompt none" in md
    with pytest.raises(ValueError):
        flags.error_log([{"format": "other"}])


def test_flags_from_the_claim_page(db, conn):
    app = App(db, port=PORT)
    eid = key_items(conn, "C05")[0]
    page = get(app, "/claim", id="C05").text
    assert page.count("Flag this label") == sum(
        1 for x in claim_state(conn, "C05").evidence if x.stance.value != "irrelevant"
    )
    assert "Flag: I disagree with this verdict" in page and "Flag a record Baker missed" in page
    # no reviewer name yet: nothing recorded
    post(app, "/flag/add", claim="C05", kind="wrong_label", evidence=eid, should_be="irrelevant")
    assert flags.flags(conn) == []

    post(app, "/expert", name="Test Expert")
    before = _state(conn)
    r = post(
        app,
        "/flag/add",
        claim="C05",
        kind="wrong_label",
        evidence=eid,
        should_be="irrelevant",
        note=NOTE,
        next="/claim?id=C05",
    )
    assert r.status == 303 and r.header("Location").startswith("/claim?id=C05")
    post(app, "/flag/add", claim="C05", kind="verdict", should_be="not_sure", next="/claim?id=C05")
    assert _state(conn) == before  # no evidence decision, no verdict change
    page = get(app, "/claim", id="C05").text
    assert "Flag saved" in page and "flagged by you" in page
    assert "Your flags on this claim (2)" in page and NOTE in page

    fid = flags.active_flags(conn)[0].id
    post(app, "/flag/withdraw", flag=fid, next="/claim?id=C05")
    assert "Your flags on this claim (1)" in get(app, "/claim", id="C05").text

    case_page = get(app, "/").text
    assert "Flags for Baker" in case_page and "Download the redacted summary" in case_page
    r = get(app, "/flags/summary.json", pilot="P1")
    assert r.status == 200 and "attachment" in r.header("Content-Disposition")
    assert ("Referrer-Policy", "same-origin") in r.headers
    s = json.loads(r.body)
    assert s["pilot"] == "P1" and s["flag_counts"] == {"verdict": 1} and s["withdrawn"] == 1
    assert NOTE not in r.body.decode()


def test_flag_posts_from_other_sites_are_refused(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    r = post(app, "/flag/add", token="wrong", claim="C05", kind="verdict")
    assert r.status == 403
    r = post(app, "/flag/add", {"origin": "https://evil.example"}, claim="C05", kind="verdict")
    assert r.status == 403
    assert flags.flags(conn) == []


def test_report_names_flags_without_notes(conn):
    from core.report.html import render_report

    flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT, record=RECORD, note=NOTE)
    report = render_report(conn)
    assert "flag.add" in report and "missed_record" in report
    assert NOTE not in report and "ZZ412" not in report


def test_cli_export_and_log(db, tmp_path, capsys):
    c = sqlite3.connect(db)
    c.close()
    assert cli_main(["flags", "--db", str(db), "list"]) == 0
    out = tmp_path / "s.json"
    assert cli_main(["flags", "--db", str(db), "export", "--pilot", "P1", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["pilot"] == "P1"
    md = tmp_path / "log.md"
    assert cli_main(["flag-log", str(out), str(out), "--out", str(md)]) == 0
    assert "| P1 | 2 |" in md.read_text()


def test_counted_flags_match_the_run_they_are_divided_by(conn):
    """Flags from an earlier run, or repeats on one target, never push a rate past 100%."""
    eid = key_items(conn, "C05")[0]
    flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="contradicted")
    flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="supported")  # changed mind
    flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, eid, "irrelevant")
    flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, eid, "contradicts")
    flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT)
    s = flags.summary(conn)
    assert s["flag_counts"] == {"missed_record": 1, "verdict": 1, "wrong_label": 1}
    assert s["not_counted"] == 2
    assert {f["should_be"] for f in s["flags"]} >= {"supported", "contradicts"}

    redecide(conn, EXPERT)  # a new run: new verdicts, the same evidence items
    s = flags.summary(conn)
    assert s["flag_counts"] == {"wrong_label": 1} and s["not_counted"] == 4


def test_irrelevant_records_can_be_flagged_on_their_own_page(db, conn):
    conn.execute(
        "UPDATE evidence_items SET stance = 'irrelevant' WHERE id = ?", (key_items(conn, "C05")[0],)
    )
    conn.commit()
    eid = next(x.id for x in claim_state(conn, "C05").evidence if x.stance.value == "irrelevant")
    app = App(db, expert="Test Expert", port=PORT)
    page = get(app, "/claim", id="C05").text
    assert "labeled irrelevant</summary>" in page and "Open, or flag this label" in page
    ev = get(app, "/evidence", id=eid).text
    assert "Flag this label" in ev
    post(app, "/flag/add", claim="C05", kind="wrong_label", evidence=eid, should_be="supports")
    assert flags.summary(conn)["flag_counts"] == {"wrong_label": 1}


def test_flag_records_bakers_verdict_after_an_override(conn):
    from core.contracts import Verdict
    from core.review import actions

    actions.override_verdict(conn, "C06", Verdict.CONTRADICTED, EXPERT, "Reads otherwise.")
    f = flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="contradicted")
    assert f.at_flag["verdict"] == "unproven" and f.at_flag["expert_override"]
    s = flags.summary(conn)
    assert s["flags"][0]["verdict_at_flag"] == "unproven"
    assert s["flags"][0]["expert_override_at_flag"]


def test_stale_or_unaudited_flags_are_refused(conn):
    run = claim_state(conn, "C05").run_id
    with pytest.raises(ReviewError, match="changed"):
        flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT, seen_run="run:older")
    flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT, seen_run=run)
    para = conn.execute("SELECT paragraph_id FROM claims WHERE id = 'C05'").fetchone()[0]
    from core.contracts import ClaimType
    from core.review import actions

    actions.add_claim(conn, "C99", para, 'Sent "ok".', ClaimType.EVENT, EXPERT)
    with pytest.raises(ReviewError, match="no verdict"):
        flags.add_flag(conn, "C99", flags.MISSED_RECORD, EXPERT)
    assert len(flags.flags(conn)) == 1


def test_error_log_keeps_unnamed_pilots_apart_and_always_names_versions(conn):
    flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="contradicted")
    s = flags.summary(conn)
    log = flags.error_log([s, s])
    assert [r.pilot for r in log.rows] == [
        "(no pilot named, file 1)",
        "(no pilot named, file 2)",
    ]
    md = flags.error_log_markdown(flags.error_log([{**s, "pilot": "Quiet", "flags": []}, s]))
    assert md.count("- Versions:") == 2 and md.count("- Models:") == 2
    assert "(rules 0.2" in md


def test_flags_must_disagree_and_target_the_audit_on_screen(db, conn):
    # A verdict flag naming the verdict Baker gave is not a disagreement.
    baker = claim_state(conn, "C06").decision.verdict.value
    with pytest.raises(ReviewError, match="verdict Baker gave"):
        flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be=baker)
    app = App(db, expert="Test Expert", port=PORT)
    page = get(app, "/claim", id="C06").text
    form = page.split("Flag: I disagree with this verdict", 1)[1].split("</form>", 1)[0]
    assert f"value='{baker}'" not in form

    # An evidence item the audit on screen does not hold (an older run's) can't be flagged.
    eid = key_items(conn, "C05")[0]
    cols = [r[1] for r in conn.execute("PRAGMA table_info(evidence_items)")]
    rest = ", ".join(c for c in cols if c != "id")
    with conn:
        conn.execute(
            f"INSERT INTO evidence_items (id, {rest}) SELECT 'ev:old', {rest}"
            " FROM evidence_items WHERE id = ?",
            (eid,),
        )
    with pytest.raises(ReviewError, match="not in the audit on screen"):
        flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, "ev:old", "irrelevant")
    assert "Flag this label" not in get(app, "/evidence", id="ev:old").text
    assert flags.flags(conn) == []


def test_error_log_leaves_out_summaries_of_unfinished_audits(conn):
    s = flags.summary(conn, pilot="P")
    assert s["audit_complete"] is True
    log = flags.error_log([s, {**s, "audit_complete": False}])
    assert log.partial == 1 and log.rows[0].cases == 1
    assert "before the case's audit finished" in flags.error_log_markdown(log)


def test_no_op_label_flags_and_removed_claims_are_refused_and_never_counted(conn):
    from core.contracts import ClaimStatus
    from core.review import actions

    eid = key_items(conn, "C05")[0]
    with pytest.raises(ReviewError, match="label the item has"):
        flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, eid, "supports")
    flags.add_flag(conn, "C05", flags.WRONG_LABEL, EXPERT, eid, "irrelevant")
    flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT)
    flags.add_flag(conn, "C06", flags.VERDICT, EXPERT, should_be="contradicted")
    assert flags.summary(conn)["flag_counts"] == {
        "missed_record": 1,
        "verdict": 1,
        "wrong_label": 1,
    }
    actions.set_claim_status(conn, "C05", ClaimStatus.REMOVED, EXPERT)
    s = flags.summary(conn)
    assert s["flag_counts"] == {"verdict": 1} and s["not_counted"] == 2
    with pytest.raises(ReviewError, match="was removed"):
        flags.add_flag(conn, "C05", flags.MISSED_RECORD, EXPERT)
