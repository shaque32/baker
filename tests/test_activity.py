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
from core.contracts import EvidenceStatus
from core.report.html import render_report
from core.review import activity, audit_log
from core.review.actions import ReviewError
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
    get(app, "/evidence", id=eid)  # the page the form returns to
    view, decision, back = activity.steps(conn)[-3:]
    assert decision.action == "evidence.decide" and decision.claim_id == "C05"
    assert view.seconds is not None and view.seconds >= 0
    assert activity.by_claim([view, decision, back])["C05"].actions == 1


def test_an_action_from_elsewhere_does_not_end_a_page(db, conn):
    from core.review import actions
    from core.review.status import claim_state as state

    app, clock = _app(db)
    get(app, "/claim", id="C05")
    clock.tick(seconds=30)
    eid = state(conn, "C05").evidence[0].id
    for by in ("expert:Someone Else", EXPERT):  # another examiner, or this one's command line
        actions.decide_evidence(conn, eid, EvidenceStatus.DISMISSED, by, "Not relevant.")
    clock.tick(seconds=20)
    get(app, "/claim", id="C06")
    view = next(s for s in activity.steps(conn) if s.is_view)
    assert view.seconds == 50  # the page stayed open until the next page on this screen


def test_a_page_with_no_later_page_on_its_screen_is_not_timed(db, conn):
    app, _ = _app(db)
    get(app, "/claim", id="C05")
    other, _ = _app(db)  # a second screen on the case
    get(other, "/claim", id="C06")
    view = next(s for s in activity.steps(conn) if s.is_view)
    assert view.seconds is None
    a = activity.by_claim(activity.steps(conn))["C05"]
    assert a.untimed == 1 and activity.time_on_pages(a) == "0 s, plus 1 not timed"


def test_going_to_another_page_and_back_is_two_views(db, conn):
    app, _ = _app(db)
    get(app, "/claim", id="C05")
    get(app, "/cases")  # not a case page, but the examiner left the claim
    get(app, "/claim", id="C05")
    assert [p["id"] for _, p in _views(conn)] == ["C05", "C05"]


def test_a_capped_list_is_counted_as_a_floor():
    s = activity.Step(
        1, "2026-10-21T15:00:00Z", EXPERT, "view",
        {"page": "/claim", "id": "C05", "listed": ["ev:a"], "listed_left_out": 3}, "h",
        claim_id="C05",
    )  # fmt: skip
    assert activity.listed_count(activity.by_claim([s])["C05"]) == "at least 1"


def test_a_withdrawn_flag_counts_on_its_claim(conn):
    t = datetime(2026, 10, 21, tzinfo=UTC)
    with conn:
        audit_log.append(conn, t, EXPERT, "flag.add", {"flag_id": "fl:1", "claim_id": "C05"})
        audit_log.append(conn, t, EXPERT, "flag.withdraw", {"flag_id": "fl:1"})
    added, withdrawn = activity.steps(conn)[-2:]
    assert (added.claim_id, withdrawn.claim_id) == ("C05", "C05")


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
    assert "page views in" not in render_report(conn)  # the table is off by default
    post(app, "/activity/report", include="1")
    report = render_report(conn)
    assert "<h2>Examiner activity</h2>" in report and "3 page views in 1 screen session" in report
    assert "<td>view</td>" not in report  # not listed as an expert action
    assert "view " not in report.split("Expert actions:")[1].split("</p>")[0]


def test_the_report_says_when_no_views_are_recorded(conn):
    activity.set_in_report(conn, T0, EXPERT, True)
    assert "No page views are recorded for this case" in render_report(conn)


def test_the_activity_table_is_in_the_report_only_when_the_expert_includes_it(db, conn):
    app, clock = _app(db)
    get(app, "/claim", id="C05")
    clock.tick(seconds=40)
    report = render_report(conn)
    assert "<h2>Examiner activity</h2>" in report and "Not included." in report
    assert "Time on its pages" not in report
    page = get(app, "/activity").text
    assert "In the report: left out</strong> (the default)" in page
    assert "Include activity in the report" in page

    assert post(app, "/activity/report", include="1").status == 303
    assert activity.in_report(conn)
    actor, payload = conn.execute(
        "SELECT actor, payload_json FROM audit_log WHERE action = ? ORDER BY seq DESC",
        (activity.REPORT_ACTION,),
    ).fetchone()
    assert actor == EXPERT and json.loads(payload) == {"include": True, "session": app.session}
    report = render_report(conn)
    assert "Time on its pages" in report and "Not included." not in report
    assert "report.activity" in report  # the choice is in the report's expert actions
    assert "In the report: included." in get(app, "/activity").text

    post(app, "/activity/report", include="1")  # already so: nothing more is logged
    n = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = ?", (activity.REPORT_ACTION,)
    ).fetchone()[0]
    assert n == 1
    post(app, "/activity/report", include="0")
    assert not activity.in_report(conn) and "Not included." in render_report(conn)
    audit_log.require_intact(conn)


def test_only_a_named_expert_can_change_the_report_switch(db, conn):
    app, _ = _app(db, name=None)
    post(app, "/activity/report", include="1")
    assert not activity.in_report(conn)
    with pytest.raises(ReviewError, match="expert:<name>"):
        activity.set_in_report(conn, T0, "viewer:unnamed", True)


def test_the_cli_sets_the_report_switch(db, conn, capsys):
    assert cli_main(["activity", "--db", str(db), "--in-report", "on"]) == 2
    assert not activity.in_report(conn)
    assert cli_main(["activity", "--db", str(db), "--in-report", "on", "--by", EXPERT]) == 0
    assert "the report includes examiner activity" in capsys.readouterr().out
    assert activity.in_report(conn)
    assert cli_main(["activity", "--db", str(db), "--in-report", "off", "--by", EXPERT]) == 0
    assert not activity.in_report(conn)


def test_activity_page_csv_and_log_page(db, conn):
    app, clock = _app(db)
    get(app, "/claim", id="C05")
    clock.tick(seconds=12)
    page = get(app, "/activity").text
    assert "Time on page runs from opening a page to the next page opened" in page
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
    real = activity.record_view

    def busy(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(activity, "record_view", busy)
    page = get(app, "/claim", id="C05")
    assert page.status == 200
    assert "could not record that you opened these pages" in page.text  # on the page itself
    assert "Claim (database is locked)" in page.text
    download = get(app, "/activity.csv")  # a download carries no warning, so it waits
    assert "could not record" not in download.text
    monkeypatch.setattr(activity, "record_view", real)
    shown = get(app, "/").text
    assert "Activity (download) (database is locked)" in shown
    assert "could not record" not in get(app, "/claims").text  # shown once


def test_a_view_that_cannot_be_written_breaks_the_refresh_check(db, conn, monkeypatch):
    app, _ = _app(db)
    real = activity.record_view
    get(app, "/claim", id="C05")

    def busy(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(activity, "record_view", busy)
    get(app, "/claim", id="C06")  # not recorded, but the examiner left C05
    monkeypatch.setattr(activity, "record_view", real)
    get(app, "/claim", id="C05")
    assert [p["id"] for _, p in _views(conn)] == ["C05", "C05"]


def test_a_report_switch_from_the_command_line_does_not_end_a_page(db, conn):
    app, clock = _app(db)
    get(app, "/claim", id="C05")
    clock.tick(seconds=40)
    activity.set_in_report(conn, clock(), EXPERT, True)  # baker activity --in-report on
    clock.tick(seconds=20)
    get(app, "/claim", id="C06")
    get(app, "/activity")
    clock.tick(seconds=10)
    post(app, "/activity/report", include="0")  # the screen's own switch ends its page
    get(app, "/claims")
    views = [s for s in activity.steps(conn) if s.is_view]
    assert views[0].payload["id"] == "C05" and views[0].seconds == 60
    assert views[2].payload["page"] == "/activity" and views[2].seconds == 10


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
    one = tmp_path / "c06.csv"
    assert cli_main(["activity", "--db", str(db), "--claim", "C06", "--csv", str(one)]) == 0
    rows = list(csv.DictReader(io.StringIO(one.read_text(encoding="utf-8"))))
    assert rows and {r["claim_id"] for r in rows} == {"C06"}


def test_listed_evidence_reads_the_pages_links():
    html_text = (
        "<a href='/evidence?id=ev%3Aa%7C1'>x</a> <a href=\"/evidence?id=ev:b\">y</a>"
        " <a href='/evidence?id=ev%3Aa%7C1'>again</a> <a href='/claim?id=C01'>c</a>"
    )
    assert listed_evidence(html_text) == ["ev:a|1", "ev:b"]


def test_item_ids_are_kept_whole_and_only_the_pages_own_switches_are_kept(conn):
    long_id = "C" + "9" * 300
    p = activity.view_payload(conn, "/claim", session="s", query={"id": long_id})
    assert p["id"] == long_id
    p = activity.view_payload(
        conn, "/activity", session="s", query={"id": "x", "claim": "C05", "all": "1"}
    )
    assert "id" not in p and p["query"] == {"all": "1", "claim": "C05"}
    p = activity.view_payload(  # free text where an id or switch would go
        conn, "/log", session="s", query={"claim": "Smith and Jones", "views": "yes", "all": "1"}
    )
    assert p["query"] == {"all": "1"} and p["query_left_out"] == 2
    p = activity.view_payload(conn, "/activity", session="s", query={"claim": "Smith and Jones"})
    assert "query" not in p and p["query_left_out"] == 1


def test_free_text_in_the_address_is_counted_not_kept(db, conn):
    app, _ = _app(db)
    get(app, "/flags/summary.json", pilot="Smith and Jones LLP", id="Smith and Jones")
    _, p = _views(conn)[-1]
    assert "query" not in p and "id" not in p and p["query_left_out"] == 2
    assert "Smith" not in json.dumps(p)


def test_a_forbidden_word_in_the_address_never_breaks_the_activity_page(db, conn):
    app, _ = _app(db)
    assert get(app, "/activity", claim="deleted").status == 200
    page = get(app, "/activity")  # not a claim, so the trail does not keep it
    assert page.status == 200 and "deleted" not in page.text


def test_the_same_page_reloaded_after_a_minute_is_a_new_view(db, conn):
    app, clock = _app(db)
    get(app, "/run")
    clock.tick(seconds=10)
    get(app, "/run")  # the progress page refreshing itself
    clock.tick(seconds=50)
    get(app, "/run")  # 50 s after the last load, though 60 s after the first
    clock.tick(minutes=5)
    get(app, "/run")  # the screen closed and the page opened again
    assert [p["page"] for _, p in _views(conn)] == ["/run", "/run"]


def test_another_sites_requests_are_not_recorded_as_views(db, conn):
    from ui.app import Request

    app, _ = _app(db)
    for headers in (
        {"sec-fetch-site": "cross-site", "sec-fetch-dest": "image"},
        {"sec-fetch-site": "cross-site", "sec-fetch-dest": "document"},
        {"sec-fetch-site": "same-origin", "sec-fetch-dest": "iframe"},
    ):
        app.handle(
            Request("GET", "/claim", {"id": "C05"}, {"host": f"127.0.0.1:{PORT}", **headers})
        )
    assert _views(conn) == []
    ok = {"sec-fetch-site": "same-origin", "sec-fetch-dest": "document"}
    app.handle(Request("GET", "/claim", {"id": "C05"}, {"host": f"127.0.0.1:{PORT}", **ok}))
    typed = {"sec-fetch-site": "none", "sec-fetch-dest": "document"}
    app.handle(Request("GET", "/claim", {"id": "C06"}, {"host": f"127.0.0.1:{PORT}", **typed}))
    assert [p["id"] for _, p in _views(conn)] == ["C05", "C06"]


def test_reading_a_long_trail_of_actions_is_linear(db, conn):
    import time

    t = datetime(2026, 10, 21, tzinfo=UTC)
    with conn:
        for i in range(6000):
            audit_log.append(
                conn, t, EXPERT, "view", {"page": "/claim", "id": "C05", "session": "s"}
            )
            audit_log.append(conn, t, EXPERT, "note", {"claim_id": "C05", "n": i})
    start = time.perf_counter()
    trail = activity.steps(conn)
    assert time.perf_counter() - start < 5  # quadratic would take minutes here
    assert all(s.seconds == 0 for s in trail if s.is_view and s.seq < trail[-1].seq - 1)


def test_a_report_that_cannot_be_anchored_records_no_view(db, conn, monkeypatch):
    app, _ = _app(db)

    def unwritable(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise audit_log.AnchorUnwritable(audit_log.anchors_path(db), OSError("read-only"))

    before = conn.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]
    monkeypatch.setattr(audit_log, "anchor", unwritable)
    assert get(app, "/report").status == 303  # no report, the case closes
    assert conn.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0] == before


def test_only_an_accepted_upload_makes_the_next_page_a_new_view(db, conn):
    from tests.test_start_case import multipart
    from ui.app import Request

    def upload(token: str) -> None:
        body, ctype = multipart({"token": token, "kind": "govdoc"}, "a.pdf", b"%PDF-1.4")
        req = Request("POST", "/case/import", {}, {"host": f"127.0.0.1:{PORT}",
                      "content-type": ctype})  # fmt: skip
        app.handle_upload(req, io.BytesIO(body), len(body))

    app, _ = _app(db)
    get(app, "/setup")
    upload("forged")  # another site cannot clear the refresh check
    get(app, "/setup")
    upload(app.token)
    get(app, "/setup")
    assert [p["page"] for _, p in _views(conn)] == ["/setup", "/setup"]


def test_every_accepted_post_makes_the_next_page_a_new_view(db, conn):
    app, _ = _app(db)
    get(app, "/setup")
    post(app, "/case/recovery/done")  # handled before the case database opens
    get(app, "/setup")
    assert [p["page"] for _, p in _views(conn)] == ["/setup", "/setup"]
