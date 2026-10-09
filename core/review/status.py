"""What each claim needs from the expert, read from the case database. Read-only.

The review screen (ui/) and the report (core/report/) both use this module, so they always say
the same thing about a claim.

The display label comes from the stored verdict (rules.py decided it) plus the review state of
the evidence that verdict was decided on. It never upgrades a verdict:
- "Supported (expert-confirmed)" only when rules.py stored supported_basis 'confirmed'.
- "Supported (AI-reviewed)" for supported_basis 'ai_reviewed'. Rules 0.2.0 never produce it,
  but if a later rule version does, it never displays as confirmed.
- "Unproven, awaiting expert review" when the verdict is unproven and supporting evidence on the
  claim has no expert decision yet (the AI reviewer accepted it, or nobody reviewed it). Under
  rules 0.2.0 an AI acceptance alone never makes a claim supported; the expert decides.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from core import pipeline
from core.contracts import (
    Assumption,
    CheckResult,
    Claim,
    EvidenceItem,
    EvidenceStatus,
    Stance,
    SupportedBasis,
    Verdict,
    VerdictDecision,
)

SUPPORTED_AI = "Supported (AI-reviewed)"
SUPPORTED_EXPERT = "Supported (expert-confirmed)"
AWAITING_EXPERT = "Unproven, awaiting expert review"
NOT_AUDITED = "Not audited"
RULES_PENDING = "Unproven (rules not written yet)"

AGAINST = (Stance.CONTRADICTS, Stance.COMPLICATES)


@dataclass
class ClaimState:
    claim: Claim
    where: str  # "page 1, paragraph 4"
    paragraph_text: str | None
    run_id: str | None
    decision: VerdictDecision | None
    assumptions: list[Assumption] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    # evidence id -> 'ai' or 'expert' for the latest review row; absent when never reviewed
    last_reviewer: dict[str, str] = field(default_factory=dict)
    ai_accepted: int = 0  # supporting items the AI reviewer accepted, no expert decision yet
    open_support: int = 0  # supporting items nobody has reviewed
    ai_dismissed: int = 0  # supporting items the AI reviewer dismissed, no expert decision yet
    open_against: int = 0  # contradicting or complicating items with no expert decision
    expert_decided: int = 0
    decided_after_run: bool = False  # an expert decided one of its items after the run
    edited_after_run: bool = False  # the expert changed the claim text after the run
    unlabeled: str | None = None  # why the run did not send this claim's evidence to the model

    @property
    def awaiting_expert(self) -> bool:
        return (
            self.decision is not None
            and self.decision.verdict == Verdict.UNPROVEN
            and self.decision.override_note is None
            and (self.ai_accepted + self.open_support) > 0
        )

    @property
    def label(self) -> str:
        return verdict_label(self.decision, self.awaiting_expert)[0]

    @property
    def css(self) -> str:
        return verdict_label(self.decision, self.awaiting_expert)[1]

    @property
    def verdict_reviewed(self) -> bool:
        return self.decision is not None and self.decision.confirmed_by is not None

    def needs(self) -> list[tuple[int, str]]:
        """(priority, what the expert should do), most urgent first. Empty when done."""
        out: list[tuple[int, str]] = []
        if self.decision is None:
            return [(8, "Not audited yet. Run the audit to check this claim.")]
        if self.edited_after_run:
            out.append((0, "Claim text changed after the audit. Run the full audit again."))
        more = self.decision.verdict == Verdict.SUPPORTED  # already carried; review is optional
        if self.ai_accepted:
            out.append(
                (
                    5 if more else 1,
                    f"{self.ai_accepted} supporting item(s) the AI reviewer accepted. "
                    "Accept or dismiss each one.",
                )
            )
        if self.open_support:
            out.append(
                (5 if more else 2, f"{self.open_support} supporting item(s) nobody has reviewed.")
            )
        if self.open_against:
            out.append((3, f"{self.open_against} contradicting or complicating item(s) to review."))
        if self.decided_after_run:
            out.append((4, "You decided evidence after the last verdict run. Re-run verdicts."))
        if self.ai_dismissed:
            out.append(
                (
                    5,
                    f"{self.ai_dismissed} supporting item(s) the AI reviewer dismissed. "
                    "You have not reviewed them.",
                )
            )
        if not self.verdict_reviewed:
            out.append((6, "Verdict not yet confirmed or overridden by you."))
        return sorted(out)

    @property
    def priority(self) -> int:
        n = self.needs()
        return n[0][0] if n else 9


def verdict_label(decision: VerdictDecision | None, awaiting: bool = False) -> tuple[str, str]:
    """(display text, css class) for a stored verdict."""
    if decision is None:
        return NOT_AUDITED, "v-unp"
    if decision.override_note is not None:
        return f"{decision.verdict.value.capitalize()} (expert override)", _css(decision.verdict)
    if decision.verdict == Verdict.SUPPORTED:
        if decision.supported_basis == SupportedBasis.CONFIRMED:
            return SUPPORTED_EXPERT, "v-sup"
        return SUPPORTED_AI, "v-supai"
    if pipeline.RULES_PENDING_REASON in decision.reasons:
        return RULES_PENDING, "v-unp"
    if decision.verdict == Verdict.UNPROVEN and awaiting:
        return AWAITING_EXPERT, "v-await"
    return decision.verdict.value.capitalize(), _css(decision.verdict)


def _css(v: Verdict) -> str:
    return {Verdict.SUPPORTED: "v-sup", Verdict.CONTRADICTED: "v-con"}.get(v, "v-unp")


def last_reviewers(conn: sqlite3.Connection, ids: list[str]) -> dict[str, str]:
    """evidence id -> reviewer_kind of its latest review row."""
    out: dict[str, str] = {}
    for eid in ids:
        r = conn.execute(
            "SELECT reviewer_kind FROM evidence_reviews WHERE evidence_id = ?"
            " ORDER BY seq DESC LIMIT 1",
            (eid,),
        ).fetchone()
        if r is not None:
            out[eid] = r[0]
    return out


def _where(conn: sqlite3.Connection, paragraph_id: str) -> tuple[str, str | None]:
    para = conn.execute(
        "SELECT page, para_no, label, text FROM govdoc_paragraphs WHERE id = ?", (paragraph_id,)
    ).fetchone()
    if para is None:
        return "paragraph not found", None
    return f"page {para[0]}, paragraph {para[2] if para[2] else '#' + str(para[1])}", para[3]


def edited_after(conn: sqlite3.Connection, since: str) -> set[str]:
    out: set[str] = set()
    for (payload,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'claim.status' AND at_utc > ?", (since,)
    ):
        p = json.loads(payload)
        if p.get("text") is not None:
            out.add(p["claim_id"])
    return out


def claim_states(
    conn: sqlite3.Connection, include_removed: bool = False, run: dict | None = None
) -> list[ClaimState]:
    """One state per claim, in claim id order, against the latest completed run."""
    run = pipeline.last_run(conn) if run is None else run
    edited = edited_after(conn, run["started_at_utc"]) if run else set()
    return [_state(conn, c, run, edited) for c in pipeline.load_claims(conn, include_removed)]


def claim_state(conn: sqlite3.Connection, claim_id: str) -> ClaimState | None:
    run = pipeline.last_run(conn)
    edited = edited_after(conn, run["started_at_utc"]) if run else set()
    for c in pipeline.load_claims(conn, include_removed=True):
        if c.id == claim_id:
            return _state(conn, c, run, edited)
    return None


def _state(
    conn: sqlite3.Connection, claim: Claim, run: dict | None, edited: set[str]
) -> ClaimState:
    where, ptext = _where(conn, claim.paragraph_id)
    items = (run or {}).get("manifest", {}).get(claim.id)
    decision = pipeline.load_verdict(conn, claim.id, run["run_id"]) if run and items else None
    st = ClaimState(
        claim=claim,
        where=where,
        paragraph_text=ptext,
        run_id=run["run_id"] if run else None,
        decision=decision,
    )
    if not items or decision is None:
        return st
    st.unlabeled = (run or {}).get("unlabeled", {}).get(claim.id)
    st.assumptions = pipeline.load_assumptions(conn, items["assumptions"])
    st.checks = pipeline.load_checks(conn, items["checks"])
    st.evidence = pipeline.load_evidence(conn, items["evidence"])
    st.last_reviewer = last_reviewers(conn, [e.id for e in st.evidence])
    for e in st.evidence:
        if e.stance == Stance.IRRELEVANT:
            continue
        expert = st.last_reviewer.get(e.id) == "expert"
        if expert and e.status != EvidenceStatus.OPEN:
            st.expert_decided += 1
            continue
        if e.stance == Stance.SUPPORTS:
            if e.status == EvidenceStatus.AI_ACCEPTED:
                st.ai_accepted += 1
            elif e.status == EvidenceStatus.DISMISSED:
                st.ai_dismissed += 1
            else:
                st.open_support += 1
        elif e.stance in AGAINST and e.status != EvidenceStatus.DISMISSED:
            st.open_against += 1
    if st.evidence:
        marks = ",".join("?" * len(st.evidence))
        later = conn.execute(
            "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind = 'expert'"  # noqa: S608
            f" AND decided_at_utc > ? AND evidence_id IN ({marks})",
            (run["started_at_utc"], *[e.id for e in st.evidence]),  # type: ignore[index]
        ).fetchone()[0]
        st.decided_after_run = later > 0
    st.edited_after_run = claim.id in edited
    return st


def queue(conn: sqlite3.Connection) -> list[ClaimState]:
    """Claims sorted by what needs the expert most, then by claim id."""
    return sorted(claim_states(conn), key=lambda s: (s.priority, s.claim.id))
