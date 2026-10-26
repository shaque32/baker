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
  in the record's stored text, re-read from the database, and take in a letter or digit of the
  record's own fields, not only Mabillon's words or a placeholder such as "(no name)" (only a run
  that records no quote-check version, made before #76 or re-deciding one, holds its evidence to
  the check of its day);
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
said by the tool. So is a forbidden word on its own in the notice that stands in for a withheld
model rationale (core/review/withheld.py), which names the word it withheld.
"""

from __future__ import annotations

import json
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
from core.enrich import records

ACCEPTED_STATUSES = (EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED)

WORDS = ("guilty", "innocent", "leader", "deleted")
FORBIDDEN_WORDS = re.compile(rf"\b({'|'.join(WORDS)})\b", re.IGNORECASE)
# Report renderers wrap every cited span (government text, evidence quotes, record text) in
# this element. Its content is HTML-escaped, so it never contains '<'.
QUOTED_SPAN = re.compile(r'<span class="q">[^<]*</span>')
# ...and every reason or note an expert typed in this element (core/report/html.said). The
# expert's own words are theirs to choose; the check is for what Mabillon or a model says.
EXPERT_SPAN = re.compile(r'<span class="said">[^<]*</span>')
# ...and the word a withheld rationale used, named in the notice shown in its place
# (core/report/html.withheld_word). Only one forbidden word, in lower case, exactly: nothing else
# can pass through this element.
WITHHELD_WORD = re.compile(rf'<span class="withheld-word">(?:{"|".join(WORDS)})</span>')


class InvariantViolation(Exception):
    """A decision or a stored record breaks a correctness rule. The run must stop."""


# ---------------------------------------------------------------- record text


def record_text(conn: sqlite3.Connection, record_id: str) -> str | None:
    """The citable text of a record, exactly as retrieval shows it to the labeler
    (core.enrich.records). None if the record does not exist.

    Messages cite their original body. Calls, contacts and attachments have no words of their
    own, so their text is a fixed rendering of stored fields: a contact "name: number", a call
    "outgoing Phone call from +1... to +1..., duration 84 s" (its time is on its context line,
    not in this text), an attachment its file name. A quote from them can only cite those fields.
    """
    return records.record_text(conn, record_id)


def record_text_before_76(conn: sqlite3.Connection, record_id: str) -> str | None:
    """How this check read a contact or a call before PR #76 (2026-10-15). Evidence stored before
    then may quote it, and stays verified: it quotes the same stored fields. New labels are checked
    against record_text only (core.pipeline), so nothing new is stored in this form, and only a
    run that records no quote-check version accepts it (pre_76_run)."""
    kind = record_id.split(":", 1)[0]
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


def _takes_in_own(quote: str, text: str, own: tuple[records.Span, ...]) -> bool:
    start = text.find(quote)
    while start != -1:
        end = start + len(quote)
        if any(text[i].isalnum() for a, b in own for i in range(max(a, start), min(b, end))):
            return True
        start = text.find(quote, start + 1)
    return False


def pre_76_run(conn: sqlite3.Connection, pipeline_run_id: str) -> bool:
    """True for a recorded run whose config holds no quote-check version: an audit made before #76,
    or a rules-only re-run of one (it carries its evidence run's, core/review/redecide.py). Every
    audit since records one (core/pipeline.py). An unknown run is not pre-#76: it fails closed."""
    row = conn.execute(
        "SELECT config_json FROM pipeline_runs WHERE id = ?", (pipeline_run_id,)
    ).fetchone()
    return row is not None and not json.loads(row[0]).get("quote_check")


def quote_is_verbatim(
    conn: sqlite3.Connection, quote: str, record_id: str, *, before_76: bool = False
) -> bool:
    """A stored quote still stands in its record: in its text now, at a place that takes in a
    letter or digit of the record's own fields, so a quote of only Mabillon's words or a placeholder
    ("(no name)", "unknown", " call from ") does not stand. With before_76, for evidence a run
    made before #76 stored (quote check 1.1.0 or earlier, no version recorded), a quote is held to
    the check of its day instead: a substring of the contact or call text the check read then, so
    a case audited earlier re-decides. Otherwise it fails closed (Grok review on #76)."""
    if not quote.strip():
        return False
    rec = records.get_record(conn, record_id)
    if rec is not None and rec.text is not None and _takes_in_own(quote, rec.text, rec.own):
        return True
    if not before_76:
        return False
    old = record_text_before_76(conn, record_id)
    return old is not None and quote in old


# ---------------------------------------------------------------- evidence


def _reviews(conn: sqlite3.Connection, evidence_id: str) -> list[tuple[str, str]]:
    """(reviewer_kind, status) per review row, oldest first."""
    return list(
        conn.execute(
            "SELECT reviewer_kind, status FROM evidence_reviews WHERE evidence_id = ? ORDER BY seq",
            (evidence_id,),
        )
    )


def check_evidence(
    conn: sqlite3.Connection, evidence: list[EvidenceItem], *, before_76: bool = False
) -> None:
    """Each item's quote and status, as the database has them. before_76: the items come from a
    run that records no quote-check version (quote_is_verbatim)."""
    for e in evidence:
        if not e.quote_verified or not quote_is_verbatim(
            conn, e.quote, e.record_id, before_76=before_76
        ):
            raise InvariantViolation(
                f"{e.id}: quote is not verbatim in {e.record_id}'s own fields; unverified quotes"
                " are not stored"
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
    # Only a run that records no quote-check version holds its evidence to the pre-#76 check.
    check_evidence(conn, evidence, before_76=pre_76_run(conn, pipeline_run_id))

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
    """Tool-authored report text never uses the forbidden words. Cited spans, the expert's own
    reasons and notes, and the word a withheld rationale used are exempt. A model's rationale is
    checked item by item before it is shown (core/review/withheld.py), so one that reaches the
    page anyway, or a model's reason, is checked like Mabillon's."""
    own_text = WITHHELD_WORD.sub("", EXPERT_SPAN.sub("", QUOTED_SPAN.sub("", html)))
    m = FORBIDDEN_WORDS.search(own_text)
    if m:
        start = max(0, m.start() - 60)
        raise InvariantViolation(
            f"report says {m.group(0)!r}: ...{own_text[start : m.end() + 60]}..."
        )
