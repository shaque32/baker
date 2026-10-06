"""Verdict rules. HUMAN-OWNED (Arsh). Agents: do not modify.

STUB. The logic below is intentionally not written yet. The intended rules, from the
project brief, are:

    CONTRADICTED if any deterministic check fails on a core assumption
                 OR observed/derived/confirmed evidence contradicts a core assumption
    SUPPORTED    if every core assumption is observed/derived/confirmed
                 AND at least one verified, observed supporting item exists
                 AND no open contradicting or complicating items remain
    UNPROVEN     otherwise (including any core assumption still 'inferred')

Rules are versioned. Bump RULE_VERSION on every change; every VerdictDecision records it.
"""

from __future__ import annotations

from core.contracts import Assumption, CheckResult, Claim, EvidenceItem, VerdictDecision

RULE_VERSION = "0.0.0-stub"


def decide_verdict(
    claim: Claim,
    assumptions: list[Assumption],
    evidence: list[EvidenceItem],
    checks: list[CheckResult],
) -> VerdictDecision:
    raise NotImplementedError("Verdict rules are human-owned and not written yet.")
