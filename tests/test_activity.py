# ruff: noqa: F811  (the screen fixtures, imported from test_review_screen)
"""The examiner's activity trail (core/review/activity.py): each page opened in a case is an
audit-log entry, shown on the Activity page, in the CSV, the CLI and the report. Synthetic
case01 only."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from cli.main import main as cli_main
from core.report.html import render_report
from core.review import activity, audit_log
from core.review.status import claim_state, queue
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
from ui.app import App, listed_evidence

T0 = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def tick(self, **delta: float) -> None:
        self.now += timedelta(**delta)


def _app(db, name: str | None = "Test Expert") -> tuple[App, Clock]:  # noqa: ANN001
    app = App(db, expert=name, port=PORT)
    clock = Clock()
    app.clock = clock
    return app, clock


def _views(conn: sqlite3.Connection) -> list[tuple[str, dict]]:
    return [
        (actor, json.loads(p))
        for actor, p in conn.execute(
            "SELECT actor, payload_json FROM audit_log WHERE action = 'view' ORDER BY seq"
        )
    ]


def test_each_page_opened_is_logged_with_time_name_and_what_it_listed(db, conn):
    app, _ = _app(db)
    assert get(app, "/claim", id="C05").status == 200
    (actor, p), *_ = _views(conn)
    assert actor == EXPERT
    assert p["page"] == "/claim" and p["id"] == "C05" and p["session"] == app.session
    shown = {e.id for e in claim_state(conn, "C05").evidence}
    assert p["listed"] and set(p["listed"]) <= shown
    at = conn.execute("SELECT at_utc FROM audit_log WHERE action = 'view'").fetchone()[0]
    assert at == "2026-10-21T15:00:00Z"
    audit_log.require_intact(conn)  # hash-chained like every other entry


def test_an_evidence_view_says_where_its_record_sits(db, conn):
    app, _ = _app(db)
    eid = key_items(conn, "C05")[0]
    get(app, "/evidence", id=eid)
    _, p = _views(conn)[-1]
    rec, src, loc = conn.execute(
        "SELECT record_id, source_id, locator FROM evidence_items WHERE id = ?", (eid,)
    ).fetchone()
    assert (p["id"], p["record_id"], p["source_id"], p["locator"]) == (eid, rec, src, loc)
    assert p["claim_id"] == "C05"
    assert "quote" not in p and "text" not in p  # where the record is, never its text


def test_a_refresh_is_one_view_but_a_post_between_makes_another(db, conn):
    app, clock = _app(db)
    get(app, "/claim", id="C05")
    clock.tick(seconds=5)
    get(app, "/claim", id="C05")  # a refresh, nothing done between
    assert len(_views(conn)) == 1
    eid = key_items(conn, "C05")[0]
    post(app, "/evidence/decide", id=eid, status="accepted", reason="Seen in the sheet.")
    get(app, "/claim", id="C05")
    assert len(_views(conn)) == 2
    get(app, "/claim", id="C06")
    assert [p["id"] for _, p in _views(conn)] == ["C05", "C05", "C06"]


def test_time_on_page_runs_to_the_next_step_and_long_stretches_say_so(db, conn):
    app, clock = _app(db)
    eid = key_items(conn, "C05")[0]
    get(app, "/claim", id="C05")
    clock.tick(seconds=40)
    get(app, "/evidence", id=eid)
    clock.tick(minutes=45)
    get(app, "/claim", id="C06")
    clock.tick(seconds=1)
    get(app, "/claim", id="C05")
    trail = [s for s in activity.steps(conn) if s.is_view]
    assert [s.seconds for s in trail] == [40, 45 * 60, 1, None]  # the last has no end yet
    assert [s.away for s in trail] == [False, True, False, False]
    assert activity.duration(trail[1].seconds, trail[1].away).endswith("may include time away")
    a = activity.by_claim(trail)["C05"]
    assert a.opened == 2 and a.evidence_opened == {eid} and a.actions == 0
    assert a.seconds == 40 and a.away == 1  # the long stretch is counted apart
    assert (a.first_at, a.last_at) == ("2026-10-21T15:00:00Z", "2026-10-21T15:45:41Z")


def test_an_expert_action_ends_the_time_on_page_and_counts_on_its_claim(db, conn):
    app, _ = _app(db)
    app.clock = lambda: datetime.now(UTC)  # the decision is logged at the real time
    eid = key_items(conn, "C05")[0]
    get(app, "/evidence", id=eid)
    post(app, "/evidence/decide", id=eid, status="accepted", reason="Seen in the sheet.")
    view, decision = activity.steps(conn)[-2:]
    assert decision.action == "evidence.decide" and decision.claim_id == "C05"
    assert view.seconds is not None and view.seconds >= 0
    assert activity.by_claim([view, decision])["C05"].actions == 1


def test_a_new_screen_session_leaves_the_last_page_time_unknown(db, conn):
    first, clock = _app(db)
    get(first, "/claim", id="C05")
    second, clock2 = _app(db)
    clock2.now = T0 + timedelta(hours=3)
    get(second, "/claim", id="C06")
    views = [s for s in activity.steps(conn) if s.is_view]
    assert views[0].payload["session"] != views[1].payload["session"]
    assert views[0].seconds is None  # the screen was closed at a time Baker did not record


def test_a_page_opened_before_a_name_is_entered_says_so(db, conn):
    app, _ = _app(db, name=None)
    get(app, "/")
    actor, _ = _views(conn)[-1]
    assert actor == activity.UNNAMED
    assert activity.steps(conn)[-1].examiner == "(no name entered)"


def test_views_change_no_verdict_and_stay_out_of_the_expert_actions(db, conn):
    before = [(s.claim.id, s.decision.verdict, s.label) for s in queue(conn)]
    app, clock = _app(db)
    for cid in ("C05", "C06", "C05"):
        get(app, "/claim", id=cid)
        clock.tick(seconds=30)
    assert [(s.claim.id, s.decision.verdict, s.label) for s in queue(conn)] == before
    report = render_report(conn)
    assert "<h2>Examiner activity</h2>" in report and "3 page views in 1 screen session" in report
    assert "<td>view</td>" not in report  # not listed as an expert action
    assert "view " not in report.split("Expert actions:")[1].split("</p>")[0]


def test_the_report_says_when_no_views_are_recorded(conn):
    assert "No page views are recorded for this case" in render_report(conn)


def test_activity_page_csv_and_log_page(db, conn):
    app, clock = _app(db)
    get(app, "/claim", id="C05")
    clock.tick(seconds=12)
    page = get(app, "/activity").text
    assert "Time on page runs from opening a page to the next page or action" in page
    # the Activity page is recorded before it renders, so it ends the claim page's time
    c05 = page.split("activity?claim=C05'>C05</a></td>")[1].split("</tr>")[0]
    assert c05.startswith("<td>1</td>") and "<td>12 s</td>" in c05
    c06 = page.split("activity?claim=C06'>C06</a></td>")[1].split("</tr>")[0]
    assert c06.startswith("<td>0</td><td colspan='5' class='muted'>not opened</td>")
    assert c06.endswith("<td>1</td>")  # its claim.add at setup is an action, not a view
    only = get(app, "/activity", claim="C05").text
    assert "Trail for claim C05" in only
    r = get(app, "/activity.csv")
    assert r.header("Content-Type").startswith("text/csv")
    assert "attachment" in r.header("Content-Disposition")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    first = next(x for x in rows if x["action"] == "view")
    assert first["page"] == "/claim" and first["claim_id"] == "C05"
    assert first["seconds_on_page"] == "12" and first["evidence_listed"] != "0"
    assert rows[-1]["page"] == "/activity.csv"  # the download includes itself
    hashes = dict(conn.execute("SELECT seq, hash FROM audit_log").fetchall())
    assert all(hashes[int(x["seq"])] == x["entry_hash"] for x in rows)
    log = get(app, "/log").text
    assert "page views not shown" in log and "<td>view</td>" not in log
    assert "<td>view</td>" in get(app, "/log", views="1").text


def test_csv_cells_a_spreadsheet_would_run_are_neutralised():
    s = activity.Step(1, "2026-10-21T15:00:00Z", "expert:=cmd", "view", {"page": "/"}, "h")
    row = next(csv.DictReader(io.StringIO(activity.csv_text([s]))))
    assert row["examiner"] == "'=cmd"


def test_editing_a_view_breaks_the_chain(db, conn):
    app, _ = _app(db)
    get(app, "/claim", id="C05")
    conn.execute("DROP TRIGGER audit_log_no_update")
    conn.execute(
        "UPDATE audit_log SET payload_json = replace(payload_json, 'C05', 'C06')"
        " WHERE action = 'view'"
    )
    conn.commit()
    with pytest.raises(audit_log.ChainBroken):
        audit_log.require_intact(conn)


def test_a_view_that_cannot_be_written_is_reported_not_hidden(db, conn, monkeypatch):
    app, _ = _app(db)

    def busy(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(activity, "record_view", busy)
    assert get(app, "/claim", id="C05").status == 200
    assert "could not record that you opened this page" in get(app, "/").text


def test_cli_lists_and_exports_the_trail(db, tmp_path, capsys):
    app, _ = _app(db)
    get(app, "/claim", id="C05")
    get(app, "/claim", id="C06")
    assert cli_main(["activity", "--db", str(db), "--claim", "C06"]) == 0
    out = capsys.readouterr().out
    assert "Claim  C06" in out and "C05" not in out
    target = tmp_path / "trail.csv"
    assert cli_main(["activity", "--db", str(db), "--csv", str(target)]) == 0
    assert target.read_text(encoding="utf-8").startswith("seq,at_utc,examiner")


def test_listed_evidence_reads_the_pages_links():
    html_text = (
        "<a href='/evidence?id=ev%3Aa%7C1'>x</a> <a href=\"/evidence?id=ev:b\">y</a>"
        " <a href='/evidence?id=ev%3Aa%7C1'>again</a> <a href='/claim?id=C01'>c</a>"
    )
    assert listed_evidence(html_text) == ["ev:a|1", "ev:b"]
