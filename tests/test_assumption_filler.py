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
    for d in map(json.loads, (ROOT / "eval/gold/case01/gold.jsonl").read_text().splitlines())
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
    assert c03.params.account_ids == tuple(NORTHSTAR)
    assert c03.params.person_ids == (PETROV,)
    assert (c03.params.expected_count, c03.params.count_op) == (13, "eq")
    assert c03.params.window.tz == "America/New_York"
    assert c03.params.window.raw == "From March 10 through March 31, 2026"
    c02 = {a.template_id: a for a in build(conn, "C02")[0]}
    assert c02["same_account"].params.handles == ("@alex92", "@northstar")
    (c09,) = build(conn, "C09")[0]
    assert c09.params.account_ids == tuple(MARC_0122)
    assert c09.params.person_ids == (PETROV,)  # named in the paragraph, not the claim


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
        "C14",
        {
            "window": W(
                "between March 20 and March 23, 2026", "2026-03-19T00:00", "2026-03-24T00:00"
            )
        },
        "not a date the claim states",
        id="window-start-not-stated",
    ),
    pytest.param(
        "C14",
        {
            "window": W(
                "between March 20 and March 23, 2026", "2026-03-20T00:00", "2026-03-26T00:00"
            )
        },
        "not a date the claim states",
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
        "does not say UTC",
        id="utc-not-written",
    ),
    pytest.param(
        "C14",
        {"window": W("between March 20 and 23", "2026-03-20T00:00", "2026-03-24T00:00")},
        "not written in the claim",
        id="window-words-invented",
    ),
    pytest.param(
        "C10",
        {"window": W("At 2:31 a.m. on March 5, 2026", "2026-03-05T07:31", "2026-03-05T07:32")},
        "not near a time",
        id="utc-time-as-local",
    ),
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
]


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
        ("C05", "sender", "states a date"),  # date untested
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
