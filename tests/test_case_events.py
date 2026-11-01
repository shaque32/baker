"""Case events (schema 0.7.0, signed by Arsh 2026-11-01): the dated events the government
document defines, so a claim dated only by one ("two days before the SEARCH") can be tested.

In the case04 alias replay, 8 of the 11 remaining window or quote refusals were claims dated by
an event or by the sentence before. Only an expert enters an event, with the paragraph and the
words that define it, checked verbatim. The filler reads an allow list of whole-day ties to a
one-day event, in the phone's zone, and refuses everything else.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.audit import case_events
from core.audit._llm_json import prompt_body
from core.audit.assumption_filler import LocalAssumptionFiller, event_windows
from core.audit.assumptions import TemplateAssumptionBuilder
from core.audit.invariants import check_report_text
from core.contracts import Claim, ClaimStatus, ClaimType
from core.db import connect
from core.report.html import render_report
from core.review import actions, status
from core.review.actions import ReviewError
from eval import run_pipeline
from tests.fake_model import FakeModel
from ui.app import App, Request

EXPERT = "expert:Test Expert"
WHEN = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
DRAFT = prompt_body((ROOT / "docs/prompts/assumptions.md").read_text("utf-8"))
PETROV, REYES = "person:dev:item1:owner", "person:dev:item2:owner"
HOST = {"host": "127.0.0.1:8765"}
PARA = "para:events"
DEFINES = (
    'On Friday, March 20, 2026, officers searched the storage unit (the "RAID"). Between March '
    "19 and March 20, 2026, agents ran the OPERATION. On Saturday, March 7, 2026, police stopped "
    "the TRUCK. On Saturday, October 31, 2026, the PARTY was held. On Monday, March 2, 2026, "
    "Petrov arrived."
)
RAID = 'On Friday, March 20, 2026, officers searched the storage unit (the "RAID")'


def _clock() -> datetime:
    return WHEN


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("events") / "case01.db"
    conn = run_pipeline.build_case("case01", path)
    gd = conn.execute("SELECT id FROM govdocs LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
        " char_end, text) VALUES (?, ?, 9, 99, '99', 0, ?, ?)",
        (PARA, gd, len(DEFINES), DEFINES),
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def conn(built, tmp_path) -> sqlite3.Connection:
    copy = tmp_path / "case.db"
    shutil.copy(built, copy)
    c = connect(copy)
    yield c
    c.close()


@pytest.fixture
def events(conn) -> sqlite3.Connection:
    actions.add_event(conn, "RAID", "2026-03-20", "2026-03-20", PARA, RAID, EXPERT, _clock)
    actions.add_event(
        conn,
        "OPERATION",
        "2026-03-19",
        "2026-03-20",
        PARA,
        "Between March 19 and March 20, 2026, agents ran the OPERATION",
        EXPERT,
        _clock,
    )
    for name, day, words in [
        ("TRUCK", "2026-03-07", "On Saturday, March 7, 2026, police stopped the TRUCK"),
        ("PARTY", "2026-10-31", "On Saturday, October 31, 2026, the PARTY was held"),
    ]:
        actions.add_event(conn, name, day, day, PARA, words, EXPERT, _clock)
    return conn


def _log(conn: sqlite3.Connection, action: str) -> list[dict]:
    return [
        json.loads(p)
        for (p,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq", (action,)
        )
    ]


# ---------------------------------------------------------------- entering them


def test_an_expert_enters_an_event_with_its_defining_words_and_it_is_logged(conn):
    # A definition a PDF wrapped over two lines is still the paragraph's words.
    wrapped = RAID.replace("officers searched", "officers\nsearched")
    name = actions.add_event(conn, " RAID ", "2026-03-20", "2026-03-20", PARA, wrapped, EXPERT)
    assert name == "RAID"
    (ev,) = case_events.stored(conn)
    assert (ev.first_day.isoformat(), ev.one_day, ev.defined_as) == ("2026-03-20", True, RAID)
    assert ev.created_by == EXPERT and ev.paragraph_id == PARA
    (logged,) = _log(conn, case_events.ADD_ACTION)
    assert logged == {
        "name": "RAID",
        "first_day": "2026-03-20",
        "last_day": "2026-03-20",
        "paragraph_id": PARA,
        "defined_as": RAID,
    }
    actions.remove_event(conn, "raid", EXPERT)
    assert case_events.stored(conn) == []
    assert _log(conn, case_events.REMOVE_ACTION)[0]["defined_as"] == RAID


@pytest.mark.parametrize(
    "name, first, last, words, why",
    [
        # words the paragraph does not hold: every event traces to the document
        ("RAID", "2026-03-20", "2026-03-20", RAID.replace("officers", "agents"), "not in that"),
        # a typo in the day the defining words state plainly
        ("RAID", "2026-03-21", "2026-03-21", RAID, "state 2026-03-20"),
        ("RAID", "2026-03-20", "2026-03-19", RAID, "before the first"),
        ("RAID", "March 20", "March 20", RAID, "YYYY-MM-DD"),
        ("--", "2026-03-20", "2026-03-20", RAID, "no letter or digit"),
    ],
)
def test_an_event_the_document_does_not_back_is_refused(conn, name, first, last, words, why):
    with pytest.raises(ReviewError, match=why):
        actions.add_event(conn, name, first, last, PARA, words, EXPERT)
    assert case_events.stored(conn) == []


def test_the_words_may_define_the_place_the_event_is_named_by(conn):
    # `the storage unit (the "RAID")` defines a place; the claims say "the RAID search".
    actions.add_event(conn, "RAID search", "2026-03-20", "2026-03-20", PARA, RAID, EXPERT)
    assert [e.name for e in case_events.readable(conn)] == ["RAID search"]


def test_a_name_another_person_or_event_is_matched_by_is_refused(conn):
    with pytest.raises(ReviewError, match="Daniel Petrov"):  # Daniel Petrov's surname
        actions.add_event(
            conn,
            "Petrov",
            "2026-03-02",
            "2026-03-02",
            PARA,
            "On Monday, March 2, 2026, Petrov arrived",
            EXPERT,
        )
    actions.set_aliases(conn, PETROV, ["RAID"], EXPERT)
    with pytest.raises(ReviewError, match="would also match the person"):
        actions.add_event(conn, "RAID", "2026-03-20", "2026-03-20", PARA, RAID, EXPERT)
    actions.set_aliases(conn, PETROV, [], EXPERT)
    actions.add_event(conn, "RAID", "2026-03-20", "2026-03-20", PARA, RAID, EXPERT)
    with pytest.raises(ReviewError, match="would also match the event RAID"):
        actions.add_event(conn, "raid", "2026-03-20", "2026-03-20", PARA, RAID, EXPERT)


def test_non_ascii_names_are_compared_by_code_not_by_the_column(conn):
    # SQLite's NOCASE folds ASCII only: code folds "ÉCLAIR" and "éclair", and "Groß" and "GROSS",
    # as one name, so the database and the filler never disagree about it (Grok on #190).
    gd = conn.execute("SELECT govdoc_id FROM govdoc_paragraphs WHERE id = ?", (PARA,)).fetchone()
    words = "On March 2, 2026, the ÉCLAIR met the Groß crew"
    conn.execute(
        "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
        " char_end, text) VALUES ('para:fr', ?, 9, 100, '100', 0, ?, ?)",
        (gd[0], len(words), words),
    )
    actions.add_event(conn, "ÉCLAIR", "2026-03-02", "2026-03-02", "para:fr", words, EXPERT)
    with pytest.raises(ReviewError, match="would also match the event ÉCLAIR"):
        actions.add_event(conn, "éclair", "2026-03-02", "2026-03-02", "para:fr", words, EXPERT)
    actions.add_person(conn, "Anna GROSS", EXPERT)
    with pytest.raises(ReviewError, match="Anna GROSS"):
        actions.add_event(conn, "Groß", "2026-03-02", "2026-03-02", "para:fr", words, EXPERT)


def test_an_event_that_later_clashes_with_a_person_dates_nothing(events):
    assert {e.name for e in case_events.readable(events)} >= {"RAID"}
    actions.add_person(events, "Rita RAID", EXPERT)  # the surname rule now reaches "RAID"
    assert "RAID" not in {e.name for e in case_events.readable(events)}


# ---------------------------------------------------------------- what the filler reads


def _no_contact(conn, text: str, window: dict | None = None):
    prop = {
        "template_id": "no_contact",
        "people": ["PETROV", "REYES"],
        "accounts": [],
        "handles": [],
        "phones": [],
        "channels": [],
        "quoted_text": "",
        "count": None,
        "duration": None,
        "window": window,
    }
    filler = LocalAssumptionFiller(
        FakeModel(json.dumps({"assumptions": [prop]})), conn, template=DRAFT
    )
    c = Claim(
        id="X1",
        paragraph_id=PARA,
        text=text,
        claim_type=ClaimType.ABSENCE,
        status=ClaimStatus.ACCEPTED,
    )
    made = [a for a in TemplateAssumptionBuilder(filler).build(c) if a.template_id == "no_contact"]
    return made, filler


def _day(conn, date_words: str):
    (a,), filler = _no_contact(
        conn, f"On {date_words}, PETROV and REYES had no contact of any kind."
    )
    return a.params.window


@pytest.mark.parametrize(
    "tie, day",
    [
        ("On the day of the RAID", "March 20, 2026"),
        ("On the same day as the RAID", "March 20, 2026"),
        ("The day after the RAID", "March 21, 2026"),
        ("On the day before the RAID", "March 19, 2026"),
        ("Two days before the RAID", "March 18, 2026"),
        ("3 days after the RAID", "March 23, 2026"),
    ],
)
def test_a_whole_day_tied_to_a_one_day_event_is_read(events, tie, day):
    text = f"{tie}, PETROV and REYES had no contact of any kind."
    # the model's own guess at the edges is refused and the event's day replaces it
    guess = {
        "as_written": tie,
        "start": "2026-03-01T00:00",
        "end": "2026-03-02T00:00",
        "zone": "phone",
    }
    for window in (None, guess):
        made, filler = _no_contact(events, text, window)
        assert len(made) == 1, filler.drops
        (a,) = made
        assert a.params.window == _day(events, day).model_copy(update={"raw": tie})


@pytest.mark.parametrize(
    "text",
    [
        "In the days before the RAID, PETROV and REYES had no contact of any kind.",
        "Shortly before the RAID, PETROV and REYES had no contact of any kind.",
        "On the night of the RAID, PETROV and REYES had no contact of any kind.",
        "After the RAID, PETROV and REYES had no contact of any kind.",
        "About two days after the RAID, PETROV and REYES had no contact of any kind.",
        "Within two days after the RAID, PETROV and REYES had no contact of any kind.",
        "At least a day before the RAID, PETROV and REYES had no contact of any kind.",
        "The morning after the RAID, PETROV and REYES had no contact of any kind.",
        "The day after the RAID and later, PETROV and REYES had no contact of any kind.",
        "The day after the RAID at 9 p.m., PETROV and REYES had no contact of any kind.",
        "The day after the RAID, a Saturday, PETROV and REYES had no contact of any kind.",
        "The next day after the RAID, PETROV and REYES had no contact of any kind.",
        # a relation to an event of more than one day
        "The day after the OPERATION, PETROV and REYES had no contact of any kind.",
        # two ties: never picked
        "The day before the RAID and the day after the TRUCK, PETROV and REYES had no contact.",
        # an event's name inside quotation marks is a message's words, not the claim's
        'The day after the "RAID", PETROV and REYES had no contact of any kind.',
        # the event's name written as part of a longer word or a possessive
        "The day after the RAID's end, PETROV and REYES had no contact of any kind.",
        "The day after the RAID warrant, PETROV and REYES had no contact of any kind.",
        "PETROV and REYES had no contact the day after the RAID-related arrests.",
        # the claim's own date is not the event's day it names
        "On March 22, 2026, the day after the RAID, PETROV and REYES had no contact of any kind.",
    ],
)
def test_any_other_tie_is_refused(events, text):
    made, filler = _no_contact(events, text)
    assert made == [], [a.params.window for a in made]


def test_the_claims_own_date_agreeing_with_the_tie_is_read(events):
    text = "On March 21, 2026, the day after the RAID, PETROV and REYES had no contact of any kind."
    (a,), _ = _no_contact(events, text)
    assert a.params.window == _day(events, "March 21, 2026").model_copy(
        update={"raw": a.params.window.raw}
    )


def test_a_tied_day_with_a_clock_change_is_its_wall_clock_day(events):
    # New York: March 8, 2026 is 23 hours long and November 1, 2026 is 25.
    (a,), _ = _no_contact(events, "The day after the TRUCK, PETROV and REYES had no contact.")
    w = a.params.window
    assert w.tz == "America/New_York"
    assert w.start_utc == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    assert w.end_utc - w.start_utc == timedelta(hours=23) - timedelta(microseconds=1)
    (b,), _ = _no_contact(events, "The day after the PARTY, PETROV and REYES had no contact.")
    assert b.params.window.end_utc - b.params.window.start_utc == timedelta(hours=25) - timedelta(
        microseconds=1
    )


def test_no_event_means_no_change(conn):
    assert event_windows("The day after the RAID, they met.", []) == []
    made, _ = _no_contact(conn, "The day after the RAID, PETROV and REYES had no contact.")
    assert made == []  # no event entered: refused as before


# ---------------------------------------------------------------- after a run, reports, bundles


def test_an_event_entered_after_a_run_makes_its_verdicts_not_current(conn):
    run = {"started_at_utc": "2026-11-01T18:00:00Z", "run_id": "r1"}
    assert not status.case_changed_after(conn, run)
    actions.add_event(conn, "RAID", "2026-03-20", "2026-03-20", PARA, RAID, EXPERT, _clock)
    assert status.case_changed_after(conn, run)


def test_the_report_lists_each_event_as_an_expert_statement(events):
    html = render_report(events)
    assert "When a defined event happened is an expert statement, not a finding." in html
    assert (
        'that the document\'s <span class="q">OPERATION</span> is 2026-03-19 to 2026-03-20' in html
    )
    assert "paragraph 99, page 9" in html
    check_report_text(html)


def test_verify_bundle_holds_each_event_to_the_experts_logged_action(events):
    from core.bundle import verify as V

    def check() -> list[tuple[str, str]]:
        out = V._Out()
        V._events(events, out)
        return [(f.level, f.detail) for f in out.items]

    assert check() == [(V.PASS, "4 defined events match the expert's logged actions")]
    events.execute("UPDATE case_events SET first_day = '2026-03-18' WHERE name = 'OPERATION'")
    assert [level for level, _ in check()] == [V.FAIL]
    events.execute("UPDATE case_events SET first_day = '2026-03-19' WHERE name = 'OPERATION'")
    events.execute("DELETE FROM case_events WHERE name = 'TRUCK'")
    assert check() == [(V.FAIL, "the log records the event 'TRUCK', but it is missing")]


def _get(app: App, path: str):  # noqa: ANN202
    return app.handle(Request("GET", path, {}, dict(HOST)))


def _post(app: App, path: str, **form: str):  # noqa: ANN202
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def test_the_setup_page_adds_and_removes_events(conn):
    conn.commit()
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    app = App(db_path, expert="Test Expert", port=8765)
    page = _get(app, "/setup").text
    assert "Events the document defines" in page and "Add event" in page
    form = dict(name="RAID", first_day="2026-03-20", paragraph=PARA, defined_as=RAID)
    assert _post(app, "/event/add", **form, next="/setup").status == 303
    assert app.flash and not app.flash[1] and "RAID" in app.flash[0]
    _post(app, "/event/add", **{**form, "first_day": "2026-03-21"})
    assert app.flash and app.flash[1]  # the words state March 20
    page = _get(app, "/setup").text
    assert "2026-03-20" in page and "officers searched the storage unit" in page
    _post(app, "/event/remove", name="RAID")
    assert app.flash and not app.flash[1]
    assert case_events.stored(connect(db_path)) == []
