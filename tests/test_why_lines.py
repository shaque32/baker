"""The claim page's plain "Why" lines (core/report/why.py) read every reason the verdict rules
write. Each case below makes core/audit/rules.py write one kind of reason, so a change to the
signed rules' wording fails here instead of reaching the screen as raw rule text.

SYNTHETIC. Display only: nothing here decides a verdict.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime

import pytest

from core import contracts as c
from core import db
from core.audit import rules
from core.contracts import AssumptionKind as K
from core.contracts import CheckOutcome as O
from core.contracts import EvidenceStatus as S
from core.contracts import ProvenanceTier as T
from core.contracts import Stance, Verdict
from core.report import why

RUN = "run:test"
T0 = datetime(2026, 10, 7, tzinfo=UTC)
CLAIM = c.Claim(
    id="C1",
    paragraph_id="p",
    text="On March 12, PETROV wrote 'need 2 more by friday'.",
    claim_type=c.ClaimType.EVENT,
    status=c.ClaimStatus.ACCEPTED,
)


def asm(n: int, kind: K = K.EVENT, *, core: bool = True, people=()) -> c.Assumption:
    return c.Assumption(
        id=f"asm:C1:t{n}",
        claim_id="C1",
        kind=kind,
        template_id=f"t{n}",
        template_version="1",
        params=c.AssumptionParams(person_ids=tuple(people)),
        text=f"assumption {n} about person:petrov's (phone)",
        is_core=core,
        tier=T.INFERRED,
    )


def ev(n: int, a: c.Assumption, stance=Stance.SUPPORTS, status=S.ACCEPTED) -> c.EvidenceItem:
    rid = f"msg:item1:Chats!{n}"
    return c.EvidenceItem(
        id=f"ev:{a.id}|{rid}|x",
        assumption_id=a.id,
        record_id=rid,
        ref=c.SourceRef(source_id="item1", locator=f"Chats!{n}"),
        stance=stance,
        quote="q",
        quote_verified=True,
        rationale="r",
        tier=T.OBSERVED,
        status=status,
        model_run_id="m",
    )


def chk(a: c.Assumption, outcome=O.PASS, name="time") -> c.CheckResult:
    return c.CheckResult(
        id=c.check_id(a.id, name, "1"),
        assumption_id=a.id,
        check_name=name,
        check_version="1",
        outcome=outcome,
        searched="s",
        detail=f"detail of {name}",
    )


def stip(status=c.StipulationStatus.CONFIRMED) -> c.Stipulation:
    decided = status is not c.StipulationStatus.PROPOSED
    return c.Stipulation(
        id=c.stipulation_id(c.StipulationKind.DEVICE_OWNER, "dev:item1"),
        kind=c.StipulationKind.DEVICE_OWNER,
        subject_id="dev:item1",
        person_id="person:petrov",
        statement="dev:item1 is person:petrov's phone",
        status=status,
        decided_by="expert:pat" if decided else None,
        decided_at_utc=T0 if decided else None,
    )


@pytest.fixture
def conn():
    out = db.connect(":memory:")
    db.apply_schema(out)
    return out


def plain(conn, d: c.VerdictDecision, assumptions, evidence=(), checks=()) -> list[str]:
    got = why.lines(conn, d.reasons, list(assumptions), list(checks), list(evidence))
    assert [r for ln in got for r in ln.reasons] == list(d.reasons)  # nothing lost or reordered
    return [html.unescape(re.sub(r"<[^>]+>", "", ln.html)) for ln in got]


def decide(assumptions, evidence=(), checks=(), stipulations=(), claim=CLAIM, **kw):
    return rules.decide_verdict(
        claim, list(assumptions), list(evidence), list(checks), list(stipulations), RUN, **kw
    )


def no_rule_text(lines: list[str]) -> None:
    for line in lines:
        assert not line.startswith("Rule ") and "covered at tier" not in line, line


def test_supported_by_an_expert_reads_as_backed_and_shown(conn):
    a = asm(1)
    d = decide([a], [ev(1, a)])
    assert d.verdict is Verdict.SUPPORTED
    got = plain(conn, d, [a], [ev(1, a)])
    no_rule_text(got)
    assert got[0].startswith("Every part of the claim that has to be true is backed")
    assert got[1].startswith("Shown by evidence an expert accepted: assumption 1")


def test_a_failed_check_names_the_check_and_the_assumption(conn):
    a, b = asm(1), asm(2, K.TIME)
    fail = chk(b, O.FAIL, name="weekday")
    d = decide([a, b], [ev(1, a)], [fail])
    assert d.verdict is Verdict.CONTRADICTED
    got = plain(conn, d, [a, b], [ev(1, a)], [fail])
    no_rule_text(got)
    assert got == [
        "The weekday check on the phone records does not match: assumption 2 about "
        "person:petrov's (phone)."
    ]


def test_an_agents_failed_check_waits_for_you(conn):
    a = asm(1)
    fail = chk(a, O.FAIL, name="count")
    d = decide([a], [], [fail], agent_proposed=frozenset({a.id}))
    got = plain(conn, d, [a], [], [fail])
    no_rule_text(got)
    assert any(line.endswith("It counts once you confirm it.") for line in got)


def test_contradicting_records_share_one_line(conn):
    a = asm(1)
    items = [ev(n, a, Stance.CONTRADICTS) for n in (1, 2, 3)]
    d = decide([a], items)
    assert d.verdict is Verdict.CONTRADICTED and len(d.reasons) == 3
    got = plain(conn, d, [a], items)
    assert len(got) == 1
    assert got[0].startswith("3 records contradict this: assumption 1")
    assert "An expert accepted each." in got[0] and "Records: " in got[0]


def test_unproven_reasons_say_what_is_missing(conn):
    meaning, event = asm(1, K.MEANING), asm(2)
    side = asm(3, core=False)
    items = [ev(1, event, Stance.SUPPORTS, S.AI_ACCEPTED), ev(2, side, Stance.COMPLICATES)]
    checks = [chk(side, O.FAIL, name="sender")]
    d = decide([meaning, event, side], items, checks)
    assert d.verdict is Verdict.UNPROVEN
    got = plain(conn, d, [meaning, event, side], items, checks)
    no_rule_text(got)
    assert "Only an expert can accept what the words mean." in got[0]
    assert any("1 record the AI reviewer accepted waits for you" in g for g in got)
    assert any(g.startswith("A sender check failed on a side point") for g in got)
    assert any(g.startswith("A record complicates this") for g in got)


def test_an_unconfirmed_owner_says_who_uses_the_phone_is_not_confirmed(conn):
    a = asm(1, K.IDENTITY, people=("person:petrov",))
    d = decide([a], [], [chk(a)], [stip(c.StipulationStatus.PROPOSED)])
    got = plain(conn, d, [a], [], [chk(a)])
    no_rule_text(got)
    assert any("Who uses the phone is proposed but not confirmed" in g for g in got)


def test_nothing_tested_and_a_missing_central_point(conn):
    d = decide([])
    assert plain(conn, d, []) == ["Nothing was tested: no part of this claim could be checked."]
    a = asm(1)
    timing = CLAIM.model_copy(update={"claim_type": c.ClaimType.TIMING})
    d = decide([a], [ev(1, a)], claim=timing)
    got = plain(conn, d, [a], [ev(1, a)])
    no_rule_text(got)
    assert any(g.startswith("The claim's central point was never tested") for g in got)


def test_a_reason_it_cannot_place_prints_as_the_rules_wrote_it(conn):
    d = decide([asm(1)]).model_copy(update={"reasons": ("A reason from a later rule set.",)})
    assert plain(conn, d, [asm(1)]) == ["A reason from a later rule set."]


def test_rule_3c_keeps_the_observed_record_requirement(conn):
    a = asm(1)
    d = decide([a], [ev(1, a, Stance.SUPPORTS, S.AI_ACCEPTED)])
    got = plain(conn, d, [a], [ev(1, a, Stance.SUPPORTS, S.AI_ACCEPTED)])
    assert any("supporting evidence on an observed phone record" in g for g in got)


def test_links_name_the_assumption_and_stance_the_line_reads(conn):
    """One record can back two assumptions of a claim; the link asks for the item on the line's
    own assumption, read with the line's stance."""
    a, b = asm(1), asm(2)
    items = [ev(1, a, Stance.CONTRADICTS), ev(1, b, Stance.SUPPORTS)]
    d = decide([a, b], items)
    asked: list[tuple] = []

    def href(rid, assumption, stance):
        asked.append((rid, assumption, stance))
        return "/x"

    why.lines(conn, d.reasons, [a, b], [], items, href=href)
    assert asked == [("msg:item1:Chats!1", a.id, Stance.CONTRADICTS)]
