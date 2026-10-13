"""Timeline check and quiet stretches on synthetic case01, the screen pages and the report.

case01's affidavit plants the traps these views exist for: paragraph 8 states the time a report
printed in UTC+0 for a phone set to New York, paragraph 9 reverses the order of a message and a
call, and both phones hold no WhatsApp records from the evening of March 19 to March 24.
All data is synthetic.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit.invariants import check_report_text
from core.casework import cases
from core.db import apply_schema, connect
from core.report.html import render_report
from core.report.timeline import compute
from core.review.actions import ReviewError
from core.timeline import settings as tl_settings
from core.timeline.check import TimelineRow, timeline
from core.timeline.gaps import find_gaps
from core.timeline.records import CaseRecords
from core.timeline.settings import Settings
from core.timeline.stated import read_document
from eval import run_pipeline
from ui.app import App, Request

EXPERT = "expert:Test Expert"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
HOST = {"host": "127.0.0.1:8765"}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("timeline") / "case01.db"
    run_pipeline.build_case("case01", path).close()
    return path


@pytest.fixture
def db(built, tmp_path) -> Path:
    copy = tmp_path / "case.db"
    shutil.copy(built, copy)
    return copy


@pytest.fixture
def conn(db) -> sqlite3.Connection:
    c = connect(db)
    yield c
    c.close()


def rows_for(conn: sqlite3.Connection, s: Settings | None = None) -> list[TimelineRow]:
    return timeline(CaseRecords(conn), read_document(conn), s or Settings())


def row(rows: list[TimelineRow], para: str, starts: str) -> TimelineRow:
    got = [r for r in rows if r.stated.para_label == para and r.stated.text.startswith(starts)]
    assert len(got) == 1, [(r.stated.para_label, r.stated.text) for r in rows]
    return got[0]


# ---------------------------------------------------------------- timeline


def test_a_time_read_off_the_printed_utc_clock_differs_by_five_hours(conn):
    r = row(rows_for(conn), "8", "At 2:31 a.m.")
    assert r.status == "differs"
    (lk,) = r.links
    assert lk.how == "quote" and lk.words == "its done" and lk.total == 2
    assert {c.record.id for c in lk.shown} == {"msg:item1:Chats!1011", "msg:item2:Chats!903"}
    assert all(c.delta_s == -5 * 3600 for c in lk.shown)
    assert "5 h before" in r.summary
    assert any("agrees with the clock the report printed" in n for n in r.notes)


def test_a_wide_enough_tolerance_lets_the_same_record_match(conn):
    r = row(rows_for(conn, Settings(tolerance_min=300)), "8", "At 2:31 a.m.")
    assert r.status == "matches"
    assert {c.status for c in r.links[0].shown} == {"within"}


def test_the_document_ordering_a_message_after_a_call_is_tested_as_order(conn):
    r = row(rows_for(conn), "9", "At 10:05 p.m.")
    assert r.status == "order"
    (lk,) = r.links
    assert lk.relation == "after" and lk.words == "move it tonight"  # line break folded
    (c,) = lk.shown
    assert c.order_conflict and c.record.id == "msg:item1:Chats!952"
    assert "14 min before" in r.summary


def test_a_call_is_tied_by_the_number_in_its_sentence(conn):
    r = row(rows_for(conn), "7", "At about 7:58 p.m.")
    assert r.status == "matches"
    (lk,) = r.links
    assert lk.how == "number" and lk.total > 2
    assert {c.record.id for c in lk.shown[:2]} == {
        "call:item1:Call Log!9",
        "call:item2:Call Log!15",
    }
    assert all(c.status == "inside" for c in lk.shown[:2])


def test_a_statement_with_nothing_to_tie_shows_records_around_it(conn):
    r = row(rows_for(conn), "7", "at 8 p.m. on Monday")
    assert r.status == "not_tied" and r.stated.weekday_ok is True
    assert r.nearby and r.nearby_total >= len(r.nearby)
    assert all(abs(c.delta_s or 0) <= 300 for c in r.nearby)
    day = row(rows_for(conn), "3", "March 10, 2026")
    assert day.status == "not_tied" and day.counts


def test_messages_on_the_stated_day_match_and_quoted_names_are_not_quotes(conn):
    rows = rows_for(conn)
    assert row(rows, "10", "March 19, 2026").status == "matches"
    r = row(rows, "15", "March 25, 2026")
    assert [lk.words for lk in r.links] == ["got the tickets"]  # "Alex" is a contact name


def test_rows_run_in_time_order(conn):
    keys = [r.start_utc for r in rows_for(conn) if r.start_utc is not None]
    assert keys == sorted(keys)


def test_the_check_only_reads(conn):
    before = conn.total_changes
    compute(conn, Settings())
    assert conn.total_changes == before


# ---------------------------------------------------------------- quiet stretches


def _whatsapp(gaps):
    return [g for g in gaps if g.series.scope == "app" and g.series.app == "WhatsApp"]


def test_both_phones_show_the_whatsapp_silence_around_paragraph_11(conn):
    data = CaseRecords(conn)
    gaps = find_gaps(data, read_document(conn), Settings())
    found = {}
    for g in _whatsapp(gaps):
        if g.start <= datetime(2026, 3, 20, 4, tzinfo=UTC) and g.end >= datetime(
            2026, 3, 24, 4, tzinfo=UTC
        ):
            found[g.series.source_id] = g
    assert set(found) == {"item1", "item2"}
    g = found["item1"]
    assert g.before.when().startswith("2026-03-19 22:48")
    assert g.expected >= 8 and g.elsewhere  # item2 holds other records then
    assert any(st.para_label == "11" for st in g.stated)


def test_a_longer_shortest_stretch_drops_it(conn):
    data = CaseRecords(conn)
    gaps = find_gaps(data, read_document(conn), Settings(gap_hours=120))
    assert not [g for g in _whatsapp(gaps) if g.start.date().isoformat() == "2026-03-20"]


def test_a_thread_stretch_its_app_already_has_is_listed_once(conn):
    data = CaseRecords(conn)
    gaps = find_gaps(data, read_document(conn), Settings())
    apps = [g for g in gaps if g.series.scope == "app"]
    for t in (g for g in gaps if g.series.scope == "thread"):
        assert not any(
            a.series.source_id == t.series.source_id
            and a.series.app == t.series.app
            and a.start <= t.start
            and t.end <= a.end
            for a in apps
        )


# ---------------------------------------------------------------- settings


def test_settings_save_logs_the_expert_and_refuse_bad_values(db, conn):
    case = cases.Case(db)
    assert tl_settings.from_case(case.settings) == Settings(5, 72)
    s = tl_settings.save(case, conn, EXPERT, "10", "48", clock=lambda: NOW)
    assert s == Settings(10, 48) and tl_settings.from_case(case.settings) == s
    actor, action, payload = conn.execute(
        "SELECT actor, action, payload_json FROM audit_log ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    assert (actor, action) == (EXPERT, "timeline.settings")
    assert json.loads(payload) == {"tolerance_min": [5, 10], "gap_hours": [72, 48]}
    n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    tl_settings.save(case, conn, EXPERT, "10", "48")  # unchanged: nothing logged
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == n
    for tol, gap in (("-1", "48"), ("10", "0"), ("ten", "48"), ("10", "99999")):
        with pytest.raises(ReviewError):
            tl_settings.save(case, conn, EXPERT, tol, gap)
    with pytest.raises(ReviewError):
        tl_settings.save(case, conn, "system", "10", "48")
    assert tl_settings.from_case({"timeline_tolerance_min": "x", "gap_min_hours": 0}) == (
        Settings()
    )


# ---------------------------------------------------------------- screen and report


def test_screen_pages_and_report(db):
    app = App(db, expert="Test Expert", port=8765)

    def get(path: str):  # noqa: ANN202
        r = app.handle(Request("GET", path, {}, dict(HOST)))
        assert r.status == 200
        check_report_text(r.text)  # cites paragraph 11's own words; the tool never says them
        return r.text

    page = get("/timeline")
    assert "Differs" in page and "Order differs" in page and "its done" in page
    assert "agrees with the clock the report printed" in page
    gaps = get("/gaps")
    assert 'No <span class="q">WhatsApp</span> messages on' in gaps
    assert "Not found does not mean" in gaps
    report = get("/report")
    assert "<h2>Timeline check</h2>" in report and "<h2>Quiet stretches</h2>" in report
    r = app.handle(
        Request(
            "POST",
            "/timeline/settings",
            {},
            dict(HOST),
            {"token": app.token, "tolerance_min": "300", "gap_hours": "72", "next": "/timeline"},
        )  # fmt: skip
    )
    assert r.status == 303 and r.header("Location") == "/timeline"
    assert "tolerance 300 min" in (app.flash or ("", True))[0]
    assert "Tolerance 300 min" in get("/report")
    refused = app.handle(
        Request(
            "POST",
            "/timeline/settings",
            {},
            dict(HOST),
            {"token": "wrong", "tolerance_min": "1", "gap_hours": "1"},
        )  # fmt: skip
    )
    assert refused.status == 403


def test_render_report_takes_default_settings(conn):
    html = render_report(conn)
    assert "Tolerance 5 min" in html
    check_report_text(html)


# ---------------------------------------------------------------- zones


def _tiny(tz: str | None, ts_utc: str, offset: int, raw: str, para: str) -> sqlite3.Connection:
    conn = connect(":memory:")
    apply_schema(conn)
    conn.executescript(
        f"""
        INSERT INTO sources VALUES ('s1', 'cellebrite_excel', 'full_extraction', 'logical',
          'p.xlsx', '{"0" * 64}', NULL, NULL, NULL, '2026-10-01T00:00:00Z');
        INSERT INTO sources VALUES ('g1', 'govdoc', 'unknown', 'not_applicable', 'a.pdf',
          '{"1" * 64}', NULL, NULL, NULL, '2026-10-01T00:00:00Z');
        INSERT INTO devices VALUES ('d1', 's1', 'Summary!1', 'Phone A', NULL, NULL,
          {"NULL" if tz is None else repr(tz)});
        INSERT INTO threads VALUES ('t1', 's1', 'Chats!1', 'd1', 'SMS', 'Pat');
        INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc,
          ts_offset_min, ts_raw, body)
          VALUES ('m1', 's1', 'Chats!2', 't1', 'outgoing', '{ts_utc}', {offset}, '{raw}',
          'bring the blue bag');
        INSERT INTO govdocs VALUES ('doc1', 'g1', 'Affidavit', 'affidavit');
        INSERT INTO govdoc_paragraphs VALUES ('p1', 'doc1', 1, 1, '1', 0, {len(para)},
          '{para}', 0);
        """
    )
    return conn


def test_an_unknown_phone_zone_is_never_guessed():
    conn = _tiny(None, "2026-03-05T02:31:00Z", 0, "3/5/2026 2:31:00 AM(UTC+0)",
                 'At 9:31 p.m. on March 4, 2026, he wrote "bring the blue bag".')  # fmt: skip
    (r,) = rows_for(conn)
    assert r.status == "not_tied"
    assert [c.status for c in r.links[0].shown] == ["no_zone"]


def test_a_zone_the_document_names_is_used_and_needs_no_phone_zone():
    conn = _tiny(None, "2026-03-05T02:31:00Z", 0, "3/5/2026 2:31:00 AM(UTC+0)",
                 'At 2:31 a.m. UTC on March 5, 2026, he wrote "bring the blue bag".')  # fmt: skip
    (r,) = rows_for(conn)
    assert r.status == "matches" and r.links[0].shown[0].status == "inside"


def test_the_phone_zone_follows_daylight_saving():
    para = 'At 9:31 p.m. on March 9, 2026, he wrote "bring the blue bag".'
    conn = _tiny("America/New_York", "2026-03-10T01:31:00Z", -240, "x", para)  # EDT
    assert rows_for(conn)[0].status == "matches"
    conn = _tiny("America/New_York", "2026-03-10T02:31:00Z", -240, "x", para)
    assert rows_for(conn)[0].status == "differs"


def test_quiet_stretches_need_records_on_both_sides():
    conn = _tiny("UTC", "2026-03-05T02:31:00Z", 0, "x", "No dates here.")
    assert find_gaps(CaseRecords(conn), [], Settings(gap_hours=1)) == []
