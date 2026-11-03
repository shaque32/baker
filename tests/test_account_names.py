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
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit import case_events, testability
from core.audit._llm_json import prompt_body
from core.audit.assumption_filler import (
    LocalAssumptionFiller,
    Reject,
    _Account,
    _ProposalOut,
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
        ("the COURIER", "the courier", True),
        ("COURIER", "the COURIER", True),
        ("The Courier", "COURIER", True),
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
    assert filler._person("the Courier") == PETROV
    with pytest.raises(Reject):
        filler._person("COURIER VAN")


def test_a_phone_name_matches_with_or_without_the(conn):
    actions.name_device(conn, "dev:item1", ["the SAMSUNG"], EXPERT, _clock)
    filler = _filler(conn)
    assert filler._device("SAMSUNG") == "dev:item1"
    assert filler._device("the samsung") == "dev:item1"
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
    assert "not a person" in found[0][0].means


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
