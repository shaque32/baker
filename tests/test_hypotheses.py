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
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import pipeline
from core.audit.invariants import FORBIDDEN_WORDS, check_report_text
from core.contracts import GoldClaim
from core.db import connect
from core.hypotheses import explain
from core.hypotheses.explain import Alternative
from core.identity.links import CITE_CLOSE, CITE_OPEN
from core.report.html import render_report
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
    assert {f.source_id for f in quiet.fits} == {"item1", "item2"}
    assert all("WhatsApp" in f.note for f in quiet.fits)
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
    assert before.quote == "WhatsApp call, 30 s"


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
