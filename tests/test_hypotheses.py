"""Other explanations (core/hypotheses/) on synthetic case01, the claim page and the report.

case01 plants the situations these leads exist for: Ilya Morozov writing from Petrov's shared
Instagram login (C16), a time read off a report that prints UTC for a phone set to New York
(C10), a WhatsApp silence that covers the whole app on both phones (C15) and a Telegram user who
names himself Sasha (C18). Code finds the records; nothing here may touch a verdict. All data is
synthetic.
"""

from __future__ import annotations

import ast
import re
import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import pipeline
from core.audit.invariants import FORBIDDEN_WORDS, check_report_text
from core.contracts import GoldClaim
from core.db import connect
from core.hypotheses import explain
from core.hypotheses.explain import Alternative
from core.identity.links import CITE_CLOSE, CITE_OPEN, Person
from core.report.html import render_report
from core.report.hypotheses import alternatives_html
from core.review.status import claim_state, claim_states
from eval import run_pipeline
from eval.run_eval import load_jsonl
from eval.simulated_expert import GoldKey
from ui.app import App, Request

ROOT = Path(__file__).resolve().parents[1]
RUN_TIME = datetime(2026, 10, 7, tzinfo=UTC)
HOST = {"host": "127.0.0.1:8765"}


def _spec() -> Path:
    signed = ROOT / "eval/gold/case01/assumptions.jsonl"
    return signed if signed.exists() else ROOT / "eval/probe_draft/case01_assumptions.jsonl"


@pytest.fixture(scope="module")
def audited(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("alts") / "case01.db"
    conn = run_pipeline.build_case("case01", path)
    gold = GoldKey(load_jsonl(ROOT / "eval/gold/case01/gold.jsonl", GoldClaim))
    comps = run_pipeline.model_free_components(conn, _spec(), gold)
    pipeline.run_audit(conn, comps, clock=lambda: RUN_TIME)
    conn.close()
    return path


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


def alts_for(conn: sqlite3.Connection, claim_id: str) -> dict[str, Alternative]:
    st = claim_state(conn, claim_id)
    assert st is not None and st.assumptions
    return {a.kind: a for a in explain.alternatives(explain.load(conn), st.assumptions)}


def every_alt(conn: sqlite3.Connection) -> list[tuple[str, Alternative]]:
    case = explain.load(conn)
    return [
        (st.claim.id, a)
        for st in claim_states(conn)
        for a in explain.alternatives(case, st.assumptions)
    ]


def own_words(text: str) -> str:
    """Baker's words only: text cited from the case removed."""
    return re.sub(f"{CITE_OPEN}[^{CITE_CLOSE}]*{CITE_CLOSE}", "", text)


# ---------------------------------------------------------------- what code finds


def test_a_shared_login_points_to_someone_else_writing(conn):
    other = alts_for(conn, "C16")["other_user"]
    ids = [f.record_id for f in other.fits]
    assert ids == ["msg:item1:Chats!1026", "msg:item1:Chats!857"]
    first, second = other.fits
    assert first.quote == "its ilya btw, dan's at work. he left his login on my ipad"
    assert "ilya" in first.note and "Daniel Petrov" in first.note  # names itself, not Petrov
    assert "left his login" in first.note  # and speaks of a login, in one line
    assert "using ur insta" in second.note
    assert other.title == "Someone else may have written it"
    assert "Searched" in other.searched


def test_a_hand_off_about_another_app_is_not_pinned_on_an_sms(conn):
    # C12 is an SMS the day after Ilya wrote about using Petrov's Instagram: not a lead for it.
    assert "other_user" not in alts_for(conn, "C12")


def test_a_time_read_off_the_printed_utc_clock(conn):
    clock = alts_for(conn, "C10")["clock"]
    (fit,) = clock.fits  # item2 prints the phone's own time, so its copy reads correctly
    assert fit.record_id == "msg:item1:Chats!1011"
    assert "UTC+00:00" in fit.note and "2026-03-05 02:31" in fit.note
    assert fit.when.startswith("2026-03-04 21:31:00 EDT") or fit.when.startswith(
        "2026-03-04 21:31:00 EST"
    )


def test_a_whole_app_quiet_on_both_phones(conn):
    alts = alts_for(conn, "C15")
    quiet = alts["app_quiet"]
    # Both phones are quiet; their edge records are copies of one exchange, so each shows once
    # with both phones' notes.
    assert "item1" in quiet.summary and "item2" in quiet.summary
    assert quiet.total == 2
    assert all("WhatsApp" in f.note and "item2" in f.note for f in quiet.fits)
    assert "curated" in alts
    for a in alts.values():  # the claim says "deleted"; Baker's own words never do
        for text in (a.title, a.summary, a.searched, *(f.note for f in a.fits)):
            assert not FORBIDDEN_WORDS.search(own_words(text)), text


def test_dates_read_in_utc_move_a_record_into_the_window(conn):
    day = alts_for(conn, "C14")["day_boundary"]
    (fit,) = day.fits
    assert fit.record_id == "msg:item1:Chats!965"
    assert "inside them in UTC" in fit.note


def test_an_account_that_names_itself(conn):
    other = alts_for(conn, "C18")["other_user"]
    assert other.title == "Someone else may be behind the account"
    assert [f.quote for f in other.fits] == ["hey its sasha. marc gave me ur name"]


def test_claims_with_nothing_in_the_records_get_no_alternative(conn):
    for cid in ("C01", "C05", "C09", "C17"):
        assert alts_for(conn, cid) == {}, cid


def test_every_fit_is_the_case_text_verbatim_with_its_source(conn):
    for cid, a in every_alt(conn):
        assert a.fits and a.total >= len(a.fits) and len(a.fits) <= explain.MAX_FITS
        for f in a.fits:
            assert f.source_id, (cid, f)
            if f.record_id.startswith("msg:"):
                body, sid, loc = conn.execute(
                    "SELECT body, source_id, locator FROM messages WHERE id = ?", (f.record_id,)
                ).fetchone()
                assert (f.quote, f.source_id, f.locator) == (body, sid, loc)
            elif f.record_id.startswith("contact:"):
                name = conn.execute(
                    "SELECT name FROM contacts WHERE id = ?", (f.record_id,)
                ).fetchone()[0]
                assert f.quote == name
            elif a.kind == "curated":
                name = conn.execute(
                    "SELECT file_name FROM sources WHERE id = ?", (f.record_id,)
                ).fetchone()[0]
                assert f.quote == name


def test_own_words_never_use_the_forbidden_words(conn):
    for _, a in every_alt(conn):
        for text in (a.title, a.summary, a.searched, *(f.note for f in a.fits)):
            assert not FORBIDDEN_WORDS.search(own_words(text)), text


# ---------------------------------------------------------------- never a verdict


def _snapshot(conn: sqlite3.Connection) -> dict[str, list]:
    tables = (
        "verdicts", "evidence_items", "evidence_reviews", "identity_links", "stipulations",
        "check_results", "audit_log", "model_calls", "model_runs", "pipeline_runs",
    )  # fmt: skip
    return {t: list(conn.execute(f"SELECT * FROM {t} ORDER BY 1")) for t in tables}  # noqa: S608


def test_alternatives_write_nothing_and_change_no_verdict(db):
    c = connect(db)
    before = _snapshot(c)
    labels = {st.claim.id: st.label for st in claim_states(c)}
    c.execute("PRAGMA query_only = ON")  # any write now fails
    every_alt(c)
    render_report(c)
    assert {st.claim.id: st.label for st in claim_states(c)} == labels
    c.execute("PRAGMA query_only = OFF")
    assert _snapshot(c) == before
    c.close()


def test_the_module_calls_no_model_and_no_network():
    banned = ("core.llm", "core.audit.stance", "core.audit.review", "core.audit._local_model",
              "socket", "urllib", "http", "requests")  # fmt: skip
    for path in (ROOT / "core/hypotheses").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert not n.startswith(banned), (path.name, n)


# ---------------------------------------------------------------- screen and report


def _app(db: Path) -> App:
    return App(db, expert="Test Expert", port=8765)


def test_claim_page_shows_alternatives_with_a_link_to_the_conversation(db):
    app = _app(db)
    r = app.handle(Request("GET", "/claim", {"id": "C16"}, dict(HOST)))
    assert r.status == 200
    page = r.body.decode()
    assert "Other explanations to check (1)" in page
    assert "Someone else may have written it" in page
    assert "/selection/context?id=msg%3Aitem1%3AChats%211026" in page
    assert "never change a verdict" in page
    check_report_text(page)
    r = app.handle(Request("GET", "/claim", {"id": "C01"}, dict(HOST)))
    assert "Other explanations" not in r.body.decode()


def test_report_lists_alternatives_under_their_claims(conn):
    report = render_report(conn)
    check_report_text(report)
    c15 = report[report.index('id="C15"') : report.index('id="C16"')]
    assert "The whole app is quiet, not one conversation" in c15
    assert "Other explanations (code)" in report  # the versions table names the code version


# ---------------------------------------------------------------- the word rules


@pytest.mark.parametrize(
    ("body", "app", "claimed_app", "found"),
    [
        ("using ur insta on my ipad", "SMS", "Instagram", "using ur insta"),
        ("using ur insta on my ipad", "SMS", "SMS", None),  # about another app
        ("i borrowed his phone last night", "SMS", "WhatsApp", "borrowed his phone"),  # a device
        ("he left his login on my ipad", "Instagram", "Instagram", "left his login"),
        ("he left his login on my ipad", "Instagram", "SMS", None),  # a login on another app
        ("call me on my phone", "SMS", "SMS", None),  # the owner's own phone, no hand-off
        ("logged in on his ipad", "SMS", "WhatsApp", "logged in on his ipad"),
        ("logged into ur insta again", "Instagram", "Instagram", "logged into ur insta"),
        ("logged in from home", "Instagram", "Instagram", None),  # no one else's
        ("signed in as Daniel", "Instagram", "Instagram", None),  # no one else's thing
        ("logged in on my phone", "SMS", "SMS", None),  # one's own phone
        ("im using my phone rn", "SMS", "SMS", None),  # one's own phone, either phrasing
        ("i never used his account", "Instagram", "Instagram", None),  # a denial
        ("I didn't use her phone", "SMS", "SMS", None),
        ("I did not borrow his phone", "SMS", "SMS", None),
        ("I couldn't use his phone", "SMS", "SMS", None),
        ("I wouldn’t use her account", "Instagram", "Instagram", None),
        ("you shouldnt borrow his phone", "SMS", "SMS", None),
        ("I cannot use his phone", "SMS", "SMS", None),
        ("I used his phone number", "SMS", "SMS", None),  # a contact detail, not a device
        ("took her phone # earlier", "SMS", "SMS", None),
        ("he left his phone at home", "SMS", "SMS", None),  # left somewhere, not handed over
        ("she left me her password", "SMS", "SMS", "left me her password"),
        ("not sure but im using his phone", "SMS", "SMS", "using his phone"),  # not a denial
        ("I did not have a chance to use his phone", "SMS", "SMS", None),  # a longer denial
        ("never got around to using her account", "Instagram", "Instagram", None),
        ("no idea why but i used his phone", "SMS", "SMS", "used his phone"),  # a new clause
        ("I took his phone call", "SMS", "SMS", None),  # a call, not the device
        ("give her phone a call later", "SMS", "SMS", None),
        ("I used his phone's number", "SMS", "SMS", None),  # possessive, still a number
        ("i borrowed his phone’s charger", "SMS", "SMS", "borrowed his phone"),
        ("I did not, in fact, use his phone", "SMS", "SMS", None),  # an aside in a denial
        ("no, i used his phone", "SMS", "SMS", "used his phone"),  # an answer, then a clause
        ("not now, im using his phone", "SMS", "SMS", "using his phone"),
        ("I haven’t used his phone", "SMS", "SMS", None),  # curly apostrophes
        ("I wasn’t using his phone", "SMS", "SMS", None),
        ("she isn't using her phone", "SMS", "SMS", None),
    ],
)
def test_hand_off_words(body, app, claimed_app, found):
    m = explain._handoff(body, app, claimed_app)
    assert (m.group(0) if m else None) == found


@pytest.mark.parametrize(
    ("body", "name"),
    [
        ("hey its alex turner, new number", "alex"),
        ("its ilya btw", "ilya"),
        ("its done", "done"),  # read here; dropped later as no name in the case
        ("i think its sasha who called", None),  # a name mid-sentence is not an introduction
    ],
)
def test_self_introductions(body, name):
    m = explain._INTRO.search(body)
    assert (m.group(1) if m else None) == name


def _person(name: str):  # noqa: ANN202
    from core.identity.links import Person, tokens

    return Person("person:x", name, "expert:t", tuple(tokens(name)), ())


@pytest.mark.parametrize(
    ("person", "words", "conflicts"),
    [
        ("Daniel Petrov", ["ilya"], True),
        ("Daniel Petrov", ["daniel", "jones"], True),  # same first name, another surname
        ("Daniel Petrov", ["dan"], False),  # a short form of his first name
        ("Daniel Petrov", ["daniel", "petrov"], False),
        ("John Michael Smith", ["michael"], False),  # a middle name is part of the name
        ("John Michael Smith", ["john", "michael"], False),  # the full name, cut at two words
        ("John Michael Smith", ["john", "jones"], True),
    ],
)
def test_who_an_introduction_names(person, words, conflicts):
    assert explain._intro_conflicts(_person(person), words) is conflicts


def test_a_middle_name_is_a_shared_part():
    assert explain._shares_word(_person("John Michael Smith"), ["michael"])
    assert explain._shares_word(_person("Daniel Petrov"), ["dan", "p"])
    assert not explain._shares_word(_person("Daniel Petrov"), ["sasha", "n"])


def _row(rid: str, source: str, text: str, ts: datetime | None):  # noqa: ANN202
    from core.audit.checks._common import Row

    return Row(rid, "message", source, "SMS", None, (), ts, None, text)


_NO_ACCOUNTS = SimpleNamespace(accounts={})


def test_copies_collapse_only_across_phones():
    t = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    rows = [
        _row("a1", "item1", "ok", t),
        _row("a2", "item1", "ok", t),
        _row("b1", "item2", "ok", t),
    ]
    assert [r.id for r in explain._dedupe(_NO_ACCOUNTS, rows)] == [
        "a1",
        "a2",
    ]  # two replies on one phone


def test_a_record_with_no_time_gets_no_derived_time(conn):
    fit = explain._fit(explain.load(conn), _row("msg:none", "item1", "x", None), "note")
    assert fit.when == ""


# ---------------------------------------------------------------- scope (second Codex review)


def _asm(conn: sqlite3.Connection, claim_id: str, template_id: str, **params):  # noqa: ANN202
    """The claim's first assumption of this template, with some parameters replaced."""
    st = claim_state(conn, claim_id)
    assert st is not None
    a = next(x for x in st.assumptions if x.template_id == template_id)
    return a.model_copy(update={"params": a.params.model_copy(update=params)})


def test_a_weekday_reference_gets_no_clock_lead(conn):
    # A weekday's target day is counted from the send date, so another clock moves it too.
    a = _asm(conn, "C10", "record_time")
    assert explain._clock(explain.load(conn), [a]) is not None
    weekday = a.model_copy(update={"template_id": "weekday_date"})
    assert explain._clock(explain.load(conn), [weekday]) is None


def test_day_boundary_notes_name_the_stated_zone(conn):
    (fit,) = alts_for(conn, "C14")["day_boundary"].fits
    assert "stated zone" in fit.note and "America/New_York" in fit.note
    assert "phone's zone" not in fit.note


@pytest.mark.parametrize("device", ["dev:item1", "dev:item2"])
def test_other_app_records_stay_on_the_named_phone(conn, device):
    a = _asm(conn, "C14", "no_contact", channels=("WhatsApp",), device_ids=(device,))
    alt = explain._other_app(explain.load(conn), [a])
    assert alt is not None
    assert {f.source_id for f in alt.fits} == {device.removeprefix("dev:")}


def test_clock_calls_stay_on_the_named_phone_and_parties(conn):
    case = explain.load(conn)
    a = _asm(conn, "C09", "record_time")
    accounts = set(a.params.account_ids)
    rows = explain._clock_rows(case, a, {})
    assert rows and all(r.source_id == "item1" and r.accounts & accounts for r in rows)
    other = a.model_copy(update={"params": a.params.model_copy(update={"device_ids": ("dev:x",)})})
    assert explain._clock_rows(case, other, {}) == []


def test_a_quiet_app_edge_can_be_a_call(conn):
    conn.execute(
        "INSERT INTO calls (id, source_id, locator, device_id, app, from_account_id,"
        " to_account_id, direction, ts_utc, ts_offset_min, ts_raw, duration_s)"
        " VALUES ('call:item1:test', 'item1', 'Test!1', 'dev:item1', 'WhatsApp', NULL, NULL,"
        " 'incoming', '2026-03-20T03:00:00Z', 0, '3/20/2026 3:00:00 AM(UTC+0)', 30)"
    )
    quiet = alts_for(conn, "C15")["app_quiet"]
    before = next(f for f in quiet.fits if f.source_id == "item1" and "last before" in f.note)
    assert before.record_id == "call:item1:test"
    assert before.quote == ""  # a call has no words to quote
    assert before.label == "A call on WhatsApp, 30 s"


# ---------------------------------------------------------------- scope (third Codex review)


def test_copies_need_the_same_people():
    from core.audit.checks._common import Row

    t = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    rows = [
        Row("a", "message", "item1", "SMS", "acct:a", ("acct:b",), t, None, "ok"),
        Row("b", "message", "item2", "SMS", "acct:c", ("acct:d",), t, None, "ok"),
    ]
    assert [r.id for r in explain._dedupe(_NO_ACCOUNTS, rows)] == ["a", "b"]


def test_a_quoted_time_needs_every_named_party(conn):
    case = explain.load(conn)
    # Petrov and a stranger's number: the quoted message is between Petrov and someone else.
    timed = _asm(
        conn,
        "C10",
        "record_time",
        person_ids=("person:dev:item1:owner",),
        account_ids=("acct:item1:SMS:+12125550133",),
    )
    assert explain._quoted_rows(case, timed) == []
    # A sender statement keeps every copy: the claim may name the wrong sender.
    sender = timed.model_copy(update={"template_id": "sender"})
    assert explain._quoted_rows(case, sender)


def test_each_other_app_sentence_names_its_own_app(conn):
    whatsapp = _asm(conn, "C14", "no_contact", channels=("WhatsApp",))
    telegram = _asm(conn, "C14", "no_contact", channels=("Telegram",))
    alt = explain._other_app(explain.load(conn), [whatsapp, telegram])
    assert alt is not None
    sentences = alt.summary.split(". ")
    assert len(sentences) == 2
    assert "WhatsApp" in sentences[0] and "Telegram" not in sentences[0]
    assert "Telegram" in sentences[1] and "WhatsApp" not in sentences[1]


def test_a_call_never_moves_a_message_count(conn):
    frm, to = conn.execute(
        "SELECT from_account_id, to_account_id FROM calls WHERE id = 'call:item1:Call Log!16'"
    ).fetchone()
    conn.execute(
        "INSERT INTO calls (id, source_id, locator, device_id, app, from_account_id,"
        " to_account_id, direction, ts_utc, ts_offset_min, ts_raw, duration_s)"
        " VALUES ('call:item1:edge', 'item1', 'Test!2', 'dev:item1', 'Phone', ?, ?,"
        " 'outgoing', '2026-03-20T02:00:00Z', 0, '3/20/2026 2:00:00 AM(UTC+0)', 60)",
        (frm, to),
    )
    case = explain.load(conn)
    silence = _asm(conn, "C14", "no_contact")
    ids = [f.record_id for f in explain._day_boundary(case, [silence]).fits]
    assert "call:item1:edge" in ids
    count = silence.model_copy(update={"template_id": "message_count"})
    ids = [f.record_id for f in explain._day_boundary(case, [count]).fits]
    assert "call:item1:edge" not in ids and ids


def test_each_quiet_app_sentence_keeps_its_own_app_and_window(conn):
    whatsapp = _asm(conn, "C15", "event")
    # The same WhatsApp silence again, under another window label: two sentences, never merged.
    other = whatsapp.model_copy(
        update={
            "id": "asm:test",
            "params": whatsapp.params.model_copy(
                update={
                    "window": whatsapp.params.window.model_copy(update={"raw": "second window"})
                }
            ),
        }
    )
    alt = explain._app_quiet(explain.load(conn), [whatsapp, other])
    assert alt is not None
    sentences = [x for x in alt.summary.split(". ") if "has no record" in x]
    assert len(sentences) == 2
    assert "second window" in sentences[1] and "second window" not in sentences[0]
    assert all("second window" in f.note or "March" in f.note for f in alt.fits)


# ---------------------------------------------------------------- copies and clocks (fourth review)


def test_each_statement_is_checked_against_its_own_people(conn, monkeypatch):
    # C18: the Telegram account's user names himself Sasha, not Sokolov. Another statement
    # naming a Sasha for a different account must not hide that.
    sasha = Person("person:sasha", "Sasha Ivanov", "expert:t", ("sasha", "ivanov"), ())
    real = explain.Case.person
    monkeypatch.setattr(
        explain.Case, "person", lambda self, pid: sasha if pid == sasha.id else real(self, pid)
    )
    claim = _asm(conn, "C18", "person_identity")
    other = claim.model_copy(
        update={
            "id": "asm:other",
            "template_id": "sender",
            "params": claim.params.model_copy(
                update={
                    "person_ids": (sasha.id,),
                    "account_ids": ("acct:item1:SMS:+12125550133",),
                    "handles": (),
                }
            ),
        }
    )
    case = explain.load(conn)
    alone = explain._other_user(case, [claim])
    both = explain._other_user(case, [claim, other])
    assert alone is not None and both is not None
    assert "msg:item1:Chats!938" in {f.record_id for f in both.fits}
    # Each statement gets its own sentence: Sasha is never pooled with another statement's person.
    sasha_cited = f"{CITE_OPEN}Sasha Ivanov{CITE_CLOSE}"
    assert f"{sasha_cited} or " not in both.summary
    assert f" or {sasha_cited}" not in both.summary


@pytest.mark.parametrize("device", ["dev:item1", "dev:item2"])
def test_day_boundary_keeps_the_named_phones_copy(conn, device):
    a = _asm(conn, "C14", "no_contact", device_ids=(device,))
    alt = explain._day_boundary(explain.load(conn), [a])
    assert alt is not None
    assert {f.source_id for f in alt.fits} == {device.removeprefix("dev:")}


def test_rows_carry_their_recipients(conn):
    case = explain.load(conn)
    assert explain._recipients(case, "msg:item1:Chats!1011") == ("acct:item1:SMS:+12125550122",)


def test_copies_keep_the_most_rows_any_phone_holds():
    t = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    rows = [
        _row("b1", "item2", "ok", t),
        _row("a1", "item1", "ok", t),
        _row("a2", "item1", "ok", t),
    ]
    assert [r.id for r in explain._dedupe(_NO_ACCOUNTS, rows)] == ["a1", "a2"]


def test_every_copy_is_read_on_its_own_clock(conn, monkeypatch):
    # Each copy is read on its own phone's clocks, whichever comes first, and the record shows
    # once: item1's copy fits on its printed UTC clock, item2's when read in UTC.
    real = explain._clock_rows
    monkeypatch.setattr(explain, "_clock_rows", lambda *a: list(reversed(real(*a))))
    clock = explain._clock(explain.load(conn), [_asm(conn, "C10", "record_time")])
    assert clock is not None
    (fit,) = clock.fits
    assert fit.record_id in {"msg:item1:Chats!1011", "msg:item2:Chats!903"}


def test_no_clock_lead_when_the_phone_zone_is_unknown(conn):
    case = explain.load(conn)
    case.data.tz_for = lambda source_id: None
    assert explain._clock(case, [_asm(conn, "C10", "record_time")]) is None


# ---------------------------------------------------------------- fifth review


def test_a_record_in_the_windows_first_fraction_of_a_second_is_inside(conn):
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw, body)"
        " VALUES ('msg:item1:frac', 'item1', 'Test!3', 'thr:item1:WhatsApp:1', 'incoming',"
        " '2026-03-20T04:00:00.500000Z', 'test', 'hi')"
    )
    quiet = alts_for(conn, "C15")["app_quiet"]
    assert {f.source_id for f in quiet.fits} == {"item2"}  # item1's WhatsApp is not quiet


def test_a_calls_only_statement_quotes_no_message(conn):
    a = _asm(conn, "C10", "record_time", channels=("call",))
    assert explain._quoted_rows(explain.load(conn), a) == []


def test_one_message_two_meaning_statements_point_to_shows_once(conn):
    case = explain.load(conn)
    meaning = next(a for a in claim_state(conn, "C13").assumptions if a.template_id == "meaning")
    (claimed, *_) = explain._quoted_rows(case, meaning)
    thread = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (claimed.id,)).fetchone()
    word = explain._words(meaning.params.quoted_text or "")[0]
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw, body)"
        " VALUES ('msg:test:same', ?, 'Test!4', ?, 'incoming', '2026-03-01T12:00:00Z', 'test', ?)",
        (claimed.source_id, thread[0], f"we {word} later"),
    )
    twice = meaning.model_copy(update={"id": "asm:twice"})
    alt = explain._same_words(explain.load(conn), [meaning, twice])
    assert alt is not None
    assert [f.record_id for f in alt.fits].count("msg:test:same") == 1
    assert alt.total == len({f.record_id for f in alt.fits})


def test_a_phone_with_no_zone_shows_no_derived_local_time(conn):
    case = explain.load(conn)
    case.data.tz_for = lambda source_id: None
    row = explain._quoted_rows(case, _asm(conn, "C10", "record_time"))[0]
    fit = explain._fit(case, row, "note")
    assert fit.when and not fit.local
    assert "local time derived" not in alternatives_html(
        [Alternative("clock", "timing", "t", "s", (fit,), 1, "", ())]
    )


def test_a_record_at_the_instant_after_the_window_is_outside(conn):
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw, body)"
        " VALUES ('msg:item1:next', 'item1', 'Test!5', 'thr:item1:WhatsApp:1', 'incoming',"
        " '2026-03-24T04:00:00Z', 'test', 'hi')"
    )
    quiet = alts_for(conn, "C15")["app_quiet"]
    assert {f.source_id for f in quiet.fits} == {"item1", "item2"}  # item1 is still quiet
    after = next(f for f in quiet.fits if f.source_id == "item1" and "first after" in f.note)
    assert after.record_id == "msg:item1:next"


# ---------------------------------------------------------------- seventh review


def test_a_record_in_the_windows_last_microsecond_is_inside(conn):
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw, body)"
        " VALUES ('msg:item1:last', 'item1', 'Test!6', 'thr:item1:WhatsApp:1', 'incoming',"
        " '2026-03-24T03:59:59.999999Z', 'test', 'hi')"
    )
    quiet = alts_for(conn, "C15")["app_quiet"]
    assert {f.source_id for f in quiet.fits} == {"item2"}  # item1's WhatsApp is not quiet


def test_one_record_outside_two_named_apps_shows_once(conn):
    whatsapp = _asm(conn, "C14", "no_contact", channels=("WhatsApp",))
    telegram = _asm(conn, "C14", "no_contact", channels=("Telegram",))
    alt = explain._other_app(explain.load(conn), [whatsapp, telegram])
    assert alt is not None
    ids = [f.record_id for f in alt.fits]
    assert len(ids) == len(set(ids)) == alt.total
    both = [f for f in alt.fits if "WhatsApp" in f.note and "Telegram" in f.note]
    assert both  # a record outside both apps keeps both statements' notes


def test_two_identical_records_on_one_phone_both_show_on_the_clock(conn):
    rid = "msg:item1:Chats!1011"
    conn.execute(
        "INSERT INTO messages SELECT 'msg:item1:twin', source_id, 'Test!7', thread_id,"
        " sender_account_id, sender_raw, direction, ts_utc, ts_offset_min, ts_raw, body, lang,"
        " deleted_flag, bookmarked FROM messages WHERE id = ?",
        (rid,),
    )
    conn.execute(
        "INSERT INTO message_recipients SELECT 'msg:item1:twin', account_id, raw"
        " FROM message_recipients WHERE message_id = ?",
        (rid,),
    )
    clock = explain._clock(explain.load(conn), [_asm(conn, "C10", "record_time")])
    assert clock is not None
    ids = {f.record_id for f in clock.fits}
    assert "msg:item1:twin" in ids
    assert ids & {rid, "msg:item2:Chats!903"}


# ---------------------------------------------------------------- eighth review


def test_one_record_two_time_statements_point_to_shows_once_on_the_clock(conn):
    a = _asm(conn, "C10", "record_time")
    twice = a.model_copy(update={"id": "asm:twice"})
    clock = explain._clock(explain.load(conn), [a, twice])
    assert clock is not None
    ids = [f.record_id for f in clock.fits]
    assert len(ids) == len(set(ids)) == clock.total == 1


def test_no_other_clock_when_the_phones_own_clock_fits_too(conn):
    from zoneinfo import ZoneInfo

    from core.contracts import TimeWindow

    case = explain.load(conn)
    a = _asm(conn, "C10", "record_time")
    (fit,) = explain._clock(case, [a]).fits
    (ts,) = conn.execute("SELECT ts_utc FROM messages WHERE id = ?", (fit.record_id,)).fetchone()
    at = explain._parse(ts)
    own = at.astimezone(case.data.tz_for(fit.source_id)).replace(tzinfo=None)
    printed = at.replace(tzinfo=None)
    # Stated in Tokyo, wide enough for the phone's own reading and the printed UTC reading, while
    # the record's instant is outside it.
    tokyo = ZoneInfo("Asia/Tokyo")
    lo = (min(own, printed) - timedelta(minutes=1)).replace(tzinfo=tokyo).astimezone(UTC)
    hi = (max(own, printed) + timedelta(minutes=1)).replace(tzinfo=tokyo).astimezone(UTC)
    window = TimeWindow(start_utc=lo, end_utc=hi, tz="Asia/Tokyo", raw="test")
    assert not (lo <= at <= hi)
    assert explain._clock(case, [_asm(conn, "C10", "record_time", window=window)]) is None


def test_a_sender_statement_keeps_a_copy_in_another_conversation(conn):
    a = _asm(conn, "C05", "sender")
    case = explain.load(conn)
    (claimed, *_) = explain._quoted_rows(case, a)
    (thread,) = conn.execute(
        "SELECT m.thread_id FROM messages m JOIN threads t ON t.id = m.thread_id"
        " WHERE m.source_id = ? AND t.app = ? AND m.thread_id != ("
        "  SELECT thread_id FROM messages WHERE id = ?) LIMIT 1",
        (claimed.source_id, claimed.app, claimed.id),
    ).fetchone()
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw, body)"
        " VALUES ('msg:test:elsewhere', ?, 'Test!8', ?, 'incoming', '2026-03-01T12:00:00Z',"
        " 'test', ?)",
        (claimed.source_id, thread, claimed.text),
    )
    ids = [r.id for r in explain._quoted_rows(explain.load(conn), a)]
    assert claimed.id in ids and "msg:test:elsewhere" in ids


def test_an_identical_row_of_the_quoted_message_is_itself_a_quoted_row(conn):
    meaning = next(a for a in claim_state(conn, "C13").assumptions if a.template_id == "meaning")
    (claimed, *_) = explain._quoted_rows(explain.load(conn), meaning)
    conn.execute(
        "INSERT INTO messages SELECT 'msg:test:twin', source_id, 'Test!9', thread_id,"
        " sender_account_id, sender_raw, direction, ts_utc, ts_offset_min, ts_raw, body, lang,"
        " deleted_flag, bookmarked FROM messages WHERE id = ?",
        (claimed.id,),
    )
    conn.execute(
        "INSERT INTO message_recipients SELECT 'msg:test:twin', account_id, raw"
        " FROM message_recipients WHERE message_id = ?",
        (claimed.id,),
    )
    case = explain.load(conn)
    assert "msg:test:twin" in {r.id for r in explain._quoted_rows(case, meaning)}


def test_a_word_after_a_first_name_is_a_surname_only_when_the_case_knows_it(conn):
    acct = "acct:item1:WhatsApp:12125550111@s.whatsapp.net"
    (thread,) = conn.execute(
        "SELECT thread_id FROM messages WHERE sender_account_id = ? LIMIT 1", (acct,)
    ).fetchone()
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
        " ts_utc, ts_raw, body) VALUES ('msg:test:intro', 'item1', 'Test!10', ?, ?, 'outgoing',"
        " '2026-03-01T12:00:00Z', 'test', 'hey im daniel working today')",
        (thread, acct),
    )
    case = explain.load(conn)
    person = case.person("person:dev:item1:owner")
    found, _ = explain._intro_fits(case, {case.data.accounts[acct].key}, [person])
    assert "msg:test:intro" not in {r.id for r, _ in found}


# ---------------------------------------------------------------- ninth review


def test_a_quoted_authorship_statement_gets_its_hand_off_words(conn):
    quote = _asm(conn, "C16", "sender").params.quoted_text
    auth = _asm(conn, "C16", "authorship", quoted_text=quote)
    case = explain.load(conn)
    assert explain._claimed_rows(case, [auth])[auth.id]
    alt = explain._other_user(case, [auth])
    assert alt is not None
    assert any("Speaks of using another person's" in f.note for f in alt.fits)


def test_an_edge_record_two_windows_share_shows_once(conn):
    a = _asm(conn, "C15", "event")
    alt = explain._app_quiet(explain.load(conn), [a, a.model_copy(update={"id": "asm:twice"})])
    assert alt is not None
    ids = [f.record_id for f in alt.fits]
    assert len(ids) == len(set(ids)) == alt.total


def test_each_phone_is_read_once_per_case(conn):
    case = explain.load(conn)
    assert explain._phone_rows(case, "item1") is explain._phone_rows(case, "item1")


def test_a_record_two_statements_move_across_the_day_shows_once(conn):
    a = _asm(conn, "C14", "no_contact")
    one = explain._day_boundary(explain.load(conn), [a])
    two = explain._day_boundary(explain.load(conn), [a, a.model_copy(update={"id": "asm:twice"})])
    assert [f.record_id for f in two.fits] == [f.record_id for f in one.fits]
    assert two.total == one.total


@pytest.mark.parametrize("finder", ["_clock", "_other_app", "_day_boundary"])
def test_copies_two_phone_scoped_statements_point_to_show_once(conn, finder):
    claim, template, extra = {
        "_clock": ("C10", "record_time", {}),
        "_other_app": ("C14", "no_contact", {"channels": ("WhatsApp",)}),
        "_day_boundary": ("C14", "no_contact", {}),
    }[finder]
    one = _asm(conn, claim, template, device_ids=("dev:item1",), **extra)
    two = _asm(conn, claim, template, device_ids=("dev:item2",), **extra)
    two = two.model_copy(update={"id": "asm:item2"})
    case = explain.load(conn)
    find = getattr(explain, finder)
    both = find(case, [one, two])
    alone = find(case, [one])
    assert both is not None and alone is not None
    # item2's copies of item1's records add nothing: the same records, the same total.
    assert {f.record_id for f in both.fits} == {f.record_id for f in alone.fits}
    assert both.total == alone.total


# ---------------------------------------------------------------- tenth review


def test_a_copy_on_another_phone_adds_its_own_clock_reading(conn):
    one = _asm(conn, "C10", "record_time", device_ids=("dev:item1",))
    two = _asm(conn, "C10", "record_time", device_ids=("dev:item2",))
    two = two.model_copy(update={"id": "asm:item2"})
    clock = explain._clock(explain.load(conn), [one, two])
    assert clock is not None
    (fit,) = clock.fits
    assert fit.source_id == "item1"
    assert "'s copy: Read on" in fit.note  # item2's own reading kept on the same line
    assert set(clock.assumption_ids) == {one.id, two.id}


def test_quiet_app_sentences_keep_windows_with_the_same_words_apart(conn):
    a = _asm(conn, "C15", "event")
    w = a.params.window
    moved = w.model_copy(
        update={
            "start_utc": w.start_utc + timedelta(minutes=1),
            "end_utc": w.end_utc + timedelta(minutes=1),
        }
    )
    b = _asm(conn, "C15", "event", window=moved).model_copy(update={"id": "asm:moved"})
    alt = explain._app_quiet(explain.load(conn), [a, b])
    assert alt is not None
    assert alt.summary.count("has no record in any conversation") == 2


def test_locators_are_looked_up_only_for_shown_records(conn, monkeypatch):
    case = explain.load(conn)
    real = case.locator

    def refuse(rid: str) -> tuple[str, str]:
        raise AssertionError(f"looked up {rid} before it was shown")

    monkeypatch.setattr(case, "locator", refuse)
    row = explain._quoted_rows(case, _asm(conn, "C10", "record_time"))[0]
    fit = explain._fit(case, row, "note")  # every match makes a fit; none is looked up yet
    calls: list[str] = []
    monkeypatch.setattr(case, "locator", lambda rid: calls.append(rid) or real(rid))
    alts = explain.alternatives(case, claim_state(conn, "C14").assumptions)
    assert alts and len(calls) <= sum(len(a.fits) for a in alts)
    shown = explain._located(case, Alternative("clock", "timing", "t", "s", (fit,), 9, "", ()))
    (sid, loc) = conn.execute(
        "SELECT source_id, locator FROM messages WHERE id = ?", (row.id,)
    ).fetchone()
    assert (shown.fits[0].source_id, shown.fits[0].locator) == (sid, loc)


def test_no_leads_for_a_claim_edited_after_the_audit(conn):
    from core.report.html import _claim_block
    from ui.pages import _alternatives

    st = claim_state(conn, "C16")
    assert "Other explanations to check" in _claim_block(conn, st, explain.load(conn))
    st.edited_after_run = True
    assert "Other explanations to check" not in _claim_block(conn, st, explain.load(conn))
    page = _alternatives(conn, st)
    assert "id='alternatives'" not in page and "re-run" in page


def test_one_saved_name_on_two_accounts_shows_for_each(conn):
    case = explain.load(conn)

    def name(rid: str):  # noqa: ANN202
        return SimpleNamespace(
            text="Ilya M",
            kind="contact name",
            words=("ilya", "m"),
            record_id=rid,
            source_id="item1",
            locator=rid,
            note="",
        )

    k1, k2 = ("sms", "+1"), ("whatsapp", "1@s")
    case.ids.groups = {
        k1: SimpleNamespace(label="a", names=[name("c1")]),
        k2: SimpleNamespace(label="b", names=[name("c2")]),
    }
    fits = explain._name_fits(case, {k1, k2}, [_person("Daniel Petrov")])
    assert {f.record_id for f in fits} == {"c1", "c2"}


# ---------------------------------------------------------------- eleventh review


def test_a_possessive_name_is_not_an_introduction(conn):
    acct = "acct:item1:WhatsApp:12125550111@s.whatsapp.net"
    (thread,) = conn.execute(
        "SELECT thread_id FROM messages WHERE sender_account_id = ? LIMIT 1", (acct,)
    ).fetchone()
    for i, body in enumerate(["this is ilya's phone", "hey its ilya morozov’s ipad"]):
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, ts_utc, ts_raw, body) VALUES (?, 'item1', ?, ?, ?, 'outgoing',"
            " '2026-03-01T12:00:00Z', 'test', ?)",
            (f"msg:test:poss{i}", f"Test!{20 + i}", thread, acct, body),
        )
    case = explain.load(conn)
    person = case.person("person:dev:item1:owner")
    found, _ = explain._intro_fits(case, {case.data.accounts[acct].key}, [person])
    assert not {"msg:test:poss0", "msg:test:poss1"} & {r.id for r, _ in found}


def test_a_copy_found_by_another_phones_statement_keeps_its_note(conn):
    one = _asm(conn, "C14", "no_contact", channels=("WhatsApp",), device_ids=("dev:item1",))
    two = _asm(conn, "C14", "no_contact", channels=("Telegram",), device_ids=("dev:item2",))
    two = two.model_copy(update={"id": "asm:item2"})
    alt = explain._other_app(explain.load(conn), [one, two])
    assert alt is not None
    assert {f.source_id for f in alt.fits} == {"item1"}
    # item2's copy fits the Telegram statement too: its line carries both statements' notes.
    assert any(f.note.count("outside") == 2 for f in alt.fits)


def test_same_words_copies_two_phone_scoped_statements_find_show_once(conn):
    meaning = next(a for a in claim_state(conn, "C13").assumptions if a.template_id == "meaning")
    case = explain.load(conn)
    word = explain._words(meaning.params.quoted_text or "")[0]
    # The same neighboring message on both phones, next to each phone's copy of the quote.
    for r in explain._quoted_rows(case, meaning):
        (thread,) = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (r.id,)).fetchone()
        mid = f"msg:{r.source_id}:neighbor"
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, ts_utc, ts_raw, body) VALUES (?, ?, 'Test!30', ?, ?, 'incoming',"
            " '2026-03-01T12:00:00Z', 'test', ?)",
            (mid, r.source_id, thread, r.sender, f"we {word} later"),
        )
        for acct in r.recipients:
            conn.execute(
                "INSERT INTO message_recipients (message_id, account_id) VALUES (?, ?)",
                (mid, acct),
            )
    scoped = [
        meaning.model_copy(
            update={
                "id": f"asm:{d}",
                "params": meaning.params.model_copy(update={"device_ids": (f"dev:{d}",)}),
            }
        )
        for d in ("item1", "item2")
    ]
    case = explain.load(conn)
    both = explain._same_words(case, scoped)
    alone = explain._same_words(case, scoped[:1])
    assert both is not None and alone is not None
    assert both.total == alone.total
    assert {f.record_id for f in both.fits} == {f.record_id for f in alone.fits}


# ---------------------------------------------------------------- twelfth review


def _twin(conn, rid: str, new: str) -> None:  # noqa: ANN001
    conn.execute(
        "INSERT INTO messages SELECT ?, source_id, 'Test!40', thread_id, sender_account_id,"
        " sender_raw, direction, ts_utc, ts_offset_min, ts_raw, body, lang, deleted_flag,"
        " bookmarked FROM messages WHERE id = ?",
        (new, rid),
    )
    conn.execute(
        "INSERT INTO message_recipients SELECT ?, account_id, raw FROM message_recipients"
        " WHERE message_id = ?",
        (new, rid),
    )


def test_two_rows_on_the_later_phone_stay_two_records(conn):
    _twin(conn, "msg:item2:Chats!912", "msg:item2:twin")
    one = _asm(conn, "C14", "no_contact", channels=("WhatsApp",), device_ids=("dev:item1",))
    two = _asm(conn, "C14", "no_contact", channels=("Telegram",), device_ids=("dev:item2",))
    two = two.model_copy(update={"id": "asm:item2"})
    case = explain.load(conn)
    alone = explain._other_app(case, [one])
    both = explain._other_app(case, [one, two])
    assert both.total == alone.total + 1  # item2's second row is a record of its own


def test_clock_twins_on_the_later_phone_stay_two_records(conn):
    _twin(conn, "msg:item2:Chats!903", "msg:item2:twin")
    one = _asm(conn, "C10", "record_time", device_ids=("dev:item1",))
    two = _asm(conn, "C10", "record_time", device_ids=("dev:item2",))
    two = two.model_copy(update={"id": "asm:item2"})
    clock = explain._clock(explain.load(conn), [one, two])
    assert clock is not None
    assert clock.total == 2
    assert [f.source_id for f in clock.fits] == ["item1", "item2"]


# ---------------------------------------------------------------- thirteenth review


def test_a_later_introduction_in_the_same_message_still_counts(conn):
    acct = "acct:item1:WhatsApp:12125550111@s.whatsapp.net"
    (thread,) = conn.execute(
        "SELECT thread_id FROM messages WHERE sender_account_id = ? LIMIT 1", (acct,)
    ).fetchone()
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
        " ts_utc, ts_raw, body) VALUES ('msg:test:twointros', 'item1', 'Test!50', ?, ?,"
        " 'outgoing', '2026-03-01T12:00:00Z', 'test', 'im daniel. its ilya actually')",
        (thread, acct),
    )
    case = explain.load(conn)
    person = case.person("person:dev:item1:owner")
    found, _ = explain._intro_fits(case, {case.data.accounts[acct].key}, [person])
    assert "msg:test:twointros" in {r.id for r, _ in found}


def test_an_account_on_phones_all_owned_by_the_named_person_is_no_lead(conn):
    case = explain.load(conn)
    acct = case.data.accounts["acct:item1:Phone:+12125550122"]
    g = case.ids.groups[acct.key]
    g.owner_devices[:] = ["dev:item2", "dev:item3"]  # an owner account on two phones
    daniel = Person("p", "Daniel Petrov", "t", ("daniel", "petrov"), tuple(g.owner_devices))

    def owned(*statuses: str) -> int:
        case.data.stipulations = [
            (f"s{i}", d, "p", st)
            for i, (d, st) in enumerate(zip(g.owner_devices, statuses, strict=False))
        ]
        return len(explain._multi_owner_fits(case, {acct.key}, [daniel]))

    assert owned("confirmed", "confirmed") == 0
    assert owned("confirmed") == 1  # one phone not stipulated to him
    assert owned("confirmed", "proposed") == 1  # proposed is not ownership yet
    assert owned("proposed", "proposed") == 1


def test_same_words_nearest_first_across_statements(conn):
    states = [claim_state(conn, c) for c in ("C13", "C17")]
    first, second = (next(a for a in st.assumptions if a.template_id == "meaning") for st in states)
    case = explain.load(conn)

    def place(a, rid: str, minutes: int, n: int) -> None:  # noqa: ANN001
        (claimed, *_) = explain._quoted_rows(case, a)
        (thread,) = conn.execute(
            "SELECT thread_id FROM messages WHERE id = ?", (claimed.id,)
        ).fetchone()
        word = explain._words(a.params.quoted_text or "")[0]
        at = claimed.ts_utc + timedelta(minutes=minutes)
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw,"
            " body) VALUES (?, ?, ?, ?, 'incoming', ?, 'test', ?)",
            (rid, claimed.source_id, f"Test!{60 + n}", thread, at.isoformat(), f"so {word} ok"),
        )

    for n in range(explain.MAX_FITS + 1):  # far matches for the first quote
        place(first, f"msg:test:far{n}", 600 + n, n)
    place(second, "msg:test:near", 1, 20)
    alt = explain._same_words(explain.load(conn), [first, second])
    assert alt is not None
    assert alt.fits[0].record_id == "msg:test:near"


# ---------------------------------------------------------------- fourteenth review


def test_quiet_app_call_copies_are_told_apart_by_callee(conn):
    case = explain.load(conn)
    caller, one, other = sorted({a.key: a.id for a in case.data.accounts.values()}.values())[:3]
    for sid, to in (("item1", one), ("item2", other)):
        conn.execute(
            "INSERT INTO calls (id, source_id, locator, app, from_account_id, to_account_id,"
            " direction, ts_utc, ts_raw, duration_s) VALUES (?, ?, 'Test!1', 'WhatsApp', ?, ?,"
            " 'outgoing', '2026-03-01T12:00:00Z', 'test', 30)",
            (f"call:{sid}:test", sid, caller, to),
        )
    case = explain.load(conn)
    rows = [
        r
        for sid in ("item1", "item2")
        for r in explain._phone_rows(case, sid)
        if r.id == f"call:{sid}:test"
    ]
    assert [r.recipients for r in rows] == [(one,), (other,)]
    assert len(explain._collapse(case, [(r, "edge") for r in rows])) == 2  # two calls, not copies


def test_same_words_nearness_counts_every_quoted_message(conn):
    meaning = next(a for a in claim_state(conn, "C13").assumptions if a.template_id == "meaning")
    case = explain.load(conn)
    (quoted, *_) = explain._quoted_rows(case, meaning)
    (thread,) = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (quoted.id,)).fetchone()
    word = explain._words(meaning.params.quoted_text or "")[0]

    def add(rid: str, minutes: int, body: str) -> None:
        at = quoted.ts_utc + timedelta(minutes=minutes)
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw,"
            " body) VALUES (?, ?, ?, ?, 'incoming', ?, 'test', ?)",
            (rid, quoted.source_id, f"Test!{rid}", thread, at.isoformat(), body),
        )

    add("msg:test:again", 5000, meaning.params.quoted_text or "")  # the quote, a second time
    for n in range(explain.MAX_FITS + 1):
        add(f"msg:test:first{n}", 2 + n, f"so {word} ok")
    add("msg:test:by-again", 5001, f"and {word} too")
    case = explain.load(conn)
    assert len(explain._quoted_rows(case, meaning)) > 1
    alt = explain._same_words(case, [meaning])
    assert alt is not None
    assert alt.fits[0].record_id == "msg:test:by-again"  # one minute from the second quote


def test_hand_off_copies_two_phone_scoped_statements_find_show_once(conn):
    quote = _asm(conn, "C16", "sender").params.quoted_text
    one = _asm(conn, "C16", "authorship", quoted_text=quote, device_ids=("dev:item1",))
    two = _asm(conn, "C16", "authorship", quoted_text=quote, device_ids=("dev:item2",))
    two = two.model_copy(update={"id": "asm:item2"})
    case = explain.load(conn)
    both = explain._other_user(case, [one, two])
    assert both is not None
    # "left his login" sits next to the quote on both phones: one record, shown once.
    assert sum("left his login" in f.note for f in both.fits) == 1


def test_the_quoted_message_itself_can_speak_of_a_hand_off(conn):
    quote = _asm(conn, "C16", "sender").params.quoted_text
    case = explain.load(conn)
    a = _asm(conn, "C16", "authorship", quoted_text=quote, device_ids=("dev:item1",))
    (quoted,) = explain._claimed_rows(case, [a])[a.id]
    conn.execute(
        "UPDATE messages SET body = ? WHERE id = ?", (f"{quote}, im using his phone", quoted.id)
    )
    a = a.model_copy(
        update={"params": a.params.model_copy(update={"quoted_text": f"{quote}, im using"})}
    )
    alt = explain._other_user(explain.load(conn), [a])
    assert alt is not None
    fit = next(f for f in alt.fits if f.record_id == quoted.id)
    assert fit.note.startswith("The message itself speaks of using another person's phone")


# ---------------------------------------------------------------- fifteenth review


def test_hand_off_search_keeps_to_the_exact_window(conn):
    quote = _asm(conn, "C16", "sender").params.quoted_text
    case = explain.load(conn)
    a = _asm(conn, "C16", "authorship", quoted_text=quote, device_ids=("dev:item1",))
    (quoted,) = explain._claimed_rows(case, [a])[a.id]
    (thread,) = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (quoted.id,)).fetchone()
    edge = quoted.ts_utc + timedelta(days=explain.HANDOFF_DAYS)
    for rid, at in (
        ("msg:test:at-edge", edge),
        ("msg:test:past-edge", edge + timedelta(microseconds=300)),
    ):
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw,"
            " body) VALUES (?, 'item1', ?, ?, 'incoming', ?, 'test', 'im using his phone')",
            (rid, f"Test!{rid}", thread, explain._iso(at)),
        )
    found, _ = explain._handoff_fits(explain.load(conn), [quoted])
    ids = {r.id for r, _ in found}
    assert "msg:test:at-edge" in ids
    assert "msg:test:past-edge" not in ids


def test_same_words_nearness_follows_every_copy_of_a_line(conn):
    meaning = next(a for a in claim_state(conn, "C13").assumptions if a.template_id == "meaning")
    case = explain.load(conn)
    word = explain._words(meaning.params.quoted_text or "")[0]
    quoted = {r.source_id: r for r in explain._quoted_rows(case, meaning)}
    assert {"item1", "item2"} <= set(quoted)
    t0 = quoted["item1"].ts_utc

    def add(r, rid: str, minutes: int, body: str) -> None:  # noqa: ANN001
        (thread,) = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (r.id,)).fetchone()
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, ts_utc, ts_raw, body) VALUES (?, ?, ?, ?, ?, 'incoming', ?, 'test', ?)",
            (rid, r.source_id, f"Test!{rid}", thread, r.sender,
             (t0 + timedelta(minutes=minutes)).isoformat(), body),
        )  # fmt: skip
        for acct in r.recipients:
            conn.execute(
                "INSERT INTO message_recipients (message_id, account_id) VALUES (?, ?)",
                (rid, acct),
            )

    for sid in ("item1", "item2"):  # one message on both phones, far from the first quote
        add(quoted[sid], f"msg:{sid}:neighbor", 5000, f"we {word} later")
    # On item2 only, the quote again a minute away from it; on item1, nearer matches.
    add(quoted["item2"], "msg:item2:again", 5001, meaning.params.quoted_text or "")
    for n in range(explain.MAX_FITS + 1):
        add(quoted["item1"], f"msg:item1:filler{n}", 2 + n, f"so {word} ok")
    scoped = [
        meaning.model_copy(
            update={
                "id": f"asm:{d}",
                "params": meaning.params.model_copy(update={"device_ids": (f"dev:{d}",)}),
            }
        )
        for d in ("item1", "item2")
    ]
    alt = explain._same_words(explain.load(conn), scoped)
    assert alt is not None
    assert alt.fits[0].record_id == "msg:item1:neighbor"  # one minute from item2's quote


# ---------------------------------------------------------------- sixteenth review


def test_hand_off_search_reads_each_phone_once(conn):
    quote = _asm(conn, "C16", "sender").params.quoted_text
    case = explain.load(conn)
    a = _asm(conn, "C16", "authorship", quoted_text=quote, device_ids=("dev:item1",))
    (quoted,) = explain._claimed_rows(case, [a])[a.id]
    many = [replace(quoted, id=f"{quoted.id}#{n}") for n in range(5)]  # one quote, five places
    reads: list[str] = []
    conn.set_trace_callback(lambda sql: reads.append(sql) if "FROM messages m" in sql else None)
    try:
        found, _ = explain._handoff_fits(explain.load(conn), many)
    finally:
        conn.set_trace_callback(None)
    assert found
    assert len(reads) == 1  # the phone's records, read once for every claimed message


# ---------------------------------------------------------------- seventeenth review


def test_one_name_in_two_records_on_one_phone_shows_twice(conn):
    case = explain.load(conn)

    def name(rid: str, sid: str):  # noqa: ANN202
        return SimpleNamespace(
            text="Ilya M", kind="contact name", words=("ilya", "m"), record_id=rid,
            source_id=sid, locator=rid, note="",
        )  # fmt: skip

    k = ("sms", "+1")
    names = [name("c1", "item1"), name("c2", "item1"), name("c3", "item2"), name("c1", "item1")]
    case.ids.groups = {k: SimpleNamespace(label="a", names=names)}
    fits = explain._name_fits(case, {k}, [_person("Daniel Petrov")])
    # Two records on item1 stay two; item2's record is a copy of one of them.
    assert [f.record_id for f in fits] == ["c1", "c2"]


def _meaning_thread(conn):  # noqa: ANN202
    meaning = next(a for a in claim_state(conn, "C13").assumptions if a.template_id == "meaning")
    (quoted, *_) = explain._quoted_rows(explain.load(conn), meaning)
    (thread,) = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (quoted.id,)).fetchone()
    return meaning, quoted, thread


def _add_message(conn, rid: str, sid: str, thread: str, at: datetime, body: str) -> None:  # noqa: ANN001
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, ts_raw,"
        " body) VALUES (?, ?, ?, ?, 'incoming', ?, 'test', ?)",
        (rid, sid, f"Test!{rid}", thread, at.isoformat(), body),
    )


def test_same_words_reads_recipients_once_per_conversation(conn):
    meaning, quoted, thread = _meaning_thread(conn)
    word = explain._words(meaning.params.quoted_text or "")[0]
    for n in range(20):
        at = quoted.ts_utc + timedelta(minutes=10 + n)
        _add_message(conn, f"msg:test:w{n}", quoted.source_id, thread, at, f"so {word} ok")
    case = explain.load(conn)
    reads: list[str] = []
    conn.set_trace_callback(
        lambda sql: reads.append(sql) if "FROM message_recipients" in sql else None
    )
    try:
        alt = explain._same_words(case, [meaning])
    finally:
        conn.set_trace_callback(None)
    assert alt is not None and alt.total >= 20
    assert len(reads) < 10  # not one query per matching message


def test_same_words_nearness_stays_in_each_conversation(conn):
    meaning, quoted, thread = _meaning_thread(conn)
    word = explain._words(meaning.params.quoted_text or "")[0]
    (other,) = conn.execute(
        "SELECT thread_id FROM messages WHERE source_id = ? AND thread_id != ? LIMIT 1",
        (quoted.source_id, thread),
    ).fetchone()
    t0 = quoted.ts_utc
    later = t0 + timedelta(minutes=5000)
    # The quote again, in another conversation, a minute from a match in the first one.
    _add_message(conn, "msg:test:elsewhere", quoted.source_id, other, later,
                 meaning.params.quoted_text or "")  # fmt: skip
    _add_message(conn, "msg:test:late", quoted.source_id, thread, later + timedelta(minutes=1),
                 f"and {word} too")  # fmt: skip
    for n in range(explain.MAX_FITS + 1):
        _add_message(conn, f"msg:test:early{n}", quoted.source_id, thread,
                     t0 + timedelta(minutes=2 + n), f"so {word} ok")  # fmt: skip
    case = explain.load(conn)
    assert any(r.id == "msg:test:elsewhere" for r in explain._quoted_rows(case, meaning))
    alt = explain._same_words(case, [meaning])
    assert alt is not None
    shown = [f.record_id for f in alt.fits]
    assert "msg:test:late" not in shown  # far from the quote in its own conversation
    assert shown[0] == "msg:test:early0"


# ---------------------------------------------------------------- eighteenth review


def test_an_account_name_and_a_contact_with_the_same_words_both_show(conn):
    case = explain.load(conn)

    def name(rid: str, sid: str, kind: str):  # noqa: ANN202
        return SimpleNamespace(
            text="Ilya M", kind=kind, words=("ilya", "m"), record_id=rid, source_id=sid,
            locator=rid, note="",
        )  # fmt: skip

    k = ("sms", "+1")
    names = [name("a1", "item1", "account name"), name("c2", "item2", "contact name")]
    case.ids.groups = {k: SimpleNamespace(label="a", names=names)}
    fits = explain._name_fits(case, {k}, [_person("Daniel Petrov")])
    assert [f.record_id for f in fits] == ["a1", "c2"]  # different records, not copies


def _trace(conn, needle: str):  # noqa: ANN202
    reads: list[str] = []
    conn.set_trace_callback(lambda sql: reads.append(sql) if needle in sql else None)
    return reads


def test_same_words_reads_quoted_conversations_in_one_query(conn):
    meaning, quoted, thread = _meaning_thread(conn)
    for n in range(5):  # the quote, five more times in its conversation
        at = quoted.ts_utc + timedelta(minutes=30 + n)
        _add_message(conn, f"msg:test:q{n}", quoted.source_id, thread, at,
                     meaning.params.quoted_text or "")  # fmt: skip
    case = explain.load(conn)
    reads = _trace(conn, "thread_id FROM messages")
    try:
        explain._same_words(case, [meaning])
    finally:
        conn.set_trace_callback(None)
    assert len(reads) == 1


def test_clock_reads_offsets_in_one_query_per_table(conn):
    a = _asm(conn, "C10", "record_time")
    case = explain.load(conn)
    ids = [r[0] for r in conn.execute("SELECT id FROM messages LIMIT 20")]
    ids += [r[0] for r in conn.execute("SELECT id FROM calls LIMIT 20")]
    reads = _trace(conn, "ts_offset_min")
    try:
        offsets = case.offsets(ids)
        assert explain._clock(case, [a]) is not None
    finally:
        conn.set_trace_callback(None)
    assert set(offsets) == set(ids)
    assert len(reads) <= 4  # two for the 40 records, two for the clock lead


def test_same_words_nearness_counts_copies_dropped_as_duplicates(conn):
    meaning = next(a for a in claim_state(conn, "C13").assumptions if a.template_id == "meaning")
    case = explain.load(conn)
    word = explain._words(meaning.params.quoted_text or "")[0]
    quoted = {r.source_id: r for r in explain._quoted_rows(case, meaning)}
    assert {"item1", "item2"} <= set(quoted)
    t0 = quoted["item1"].ts_utc

    def add(r, rid: str, minutes: int, body: str) -> None:  # noqa: ANN001
        (thread,) = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (r.id,)).fetchone()
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, ts_utc, ts_raw, body) VALUES (?, ?, ?, ?, ?, 'incoming', ?, 'test', ?)",
            (rid, r.source_id, f"Test!{rid}", thread, r.sender,
             (t0 + timedelta(minutes=minutes)).isoformat(), body),
        )  # fmt: skip
        for acct in r.recipients:
            conn.execute(
                "INSERT INTO message_recipients (message_id, account_id) VALUES (?, ?)",
                (rid, acct),
            )

    for sid in ("item1", "item2"):
        add(quoted[sid], f"msg:{sid}:neighbor", 5000, f"we {word} later")
    add(quoted["item2"], "msg:item2:again", 5001, meaning.params.quoted_text or "")
    for n in range(explain.MAX_FITS + 1):
        add(quoted["item1"], f"msg:item1:filler{n}", 2 + n, f"so {word} ok")
    alt = explain._same_words(explain.load(conn), [meaning])  # one statement, both phones
    assert alt is not None
    assert alt.fits[0].record_id in {"msg:item1:neighbor", "msg:item2:neighbor"}


def test_hand_offs_rank_by_the_nearest_claimed_message(conn):
    quote = _asm(conn, "C16", "sender").params.quoted_text
    case = explain.load(conn)
    a = _asm(conn, "C16", "authorship", quoted_text=quote, device_ids=("dev:item1",))
    (quoted,) = explain._claimed_rows(case, [a])[a.id]
    (thread,) = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (quoted.id,)).fetchone()
    later = replace(quoted, id="msg:test:later-quote", ts_utc=quoted.ts_utc + timedelta(days=10))
    for n in range(explain.MAX_FITS + 1):
        _add_message(conn, f"msg:test:h{n}", "item1", thread,
                     quoted.ts_utc + timedelta(minutes=2 + n), "im using his phone")  # fmt: skip
    _add_message(conn, "msg:test:by-later", "item1", thread,
                 later.ts_utc + timedelta(minutes=1), "im using his phone")  # fmt: skip
    found, _ = explain._handoff_fits(explain.load(conn), [quoted, later])
    ids = [r.id for r, _ in found]
    assert ids.index("msg:test:by-later") < min(ids.index(f"msg:test:h{n}") for n in range(7))


# ---------------------------------------------------------------- nineteenth review


def test_a_call_line_is_never_shown_as_cited_text():
    fit = explain.Fit("call:x", "item1", "Calls!1", "", "Mar 1", "Baker's note.", False,
                      "A call on WhatsApp, 30 s")  # fmt: skip
    alt = Alternative("app_quiet", "completeness", "t", "s", (fit,), 1, "", ())
    page = alternatives_html([alt])
    assert "A call on WhatsApp, 30 s" in page
    assert '<span class="q">A call on' not in page


def test_hand_off_words_come_before_the_accounts_names(conn, monkeypatch):
    quote = _asm(conn, "C16", "sender").params.quoted_text
    auth = _asm(conn, "C16", "authorship", quoted_text=quote)
    many = [
        explain.Fit(f"contact:n{n}", "item1", "", "Ilya M", "", "A saved name.")
        for n in range(explain.MAX_FITS + 1)
    ]
    monkeypatch.setattr(explain, "_name_fits", lambda *a, **k: list(many))
    monkeypatch.setattr(explain, "_intro_fits", lambda *a, **k: ([], ""))
    monkeypatch.setattr(explain, "_persons", lambda *a, **k: [_person("Daniel Petrov")])
    alt = explain._other_user(explain.load(conn), [auth])
    assert alt is not None
    assert alt.fits[0].note.startswith("Speaks of using another person's")  # not crowded out
