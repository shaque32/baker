"""The names a government document gives a number ("the BURNER" for "+1 (720) 555-0186"),
recorded by the expert (core/review/account_names.py), and the matching rules that came with
them in filler version 5: a name matches with or without a leading "the", a quote the claim
never makes is dropped from a time range only, and "texting" names SMS. Synthetic case01.

In the case05 go/no-go, 11 of the 28 claims the testability step did not convert named a phone
or a number by a designation code could not resolve, or wrote "COURIER" for the alias "the
COURIER"; 7 more set quoted words for a claim that quotes none.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.audit import case_events, testability
from core.audit._llm_json import prompt_body
from core.audit.assumption_filler import (
    LocalAssumptionFiller,
    Reject,
    _Account,
    _ProposalOut,
    _Window,
    unquoted_time_quote,
)
from core.audit.assumptions import TemplateAssumptionBuilder
from core.audit.checks import CHECKS
from core.audit.invariants import check_report_text
from core.bundle import verify
from core.contracts import CheckOutcome, Claim, ClaimStatus, ClaimType
from core.db import connect
from core.identity import aliases
from core.report.html import _limitations, sources
from core.review import account_names, actions, audit_log, status
from core.review.actions import ReviewError
from eval import run_pipeline
from tests.fake_model import FakeModel

EXPERT = "expert:Test Expert"
WHEN = datetime(2026, 11, 3, 20, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
DRAFT = prompt_body((ROOT / "docs/prompts/assumptions.md").read_text("utf-8"))
PETROV, REYES = "person:dev:item1:owner", "person:dev:item2:owner"
GARAGE = "+1 (212) 555-0122"  # Marc's number in case01: Phone, SMS and WhatsApp on both phones
ALEX = "+1 (212) 555-0182"  # an SMS contact on Item 1 only
ALEX_SMS = "acct:item1:SMS:+12125550182"
MARC_PHONE = "acct:item1:Phone:+12125550122"
PETROV_WA = "12125550111@s.whatsapp.net"
MARC_WA = "acct:item1:WhatsApp:12125550122@s.whatsapp.net"


def _clock() -> datetime:
    return WHEN


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("numbers") / "case01.db"
    run_pipeline.build_case("case01", path).close()
    return path


@pytest.fixture
def conn(built, tmp_path) -> sqlite3.Connection:
    copy = tmp_path / "case.db"
    shutil.copy(built, copy)
    c = connect(copy)
    yield c
    c.close()


def _log(conn: sqlite3.Connection) -> list[dict]:
    return [
        json.loads(p)
        for (p,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq",
            (account_names.ACTION,),
        )
    ]


def _filler(conn: sqlite3.Connection, props: list[dict] | None = None) -> LocalAssumptionFiller:
    answer = json.dumps({"assumptions": props or []})
    return LocalAssumptionFiller(FakeModel(answer), conn, template=DRAFT)


def _para(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT id FROM govdoc_paragraphs ORDER BY id LIMIT 1").fetchone()[0]


def _claim(conn: sqlite3.Connection, text: str, kind: ClaimType) -> Claim:
    return Claim(
        id="X1", paragraph_id=_para(conn), text=text, claim_type=kind, status=ClaimStatus.ACCEPTED
    )


def P(template_id: str, **kw) -> dict:  # noqa: N802
    base = dict(
        people=[],
        accounts=[],
        handles=[],
        phones=[],
        channels=[],
        quoted_text="",
        count=None,
        duration=None,
        window=None,
    )
    return {"template_id": template_id, **base, **kw}


def W(as_written: str, start: str, end: str) -> dict:  # noqa: N802
    return {"as_written": as_written, "start": start, "end": end, "zone": "phone"}


def build(conn: sqlite3.Connection, text: str, kind: ClaimType, props: list[dict]):
    filler = _filler(conn, props)
    return TemplateAssumptionBuilder(filler).build(_claim(conn, text, kind)), filler


def _run(conn: sqlite3.Connection, a) -> CheckOutcome:  # noqa: ANN001
    from core.audit.assumptions import TEMPLATES

    outcomes = {CHECKS[n].run(a, conn).outcome for n in TEMPLATES[a.template_id].checks}
    (outcome,) = outcomes
    return outcome


# ---------------------------------------------------------------- "the" either way


@pytest.mark.parametrize(
    ("alias", "answer", "match"),
    [
        ("the COURIER", "COURIER", True),
        ("the COURIER", "The COURIER", True),  # "the" in any case
        ("the COURIER", "the courier", False),  # a defined term in capitals only in capitals
        ("the COURIER", "Courier", False),
        ("COURIER", "the COURIER", True),
        ("The Courier", "COURIER", True),  # a name not in capitals in any case
        ("The Courier", "courier", True),
        ("the COURIER", "COURIER VAN", False),  # still whole
        ("the COURIER", "@courier", False),  # a handle is no name
        ("the COURIER", "the", False),
        ("the COURIER", "THE OTHER COURIER", False),
        ("THEO", "O", False),  # only the word "the"
        ("the TRUCK", "TRUCK", True),
    ],
)
def test_a_name_answers_whole_with_or_without_a_leading_the(alias, answer, match):
    assert aliases.answers(alias, answer) is match


def test_a_name_without_the_is_one_of_the_forms_a_clash_check_compares():
    assert aliases.forms("the COURIER") >= {"the courier", "courier"}
    assert aliases.bare("the") == "the"  # "the" alone is kept, never emptied


def test_an_alias_the_courier_is_refused_when_another_person_is_named_courier(conn):
    # The validation thread's condition: the stripped form clashes where the full one would.
    courier = actions.add_person(conn, "Courier", EXPERT, _clock)
    with pytest.raises(ReviewError, match="Courier"):
        actions.set_aliases(conn, PETROV, ["the COURIER"], EXPERT, _clock)
    actions.set_aliases(conn, courier, ["the RIDER"], EXPERT, _clock)
    with pytest.raises(ReviewError, match="would also match"):
        actions.set_aliases(conn, PETROV, ["RIDER"], EXPERT, _clock)


def test_an_event_the_courier_is_refused_when_a_person_has_the_alias_courier(conn):
    actions.set_aliases(conn, PETROV, ["COURIER"], EXPERT, _clock)
    para = _para(conn)
    text = conn.execute("SELECT text FROM govdoc_paragraphs WHERE id = ?", (para,)).fetchone()[0]
    with pytest.raises(ReviewError, match="would also match"):
        actions.add_event(conn, "the COURIER", "2026-03-20", "2026-03-20", para, text, EXPERT)
    assert "courier" in case_events.taken(conn)


def test_the_filler_reads_an_alias_written_without_its_the(conn):
    actions.set_aliases(conn, PETROV, ["the COURIER"], EXPERT, _clock)
    filler = _filler(conn)
    assert filler._person("COURIER") == PETROV
    assert filler._person("THE COURIER") == PETROV
    with pytest.raises(Reject):  # a term in capitals only in capitals (Baker Eval on #209)
        filler._person("the Courier")
    with pytest.raises(Reject):
        filler._person("COURIER VAN")


def test_a_phone_name_matches_with_or_without_the(conn):
    actions.name_device(conn, "dev:item1", ["the SAMSUNG"], EXPERT, _clock)
    filler = _filler(conn)
    assert filler._device("SAMSUNG") == "dev:item1"
    with pytest.raises(Reject):  # a term in capitals only in capitals (Baker Eval on #209)
        filler._device("the samsung")
    with pytest.raises(ReviewError, match="already names"):
        actions.name_device(conn, "dev:item2", ["SAMSUNG"], EXPERT, _clock)
    with pytest.raises(Reject, match="is a phone, not a person"):
        filler._person("SAMSUNG")


# ---------------------------------------------------------------- naming a number


def test_an_expert_names_a_number_and_it_is_logged(conn):
    assert actions.name_account(conn, ALEX, ["the  BURNER", "Burner"], EXPERT, _clock) == [
        "the BURNER",
        "Burner",
    ]
    assert account_names.holders(conn, ALEX) == [ALEX_SMS]
    assert account_names.logged_names(conn) == {ALEX: ["the BURNER", "Burner"]}
    assert _log(conn) == [{"identifier": ALEX, "names": ["the BURNER", "Burner"]}]
    for answer in ("BURNER", "the burner", "Burner"):
        assert account_names.designated(conn, answer) == ALEX
    assert account_names.designated(conn, "BURNER PHONE") is None
    assert audit_log.verify_chain(conn)


def test_the_list_replaces_the_old_one_and_an_empty_list_clears_it(conn):
    actions.name_account(conn, ALEX, ["the BURNER"], EXPERT, _clock)
    actions.name_account(conn, "12125550182", ["TARGET TELEPHONE 2"], EXPERT, _clock)
    assert account_names.logged_names(conn) == {"12125550182": ["TARGET TELEPHONE 2"]}
    assert account_names.designated(conn, "BURNER") is None
    actions.name_account(conn, ALEX, [], EXPERT, _clock)
    assert account_names.logged_names(conn) == {}
    assert len(_log(conn)) == 3


def test_a_whatsapp_id_holds_the_number_it_is_for(conn):
    assert set(account_names.holders(conn, GARAGE)) >= {
        MARC_PHONE,
        "acct:item1:WhatsApp:12125550122@s.whatsapp.net",
    }
    assert account_names.holders(conn, "7001001") == [
        "acct:item1:Telegram:7001001",
        "acct:item2:Telegram:7001001",
    ]


@pytest.mark.parametrize(
    ("names", "why"),
    [
        ([" "], "as the document writes it"),
        (["x" * 81], "as the document writes it"),
        (["--"], "no letter or digit"),
        (["the PETROV"], "Daniel Petrov"),  # a person's surname, with or without "the"
        (["Daniel Petrov"], "Daniel Petrov"),
        (["Item 2"], "already names the phone"),  # a phone's source id
        (["the item2"], "already names the phone"),
        (["7001001"], "itself a number or id"),  # another account's id
        (["(212) 555-0122"], "itself a number or id"),
    ],
)
def test_a_name_the_audit_could_not_keep_apart_is_refused(conn, names, why):
    with pytest.raises(ReviewError, match=why):
        actions.name_account(conn, ALEX, names, EXPERT, _clock)
    assert account_names.logged_names(conn) == {}


def test_a_name_another_alias_event_or_number_is_matched_by_is_refused(conn):
    actions.set_aliases(conn, REYES, ["the COURIER"], EXPERT, _clock)
    with pytest.raises(ReviewError, match="Marcus Reyes"):
        actions.name_account(conn, ALEX, ["COURIER"], EXPERT, _clock)
    actions.name_account(conn, GARAGE, ["the BURNER"], EXPERT, _clock)
    with pytest.raises(ReviewError, match="the number or account"):
        actions.name_account(conn, ALEX, ["BURNER"], EXPERT, _clock)
    # and the other way round: no person, phone or event may take a number's name
    with pytest.raises(ReviewError, match="the number or account"):
        actions.set_aliases(conn, PETROV, ["Burner"], EXPERT, _clock)
    with pytest.raises(ReviewError, match="the number or account"):
        actions.name_device(conn, "dev:item1", ["the burner"], EXPERT, _clock)
    para = _para(conn)
    text = conn.execute("SELECT text FROM govdoc_paragraphs WHERE id = ?", (para,)).fetchone()[0]
    with pytest.raises(ReviewError, match="the number or account"):
        actions.add_event(conn, "BURNER", "2026-03-20", "2026-03-20", para, text, EXPERT)


def test_only_an_expert_names_a_number_the_case_holds(conn):
    with pytest.raises(ReviewError, match="expert"):
        actions.name_account(conn, ALEX, ["the BURNER"], "system")
    with pytest.raises(ReviewError, match="no account in the case holds"):
        actions.name_account(conn, "+1 (720) 555-0186", ["the BURNER"], EXPERT)


def test_a_numbers_name_is_never_a_person_and_links_nothing(conn):
    links = conn.execute("SELECT count(*) FROM identity_links").fetchone()[0]
    persons = conn.execute("SELECT count(*) FROM persons").fetchone()[0]
    actions.name_account(conn, ALEX, ["the BURNER"], EXPERT, _clock)
    assert conn.execute("SELECT count(*) FROM identity_links").fetchone()[0] == links
    assert conn.execute("SELECT count(*) FROM persons").fetchone()[0] == persons
    filler = _filler(conn)
    with pytest.raises(Reject, match="not a person; write it as an account"):
        filler._person("BURNER")
    acc = _Account(as_written="the BURNER", app="SMS")
    assert filler._accounts(acc, ["dev:item1"], "") == {ALEX_SMS}
    with pytest.raises(Reject, match="matches no account"):  # the name never picks the app
        filler._accounts(_Account(as_written="BURNER", app="Telegram"), ["dev:item1"], "")


def test_a_change_to_a_numbers_names_makes_earlier_verdicts_not_current(conn):
    run = {"run_id": "run:x", "started_at_utc": "2026-11-03T19:00:00Z"}
    assert not status.case_changed_after(conn, run)
    actions.name_account(conn, ALEX, ["the BURNER"], EXPERT, _clock)
    assert status.case_changed_after(conn, run)


def test_the_bundle_check_lets_a_numbers_names_change_a_repair():
    assert account_names.ACTION in verify._REPAIR_INPUTS


def test_the_report_lists_each_numbers_name_as_the_experts_statement(conn):
    actions.name_account(conn, ALEX, ["the BURNER"], EXPERT, _clock)
    assert account_names.named_by(conn) == [(ALEX, EXPERT, "2026-11-03T20:00:00Z", ["the BURNER"])]
    text = _limitations(conn, sources(conn))
    assert "Which number or account the document means is an expert statement" in text
    assert "the BURNER" in text and ALEX in text and "says nothing about who used it" in text
    check_report_text(text)


def test_the_command_line_names_a_number(conn, tmp_path, capsys):
    from cli.main import main

    db = conn.execute("PRAGMA database_list").fetchone()[2]
    conn.close()
    argv = ["name-account", "--db", db, "--identifier", ALEX, "--name", "the BURNER"]
    assert main([*argv, "--by", EXPERT]) == 0
    assert "now has the BURNER" in capsys.readouterr().out
    c = connect(db)
    try:
        assert account_names.logged_names(c) == {ALEX: ["the BURNER"]}
    finally:
        c.close()


# ---------------------------------------------------------------- the claim's own words


def test_a_model_answer_naming_the_number_by_its_name_is_checked_on_that_number(conn):
    actions.name_account(conn, GARAGE, ["the BURNER"], EXPERT, _clock)
    text = (
        "At about 7:58 p.m. on March 9, 2026, Item 1 placed a call of about two minutes to the"
        " BURNER."
    )
    prop = P(
        "record_time",
        channels=["call"],
        accounts=[{"as_written": "BURNER", "app": "Phone"}],
        phones=["Item 1"],
        duration={"as_written": "about two minutes"},
        window=W("At about 7:58 p.m. on March 9, 2026", "2026-03-09T19:50", "2026-03-09T20:06"),
    )
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    (a,) = [a for a in assumptions if a.template_id == "record_time"]
    assert a.params.account_ids == (MARC_PHONE,)
    assert _run(conn, a) is CheckOutcome.PASS


def test_code_reads_a_calls_party_by_the_numbers_name(conn):
    # The model named the call without its parties: code reads them from the claim, and "the
    # BURNER" is the number the expert named, on the one app the claim names.
    conn.execute(
        "INSERT INTO calls VALUES ('call:wa:1', 'item1', 'call:wa:1', 'dev:item1', 'WhatsApp',"
        " ?, ?, 'outgoing', '2026-03-09T23:00:00Z', 0, NULL, 60, 0)",
        (f"acct:item1:WhatsApp:{PETROV_WA}", MARC_WA),
    )
    actions.name_account(conn, GARAGE, ["the BURNER"], EXPERT, _clock)
    text = "On March 9, 2026, Item 1 placed a WhatsApp call to the BURNER."
    prop = P(
        "record_time",
        channels=["call", "WhatsApp"],
        phones=["Item 1"],
        window=W("On March 9, 2026", "2026-03-09T00:00", "2026-03-10T00:00"),
    )
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    (a,) = [a for a in assumptions if a.template_id == "record_time"]
    assert a.params.account_ids == (MARC_WA,)
    assert _run(conn, a) is CheckOutcome.PASS
    # without the expert's name, "the BURNER" is no party code reads
    actions.name_account(conn, GARAGE, [], EXPERT, _clock)
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    assert not [a for a in assumptions if a.template_id == "record_time"]


def test_a_count_reads_the_numbers_name_as_that_side(conn):
    actions.name_account(conn, ALEX, ["the BURNER"], EXPERT, _clock)
    text = "On March 25, 2026, on Item 1, PETROV and the BURNER exchanged six text messages."
    prop = P(
        "message_count",
        people=["PETROV"],
        accounts=[{"as_written": "BURNER", "app": "SMS"}],
        channels=["SMS"],
        phones=["Item 1"],
        count={"value": 6},
        window=W("On March 25, 2026", "2026-03-25T00:00", "2026-03-26T00:00"),
    )
    assumptions, filler = build(conn, text, ClaimType.COUNT, [prop])
    (a,) = [a for a in assumptions if a.template_id == "message_count"]
    assert a.params.account_ids == (ALEX_SMS,) and a.params.person_ids == (PETROV,)
    assert _run(conn, a) is CheckOutcome.PASS


def test_a_count_of_what_the_named_number_sent_counts_that_side(conn):
    actions.name_account(conn, ALEX, ["the BURNER"], EXPERT, _clock)
    text = "On March 25, 2026, on Item 1, the BURNER sent PETROV three text messages."
    prop = P(
        "message_count",
        people=["PETROV"],
        accounts=[{"as_written": "BURNER", "app": "SMS"}],
        channels=["SMS"],
        phones=["Item 1"],
        count={"value": 3},
        window=W("On March 25, 2026", "2026-03-25T00:00", "2026-03-26T00:00"),
    )
    assumptions, filler = build(conn, text, ClaimType.COUNT, [prop])
    (a,) = [a for a in assumptions if a.template_id == "message_count"]
    assert a.params.sent_by == (ALEX_SMS,)
    assert _run(conn, a) is CheckOutcome.PASS


def test_no_contact_reads_the_numbers_name_as_the_other_party(conn):
    actions.name_account(conn, ALEX, ["the BURNER"], EXPERT, _clock)
    text = "dev:item1 never communicated with the BURNER."
    props = [P("no_contact", phones=["dev:item1"])]
    assumptions, filler = build(conn, text, ClaimType.ABSENCE, props)
    (a,) = [a for a in assumptions if a.template_id == "no_contact"]
    assert a.params.person_ids == (PETROV,) and a.params.account_ids == (ALEX_SMS,)
    # a name for an id that is no number is no party this reading takes
    actions.name_account(conn, "7001002", ["the RIDER"], EXPERT, _clock)
    text = "dev:item1 never communicated with the RIDER."
    assumptions, filler = build(conn, text, ClaimType.ABSENCE, props)
    assert not [a for a in assumptions if a.template_id == "no_contact"]
    assert any("names an id, not a number" in d.reason for d in filler.drops)


def test_the_testability_step_looks_up_a_numbers_name_as_every_account_holding_it(conn):
    filler = _filler(conn)
    claim = _claim(conn, "On March 9, 2026, PETROV called the BURNER.", ClaimType.COMMUNICATION)
    assert not [x for x in testability.lookups(filler, claim, "") if "BURNER" in x.written]
    actions.name_account(conn, GARAGE, ["the BURNER"], EXPERT, _clock)
    found = [
        (x, aid)
        for x, aid in testability._found(filler, (claim.text, ""))
        if x.written == "the BURNER"
    ]
    assert {x.kind for x, _ in found} == {"account"}
    assert {aid for _, aid in found} == set(account_names.holders(conn, GARAGE))
    assert all("not a person" in x.means and GARAGE in x.means for x, _ in found)
    shown = {x.means for x in testability.lookups(filler, claim, "") if x.written == "the BURNER"}
    assert {m.split(":")[0] for m in shown} >= {"an account on Phone", "an account on SMS"}
    # written without its "the", the name is still looked up
    bare = _claim(conn, "On March 9, 2026, BURNER called PETROV.", ClaimType.COMMUNICATION)
    assert [x for x in testability.lookups(filler, bare, "") if x.written == "BURNER"]


def test_the_testability_step_looks_up_aliases_and_phone_names_without_their_the(conn):
    actions.set_aliases(conn, REYES, ["the COURIER"], EXPERT, _clock)
    actions.name_device(conn, "dev:item1", ["the SAMSUNG"], EXPERT, _clock)
    filler = _filler(conn)
    claim = _claim(conn, "On March 9, 2026, COURIER texted SAMSUNG.", ClaimType.COMMUNICATION)
    got = {(x.kind, x.written) for x in testability.lookups(filler, claim, "")}
    assert {("person", "COURIER"), ("phone", "SAMSUNG")} <= got


# ---------------------------------------------------------------- quoted words and channels


@pytest.mark.parametrize(
    ("text", "template", "channels", "dropped"),
    [
        ("At 9 p.m. VARGA called ODUM.", "record_time", ["call"], True),
        ("At 9 p.m. VARGA spoke by phone with ODUM.", "record_time", ["Call"], True),
        ('At 9 p.m. VARGA called ODUM "on my way".', "record_time", ["call"], False),
        ("At 9 p.m. VARGA called ODUM “on my way”.", "record_time", ["call"], False),
        ("At 9 p.m. VARGA called ODUM 'on my way'.", "record_time", ["call"], False),
        ("At 9 p.m. VARGA texted ODUM.", "record_time", ["SMS"], False),  # a message's words
        ("At 9 p.m. VARGA texted ODUM.", "record_time", [], False),
        ("At 9 p.m. VARGA called ODUM.", "sender", ["call"], False),
        ("At 9 p.m. VARGA called ODUM.", "meaning", ["call"], False),
        # Baker Eval on #209: an apostrophe inside a word quotes nothing; a single-quoted
        # word does
        ("At 9 p.m. VARGA's phone called ODUM.", "record_time", ["call"], True),
        ("At 9 p.m. VARGA’s phone called ODUM.", "record_time", ["call"], True),
        ("At 9 p.m. VARGA called ODUM about 'the deal'.", "record_time", ["call"], False),
        ("At 9 p.m. VARGA called ODUM about ‘the deal’.", "record_time", ["call"], False),
    ],
)
def test_quoted_words_are_dropped_only_from_a_calls_time_range_when_the_claim_quotes_none(
    text, template, channels, dropped
):
    p = _ProposalOut.model_validate(P(template, quoted_text="VARGA called ODUM", channels=channels))
    kept, note = unquoted_time_quote(text, p)
    assert (note is not None) is dropped
    assert kept.quoted_text == ("" if dropped else "VARGA called ODUM")
    if dropped:
        assert "dropped" in note and "VARGA called ODUM" in note


def test_a_dropped_quote_is_logged_and_the_time_range_is_kept(conn):
    text = (
        "At about 7:58 p.m. on March 9, 2026, Item 1 placed a call of about two minutes to"
        " +1 (212) 555-0122."
    )
    prop = P(
        "record_time",
        channels=["call"],
        accounts=[{"as_written": "+1 (212) 555-0122", "app": "Phone"}],
        phones=["Item 1"],
        quoted_text="Item 1 placed a call of about two minutes",
        duration={"as_written": "about two minutes"},
        window=W("At about 7:58 p.m. on March 9, 2026", "2026-03-09T19:50", "2026-03-09T20:06"),
    )
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    (a,) = [a for a in assumptions if a.template_id == "record_time"]
    assert not a.params.quoted_text
    assert any("dropped: the claim quotes no words" in d.reason for d in filler.drops)
    assert _run(conn, a) is CheckOutcome.PASS


def test_a_dropped_quote_never_leaves_a_sender_without_its_anchor(conn):
    # The validation thread's condition. A sender rests on its words: words the claim does
    # not quote are refused, never kept or dropped, so no sender is made from this answer, and
    # a message's time range keeps needing them too.
    text = "On March 25, 2026, PETROV texted the tickets to +1 (212) 555-0182."
    sender = P("sender", people=["PETROV"], quoted_text="got the tickets", channels=["SMS"])
    timed = P(
        "record_time",
        people=["PETROV"],
        quoted_text="got the tickets",
        channels=["SMS"],
        window=W("On March 25, 2026", "2026-03-25T00:00", "2026-03-26T00:00"),
    )
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [sender, timed])
    assert assumptions == []
    reasons = [d.reason for d in filler.drops]
    assert "quoted_text is not written in the claim" in reasons
    assert not any("dropped" in r for r in reasons)


def test_texting_names_sms_and_speaking_by_phone_names_a_call(conn):
    filler = _filler(conn)
    assert filler._channels("On March 25, 2026, PETROV was texting Alex.", ["SMS"]) == ["SMS"]
    got = filler._channels("PETROV and REYES spoke by phone for eight minutes.", ["call"])
    assert got == ["call"]


def test_code_reads_a_plainly_stated_time_instead_of_the_models(conn):
    # "at about 7:58 p.m." is 7:50 to 8:06 (stated_windows). A model's 7:58 to 8:10 has both
    # ends within check_window's 15 minutes, but code's reading of the words is the range.
    text = (
        "At about 7:58 p.m. on March 9, 2026, Item 1 placed a call of about two minutes to"
        " +1 (212) 555-0122."
    )
    prop = P(
        "record_time",
        channels=["call"],
        accounts=[{"as_written": "+1 (212) 555-0122", "app": "Phone"}],
        phones=["Item 1"],
        duration={"as_written": "about two minutes"},
        window=W("At about 7:58 p.m. on March 9, 2026", "2026-03-09T19:58", "2026-03-09T20:10"),
    )
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    (a,) = [a for a in assumptions if a.template_id == "record_time"]
    w = a.params.window
    end = w.end_utc + timedelta(microseconds=1)  # stored as the last instant inside
    local = (w.start_utc.astimezone(ZoneInfo(w.tz)), end.astimezone(ZoneInfo(w.tz)))
    assert [t.strftime("%H:%M") for t in local] == ["19:50", "20:06"]
    assert w.raw == "At about 7:58 p.m. on March 9, 2026"
    # a range its words leave open keeps the model's checked times
    text = "On March 9, 2026, after 7:58 p.m., Item 1 placed a call to +1 (212) 555-0122."
    prop["window"] = W("after 7:58 p.m.", "2026-03-09T19:58", "2026-03-10T00:00")
    prop["duration"] = None
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    for a in assumptions:
        if a.template_id == "record_time":
            w = a.params.window
            assert w.start_utc.astimezone(ZoneInfo(w.tz)).strftime("%H:%M") == "19:58"


# ---------------------------------------------------------------- near misses (Baker Eval on #209)


def _local(w) -> list[str]:  # noqa: ANN001 - a TimeWindow
    end = w.end_utc + timedelta(microseconds=1)  # stored as the last instant inside
    return [t.astimezone(ZoneInfo(w.tz)).strftime("%H:%M") for t in (w.start_utc, end)]


def test_a_call_just_outside_about_a_time_is_left_open_never_contradicted(conn):
    # The call is at 7:58:02 p.m. "At about 7:49 p.m." is 7:41 up to 7:57 in code's reading
    # (8 minutes either side, the signed case01 sheet's convention). The model's 7:49 to 8:00
    # passed check_window and held the call; code's range does not. A call is picked by its
    # parties only, so one outside the window may be another call: never a fail. The claim
    # stays unproven, and the check lists the call outside the window for the expert.
    for said, model_end, want in (
        ("At about 7:49 p.m. on March 9, 2026", "2026-03-09T20:00", ["19:41", "19:57"]),
        ("At 7:49 p.m. on March 9, 2026", "2026-03-09T19:50", ["19:49", "19:50"]),
    ):
        text = f"{said}, Item 1 placed a call to +1 (212) 555-0122."
        prop = P(
            "record_time",
            channels=["call"],
            accounts=[{"as_written": "+1 (212) 555-0122", "app": "Phone"}],
            phones=["Item 1"],
            window=W(said, "2026-03-09T19:49", model_end),
        )
        assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
        (a,) = [a for a in assumptions if a.template_id == "record_time"]
        assert _local(a.params.window) == want
        result = CHECKS["time"].run(a, conn)
        assert result.outcome is CheckOutcome.INCONCLUSIVE
        assert result.detail.startswith("Outside the window: ")
        assert "call:item1:Call Log!9 at 2026-03-09 19:58:02 EDT" in result.detail
        assert "may be other calls" in result.detail


def test_a_message_just_outside_about_a_time_fails_on_code_reading_not_the_models(conn):
    # "need a quote for brake pads" was sent at 11:41:15 a.m. "At about 11:32 a.m." is 11:24
    # up to 11:40 in code's reading. The model's 11:32 to 11:47 passed check_window (each end
    # within 15 minutes of 11:32) and held the message; under code's reading a message picked
    # by its words, every copy outside the window, fails, and rule 1a contradicts the claim.
    # Before filler 5 the outcome was the model's arithmetic: a model's 11:24 to 11:40 failed
    # the same message. Now it is the one reading the case01 sheet signs, every time.
    said = "At about 11:32 a.m. on February 16, 2026"
    text = f'{said}, PETROV texted "need a quote for brake pads".'
    prop = P(
        "record_time",
        people=["PETROV"],
        channels=["SMS"],
        quoted_text="need a quote for brake pads",
        window=W(said, "2026-02-16T11:32", "2026-02-16T11:47"),
    )
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    (a,) = [a for a in assumptions if a.template_id == "record_time"]
    assert _local(a.params.window) == ["11:24", "11:40"]
    result = CHECKS["time"].run(a, conn)
    assert result.outcome is CheckOutcome.FAIL
    assert "Outside the window: msg:item1:Chats!188" in result.detail


def test_a_defined_term_in_lower_case_is_never_read_as_the_person_number_or_phone(conn):
    # "the courier dropped off the package" is the ordinary noun, not the alias "the COURIER";
    # "a burner phone" is not the number named "the BURNER", nor "the samsung" the phone named
    # "the SAMSUNG". Code never reads them as the name, and where it would have to choose, it
    # refuses: the words may be either.
    actions.set_aliases(conn, PETROV, ["the COURIER"], EXPERT, _clock)
    actions.name_account(conn, GARAGE, ["the BURNER"], EXPERT, _clock)
    actions.name_device(conn, "dev:item2", ["the SAMSUNG"], EXPERT, _clock)
    filler = _filler(conn)
    text = "On March 9, 2026, the courier dropped off the package and used a burner phone."
    for answer in ("the courier", "courier", "Courier"):
        with pytest.raises(Reject, match="matches no person"):
            filler._person(answer)
    assert account_names.designated(conn, "burner") is None
    assert account_names.written(conn, text) == []
    with pytest.raises(Reject, match="in lower case"):
        filler._person_spans(text)
    with pytest.raises(Reject, match="in lower case"):
        filler._numbers_named(text)
    with pytest.raises(Reject, match="in lower case"):
        filler._phone_spans("PETROV used the samsung.")
    with pytest.raises(Reject, match="matches 0 devices"):
        filler._device("the samsung")
    claim = _claim(conn, text, ClaimType.COMMUNICATION)
    assert not [x for x in testability.lookups(filler, claim, "") if x.kind != "account"]
    assert not [x for x in testability.lookups(filler, claim, "") if "expert named" in x.means]
    # code reading a call's parties from "a WhatsApp call to the burner" refuses
    call = "On March 9, 2026, Item 1 placed a WhatsApp call to the burner."
    prop = P(
        "record_time",
        channels=["call", "WhatsApp"],
        phones=["Item 1"],
        window=W("On March 9, 2026", "2026-03-09T00:00", "2026-03-10T00:00"),
    )
    assumptions, filler = build(conn, call, ClaimType.COMMUNICATION, [prop])
    assert not [a for a in assumptions if a.template_id == "record_time"]
    assert any("in lower case" in d.reason for d in filler.drops)
    # written in capitals, each is the name
    filler = _filler(conn)
    assert filler._person("the COURIER") == PETROV
    assert filler._device("the SAMSUNG") == "dev:item2"
    assert [i for i, *_ in account_names.written(conn, "a call to the BURNER")] == [GARAGE]
    # a name with a digit is no ordinary word, and is read in any case (Codex on #181)
    actions.set_aliases(conn, PETROV, ["SUBJECT-1"], EXPERT, _clock)
    assert _filler(conn)._person("Subject 1") == PETROV


def test_speaking_by_phone_about_messages_names_a_call_never_a_text(conn):
    # Baker Eval on #209: "spoke by phone" names a call; "about the messages" names no app, so
    # the claim is never read as texts. A call's time range searches calls only.
    filler = _filler(conn)
    text = "On March 9, 2026, PETROV and Marc spoke by phone about the messages."
    assert filler._channels(text, ["call"]) == ["call"]
    with pytest.raises(Reject, match="does not name the channel"):
        filler._channels(text, ["SMS"])


# ---------------------------------------------------------------- Codex on #209


@pytest.mark.parametrize("identifier", [GARAGE, "12125550122@s.whatsapp.net", "12125550122"])
def test_a_number_named_as_any_app_writes_it_finds_the_phone_apps_account(conn, identifier):
    # The expert may name the number as WhatsApp writes it, or as bare digits: it is still
    # that number on the phone app.
    actions.name_account(conn, identifier, ["the BURNER"], EXPERT, _clock)
    text = (
        "At about 7:58 p.m. on March 9, 2026, Item 1 placed a call of about two minutes to the"
        " BURNER."
    )
    prop = P(
        "record_time",
        channels=["call"],
        accounts=[{"as_written": "BURNER", "app": "Phone"}],
        phones=["Item 1"],
        duration={"as_written": "about two minutes"},
        window=W("At about 7:58 p.m. on March 9, 2026", "2026-03-09T19:50", "2026-03-09T20:06"),
    )
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [prop])
    (a,) = [a for a in assumptions if a.template_id == "record_time"]
    assert a.params.account_ids == (MARC_PHONE,)
    assert _run(conn, a) is CheckOutcome.PASS


def test_digits_only_an_apps_user_id_holds_are_no_phone_number(conn):
    conn.execute(
        "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier)"
        " VALUES ('acct:item1:Telegram:7185550199', 'item1', 'Contacts!99', 'dev:item1',"
        " 'Telegram', '7185550199')"
    )
    filler = _filler(conn)
    assert filler._named_number("7185550199") is None  # a user id, not (718) 555-0199
    assert filler._named_number("12125550122") == "12125550122"  # held by phone accounts
    assert filler._named_number("12125550122@s.whatsapp.net") == "12125550122"


def test_a_person_named_like_a_numbers_name_is_refused_and_never_picked(conn):
    actions.name_account(conn, GARAGE, ["the BURNER"], EXPERT, _clock)
    with pytest.raises(ReviewError, match="would also match the number or account"):
        actions.add_person(conn, "Burner", EXPERT, _clock)
    # a person entered before this check: neither reading is picked
    conn.execute(
        "INSERT INTO persons (id, name, created_by) VALUES ('person:burner', 'Burner', ?)",
        (EXPERT,),
    )
    filler = _filler(conn)
    with pytest.raises(Reject, match="names both a person"):
        filler._person("BURNER")
    with pytest.raises(Reject, match="names both a person"):
        filler._accounts(_Account(as_written="BURNER", app="Phone"), ["dev:item1"], "")


def test_the_claims_own_words_read_an_alias_without_its_the(conn):
    # Codex on #209: "COURIER sent ..." names the alias "the COURIER" in the claim, as the
    # model's answer "COURIER" does, so the sender of a count is read.
    actions.set_aliases(conn, PETROV, ["the COURIER"], EXPERT, _clock)
    filler = _filler(conn)
    text = "COURIER called Marc; the COURIER's phone"
    assert [text[s:e] for s, e in sorted(filler._person_spans(text)[PETROV])] == [
        "COURIER",
        "the COURIER",
    ]
    with pytest.raises(Reject, match="in lower case"):
        filler._person_spans("a courier called Marc")
    text = "On March 25, 2026, on Item 1, COURIER sent +1 (212) 555-0182 three text messages."
    prop = P(
        "message_count",
        people=["COURIER"],
        accounts=[{"as_written": "+1 (212) 555-0182", "app": "SMS"}],
        channels=["SMS"],
        phones=["Item 1"],
        count={"value": 3},
        window=W("On March 25, 2026", "2026-03-25T00:00", "2026-03-26T00:00"),
    )
    assumptions, filler = build(conn, text, ClaimType.COUNT, [prop])
    (a,) = [a for a in assumptions if a.template_id == "message_count"]
    assert a.params.sent_by == (PETROV,), filler.drops


# ---------------------------------------------------------------- Codex on #210


@pytest.mark.parametrize("identifier", ["12125550182", "12125550122@s.whatsapp.net"])
def test_no_contact_reads_a_number_named_by_its_whatsapp_id_or_bare_digits(conn, identifier):
    # The expert may enter the number as bare digits or as WhatsApp writes it; "never
    # communicated with the BURNER" still reads it as that number, not as an id.
    actions.name_account(conn, identifier, ["the BURNER"], EXPERT, _clock)
    text = "dev:item1 never communicated with the BURNER."
    assumptions, filler = build(
        conn, text, ClaimType.ABSENCE, [P("no_contact", phones=["dev:item1"])]
    )
    (a,) = [a for a in assumptions if a.template_id == "no_contact"]
    digits = filler._named_number(identifier)
    assert a.params.person_ids == (PETROV,) and a.params.account_ids
    assert all(digits in filler.data.accounts[x].identifier for x in a.params.account_ids)


def test_a_phone_name_is_read_in_the_claims_words_without_its_the(conn):
    actions.name_device(conn, "dev:item1", ["the SAMSUNG"], EXPERT, _clock)
    filler = _filler(conn)
    assert filler._written_phones("SAMSUNG exchanged SMS messages with REYES.") == {"dev:item1"}
    # "the SAMSUNG" is one place, not two
    assert filler._phone_spans("the SAMSUNG exchanged SMS messages.") == [("dev:item1", 0, 11)]
    with pytest.raises(Reject, match="lower case"):
        filler._written_phones("a samsung exchanged SMS messages with REYES.")
    # a count scoped to the other phone leaves the SAMSUNG untested
    with pytest.raises(Reject, match="writes a phone the count does not search"):
        filler._phones_kept(
            "SAMSUNG exchanged 3 messages with REYES.", {"device_ids": ["dev:item2"]}
        )


def test_ids_that_differ_only_in_punctuation_are_two_accounts(conn):
    for i, ident in enumerate(["alice.smith@example.com", "alice-smith@example.com"]):
        conn.execute(
            "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier)"
            f" VALUES ('acct:item1:Email:{i}', 'item1', 'Emails!{i}', 'dev:item1', 'Email', ?)",
            (ident,),
        )
    assert account_names.holders(conn, "alice.smith@example.com") == ["acct:item1:Email:0"]
    assert account_names.holders(conn, "Alice.Smith@Example.com") == ["acct:item1:Email:0"]
    assert account_names.holders(conn, "alice-smith@example.com") == ["acct:item1:Email:1"]
    actions.name_account(conn, "alice.smith@example.com", ["the MAILBOX"], EXPERT, _clock)
    actions.name_account(conn, "alice-smith@example.com", ["the DROPBOX"], EXPERT, _clock)
    assert account_names.logged_names(conn) == {
        "alice.smith@example.com": ["the MAILBOX"],
        "alice-smith@example.com": ["the DROPBOX"],
    }


# ---------------------------------------------------------------- Codex on #211


def test_a_lower_case_phone_name_in_code_fills_leaves_the_claim_unproven_and_goes_on(conn):
    # The model left the sender to code; code reads the claim's phone, and "the samsung" may be
    # the phone the expert named "the SAMSUNG" or any Samsung. The audit must not stop: the
    # claim keeps nothing and the reason is recorded, in the first pass and in a repair.
    actions.name_device(conn, "dev:item1", ["the SAMSUNG"], EXPERT, _clock)
    text = 'On March 9, 2026, PETROV texted REYES "see you at 8" on the samsung.'
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [])
    assert assumptions == []
    assert any("could not read the claim's own words" in d.reason for d in filler.drops)
    assert any("in lower case" in d.reason for d in filler.drops)
    claim = _claim(conn, text, ClaimType.COMMUNICATION)
    outcome, reasons, _, kept = testability.check_answer(
        _filler(conn), claim, [], None, testability.CLAIM_CHECK
    )
    assert outcome == "refused" and kept == []
    assert any("could not read the claim's own words" in r for r in reasons)
    # written in capitals, code fills the sender on that phone
    text = 'On March 9, 2026, PETROV texted REYES "see you at 8" on the SAMSUNG.'
    assumptions, filler = build(conn, text, ClaimType.COMMUNICATION, [])
    assert not any("could not read" in d.reason for d in filler.drops)


@pytest.mark.parametrize(
    ("text", "window", "first", "last"),
    [
        # "March 9, 2026" copied from "between March 9, 2026 and March 12, 2026": read as
        # written it is one day, and the absence would be searched on one day of four
        (
            "Between March 9, 2026 and March 12, 2026, PETROV and REYES had no contact.",
            W("March 9, 2026", "2026-03-09T00:00", "2026-03-13T00:00"),
            datetime(2026, 3, 9),
            datetime(2026, 3, 13),
        ),
        # "first ... on March 12" leaves the start open: never only March 12
        (
            "PETROV first made contact with @northstar on March 12, 2026.",
            W(
                "first made contact with @northstar on March 12, 2026",
                "2026-01-01T00:00",
                "2026-03-12T00:00",
            ),
            datetime(2026, 1, 1),
            datetime(2026, 3, 12),
        ),
        # within 15 minutes, code's reading of a plainly stated time wins
        (
            "At about 11:50 p.m. on March 9, 2026, PETROV and REYES had no contact.",
            W("At about 11:50 p.m. on March 9, 2026", "2026-03-09T23:50", "2026-03-10T00:00"),
            datetime(2026, 3, 9, 23, 42),
            datetime(2026, 3, 9, 23, 58),
        ),
    ],
)
def test_window_words_that_are_part_of_the_claims_range_never_shorten_it(
    conn, text, window, first, last
):
    # Code's reading of the window's own words replaces the model's range only within the 15
    # minutes check_window allows (Codex on #211).
    ny = ZoneInfo("America/New_York")
    got = _filler(conn)._window(text, "", _Window.model_validate(window), [], "no_contact")
    assert got.start_utc == first.replace(tzinfo=ny).astimezone(UTC)
    assert got.end_utc == last.replace(tzinfo=ny).astimezone(UTC) - timedelta(microseconds=1)


@pytest.fixture
def call_log(conn):
    # The phone's call log stores one number two ways, as a UFDR from two databases does.
    for aid, ident in [("acct:t:log1", "+12125550199"), ("acct:t:log2", "2125550199")]:
        conn.execute(
            "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier)"
            " VALUES (?, 'item1', 'x', NULL, 'unknown', ?)",
            (aid, ident),
        )
    return conn


@pytest.mark.parametrize(
    "identifier", ["+1 (212) 555-0199", "12125550199", "12125550199@s.whatsapp.net"]
)
def test_a_call_log_call_reads_a_number_named_by_bare_digits_or_whatsapp_id(call_log, identifier):
    # No app named and the other party a number the expert named: the phone's call log, with
    # the number whichever way the expert entered it.
    actions.name_account(call_log, identifier, ["the BURNER"], EXPERT, _clock)
    text = (
        "On March 12, 2026, at approximately 9:00 p.m., dev:item1 placed an outgoing telephone"
        " call to the BURNER."
    )
    assumptions, filler = build(
        call_log, text, ClaimType.COMMUNICATION, [P("record_time", channels=["call"])]
    )
    (t,) = [a.params for a in assumptions if a.template_id == "record_time"]
    assert t.account_ids == ("acct:t:log1", "acct:t:log2"), filler.drops
    assert t.channels == ("call", "unknown")


def test_a_user_ids_digits_are_never_a_number_and_two_ids_stay_two(call_log):
    for i in ["7185550199", "17185550199"]:
        call_log.execute(
            "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier)"
            f" VALUES ('acct:item1:Telegram:{i}', 'item1', 'Contacts!{i}', 'dev:item1',"
            " 'Telegram', ?)",
            (i,),
        )
    holders = account_names.holders
    assert holders(call_log, "7185550199") == ["acct:item1:Telegram:7185550199"]
    assert holders(call_log, "17185550199") == ["acct:item1:Telegram:17185550199"]
    assert holders(call_log, "+1 (718) 555-0199") == []  # a number, not a user id
    # bare digits on the call log are the number, however the expert writes it
    for written in ("+1 (212) 555-0199", "12125550199", "2125550199"):
        assert {"acct:t:log1", "acct:t:log2"} <= set(holders(call_log, written)), written
    actions.name_account(call_log, "7185550199", ["the BROKER"], EXPERT, _clock)
    actions.name_account(call_log, "17185550199", ["the COURIER"], EXPERT, _clock)
    assert account_names.logged_names(call_log) == {
        "7185550199": ["the BROKER"],
        "17185550199": ["the COURIER"],
    }
    filler = _filler(call_log)
    assert filler._named_spans("a call to the BROKER", "acct:item1:Telegram:7185550199")
    assert not filler._named_spans("a call to the BROKER", "acct:item1:Telegram:17185550199")
