"""Verdict rules. HUMAN-OWNED (Arsh). Agents: do not modify.

decide_verdict() is the only place a claim gets a verdict. It reads its arguments and writes
nothing: coverage is worked out here on every call and returned on the decision, never stored
back on an assumption. Every number of a rule below is cited by the reasons it produces.

Inputs are filtered first: assumptions, evidence and checks that belong to another claim are
ignored (and the reasons say how many). An evidence item's status is its latest review
(open, ai_accepted, accepted, dismissed); its tier is the tier of the record and never says
whether it was reviewed.

Rule 1. Contradiction. The claim is CONTRADICTED if any core assumption has
    (a) a deterministic check that failed, or
    (b) a contradicting evidence item that an expert accepted.
    A failed check on an assumption an agent proposed (agent_proposed: the testability step's,
    core/audit/testability.py, in the claim only because an examiner accepted the proposal)
    counts under (a) only once an expert confirms that failure (confirmed_fails) (rules 0.4.0,
    Arsh, 2026-10-28: an accepted wrong phone or time window must not turn a true claim
    CONTRADICTED by itself). Until then the claim stays UNPROVEN, the failure blocks SUPPORTED
    (rule 3d), and the screen and the report say "Contradiction found, confirm to finalize".
    The caller passes both sets: ids of this claim's assumptions an agent proposed, and ids of
    failed checks an expert confirmed exactly as they failed. Left empty, every failed check
    counts, as in 0.3.0.
    A model's or the AI reviewer's "contradicts" that no expert accepted does not count (rules
    0.3.0, Arsh, 2026-10-19, PR #90 URGENT FIX: on the signed probe set the local 14B scored 58%
    contradicts precision against a bar of 90%). The claim stays UNPROVEN, the item blocks
    SUPPORTED until the expert dismisses it (rule 3d), and the screen and the report say
    "Contradiction found, confirm to finalize". It counts once the expert accepts it.
    The one way back for an unaccepted label is _AUTO_CONTRADICT, a versioned set of claim
    types, EMPTY in 0.3.0. For a claim type in it, an item not dismissed whose record is
    observed or derived, or that the AI reviewer accepted, counts again (the 0.2.2 rule), except
        - on a meaning assumption (Arsh, 2026-10-07, decision 2: only a failed check or an
          accepted item can contradict a meaning), and
        - on an assumption whose deterministic checks all passed (at least one ran): a model
          label cannot overrule a passed check (Arsh, 2026-10-14, rules 0.2.1; case01 Mac run,
          where the 14B read the receiving phone's copy of a message the sender check had
          passed as contradicting it).
    A claim type enters _AUTO_CONTRADICT only after a recorded probe run of the local labeler
    meets the signed bars for that type (contradicts precision >= 0.90, supports recall >= 0.90,
    0 moved traps shown as supports, with Wilson intervals), and with Arsh's sign-off on the
    entry. The entry names that probe run, and every report prints it.

Rule 2. Coverage of one core assumption. It is covered when, and only when, one of these holds:
    (a) every deterministic check on it passed (at least one ran) -> tier derived;
    (b) an expert accepted a supporting item on it whose record is observed or derived
        -> tier confirmed;
    (c) the AI reviewer accepted a supporting item on it whose record is observed or derived,
        and its kind is in _AI_MAY_COVER -> tier ai_reviewed. For the alpha that set is EMPTY,
        so AI review alone covers nothing (Arsh, 2026-10-07, decision 6: on his signed probe
        set the best local model, Qwen3-14B, still accepted 3 overreach traps, and the bar is
        0). The AI reviewer still sorts evidence for the expert. Event assumptions (a message or
        call happened, with these words) may return to the set only once a local model accepts
        0 overreach traps on the signed probe set, and that change bumps RULE_VERSION.
        Even then, AI review never covers an identity, time, completeness or meaning
        assumption: the AI reviewer never confirms identity, timing is computed by a check,
        silence has no quote to verify, and what words mean is interpretation for an expert
        (Arsh, 2026-10-07, decision 5; red-team R09, R18, R19; C06 and C20).
    Never covered by: a model label nobody accepted, an item the reviewer or expert dismissed,
    an inferred record (a machine translation, even when accepted; C17 is a known miss,
    Arsh, 2026-10-07, decision 4), an inconclusive check, or an assumption's stored tier.
    An assumption that names a person is not covered while that person's only device_owner
    stipulation is unconfirmed: ownership counts once an expert confirms it (decision 3).

Rule 3. SUPPORTED needs all of:
    (a) the claim has at least one core assumption;
    (b) every core assumption is covered (rule 2);
    (c) at least one supporting item on a core assumption, whose record is observed and whose
        label an expert accepted (CLAUDE.md: never SUPPORTED on a model label alone, nor
        without one). An AI acceptance does not satisfy this while _AI_MAY_COVER is empty
        (decision 6): in the alpha the expert accepts the key evidence for every SUPPORTED;
    (d) no complicating item that is not dismissed, no counting contradiction and no failed
        check on any assumption of the claim, core or not;
    (e) the core assumptions include the kind the claim type turns on: identity for a
        communication claim (who sent it: C16's shared account) or an identity claim, a
        meaning assumption for a content-meaning claim, completeness for an absence or count
        claim, time for a timing claim. A claim whose hard part was never made an assumption
        is not tested, whatever else is covered;
    (f) for identity, role and content-meaning claims, no core assumption is covered by AI
        review alone (a role template may be an event assumption, but who directed whom is
        interpretation). Rules 2c, 3e and 3f: Arsh, 2026-10-07, decision 5.
    supported_basis is confirmed only when no coverage and no cited support rests on the AI
    reviewer alone; otherwise ai_reviewed, and the reasons say so. Under decision 6 every
    SUPPORTED is confirmed; the ai_reviewed path stays for when AI coverage returns. Reports
    show the two differently. A human decision always overrides the AI reviewer, through the
    item's latest review.

Rule 4. Otherwise UNPROVEN, with a reason naming each core assumption left uncovered.

Rules are versioned. Bump RULE_VERSION on every change; every VerdictDecision records it.
0.2.2 (Arsh, 2026-10-15, PR #66) changes no rule above. It marks that time ranges are read
differently (core/audit/assumption_filler.py): "after March 3" starts on March 4, and offsets
("two days after") and weekdays that are not the date's are refused. Verdicts decided under
0.2.1 can differ.
0.3.0 (Arsh, 2026-10-19) changes rule 1b as above: only an expert-accepted contradiction counts
unless the claim type is in _AUTO_CONTRADICT. A claim decided CONTRADICTED under 0.2.x on an
unaccepted label is UNPROVEN under 0.3.0 until the expert confirms the contradiction.
0.4.0 (Arsh, 2026-10-28) changes rule 1a as above: a failed check on an assumption an agent
proposed counts only once an expert confirms the failure. A call that passes no agent_proposed
decides exactly as 0.3.0 did. A claim decided CONTRADICTED under 0.3.0 on such a failed check
alone is UNPROVEN under 0.4.0 until the expert confirms it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

from core.contracts import (
    Assumption,
    AssumptionCoverage,
    AssumptionKind,
    CheckOutcome,
    CheckResult,
    Claim,
    ClaimType,
    EvidenceItem,
    EvidenceStatus,
    ProvenanceTier,
    Stance,
    Stipulation,
    StipulationKind,
    StipulationStatus,
    SupportedBasis,
    Verdict,
    VerdictDecision,
    verdict_id,
)

RULE_VERSION = "0.4.0"

_CITABLE_RECORD = frozenset({ProvenanceTier.OBSERVED, ProvenanceTier.DERIVED})
_REVIEWED = frozenset({EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED})
# rule 2(c): assumption kinds AI review alone may cover. Empty for the alpha (decision 6);
# 0.1.0 had {EVENT}. Refill only after a local model accepts 0 traps on the signed probe set.
_AI_MAY_COVER: frozenset[AssumptionKind] = frozenset()
# rule 3(c): review statuses whose supporting label can carry a SUPPORTED. AI_ACCEPTED counts
# only while AI review may cover something.
_SUPPORT_ACCEPTED = _REVIEWED if _AI_MAY_COVER else frozenset({EvidenceStatus.ACCEPTED})
# rule 1(b): claim types whose unaccepted model "contradicts" may count, each mapped to the
# recorded probe run that qualified it (its results file). EMPTY in 0.3.0: every model
# contradiction waits for an expert. An entry needs Arsh's sign-off and a RULE_VERSION bump.
_AUTO_CONTRADICT: MappingProxyType[ClaimType, str] = MappingProxyType({})
# rule 3(e): the assumption kind each claim type turns on
_REQUIRED_KIND = {
    ClaimType.COMMUNICATION: AssumptionKind.IDENTITY,
    ClaimType.CONTENT_MEANING: AssumptionKind.MEANING,
    ClaimType.IDENTITY: AssumptionKind.IDENTITY,
    ClaimType.ABSENCE: AssumptionKind.COMPLETENESS,
    ClaimType.COUNT: AssumptionKind.COMPLETENESS,
    ClaimType.TIMING: AssumptionKind.TIME,
}
# rule 3(f): claim types an AI review may not carry on its own
_NO_AI_COVERAGE = frozenset({ClaimType.IDENTITY, ClaimType.ROLE, ClaimType.CONTENT_MEANING})


@dataclass
class _Finding:
    """What the rules found for one assumption of this claim."""

    assumption: Assumption
    failed_checks: list[CheckResult] = field(default_factory=list)
    # rule 1a, 0.4.0: failed checks on an agent's assumption that no expert confirmed yet
    awaiting_checks: list[CheckResult] = field(default_factory=list)
    contradicting: list[EvidenceItem] = field(default_factory=list)  # counts under rule 1
    unconfirmed: list[EvidenceItem] = field(default_factory=list)  # rule 1b: awaits an expert
    complicating: list[EvidenceItem] = field(default_factory=list)  # blocks rule 3(d)
    supports: list[EvidenceItem] = field(default_factory=list)  # accepted, observed (rule 3c)
    # rule 2, for core assumptions only
    covered_tier: ProvenanceTier | None = None
    covering_checks: list[str] = field(default_factory=list)
    covering_evidence: list[str] = field(default_factory=list)
    covering_stipulations: list[str] = field(default_factory=list)
    unconfirmed_people: list[str] = field(default_factory=list)

    def coverage(self) -> AssumptionCoverage:
        return AssumptionCoverage(
            assumption_id=self.assumption.id,
            covered=self.covered_tier is not None,
            tier=self.covered_tier,
            cited_ids=(
                *self.covering_checks,
                *self.covering_evidence,
                *self.covering_stipulations,
            ),
        )


def auto_contradict() -> dict[ClaimType, str]:
    """Rule 1b: claim types whose unaccepted model contradiction counts, each with the probe
    run that qualified it. Empty in 0.3.0. The report prints it."""
    return dict(_AUTO_CONTRADICT)


def _counts_as_contradiction(
    claim_type: ClaimType, a: Assumption, e: EvidenceItem, checks_passed: bool
) -> bool:
    """Rule 1b, for an item whose stance is contradicts and which is not dismissed."""
    if e.status is EvidenceStatus.ACCEPTED:
        return True
    if claim_type not in _AUTO_CONTRADICT or a.kind is AssumptionKind.MEANING or checks_passed:
        return False
    return e.status is EvidenceStatus.AI_ACCEPTED or e.tier in _CITABLE_RECORD


def _unconfirmed_people(a: Assumption, stipulations: list[Stipulation]) -> list[str]:
    """People this assumption names whose device_owner stipulations are all unconfirmed."""
    out = []
    for pid in a.params.person_ids:
        owned = [
            s
            for s in stipulations
            if s.kind is StipulationKind.DEVICE_OWNER
            and s.person_id == pid
            and s.status is not StipulationStatus.REJECTED
        ]
        if owned and not any(s.status is StipulationStatus.CONFIRMED for s in owned):
            out.append(pid)
    return sorted(out)


def _cover(
    f: _Finding,
    checks: list[CheckResult],
    evidence: list[EvidenceItem],
    stipulations: list[Stipulation],
) -> None:
    """Rule 2. Sets the covered tier and what it rests on; leaves them empty if uncovered."""
    a = f.assumption
    f.unconfirmed_people = _unconfirmed_people(a, stipulations)
    if f.unconfirmed_people:
        return
    people = sorted(
        s.id
        for s in stipulations
        if s.kind is StipulationKind.DEVICE_OWNER
        and s.status is StipulationStatus.CONFIRMED
        and s.person_id in a.params.person_ids
    )
    support = [e for e in evidence if e.stance is Stance.SUPPORTS and e.tier in _CITABLE_RECORD]
    expert = sorted(e.id for e in support if e.status is EvidenceStatus.ACCEPTED)
    ai = sorted(e.id for e in support if e.status is EvidenceStatus.AI_ACCEPTED)

    if checks and all(c.outcome is CheckOutcome.PASS for c in checks):
        f.covered_tier = ProvenanceTier.DERIVED
        f.covering_checks = sorted(c.id for c in checks)
    elif expert:
        f.covered_tier = ProvenanceTier.CONFIRMED
        f.covering_evidence = expert
    elif ai and a.kind in _AI_MAY_COVER:
        f.covered_tier = ProvenanceTier.AI_REVIEWED
        f.covering_evidence = ai
    else:
        return
    f.covering_stipulations = people


def _a(word: str) -> str:
    return ("an " if word[:1] in "aeiou" else "a ") + word


def _uncovered_reason(f: _Finding) -> str:
    text = f.assumption.text
    if f.unconfirmed_people:
        return (
            f"Rule 2: '{text}' is not covered: ownership of the phone of "
            f"{', '.join(f.unconfirmed_people)} is proposed, but no expert has confirmed it."
        )
    if f.assumption.kind not in _AI_MAY_COVER:
        return (
            f"Rule 2: '{text}' is not covered: {_a(f.assumption.kind.value)} assumption needs a "
            "passing check or an expert's acceptance; AI review alone does not cover it."
        )
    return f"Rule 2: '{text}' is not covered by a passing check or an accepted supporting item."


def _how(e: EvidenceItem) -> str:
    if e.status is EvidenceStatus.ACCEPTED:
        return "accepted by an expert"
    if e.status is EvidenceStatus.AI_ACCEPTED:
        return "accepted by the AI reviewer"
    return f"model label on an {e.tier.value} record, not reviewed"


def decide_verdict(
    claim: Claim,
    assumptions: list[Assumption],
    evidence: list[EvidenceItem],
    checks: list[CheckResult],
    stipulations: list[Stipulation],
    pipeline_run_id: str,
    *,
    agent_proposed: frozenset[str] = frozenset(),
    confirmed_fails: frozenset[str] = frozenset(),
) -> VerdictDecision:
    mine = {a.id: a for a in assumptions if a.claim_id == claim.id}
    ev_by: dict[str, list[EvidenceItem]] = defaultdict(list)
    ck_by: dict[str, list[CheckResult]] = defaultdict(list)
    foreign = 0
    for e in evidence:
        if e.assumption_id in mine:
            ev_by[e.assumption_id].append(e)
        else:
            foreign += 1
    for c in checks:
        if c.assumption_id in mine:
            ck_by[c.assumption_id].append(c)
        else:
            foreign += 1

    findings: list[_Finding] = []
    for aid in sorted(mine):
        a = mine[aid]
        f = _Finding(a)
        f.failed_checks = sorted(
            (c for c in ck_by[aid] if c.outcome is CheckOutcome.FAIL), key=lambda c: c.id
        )
        if aid in agent_proposed:  # rule 1a, 0.4.0
            f.awaiting_checks = [c for c in f.failed_checks if c.id not in confirmed_fails]
        checks_passed = bool(ck_by[aid]) and all(c.outcome is CheckOutcome.PASS for c in ck_by[aid])
        for e in sorted(ev_by[aid], key=lambda e: e.id):
            if e.status is EvidenceStatus.DISMISSED:
                continue
            if e.stance is Stance.CONTRADICTS:
                if _counts_as_contradiction(claim.claim_type, a, e, checks_passed):
                    f.contradicting.append(e)
                else:
                    f.unconfirmed.append(e)
            elif e.stance is Stance.COMPLICATES:
                f.complicating.append(e)
            elif (
                e.stance is Stance.SUPPORTS
                and e.status in _SUPPORT_ACCEPTED
                and e.tier is ProvenanceTier.OBSERVED
            ):
                f.supports.append(e)
        if a.is_core:
            _cover(f, ck_by[aid], ev_by[aid], stipulations)
        findings.append(f)

    core = [f for f in findings if f.assumption.is_core]
    reasons: list[str] = []
    if foreign:
        reasons.append(f"Ignored {foreign} evidence items or checks that belong to other claims.")

    def decide(verdict: Verdict, **kw: object) -> VerdictDecision:
        return VerdictDecision(
            id=verdict_id(claim.id, pipeline_run_id),
            claim_id=claim.id,
            pipeline_run_id=pipeline_run_id,
            verdict=verdict,
            rule_version=RULE_VERSION,
            reasons=tuple(reasons),
            coverage=tuple(f.coverage() for f in core),
            decided_at_utc=datetime.now(UTC),
            **kw,  # type: ignore[arg-type]
        )

    # Rule 1: a contradiction on a core assumption.
    failed = [(f, c) for f in core for c in f.failed_checks if c not in f.awaiting_checks]
    against = [(f, e) for f in core for e in f.contradicting]
    if failed or against:
        for f, c in failed:
            reasons.append(
                f"Rule 1a: check {c.check_name} failed on '{f.assumption.text}': {c.detail}"
                + (
                    " An agent proposed this assumption, and an expert confirmed the failure."
                    if f.assumption.id in agent_proposed
                    else ""
                )
            )
        for f, e in against:
            reasons.append(f"Rule 1b: {e.record_id} contradicts '{f.assumption.text}' ({_how(e)}).")
        return decide(
            Verdict.CONTRADICTED,
            cited_evidence_ids=tuple(sorted(e.id for _, e in against)),
            cited_check_ids=tuple(sorted(c.id for _, c in failed)),
        )

    # Rule 3: SUPPORTED, condition by condition. Any miss falls through to rule 4.
    blockers: list[str] = []
    if not core:
        blockers.append("Rule 3a: the claim has no core assumption, so nothing was tested.")
    blockers += [_uncovered_reason(f) for f in core if f.covered_tier is None]
    need = _REQUIRED_KIND.get(claim.claim_type)
    if core and need is not None and not any(f.assumption.kind is need for f in core):
        blockers.append(
            f"Rule 3e: a {claim.claim_type.value} claim needs a core {need.value} assumption, "
            "and this claim has none, so its central point was never tested."
        )
    if claim.claim_type in _NO_AI_COVERAGE:
        blockers += [
            f"Rule 3f: '{f.assumption.text}' rests on AI review alone, which cannot carry a "
            f"{claim.claim_type.value} claim; it needs a check or an expert."
            for f in core
            if f.covered_tier is ProvenanceTier.AI_REVIEWED
        ]
    supports = sorted((e for f in core for e in f.supports), key=lambda e: e.id)
    if core and not supports:
        waiting = sum(
            1
            for f in core
            for e in ev_by[f.assumption.id]
            if e.stance is Stance.SUPPORTS and e.status is EvidenceStatus.AI_ACCEPTED
        )
        if _AI_MAY_COVER:
            blockers.append(
                "Rule 3c: no supporting item on an observed record has been accepted by the AI "
                "reviewer or an expert."
            )
        else:
            blockers.append(
                "Rule 3c: no supporting item on an observed record has been accepted by an "
                "expert. AI review sorts evidence but cannot make a claim supported (decision 6)"
                + (f"; {waiting} AI-accepted item(s) await an expert." if waiting else ".")
            )
    for f in findings:
        if not f.assumption.is_core:
            blockers += [
                f"Rule 3d: check {c.check_name} failed on non-core '{f.assumption.text}'."
                for c in f.failed_checks
            ]
            blockers += [
                f"Rule 3d: {e.record_id} contradicts non-core '{f.assumption.text}' ({_how(e)})."
                for e in f.contradicting
            ]
        if f.assumption.is_core:
            blockers += [
                f"Rule 1a: check {c.check_name} failed on '{f.assumption.text}', an assumption "
                f"an agent proposed: {c.detail} Contradiction found, confirm to finalize: it "
                "counts once an expert confirms the failed check."
                for c in f.awaiting_checks
            ]
            blockers += [
                f"Rule 1b: {e.record_id} contradicts '{f.assumption.text}' ({_how(e)}). "
                "Contradiction found, confirm to finalize: it counts once an expert accepts it."
                for e in f.unconfirmed
            ]
        else:
            blockers += [
                f"Rule 3d: {e.record_id} contradicts non-core '{f.assumption.text}' "
                f"({_how(e)}) and is not dismissed."
                for e in f.unconfirmed
            ]
        blockers += [
            f"Rule 3d: {e.record_id} complicates '{f.assumption.text}' and is not dismissed."
            for e in f.complicating
        ]
    if blockers:
        reasons += blockers
        return decide(Verdict.UNPROVEN)

    expert_supports = [e for e in supports if e.status is EvidenceStatus.ACCEPTED]
    ai_covered = any(f.covered_tier is ProvenanceTier.AI_REVIEWED for f in core)
    if expert_supports and not ai_covered:
        basis = SupportedBasis.CONFIRMED
        cited_support = expert_supports
        reasons.append(
            "Rule 3: every core assumption is covered and the supporting evidence was accepted "
            "by an expert (expert-confirmed)."
        )
    else:
        basis = SupportedBasis.AI_REVIEWED
        cited_support = supports
        reasons.append(
            "Rule 3: every core assumption is covered, but the support rests on the AI "
            "reviewer, not an expert (AI-reviewed). An expert can confirm or override it."
        )
    for f in core:
        tier = f.covered_tier.value if f.covered_tier else "none"
        reasons.append(
            f"Rule 2: '{f.assumption.text}' covered at tier {tier} by "
            f"{', '.join(f.coverage().cited_ids)}."
        )
    return decide(
        Verdict.SUPPORTED,
        supported_basis=basis,
        cited_evidence_ids=tuple(
            sorted({e.id for e in cited_support} | {i for f in core for i in f.covering_evidence})
        ),
        cited_check_ids=tuple(sorted({i for f in core for i in f.covering_checks})),
        cited_stipulation_ids=tuple(sorted({i for f in core for i in f.covering_stipulations})),
    )
