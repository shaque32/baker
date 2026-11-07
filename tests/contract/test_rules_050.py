"""Rules 0.5.0 (Arsh, 2026-11-06): counsel review (option B) and code-checked support (option C)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core import contracts as c
from core.audit import rules
from core.contracts import AssumptionKind as K
from core.contracts import CheckOutcome as O
from core.contracts import ClaimType as CT
from core.contracts import EvidenceStatus as S
from core.contracts import ProvenanceTier as T
from core.contracts import Stance, SupportedBasis, Verdict
from tests.contract.test_rules import CLAIM, asm, claim_of, decide, ev, stip

T0 = datetime(2026, 11, 6, tzinfo=UTC)


def chk(a, outcome=O.PASS, name="time", records=("msg:item1:Chats!1",)):
    return c.CheckResult(
        id=c.check_id(a.id, name, "1"),
        assumption_id=a.id,
        check_name=name,
        check_version="1",
        outcome=outcome,
        searched="s",
        record_ids=tuple(records),
        detail="d",
    )


TIME = asm(1, K.TIME)
EVENT = asm(2)
SENDER = asm(3, K.IDENTITY, template="sender")
COUNT = asm(4, K.COMPLETENESS)
MEANING = asm(5, K.MEANING)
TIMING = claim_of(CT.TIMING)
COMMUNICATION = claim_of(CT.COMMUNICATION)


def test_version_and_sets():
    assert rules.RULE_VERSION == "0.5.0"
    assert rules._CODE_MAY_SUPPORT == frozenset({CT.COMMUNICATION, CT.TIMING, CT.COUNT})


# ------------------------------------------------------------ option C, rule 3c'


def test_a_timing_claim_whose_checks_all_pass_is_supported_by_the_checks():
    check = chk(TIME)
    d = decide([TIME], [], [check], claim=TIMING)
    assert d.verdict is Verdict.SUPPORTED
    assert d.supported_basis is SupportedBasis.CHECKED
    assert d.cited_check_ids == (check.id,) and d.cited_evidence_ids == ()
    assert any(r.startswith("Rule 3c':") for r in d.reasons)


def test_checked_support_ignores_unreviewed_model_labels():
    d = decide([TIME], [ev(1, TIME, status=S.OPEN)], [chk(TIME)], claim=TIMING)
    assert d.supported_basis is SupportedBasis.CHECKED and d.cited_evidence_ids == ()


def test_a_check_that_names_no_records_cannot_carry_a_claim_alone():
    d = decide([TIME], [], [chk(TIME, records=())], claim=TIMING)
    assert d.verdict is Verdict.UNPROVEN
    assert any("Rule 3c'" in r for r in d.reasons)


@pytest.mark.parametrize("claim_type", [CT.EVENT, CT.CONTENT_MEANING, CT.IDENTITY, CT.ABSENCE])
def test_other_claim_types_never_rest_on_checks_alone(claim_type):
    kind = {CT.CONTENT_MEANING: MEANING, CT.IDENTITY: SENDER, CT.ABSENCE: COUNT}.get(
        claim_type, EVENT
    )
    d = decide([kind], [], [chk(kind)], claim=claim_of(claim_type))
    assert d.verdict is Verdict.UNPROVEN


def test_an_exact_count_never_rests_on_checks_alone():
    """The count check passes "exactly N" on a curated report that may omit records (#228)."""
    exact = c.Assumption(
        **{
            **asm(9, K.COMPLETENESS).model_dump(),
            "params": c.AssumptionParams(expected_count=3, count_op="eq"),
        }
    )
    d = decide([exact], [], [chk(exact, name="count")], claim=claim_of(CT.COUNT))
    assert d.verdict is Verdict.UNPROVEN
    assert any("an exact count needs an expert" in r for r in d.reasons)
    at_least = exact.model_copy(
        update={"params": c.AssumptionParams(expected_count=3, count_op="ge")}
    )
    d = decide([at_least], [], [chk(at_least, name="count")], claim=claim_of(CT.COUNT))
    assert d.supported_basis is SupportedBasis.CHECKED


def test_every_core_assumption_needs_its_checks_passed():
    d = decide([TIME, EVENT], [], [chk(TIME)], claim=TIMING)
    assert d.verdict is Verdict.UNPROVEN  # the event assumption has no check
    inconclusive = chk(EVENT, O.INCONCLUSIVE, name="sender")
    d = decide([TIME, EVENT], [], [chk(TIME), inconclusive], claim=TIMING)
    assert d.verdict is Verdict.UNPROVEN


def test_a_communication_claim_still_needs_an_identity_assumption():
    d = decide([TIME], [], [chk(TIME)], claim=COMMUNICATION)
    assert d.verdict is Verdict.UNPROVEN
    assert any(r.startswith("Rule 3e") for r in d.reasons)
    d = decide([SENDER, TIME], [], [chk(SENDER, name="sender"), chk(TIME)], claim=COMMUNICATION)
    assert d.supported_basis is SupportedBasis.CHECKED


def test_blockers_still_block_checked_support():
    side = asm(6, core=False)
    complicating = ev(2, side, Stance.COMPLICATES, status=S.OPEN)
    d = decide([TIME, side], [complicating], [chk(TIME)], claim=TIMING)
    assert d.verdict is Verdict.UNPROVEN
    person = asm(7, K.TIME, people=("person:petrov",))
    proposed = stip(status=c.StipulationStatus.PROPOSED)
    d = decide([person], [], [chk(person)], [proposed], claim=TIMING)
    assert d.verdict is Verdict.UNPROVEN  # ownership not confirmed: not covered


def test_a_failed_check_still_contradicts():
    d = decide([TIME], [], [chk(TIME, O.FAIL)], claim=TIMING)
    assert d.verdict is Verdict.CONTRADICTED


def test_an_expert_acceptance_keeps_the_confirmed_basis():
    accepted = ev(1, TIME, status=S.ACCEPTED)
    d = decide([TIME], [accepted], [chk(TIME)], claim=TIMING)
    assert d.supported_basis is SupportedBasis.CONFIRMED
    assert d.cited_evidence_ids == (accepted.id,)


# ------------------------------------------------------------ option B, counsel


def test_counsel_acceptance_supports_as_counsel_reviewed():
    d = decide([EVENT], [ev(1, EVENT, status=S.COUNSEL_ACCEPTED)])
    assert d.verdict is Verdict.SUPPORTED
    assert d.supported_basis is SupportedBasis.COUNSEL_REVIEWED
    assert d.coverage[0].tier is T.COUNSEL_REVIEWED
    assert any("reviewed by counsel" in r for r in d.reasons)


def test_one_assumption_resting_on_counsel_makes_the_claim_counsel_reviewed():
    other = asm(8)
    items = [ev(1, EVENT, status=S.ACCEPTED), ev(2, other, status=S.COUNSEL_ACCEPTED)]
    d = decide([EVENT, other], items)
    assert d.supported_basis is SupportedBasis.COUNSEL_REVIEWED


def test_an_expert_acceptance_ranks_above_counsel_on_one_assumption():
    items = [ev(1, EVENT, status=S.ACCEPTED), ev(2, EVENT, status=S.COUNSEL_ACCEPTED)]
    d = decide([EVENT], items)
    assert d.coverage[0].tier is T.CONFIRMED
    assert d.supported_basis is SupportedBasis.CONFIRMED  # it cites only the expert's item
    assert d.cited_evidence_ids == (items[0].id,)


def test_a_contradiction_counsel_accepted_counts_and_says_so():
    item = ev(1, EVENT, Stance.CONTRADICTS, status=S.COUNSEL_ACCEPTED)
    d = decide([EVENT], [item])
    assert d.verdict is Verdict.CONTRADICTED
    assert any("accepted by counsel, not an expert" in r for r in d.reasons)


def test_counsel_never_shows_as_confirmed():
    item = ev(1, EVENT, status=S.COUNSEL_ACCEPTED)
    assert c.display_tier(item) is T.COUNSEL_REVIEWED


def _review(kind, reviewer, status):
    return c.ReviewDecision(
        id="rv:x#1",
        evidence_id="x",
        seq=1,
        reviewer_kind=kind,
        reviewer=reviewer,
        status=status,
        reason="r",
        model_run_id=None,
        decided_at_utc=T0,
    )


def test_counsel_accepts_or_undoes_and_never_dismisses():
    _review(c.ReviewerKind.COUNSEL, "counsel:lee", S.COUNSEL_ACCEPTED)
    _review(c.ReviewerKind.COUNSEL, "counsel:lee", S.OPEN)
    for status in (S.DISMISSED, S.ACCEPTED, S.AI_ACCEPTED):
        with pytest.raises(ValidationError):
            _review(c.ReviewerKind.COUNSEL, "counsel:lee", status)
    with pytest.raises(ValidationError):
        _review(c.ReviewerKind.COUNSEL, "expert:lee", S.COUNSEL_ACCEPTED)
    with pytest.raises(ValidationError):
        _review(c.ReviewerKind.EXPERT, "expert:lee", S.COUNSEL_ACCEPTED)


def test_a_checked_verdict_cites_checks_and_no_evidence():
    base = dict(
        id="vd:C1@run",
        claim_id="C1",
        pipeline_run_id="run",
        verdict=Verdict.SUPPORTED,
        supported_basis=SupportedBasis.CHECKED,
        rule_version="0.5.0",
        reasons=("r",),
        coverage=(),
        decided_at_utc=T0,
    )
    c.VerdictDecision(**base, cited_check_ids=("chk:a",))
    with pytest.raises(ValidationError):
        c.VerdictDecision(**base)
    with pytest.raises(ValidationError):
        c.VerdictDecision(**base, cited_check_ids=("chk:a",), cited_evidence_ids=("ev:a",))


def test_the_default_claim_is_untouched():
    assert CLAIM.claim_type is CT.EVENT
