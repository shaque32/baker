"""Verdict rules 0.1.0 (core/audit/rules.py). Every rule in its docstring has a test here.

SYNTHETIC. The claims echo case01 (C06, C16, C17, C18, C20) only to name the trap each tests.
"""

from datetime import UTC, datetime

import pytest

from core import contracts as c
from core.audit import rules
from core.contracts import (
    AssumptionKind as K,
)
from core.contracts import (
    CheckOutcome as O,
)
from core.contracts import (
    EvidenceStatus as S,
)
from core.contracts import (
    ProvenanceTier as T,
)
from core.contracts import (
    Stance,
    Verdict,
)

RUN = "run:test"
T0 = datetime(2026, 10, 7, tzinfo=UTC)
CLAIM = c.Claim(
    id="C1",
    paragraph_id="p",
    text="On March 12, PETROV wrote 'need 2 more by friday'.",
    claim_type=c.ClaimType.COMMUNICATION,
    status=c.ClaimStatus.ACCEPTED,
)


def asm(n: int, kind: K = K.EVENT, *, core: bool = True, people=(), claim_id="C1"):
    params = c.AssumptionParams(person_ids=tuple(people))
    return c.Assumption(
        id=f"asm:{claim_id}:t{n}",
        claim_id=claim_id,
        kind=kind,
        template_id=f"t{n}",
        template_version="1",
        params=params,
        text=f"assumption {n}",
        is_core=core,
        tier=T.INFERRED,
    )


def ev(n, a, stance=Stance.SUPPORTS, status=S.AI_ACCEPTED, tier=T.OBSERVED):
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
        tier=tier,
        status=status,
        model_run_id="m",
    )


def chk(a, outcome=O.PASS, name="time"):
    return c.CheckResult(
        id=c.check_id(a.id, name, "1"),
        assumption_id=a.id,
        check_name=name,
        check_version="1",
        outcome=outcome,
        searched="s",
        detail="d",
    )


def stip(person="person:petrov", status=c.StipulationStatus.CONFIRMED, device="dev:item1"):
    decided = status is not c.StipulationStatus.PROPOSED
    return c.Stipulation(
        id=c.stipulation_id(c.StipulationKind.DEVICE_OWNER, device),
        kind=c.StipulationKind.DEVICE_OWNER,
        subject_id=device,
        person_id=person,
        statement=f"{device} is {person}'s phone",
        status=status,
        decided_by="expert:pat" if decided else None,
        decided_at_utc=T0 if decided else None,
    )


def decide(assumptions, evidence=(), checks=(), stipulations=(), claim=CLAIM):
    return rules.decide_verdict(
        claim, list(assumptions), list(evidence), list(checks), list(stipulations), RUN
    )


EVENT = asm(1)
TIME = asm(2, K.TIME)


def test_version_is_not_a_stub():
    assert not rules.RULE_VERSION.endswith("-stub")


# ------------------------------------------------------------ controls


def test_ai_reviewed_support():
    d = decide([EVENT, TIME], [ev(1, EVENT)], [chk(TIME)])
    assert d.verdict is Verdict.SUPPORTED
    assert d.supported_basis is c.SupportedBasis.AI_REVIEWED
    assert "AI-reviewed" in " ".join(d.reasons)
    assert d.cited_evidence_ids == (ev(1, EVENT).id,)
    assert d.cited_check_ids == (chk(TIME).id,)
    assert d.id == c.verdict_id("C1", RUN) and d.rule_version == rules.RULE_VERSION
    assert d.confirmed_by is None


def test_expert_confirmed_support():
    d = decide([EVENT, TIME], [ev(1, EVENT, status=S.ACCEPTED)], [chk(TIME)])
    assert d.verdict is Verdict.SUPPORTED
    assert d.supported_basis is c.SupportedBasis.CONFIRMED


def test_expert_support_but_ai_coverage_elsewhere_is_ai_reviewed():
    meaning = asm(3, K.MEANING)
    d = decide(
        [EVENT, meaning],
        [ev(1, EVENT, status=S.ACCEPTED), ev(2, meaning, status=S.AI_ACCEPTED)],
    )
    assert d.verdict is Verdict.SUPPORTED
    assert d.supported_basis is c.SupportedBasis.AI_REVIEWED


def test_coverage_is_returned_per_core_assumption_and_never_written_back():
    d = decide([EVENT, TIME, asm(9, core=False)], [ev(1, EVENT)], [chk(TIME)])
    tiers = {cov.assumption_id: cov.tier for cov in d.coverage}
    assert tiers == {EVENT.id: T.AI_REVIEWED, TIME.id: T.DERIVED}
    assert EVENT.tier is T.INFERRED and TIME.tier is T.INFERRED


# ------------------------------------------------------------ rule 1: contradiction


def test_failed_check_contradicts_despite_accepted_support():
    d = decide([EVENT, TIME], [ev(1, EVENT, status=S.ACCEPTED)], [chk(TIME, O.FAIL)])
    assert d.verdict is Verdict.CONTRADICTED
    assert d.cited_check_ids == (chk(TIME, O.FAIL).id,)
    assert d.supported_basis is None


def test_unreviewed_contradiction_on_observed_record_counts():
    d = decide([EVENT], [ev(1, EVENT), ev(2, EVENT, Stance.CONTRADICTS, S.OPEN)])
    assert d.verdict is Verdict.CONTRADICTED


def test_unreviewed_contradiction_on_inferred_record_only_complicates():
    d = decide([EVENT], [ev(1, EVENT), ev(2, EVENT, Stance.CONTRADICTS, S.OPEN, T.INFERRED)])
    assert d.verdict is Verdict.UNPROVEN


def test_dismissed_contradiction_is_ignored():
    d = decide([EVENT], [ev(1, EVENT), ev(2, EVENT, Stance.CONTRADICTS, S.DISMISSED)])
    assert d.verdict is Verdict.SUPPORTED


@pytest.mark.parametrize("status", [S.OPEN, S.AI_ACCEPTED])
def test_decision_2_model_contradicts_on_meaning_only_complicates(status):
    """C06, C13, C20: a model's 'contradicts' on a meaning stays unproven."""
    meaning = asm(3, K.MEANING)
    d = decide([EVENT, meaning], [ev(1, EVENT), ev(2, meaning, Stance.CONTRADICTS, status)])
    assert d.verdict is Verdict.UNPROVEN
    assert "complicates" in " ".join(d.reasons)


def test_decision_2_expert_accepted_contradiction_on_meaning_counts():
    meaning = asm(3, K.MEANING)
    d = decide([meaning], [ev(2, meaning, Stance.CONTRADICTS, S.ACCEPTED)])
    assert d.verdict is Verdict.CONTRADICTED


def test_contradiction_on_non_core_assumption_blocks_support_only():
    side = asm(9, core=False)
    d = decide([EVENT, side], [ev(1, EVENT), ev(2, side, Stance.CONTRADICTS, S.OPEN)])
    assert d.verdict is Verdict.UNPROVEN


# ------------------------------------------------------------ rule 2: coverage


def test_unreviewed_or_dismissed_support_does_not_cover():
    for status in (S.OPEN, S.DISMISSED):
        assert decide([EVENT], [ev(1, EVENT, status=status)]).verdict is Verdict.UNPROVEN


def test_decision_4_inferred_record_never_covers():
    """C17: a machine translation, even accepted by an expert, stays unproven."""
    meaning = asm(3, K.MEANING)
    d = decide([meaning], [ev(1, meaning, status=S.ACCEPTED, tier=T.INFERRED)])
    assert d.verdict is Verdict.UNPROVEN


def test_inconclusive_check_does_not_cover():
    assert decide([EVENT, TIME], [ev(1, EVENT)], [chk(TIME, O.INCONCLUSIVE)]).verdict is (
        Verdict.UNPROVEN
    )


def test_one_inconclusive_check_spoils_a_pass():
    checks = [chk(TIME), chk(TIME, O.INCONCLUSIVE, "other")]
    assert decide([EVENT, TIME], [ev(1, EVENT)], checks).verdict is Verdict.UNPROVEN


@pytest.mark.parametrize("kind", [K.IDENTITY, K.TIME, K.COMPLETENESS])
def test_ai_review_alone_never_covers_identity_time_or_completeness(kind):
    """C16, C18 and absence claims: the AI reviewer never confirms identity or silence."""
    a = asm(5, kind)
    assert decide([a], [ev(1, a)]).verdict is Verdict.UNPROVEN
    assert decide([a], [ev(1, a, status=S.ACCEPTED)]).verdict is Verdict.SUPPORTED


def test_decision_3_unconfirmed_ownership_never_covers():
    sender = asm(6, K.IDENTITY, people=("person:petrov",))
    parts = ([EVENT, sender], [ev(1, EVENT)], [chk(sender, name="sender")])
    proposed = stip(status=c.StipulationStatus.PROPOSED)
    d = decide(*parts, [proposed])
    assert d.verdict is Verdict.UNPROVEN
    assert "no expert has confirmed it" in " ".join(d.reasons)
    d = decide(*parts, [stip()])
    assert d.verdict is Verdict.SUPPORTED
    assert d.cited_stipulation_ids == (stip().id,)


def test_foreign_items_are_ignored():
    other = asm(1, claim_id="C2")
    d = decide([EVENT, TIME], [ev(1, other)], [chk(other), chk(TIME)])
    assert d.verdict is Verdict.UNPROVEN
    assert "other claims" in d.reasons[0]


# ------------------------------------------------------------ rule 3: SUPPORTED conditions


def test_no_core_assumption_is_never_supported():
    assert decide([], []).verdict is Verdict.UNPROVEN
    side = asm(9, core=False)
    assert decide([side], [ev(1, side)]).verdict is Verdict.UNPROVEN


def test_checks_alone_never_support():
    """CLAUDE.md: SUPPORTED needs an accepted label on observed evidence too."""
    d = decide([TIME], [], [chk(TIME)])
    assert d.verdict is Verdict.UNPROVEN
    assert "Rule 3c" in " ".join(d.reasons)


def test_derived_record_covers_but_does_not_satisfy_rule_3c():
    d = decide([EVENT], [ev(1, EVENT, tier=T.DERIVED)])
    assert d.verdict is Verdict.UNPROVEN


@pytest.mark.parametrize("status", [S.OPEN, S.AI_ACCEPTED, S.ACCEPTED])
def test_any_live_complication_blocks_support(status):
    d = decide([EVENT], [ev(1, EVENT), ev(2, EVENT, Stance.COMPLICATES, status)])
    assert d.verdict is Verdict.UNPROVEN


def test_irrelevant_items_change_nothing():
    d = decide([EVENT], [ev(1, EVENT), ev(2, EVENT, Stance.IRRELEVANT, S.ACCEPTED)])
    assert d.verdict is Verdict.SUPPORTED


def test_order_of_inputs_does_not_matter():
    items = [ev(1, EVENT), ev(2, EVENT, status=S.ACCEPTED), ev(3, TIME, Stance.IRRELEVANT)]
    a = decide([EVENT, TIME], items, [chk(TIME)])
    b = decide([TIME, EVENT], items[::-1], [chk(TIME)])
    assert a.model_dump(exclude={"decided_at_utc"}) == b.model_dump(exclude={"decided_at_utc"})
