"""The assumption filler on synthetic case01, with a scripted fake model.

The fake answers what a good model should, and the tests check that code turns those words
into the parameters the check tests use (tests/checks/test_case01.py), that the checks then
find what they find there, and that wrong or unsupported values are dropped.
"""

import json
import re
import sqlite3
from datetime import datetime as D
from pathlib import Path

import pytest

from core.audit._llm_json import prompt_body
from core.audit.assumption_filler import (
    LocalAssumptionFiller,
    Reject,
    _ProposalOut,
    check_window,
    count_op,
    date_mentions,
)
from core.audit.assumptions import TEMPLATES, TemplateAssumptionBuilder
from core.audit.checks import CHECKS
from core.contracts import CheckOutcome, Claim, ClaimStatus, ClaimType, ModelCallOutcome
from eval.synthetic.generate import generate
from tests.checks.helpers import stipulate
from tests.fake_model import FakeModel

ROOT = Path(__file__).parents[1]
DRAFT = prompt_body((ROOT / "docs/prompts/assumptions.md").read_text("utf-8"))
GOLD = {
    d["claim_id"]: d
    for d in map(
        json.loads, (ROOT / "eval/gold/case01/gold.jsonl").read_text(encoding="utf-8").splitlines()
    )
}
PETROV, REYES = "person:petrov", "person:reyes"
NORTHSTAR = ["acct:item1:Telegram:5551234", "acct:item2:Telegram:5551234"]
MARC_0122 = ["acct:item1:Phone:+12125550122"]


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    db = out / "case01.db"
    generate(out, db)
    c = sqlite3.connect(db)
    stipulate(c, PETROV, "Daniel Petrov", "dev:item1")
    stipulate(c, REYES, "Marcus Reyes", "dev:item2")
    c.execute("PRAGMA foreign_keys = OFF")
    affidavit = (ROOT / "eval/synthetic/case01/affidavit_draft.md").read_text("utf-8")
    for label, text in re.findall(r"^(\d+)\. (.+)$", affidavit, re.M):
        c.execute(
            "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
            " char_end, text) VALUES (?, 'gd', 1, ?, ?, 0, ?, ?)",
            (f"para:{label}", int(label), label, len(text), text),
        )
    yield c
    c.close()


def claim(cid: str) -> Claim:
    g = GOLD[cid]
    return Claim(
        id=cid,
        paragraph_id=f"para:{g['para_no']}",
        text=g["text"],
        claim_type=ClaimType(g["claim_type"]),
        status=ClaimStatus.ACCEPTED,
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


def W(as_written: str, start: str, end: str, zone: str = "phone") -> dict:  # noqa: N802
    return {"as_written": as_written, "start": start, "end": end, "zone": zone}


MARC = {"as_written": "+1 (212) 555-0122", "app": "Phone"}
DP_GARAGE = {"as_written": "dp_garage", "app": "Instagram"}

# What a good model answers for each claim the check tests cover.
GOOD = {
    "C01": [P("contact_entry", phones=["Item 1"], quoted_text="Marc Garage", accounts=[MARC])],
    "C02": [
        P("same_account", handles=["@alex92", "@northstar"], channels=["Telegram"]),
        P(
            "event",
            people=["PETROV"],
            channels=["Telegram"],
            phones=["Item 1"],
            window=W(
                "Between February 20 and March 28, 2026", "2026-02-20T00:00", "2026-03-29T00:00"
            ),
        ),
    ],
    "C03": [
        P(
            "message_count",
            phones=["Item 1"],
            people=["PETROV"],
            handles=["@northstar"],
            channels=["Telegram"],
            count={"value": 13},
            window=W(
                "From March 10 through March 31, 2026", "2026-03-10T00:00", "2026-04-01T00:00"
            ),
        )
    ],
    "C04": [
        P(
            "no_contact",
            people=["PETROV"],
            handles=["@northstar"],
            window=W(
                "first made contact with @northstar on March 12, 2026",
                "2026-01-01T00:00",
                "2026-03-12T00:00",
            ),
        )
    ],
    "C05": [
        P("sender", people=["PETROV"], quoted_text="need 2 more by friday"),
        P(
            "record_time",
            people=["PETROV"],
            quoted_text="need 2 more by friday",
            window=W("On March 12, 2026", "2026-03-12T00:00", "2026-03-13T00:00"),
        ),
    ],
    "C09": [
        P(
            "record_time",
            channels=["call"],
            people=["PETROV"],
            accounts=[MARC],
            phones=["Item 1"],
            duration={"as_written": "about two minutes"},
            window=W("At about 7:58 p.m. on March 9, 2026", "2026-03-09T19:50", "2026-03-09T20:06"),
        )
    ],
    "C10": [
        P(
            "record_time",
            people=["PETROV", "REYES"],
            quoted_text="its done",
            window=W("At 2:31 a.m. on March 5, 2026", "2026-03-05T02:31", "2026-03-05T02:32"),
        )
    ],
    "C11": [
        P(
            "record_time",
            people=["PETROV"],
            quoted_text="move it tonight",
            window=W(
                "At 10:05 p.m. on March 14, 2026, REYES received a phone call warning him "
                "about police activity at his shop, and after that call",
                "2026-03-14T22:05",
                "2026-03-15T00:00",
            ),
        )
    ],
    "C14": [
        P(
            "no_contact",
            people=["PETROV", "REYES"],
            window=W("between March 20 and March 23, 2026", "2026-03-20T00:00", "2026-03-24T00:00"),
        )
    ],
    "C16": [
        P("sender", accounts=[DP_GARAGE], quoted_text="got the money, come get it"),
        P(
            "record_time",
            accounts=[DP_GARAGE],
            quoted_text="got the money, come get it",
            window=W("On March 18, 2026", "2026-03-18T00:00", "2026-03-19T00:00"),
        ),
    ],
}

# The outcome tests/checks/test_case01.py pins for each claim's checks.
EXPECTED = {
    "C01": [CheckOutcome.PASS],
    "C02": [CheckOutcome.PASS],
    "C03": [CheckOutcome.PASS],
    "C04": [CheckOutcome.FAIL],
    "C05": [CheckOutcome.PASS, CheckOutcome.PASS],
    "C09": [CheckOutcome.PASS],
    "C10": [CheckOutcome.FAIL],
    "C11": [CheckOutcome.FAIL],
    "C14": [CheckOutcome.FAIL],
    "C16": [CheckOutcome.PASS, CheckOutcome.PASS],
}


def by_claim(answers: dict[str, list[dict]]):
    def reply(prompt: str) -> str:
        for cid, props in answers.items():
            if f"[CLAIM START]\n{GOLD[cid]['text']}\n[CLAIM END]" in prompt:
                return json.dumps({"assumptions": props})
        return json.dumps({"assumptions": []})

    return reply


def build(conn, cid: str, answers: dict[str, list[dict]] | None = None):
    filler = LocalAssumptionFiller(FakeModel(by_claim(answers or GOOD)), conn, template=DRAFT)
    builder = TemplateAssumptionBuilder(filler)
    return builder.build(claim(cid)), filler, builder


@pytest.mark.parametrize("cid", sorted(GOOD))
def test_good_answers_become_checkable_assumptions(conn, cid):
    assumptions, filler, builder = build(conn, cid)
    assert not filler.drops, filler.drops
    assert not builder.rejected, builder.rejected
    assert len(assumptions) == len(GOOD[cid])
    outcomes = []
    for a in assumptions:
        assert a.is_core
        for name in TEMPLATES[a.template_id].checks:  # event, meaning, role: stance only
            outcomes.append(CHECKS[name].run(a, conn).outcome)
    assert sorted(outcomes) == sorted(EXPECTED[cid])


def test_parameters_match_the_check_tests(conn):
    (c01,) = build(conn, "C01")[0]
    assert c01.params.device_ids == ("dev:item1",)
    assert c01.params.account_ids == tuple(MARC_0122)
    (c03,) = build(conn, "C03")[0]
    assert c03.params.handles == ("@northstar",) and c03.params.account_ids == ()
    assert c03.params.person_ids == (PETROV,)
    assert c03.params.channels == ("Telegram",)
    assert (c03.params.expected_count, c03.params.count_op) == (13, "eq")
    assert c03.params.window.tz == "America/New_York"
    assert c03.params.window.raw == "From March 10 through March 31, 2026"
    c02 = {a.template_id: a for a in build(conn, "C02")[0]}
    assert c02["same_account"].params.handles == ("@alex92", "@northstar")
    (c09,) = build(conn, "C09")[0]
    assert c09.params.account_ids == tuple(MARC_0122)
    assert c09.params.person_ids == (PETROV,)  # named in the paragraph, not the claim
    assert c09.params.duration_s == (90, 150)


def test_prompt_shows_only_allowed_templates_and_marks_data(conn):
    _, filler, _ = build(conn, "C14")
    prompt = filler.recorder.calls[0].prompt
    assert "- no_contact:" in prompt and "- same_account:" not in prompt
    assert "[PARAGRAPH START]\nPETROV and REYES had no contact" in prompt
    assert filler.recorder.calls[0].outcome is ModelCallOutcome.OK


def _one(cid: str, **change) -> dict[str, list[dict]]:
    """The good answer for the claim, with the same change made to every proposal."""
    return {cid: [{**p, **change} for p in GOOD[cid]]}


C14_RAW = "between March 20 and March 23, 2026"
BAD = [
    pytest.param("C14", {"people": ["PETROV", "SOKOLOV"]}, "not written", id="name-not-in-text"),
    pytest.param("C14", {"people": ["Petrov"]}, "not written", id="name-not-verbatim"),
    pytest.param("C14", {"channels": ["WhatsApp"]}, "does not name the channel", id="narrowed"),
    pytest.param("C14", {"channels": ["Signal"]}, "not an app", id="unknown-app"),
    pytest.param(
        "C03",
        {"count": {"value": 10}},
        "not written in the claim as a number",
        id="count-is-another-number",
    ),
    pytest.param("C03", {"phones": ["Item 3"]}, "not written", id="phone-not-in-text"),
    pytest.param(
        "C09",
        {"accounts": [{"as_written": "+1 (212) 555-0122", "app": "WhatsApp"}]},
        "matches no account",
        id="wrong-app",
    ),
    pytest.param(
        "C16",
        {"accounts": [{"as_written": "dp_garage", "app": "Telegram"}]},
        "matches no account",
        id="account-on-wrong-app",
    ),
    pytest.param("C14", {"template_id": "same_account"}, "not allowed", id="template-not-allowed"),
    pytest.param("C01", {"handles": ["Marc Garage"]}, "does not take handles", id="handle-refused"),
    pytest.param(
        "C09",
        {"duration": {"as_written": "about 2 minutes"}},
        "not written",
        id="duration-not-verbatim",
    ),
]


# The model's range is refused, so code uses the range the claim plainly states instead
# (stated_windows): the same assumption as the good answer, never a guess at the model's.
BAD_WINDOWS = [
    pytest.param(
        "C14",
        {
            "window": W(
                "between March 20 and March 23, 2026", "2026-03-19T00:00", "2026-03-24T00:00"
            )
        },
        id="window-start-not-stated",
    ),
    pytest.param(
        "C14",
        {
            "window": W(
                "between March 20 and March 23, 2026", "2026-03-20T00:00", "2026-03-26T00:00"
            )
        },
        id="window-end-not-stated",
    ),
    pytest.param(
        "C14",
        {
            "window": W(
                "between March 20 and March 23, 2026",
                "2026-03-20T00:00",
                "2026-03-24T00:00",
                zone="UTC",
            )
        },
        id="utc-not-written",
    ),
    pytest.param(
        "C14",
        {"window": W("between March 20 and 23", "2026-03-20T00:00", "2026-03-24T00:00")},
        id="window-words-invented",
    ),
    pytest.param(
        "C10",
        {"window": W("At 2:31 a.m. on March 5, 2026", "2026-03-05T07:31", "2026-03-05T07:32")},
        id="utc-time-as-local",
    ),
]


@pytest.mark.parametrize(("cid", "change"), BAD_WINDOWS)
def test_a_refused_model_range_is_replaced_by_the_range_the_claim_states(conn, cid, change):
    good = {a.template_id: a for a in build(conn, cid)[0]}
    repaired = {a.template_id: a for a in build(conn, cid, _one(cid, **change))[0]}
    assert repaired.keys() == good.keys()
    for tid, a in repaired.items():
        assert a.params.window == good[tid].params.window, tid
        assert a.params == good[tid].params


def test_a_model_range_on_a_day_the_claim_does_not_state_is_still_dropped(conn):
    # C07 states two dates (March 6 and March 9); a range on neither day matches no stated one.
    answers = {
        "C07": [
            P(
                "record_time",
                people=["PETROV", "REYES"],
                channels=["SMS"],
                window=W("On March 6, 2026", "2026-03-08T00:00", "2026-03-09T00:00"),
            )
        ]
    }
    assumptions, filler, _ = build(conn, "C07", answers)
    assert assumptions == []
    assert any("not one the claim plainly states" in d.reason for d in filler.drops)


def test_a_dated_quote_gets_its_time_assumption_from_code(conn):
    # C05 "On March 12, 2026, PETROV wrote ...": the model gave only the sender.
    good = {a.template_id: a for a in build(conn, "C05")[0]}
    answers = {"C05": GOOD["C05"][:1]}
    got = {a.template_id: a for a in build(conn, "C05", answers)[0]}
    assert got.keys() == {"sender", "record_time"}
    assert got["record_time"].params == good["record_time"].params


def test_a_sender_without_a_party_gets_the_writer_the_claim_names(conn):
    # Mac run ¶6.1: the model left the sender's party out, so nobody was checked as the
    # sender and the claim could never be supported (rule 3e). "PETROV wrote" names him.
    good = {a.template_id: a for a in build(conn, "C05")[0]}
    answers = {"C05": [{**GOOD["C05"][0], "people": []}]}
    got = {a.template_id: a for a in build(conn, "C05", answers)[0]}
    assert got.keys() == {"sender", "record_time"}
    assert got["sender"].params == good["sender"].params
    assert got["record_time"].params == good["record_time"].params


@pytest.mark.parametrize(
    ("text", "quoted", "writer"),
    [
        ("On March 12, 2026, PETROV wrote to @northstar: 'need 2 more by friday'.",
         "need 2 more by friday", "PETROV"),
        ("Daniel Petrov texted REYES 'its done'.", "its done", "PETROV"),
        ("PETROV WROTE 'its done'.", "its done", "PETROV"),  # verbs in capitals too
        ("PETROV wrote 'ok' and REYES replied 'fine'.", "fine", "REYES"),  # nearest verb
        ("PETROV wrote 'ok' and REYES replied 'fine'.", "ok", "PETROV"),
        ("REYES said PETROV wrote 'its done'.", "its done", "PETROV"),  # writer, not speaker
        ("PETROV wrote a report quoting REYES: 'ok'.", "ok", None),  # "quoting" governs
        ("PETROV told agents that REYES said 'ok'.", "ok", None),  # "said" governs
        ("ALEXANDER SOKOLOV wrote 'its done'.", "its done", None),  # no such person
        ("The message 'its done' was sent at 2:31 a.m.", "its done", None),  # no writer
        ("PETROV wrote 'its done'.", "not in the claim", None),
        # The quote is handed on to someone else after the writer's verb (#57 review).
        ("PETROV sent REYES a photo, and REYES answered 'ok see you'.", "ok see you", None),
        ("PETROV texted REYES, who responded 'ok see you'.", "ok see you", None),
        ("PETROV replied to REYES's message 'ok see you'.", "ok see you", None),
        ("PETROV messaged REYES. REYES: 'ok see you'.", "ok see you", None),
        ("PETROV emailed REYES, whose reply was 'ok see you'.", "ok see you", None),
        ("PETROV texted JONES, with JONES' reply being 'ok see you'.", "ok see you", None),
        ("PETROV texted REYES and REYES wrote back 'ok see you'.", "ok see you", "REYES"),
        ("PETROV texted REYES that 'the van is ready'.", "the van is ready", "PETROV"),
        ("A friend of PETROV texted REYES 'its done'.", "its done", None),
        ("Someone posing as PETROV texted 'its done'.", "its done", None),
        ("A FRIEND OF PETROV TEXTED 'its done'.", "its done", None),
        ("Agent Daniel Petrov texted REYES 'its done'.", "its done", "PETROV"),
        ("PETROV texted REYES at 2:31 p.m.: 'ok'.", "ok", "PETROV"),  # Codex on #77
        ("PETROV texted REYES before midnight: 'ok'.", "ok", "PETROV"),
        ("As PETROV texted REYES 'ok', officers watched.", "ok", "PETROV"),
        ("Someone impersonating PETROV texted 'ok'.", "ok", None),
        ("PETROV sent REYES two texts, 'ok' and 'bye'.", "ok", "PETROV"),  # a noun
        ("PETROV texted REYES that it's 'ok see you'.", "ok see you", "PETROV"),  # contraction
        ("PETROV wrote a report with two quotes attributed to REYES: 'ok'.", "ok", None),
        ("PETROV TEXTED REYES, AND REYES SHOT BACK 'OK SEE YOU'.", "OK SEE YOU", None),
        ("PETROV TEXTED REYES AND SMITH: 'OK SEE YOU'.", "OK SEE YOU", "PETROV"),
        ("PETROV texted REYES, writing 'ok see you'.", "ok see you", "PETROV"),
        ("PETROV texted REYES, with REYES writing 'ok see you'.", "ok see you", None),
        ("PETROV texted REYES from his brother's phone: 'ok see you'.", "ok see you", "PETROV"),
        ("PETROV texted Dr. Reyes: 'ok see you'.", "ok see you", "PETROV"),
        ("PETROV texted REYES as REYES shot back 'ok see you'.", "ok see you", None),
        ("PETROV texted REYES about Exhibit A. REYES shot back 'ok see you'.", "ok see you", None),
        ("PETROV wrote a report with the quotes from REYES, 'ok see you'.", "ok see you", None),
        ("PETROV texted REYES and read her replies: 'ok'.", "ok", None),
        ("PETROV texted REYES and SMITH: 'ok'.", "ok", "PETROV"),  # Codex round 2
        ("PETROV texted REYES and he replied 'ok'.", "ok", None),
        ("PETROV texted REYES, and REYES shot back 'ok'.", "ok", None),
        ("PETROV texted @writes: 'ok'.", "ok", "PETROV"),
        ("PETROV texted REYES about the quoted statement 'ok'.", "ok", None),
        ("PETROV'S ASSISTANT REYES TEXTED 'ok'.", "ok", "REYES"),
        ("REYES's friend PETROV texted 'ok'.", "ok", "PETROV"),
        # Codex round 6
        ("PETROV wrote a report about REYES and her replies: 'ok'.", "ok", None),
        ("PETROV texted REYES and, replying 'ok', SMITH ended the exchange.", "ok", None),
        ("PETROV texted REYES, replying 'ok', and REYES left.", "ok", "PETROV"),
        ("PETROV texted REYES, writing 'ok', SMITH watching.", "ok", None),
    ],
)  # fmt: skip
def test_stated_sender_is_the_writer_of_the_quoted_words(conn, text, quoted, writer):
    filler = LocalAssumptionFiller(FakeModel(by_claim(GOOD)), conn, template=DRAFT)
    c = Claim(id="X", paragraph_id="para:1", text=text, claim_type=ClaimType.COMMUNICATION,
              status=ClaimStatus.ACCEPTED)  # fmt: skip
    got = filler.stated_sender(c, quoted)
    assert got == (filler._person(writer) if writer else None)


def test_a_phone_scope_does_not_stop_the_writer_from_being_read(conn):
    good = {a.template_id: a for a in build(conn, "C05")[0]}
    answers = {"C05": [{**GOOD["C05"][0], "people": [], "phones": ["Item 1"]}]}
    filler = LocalAssumptionFiller(FakeModel(by_claim(answers)), conn, template=DRAFT)
    para = "Item 1 holds this exchange. " + claim("C05").text  # so "Item 1" is written
    out = filler._resolve(claim("C05"), para, _ProposalOut.model_validate(answers["C05"][0]))
    assert out.params["person_ids"] == list(good["sender"].params.person_ids)
    assert out.params["device_ids"] == ["dev:item1"]


def test_stated_windows_read_the_claims_own_words():
    from core.audit.assumption_filler import stated_windows

    (w,) = stated_windows("At about 7:58 p.m. on March 9, 2026, Item 1 placed a call")
    assert (w.raw, w.start.isoformat(), w.end.isoformat()) == (
        "At about 7:58 p.m. on March 9, 2026",
        "2026-03-09T19:50:00",
        "2026-03-09T20:06:00",
    )
    (w,) = stated_windows("no contact between March 20 and March 23, 2026.")
    assert (w.start.day, w.end.day) == (20, 24)
    (w,) = stated_windows("texted REYES 'its done' at 2:31 a.m. on March 5, 2026")
    assert (w.start.hour, w.start.minute, (w.end - w.start).seconds) == (2, 31, 60)
    assert stated_windows("no contact before March 12, 2026") is None  # open: the model's call
    assert stated_windows("sent on 3/12/2026") is None  # month and day order unknown
    assert stated_windows("sent on March 12") is None  # no year anywhere
    assert stated_windows("sent on March 12", "Events of 2026.")[0].start.year == 2026


@pytest.mark.parametrize(
    ("text", "raw", "start", "end"),
    [
        (
            "Between 9 p.m. and 11 p.m. on May 2, 2026, Item 1 sent texts.",
            "Between 9 p.m. and 11 p.m. on May 2, 2026",
            "21:00",
            "23:01",
        ),
        (
            "From 9 p.m. to 11 p.m. on May 2, 2026, Item 1 sent texts.",
            "From 9 p.m. to 11 p.m. on May 2, 2026",
            "21:00",
            "23:01",
        ),
        (
            "Between 9 and 11 p.m. on May 2, 2026, Item 1 sent texts.",
            "Between 9 and 11 p.m. on May 2, 2026",
            "21:00",
            "23:01",
        ),
        ("between 10:15 a.m. and 11:45 a.m. on May 2, 2026", None, "10:15", "11:46"),
        ("between noon and 2 p.m. on May 2, 2026", None, "12:00", "14:01"),
        (
            "At about noon on May 2, 2026, Item 1 called.",
            "At about noon on May 2, 2026",
            "11:52",
            "12:08",
        ),
        ("At noon on May 2, 2026, Item 1 called.", None, "12:00", "12:01"),
        ("At about 9 p.m. on May 2, 2026, Item 1 called.", None, "20:52", "21:08"),
    ],
)
def test_stated_windows_read_times_of_day(text, raw, start, end):
    from core.audit.assumption_filler import stated_windows

    (w,) = stated_windows(text)
    assert (w.start.strftime("%H:%M"), w.end.strftime("%H:%M")) == (start, end)
    assert w.start.date() == w.end.date() == D(2026, 5, 2).date()
    if raw is not None:
        assert w.raw == raw
    check_window(w.start, w.end, w.raw, text, "", "record_time")


@pytest.mark.parametrize(
    "text",
    [
        "At midnight on May 2, 2026, Item 1 called.",  # start or end of the day
        "between 11 and 1 p.m. on May 2, 2026",  # the bare hour cannot take p.m.
        "between 10 p.m. and midnight on May 2, 2026",
        "between 11 p.m. and 1 a.m. on May 2, 2026",  # crosses midnight
        "between about 9 and 11 p.m. on May 2, 2026",
        "between 9 p.m. and about 11 p.m. on May 2, 2026",
        "between 9 and 11 on May 2, 2026",  # no a.m. or p.m.
        "at 21:00 on May 2, 2026",
    ],
)
def test_stated_windows_leave_unplain_times_to_the_model(text):
    from core.audit.assumption_filler import stated_windows

    assert stated_windows(text) is None


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (D(2026, 5, 2, 23), D(2026, 5, 2, 23, 1)),  # only the last minute
        (D(2026, 5, 2, 21), D(2026, 5, 2, 21, 1)),  # only the first minute
        (D(2026, 5, 2), D(2026, 5, 3)),  # the whole day
    ],
)
def test_check_window_holds_both_ends_of_a_stated_time_range(start, end):
    for raw in ("Between 9 and 11 p.m. on May 2, 2026", "From 9 p.m. to 11 p.m. on May 2, 2026"):
        with pytest.raises(Reject):
            check_window(start, end, raw, raw, "", "record_time")
    raw = "Between 9 and 11 p.m. on May 2, 2026"
    check_window(D(2026, 5, 2, 21), D(2026, 5, 2, 23, 1), raw, raw, "", "record_time")


def test_check_window_refuses_the_whole_day_for_a_stated_noon():
    raw = "At about noon on May 2, 2026"
    with pytest.raises(Reject):
        check_window(D(2026, 5, 2), D(2026, 5, 3), raw, raw, "", "record_time")


@pytest.mark.parametrize(
    ("text", "gap"),
    [
        ('On March 12, 2026, PETROV wrote "meet me at noon".', None),
        ("On March 12, 2026, PETROV wrote 'meet me at 9 p.m.'.", None),
        ("On March 12, 2026, PETROV wrote “see you at noon”.", None),
        ("On March 12, 2026, PETROV wrote 'I'll meet you at noon'.", None),
        ("On March 12, 2026, PETROV wrote ‘I’ll meet you at noon’.", None),
        ("At noon on March 12, 2026, PETROV wrote 'ok'.", "time of day"),  # outside the quote
        ("On March 12, 2026 at 9 p.m., PETROV's phone sent 'ok'.", "time of day"),
    ],
)
def test_a_time_inside_quoted_words_is_not_the_send_time(text, gap):
    from types import SimpleNamespace

    from core.audit.assumption_filler import coverage_gap
    from core.audit.assumptions import Proposal

    c = Claim(id="X", paragraph_id="para:1", text=text, claim_type=ClaimType.COMMUNICATION,
              status=ClaimStatus.ACCEPTED)  # fmt: skip
    window = SimpleNamespace(raw="On March 12, 2026")
    got = coverage_gap(c, [Proposal("record_time", {"window": window}), Proposal("sender", {})])
    assert (got is None) if gap is None else (gap in got)


def test_stated_windows_skip_a_time_inside_quoted_words():
    from core.audit.assumption_filler import stated_windows

    (w,) = stated_windows("On March 12, 2026, PETROV wrote 'noon'.")
    assert (w.start.hour, (w.end - w.start).days) == (0, 1)
    assert stated_windows("On March 12, 2026 at noon, PETROV wrote 'ok'.") is None
    # a date in the quoted words is the message's: no range for it
    assert stated_windows('PETROV wrote "meet me at noon on March 12, 2026".') == []
    (w,) = stated_windows("On March 11, 2026, PETROV wrote 'see you at noon on March 12'.")
    assert (w.start.day, w.start.hour) == (11, 0)


@pytest.mark.parametrize(
    ("raw", "ok_day"),
    [
        ("after March 3, 2025", 4),  # March 3 itself is not after March 3
        ("after Mar. 3rd, 2025", 4),
        ("on or after March 3, 2025", 3),
        ("since March 3, 2025", 3),
        ("after Monday, March 3, 2025", 4),  # a weekday between "after" and the date
    ],
)
def test_an_after_window_starts_the_day_after(raw, ok_day):
    c = f"PETROV had no contact with REYES {raw}."
    for day in (3, 4, 5):
        if day == ok_day:
            check_window(D(2025, 3, day), D(2025, 4, 1), raw, c, "", "no_contact")
        else:
            with pytest.raises(Reject):
                check_window(D(2025, 3, day), D(2025, 4, 1), raw, c, "", "no_contact")
    with pytest.raises(Reject):  # no time of day stated: midnight only
        check_window(D(2025, 3, ok_day, 9), D(2025, 4, 1), raw, c, "", "no_contact")


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("At 9 p.m. on Monday, March 3, 2025, PETROV texted REYES.", "21:00", "21:01"),
        ("Between 9 and 11 p.m. on Monday, March 3, 2025, PETROV texted.", "21:00", "23:01"),
    ],
)
def test_stated_windows_read_a_time_before_a_weekday_and_date(text, start, end):
    from core.audit.assumption_filler import stated_windows

    (w,) = stated_windows(text)
    assert (w.start.strftime("%H:%M"), w.end.strftime("%H:%M")) == (start, end)
    check_window(w.start, w.end, w.raw, text, "", "record_time")


def test_stated_windows_refuse_a_weekday_that_is_not_the_dates():
    from core.audit.assumption_filler import stated_windows

    assert stated_windows("At 9 p.m. on Tuesday, March 3, 2025, PETROV texted REYES.") is None
    assert stated_windows("On Tuesday, March 3, 2025, PETROV texted REYES.") is None
    assert stated_windows("On Monday, March 3, 2025, PETROV texted REYES.")[0].start.day == 3


@pytest.mark.parametrize(
    "raw",
    [
        "after Tuesday, March 3, 2025",  # March 3, 2025 is a Monday
        "On Tuesday, March 3, 2025",
        "at 9 p.m. on Tuesday, March 3, 2025",
    ],
)
def test_check_window_refuses_a_weekday_that_is_not_the_dates(raw):
    for start in (D(2025, 3, 3), D(2025, 3, 3, 21), D(2025, 3, 4)):
        with pytest.raises(Reject):
            check_window(start, D(2025, 3, 5), raw, raw, "", "no_contact")


@pytest.mark.parametrize("raw", ["two days after March 3, 2025", "shortly after March 3, 2025"])
def test_check_window_refuses_a_range_offset_from_a_date(raw):
    for day in (3, 4, 5):
        with pytest.raises(Reject):
            check_window(D(2025, 3, day), D(2025, 4, 1), raw, raw, "", "no_contact")


@pytest.mark.parametrize(("cid", "change", "why"), BAD)
def test_bad_values_drop_the_proposal_and_the_claim_stays_unproven(conn, cid, change, why):
    assumptions, filler, _ = build(conn, cid, _one(cid, **change))
    assert assumptions == []
    reasons = " | ".join(d.reason for d in filler.drops)
    assert why in reasons
    assert "stays unproven" in reasons  # the key template did not survive


def test_unknown_person_is_dropped(conn):
    answers = {"C18": [P("person_identity", people=["ALEXANDER SOKOLOV"], handles=["@northstar"])]}
    assumptions, filler, _ = build(conn, "C18", answers)
    assert assumptions == []
    assert "matches no person" in filler.drops[0].reason


def test_meaning_claim_without_a_meaning_assumption_gets_none(conn):
    # C06: the model checks only the easy part (who sent it, when) and skips the meaning.
    answers = {
        "C06": [
            P("sender", handles=["@northstar"], quoted_text="the package will be at marcs"),
        ]
    }
    assumptions, filler, _ = build(conn, "C06", answers)
    assert assumptions == []
    assert "no usable meaning assumption" in filler.drops[-1].reason


def test_meaning_claim_keeps_meaning(conn):
    quote = "the package will be at marcs"
    sent = P(
        "record_time",
        handles=["@northstar"],
        quoted_text=quote,
        window=W("on March 12, 2026", "2026-03-12T00:00", "2026-03-13T00:00"),
    )
    assumptions, filler, _ = build(conn, "C06", {"C06": [P("meaning", quoted_text=quote), sent]})
    assert not filler.drops, filler.drops
    assert {a.template_id for a in assumptions} == {"meaning", "record_time"}
    # Without the time range, the stated date would go untested.
    assumptions, filler, _ = build(conn, "C06", {"C06": [P("meaning", quoted_text=quote)]})
    assert assumptions == []
    assert "states a date" in filler.drops[-1].reason


@pytest.mark.parametrize(
    ("cid", "keep", "why"),
    [
        ("C05", "record_time", "who sent it"),  # quoted message, sender untested
        # A sender alone now gets its date from code (test_a_dated_quote_gets_its_time_...);
        # a stated date with no quote to date stays untested (C06 above).
    ],
)
def test_claim_is_not_judged_on_its_easy_parts(conn, cid, keep, why):
    answers = {cid: [p for p in GOOD[cid] if p["template_id"] == keep]}
    assumptions, filler, _ = build(conn, cid, answers)
    assert assumptions == []
    assert why in filler.drops[-1].reason


def test_dropping_the_time_of_day_is_refused(conn):
    (p,) = GOOD["C10"]
    whole_day = {**p, "window": W("on March 5, 2026", "2026-03-05T00:00", "2026-03-06T00:00")}
    assumptions, filler, _ = build(conn, "C10", {"C10": [whole_day]})
    assert assumptions == []
    assert "time of day" in filler.drops[-1].reason


@pytest.mark.parametrize("raw", ["not json", '{"assumptions": "none"}', "", RuntimeError("x")])
def test_bad_output_gives_no_assumptions_and_is_recorded(conn, raw):
    filler = LocalAssumptionFiller(FakeModel(raw), conn, template=DRAFT)
    assert TemplateAssumptionBuilder(filler).build(claim("C14")) == []
    (call,) = filler.recorder.calls
    assert call.outcome in (ModelCallOutcome.INVALID_OUTPUT, ModelCallOutcome.ERROR)
    assert filler.drops[0].model_call_id == call.id


def test_extra_field_in_a_proposal_is_dropped(conn):
    (p,) = GOOD["C14"]
    answers = {"C14": [{**p, "is_core": False}]}
    assumptions, filler, _ = build(conn, "C14", answers)
    assert assumptions == []
    assert "wrong shape" in filler.drops[0].reason


# ---------------------------------------------------------------- pure helpers


def test_date_mentions():
    ms = date_mentions("From March 10 through March 31, 2026; March 20 to 23; 3/9/2026")
    got = {(m.month, m.day, m.year) for m in ms}
    assert {(3, 10, 2026), (3, 31, 2026), (3, 20, None), (3, 23, None), (3, 9, 2026)} <= got


@pytest.mark.parametrize(
    ("claim_text", "value", "op"),
    [
        ("Item 1 recorded 13 Telegram messages", 13, "eq"),
        ("at least 13 messages", 13, "ge"),
        ("13 messages or more", 13, "ge"),
        ("at most 4 calls", 4, "le"),
    ],
)
def test_count_op(claim_text, value, op):
    assert count_op(claim_text, value) == op


@pytest.mark.parametrize(
    "claim_text", ["about 13 messages", "more than 13 messages", "on March 13 they met"]
)
def test_count_op_refuses(claim_text):
    with pytest.raises(Reject):
        count_op(claim_text, 13)


def test_window_before_and_first():
    c = "PETROV first made contact with @northstar on March 12, 2026."
    raw = "first made contact with @northstar on March 12, 2026"
    check_window(D(2026, 1, 1), D(2026, 3, 12), raw, c, "", "no_contact")
    with pytest.raises(Reject):  # "first" opens the start only for no_contact
        check_window(D(2026, 1, 1), D(2026, 3, 12), raw, c, "", "record_time")
    with pytest.raises(Reject):  # no year anywhere
        check_window(D(2026, 3, 12), D(2026, 3, 13), "On March 12", "On March 12 he left", "")
    with pytest.raises(Reject):  # no time stated: whole days only
        check_window(
            D(2026, 3, 12, 9), D(2026, 3, 13), "On March 12, 2026", "On March 12, 2026", ""
        )


def test_every_template_has_help():
    from core.audit.assumption_filler import TEMPLATE_HELP

    assert set(TEMPLATES) <= set(TEMPLATE_HELP)


@pytest.mark.parametrize(
    ("words", "rng"),
    [
        ("about two minutes", (90, 150)),
        ("two minutes", (120, 179)),
        ("about 30 seconds", (22, 38)),
        ("a minute", (60, 119)),
        ("approximately one hour", (2700, 4500)),
    ],
)
def test_duration_range(words, rng):
    from core.audit.assumption_filler import duration_range

    assert duration_range(words) == rng


@pytest.mark.parametrize("words", ["under two minutes", "more than a minute", "a while", "2m"])
def test_duration_range_refuses(words):
    from core.audit.assumption_filler import duration_range

    with pytest.raises(Reject):
        duration_range(words)
