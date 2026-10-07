"""Invariant checks that run after core/audit/rules.py and stop the pipeline if one fails.

rules.py is the only thing that sets a verdict. This module never sets one. It re-checks every
decision against the stored records, independently of the code that produced the evidence and
of the rules themselves, so a bug in a labeler, a reviewer, a quote verifier or rules.py cannot
put a wrong "supported" in front of an expert. A failure raises InvariantViolation and the
pipeline rolls back the run's work.

Every decision:
- belongs to this claim and this pipeline run, under the contract's verdict id;
- cites only evidence, checks and stipulations that were given to the rule;
- rests on evidence whose quotes are non-empty and verbatim (exact substring, no normalization)
  in the record's stored text, re-read from the database;
- sees each item's status as the database has it (the latest evidence_reviews row). 'accepted'
  comes from an expert row, 'ai_accepted' only sits on supporting items, and once an expert has
  decided an item no AI row comes after it.

Every SUPPORTED decision, re-derived here from CLAUDE.md:
- cites at least one supporting item, every cited supporting item is observed and accepted by
  the AI reviewer or an expert, and supported_basis is 'confirmed' only if an expert accepted
  every one of them;
- every core assumption is covered: its stored tier is above inferred, a check on it passed,
  an accepted observed or derived supporting item stands on it, or a confirmed stipulation
  matches its params (coverage is computed, never written back);
- no check on a core assumption failed;
- no contradicting or complicating item remains that is not dismissed.

Report text is checked too: tool-authored text never says guilty, innocent, leader or deleted.
Quoted text from the government document or the evidence is exempt, because it is cited, not
said by the tool.
"""

from __future__ import annotations

import re
import sqlite3

from core.contracts import (
    Assumption,
    AssumptionKind,
    CheckOutcome,
    CheckResult,
    Claim,
    EvidenceItem,
    EvidenceStatus,
    ProvenanceTier,
    ReviewerKind,
    Stance,
    Stipulation,
    StipulationKind,
    StipulationStatus,
    SupportedBasis,
    Verdict,
    VerdictDecision,
    verdict_id,
)

ACCEPTED_STATUSES = (EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED)

FORBIDDEN_WORDS = re.compile(r"\b(guilty|innocent|leader|deleted)\b", re.IGNORECASE)
# Report renderers wrap every cited span (government text, evidence quotes, record text) in
# this element. Its content is HTML-escaped, so it never contains '<'.
QUOTED_SPAN = re.compile(r'<span class="q">[^<]*</span>')


class InvariantViolation(Exception):
    """A decision or a stored record breaks a correctness rule. The run must stop."""


# ---------------------------------------------------------------- record text


def record_text(conn: sqlite3.Connection, record_id: str) -> str | None:
    """The citable text of a record, exactly as stored. None if the record does not exist.

    Messages cite their original body. Calls and contacts have no body, so their text is a
    fixed rendering of stored fields; a quote from them can only cite those fields.
    """
    kind = record_id.split(":", 1)[0]
    if kind == "msg":
        row = conn.execute("SELECT body FROM messages WHERE id = ?", (record_id,)).fetchone()
        return row[0] if row else None
    if kind == "contact":
        row = conn.execute(
            "SELECT name, identifier FROM contacts WHERE id = ?", (record_id,)
        ).fetchone()
        return f"{row[0] or ''} {row[1]}".strip() if row else None
    if kind == "call":
        row = conn.execute(
            "SELECT c.direction, fa.identifier, ta.identifier, c.ts_raw, c.duration_s"
            " FROM calls c LEFT JOIN accounts fa ON fa.id = c.from_account_id"
            " LEFT JOIN accounts ta ON ta.id = c.to_account_id WHERE c.id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        direction, frm, to, raw, dur = row
        return f"{direction} call from {frm or '?'} to {to or '?'} at {raw or '?'}, {dur}s"
    return None


def quote_is_verbatim(conn: sqlite3.Connection, quote: str, record_id: str) -> bool:
    text = record_text(conn, record_id)
    return bool(quote.strip()) and text is not None and quote in text


# ---------------------------------------------------------------- evidence


def _reviews(conn: sqlite3.Connection, evidence_id: str) -> list[tuple[str, str]]:
    """(reviewer_kind, status) per review row, oldest first."""
    return list(
        conn.execute(
            "SELECT reviewer_kind, status FROM evidence_reviews WHERE evidence_id = ? ORDER BY seq",
            (evidence_id,),
        )
    )


def check_evidence(conn: sqlite3.Connection, evidence: list[EvidenceItem]) -> None:
    for e in evidence:
        if not e.quote_verified or not quote_is_verbatim(conn, e.quote, e.record_id):
            raise InvariantViolation(
                f"{e.id}: quote is not verbatim in {e.record_id}; unverified quotes are not stored"
            )
        rows = _reviews(conn, e.id)
        stored = EvidenceStatus(rows[-1][1]) if rows else EvidenceStatus.OPEN
        if e.status != stored:
            raise InvariantViolation(
                f"{e.id}: rules saw status {e.status.value}, the database says {stored.value}"
            )
        if e.status == EvidenceStatus.ACCEPTED and rows[-1][0] != ReviewerKind.EXPERT.value:
            raise InvariantViolation(f"{e.id}: accepted without an expert review row")
        if e.status == EvidenceStatus.AI_ACCEPTED and e.stance != Stance.SUPPORTS:
            raise InvariantViolation(
                f"{e.id}: ai_accepted on a {e.stance.value} item; the reviewer only sees support"
            )
        kinds = [k for k, _ in rows]
        if ReviewerKind.EXPERT.value in kinds:
            first_expert = kinds.index(ReviewerKind.EXPERT.value)
            if ReviewerKind.AI.value in kinds[first_expert:]:
                raise InvariantViolation(f"{e.id}: an AI review came after an expert decision")


# ---------------------------------------------------------------- coverage


def covered(
    assumption: Assumption,
    evidence: list[EvidenceItem],
    checks: list[CheckResult],
    stipulations: list[Stipulation],
) -> bool:
    if assumption.tier != ProvenanceTier.INFERRED:
        return True
    if any(c.assumption_id == assumption.id and c.outcome == CheckOutcome.PASS for c in checks):
        return True
    if any(
        e.assumption_id == assumption.id
        and e.stance == Stance.SUPPORTS
        and e.status in ACCEPTED_STATUSES
        and e.tier in (ProvenanceTier.OBSERVED, ProvenanceTier.DERIVED)
        for e in evidence
    ):
        return True
    p = assumption.params
    return assumption.kind == AssumptionKind.IDENTITY and any(
        s.kind == StipulationKind.DEVICE_OWNER
        and s.status == StipulationStatus.CONFIRMED
        and s.subject_id in p.device_ids
        and s.person_id in p.person_ids
        for s in stipulations
    )


# ---------------------------------------------------------------- decisions


def check_decision(
    conn: sqlite3.Connection,
    claim: Claim,
    assumptions: list[Assumption],
    evidence: list[EvidenceItem],
    checks: list[CheckResult],
    stipulations: list[Stipulation],
    decision: VerdictDecision,
    pipeline_run_id: str,
) -> None:
    """Raise InvariantViolation if the decision or its inputs break a rule."""
    if decision.claim_id != claim.id:
        raise InvariantViolation(f"decision for {decision.claim_id} returned for {claim.id}")
    if decision.pipeline_run_id != pipeline_run_id:
        raise InvariantViolation(f"{claim.id}: decision names run {decision.pipeline_run_id}")
    if decision.id != verdict_id(claim.id, pipeline_run_id):
        raise InvariantViolation(f"{claim.id}: verdict id {decision.id} is not the contract id")
    if not decision.rule_version:
        raise InvariantViolation(f"{claim.id}: decision has no rule version")
    own = {a.id for a in assumptions}
    stray = [e.id for e in evidence if e.assumption_id not in own]
    stray += [c.id for c in checks if c.assumption_id not in own]
    if stray:
        raise InvariantViolation(f"{claim.id}: inputs from another claim: {stray}")
    by_id = {e.id: e for e in evidence}
    unknown = [i for i in decision.cited_evidence_ids if i not in by_id]
    unknown += [i for i in decision.cited_check_ids if i not in {c.id for c in checks}]
    unknown += [i for i in decision.cited_stipulation_ids if i not in {s.id for s in stipulations}]
    if unknown:
        raise InvariantViolation(f"{claim.id}: decision cites ids it was not given: {unknown}")
    check_evidence(conn, evidence)

    if decision.verdict != Verdict.SUPPORTED:
        return

    cited_support = [
        by_id[i] for i in decision.cited_evidence_ids if by_id[i].stance == Stance.SUPPORTS
    ]
    if not cited_support:
        raise InvariantViolation(f"{claim.id}: SUPPORTED cites no supporting item")
    weak = [
        e.id
        for e in cited_support
        if e.status not in ACCEPTED_STATUSES or e.tier != ProvenanceTier.OBSERVED
    ]
    if weak:
        raise InvariantViolation(
            f"{claim.id}: SUPPORTED cites supporting items that are not observed and accepted: "
            f"{weak}"
        )
    basis = (
        SupportedBasis.CONFIRMED
        if all(e.status == EvidenceStatus.ACCEPTED for e in cited_support)
        else SupportedBasis.AI_REVIEWED
    )
    if decision.supported_basis != basis:
        raise InvariantViolation(
            f"{claim.id}: supported_basis {decision.supported_basis} but the cited items say "
            f"{basis.value}; AI-reviewed never shows as confirmed"
        )
    core = [a for a in assumptions if a.is_core]
    if not core:
        raise InvariantViolation(f"{claim.id}: SUPPORTED with no core assumptions")
    uncovered = [a.id for a in core if not covered(a, evidence, checks, stipulations)]
    if uncovered:
        raise InvariantViolation(
            f"{claim.id}: SUPPORTED with uncovered core assumptions {uncovered}"
        )
    core_ids = {a.id for a in core}
    failed = [
        c.id for c in checks if c.assumption_id in core_ids and c.outcome == CheckOutcome.FAIL
    ]
    if failed:
        raise InvariantViolation(f"{claim.id}: SUPPORTED despite failed checks {failed}")
    against = [
        e.id
        for e in evidence
        if e.stance in (Stance.CONTRADICTS, Stance.COMPLICATES)
        and e.status != EvidenceStatus.DISMISSED
    ]
    if against:
        raise InvariantViolation(
            f"{claim.id}: SUPPORTED with contradicting or complicating items open: {against}"
        )


def check_report_text(html: str) -> None:
    """Tool-authored report text never uses the forbidden words. Cited spans are exempt."""
    own_text = QUOTED_SPAN.sub("", html)
    m = FORBIDDEN_WORDS.search(own_text)
    if m:
        start = max(0, m.start() - 60)
        raise InvariantViolation(
            f"report says {m.group(0)!r}: ...{own_text[start : m.end() + 60]}..."
        )
