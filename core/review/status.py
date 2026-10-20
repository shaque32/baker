"""What each claim needs from the expert, read from the case database. Read-only.

The review screen (ui/) and the report (core/report/) both use this module, so they always say
the same thing about a claim.

The display label comes from the stored verdict (rules.py decided it) plus the review state of
the evidence that verdict was decided on. It never upgrades a verdict:
- "Supported (expert-confirmed)" only when rules.py stored supported_basis 'confirmed'.
- "Supported (AI-reviewed)" for supported_basis 'ai_reviewed'. Rules 0.2.0 never produce it,
  but if a later rule version does, it never displays as confirmed.
- "Support found: do you agree?" when the verdict is unproven and supporting evidence on the
  claim has no expert decision yet (the AI reviewer accepted it, or nobody reviewed it). It reads
  as Baker's finding put to the expert, never as a verdict: the verdict stays unproven, and under
  rules 0.2.0 an AI acceptance alone never makes a claim supported; the expert decides.
- "Contradiction found, confirm to finalize" when the verdict is unproven and a contradicting
  item on a core assumption has no expert decision yet. Under rules 0.3.0 a model's
  "contradicts" counts only once an expert accepts it, so this is the step that finalizes the
  verdict: one confirm (with the expert's reason) makes the claim contradicted on the next
  verdict run. It takes precedence over "Support found", since an open contradiction blocks
  supported anyway.
- "Labeling incomplete" when the run shown is an audit that has not finished (still running, or
  stopped) and has not finished this claim. Such a claim has no verdict and no evidence on
  screen or in the report; it appears for review only once all its candidates are labeled.

Which run: pipeline.view_run(), the same run for the screen and the report.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from core import pipeline
from core.contracts import (
    Assumption,
    AssumptionKind,
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
AWAITING_EXPERT = "Support found: do you agree?"
CONTRADICTION_FOUND = "Contradiction found, confirm to finalize"
# what the expert does about it, worded the same on the screen and in the report
CONFIRM_STEP = (
    "Baker found {n} record(s) it reads as contradicting a core assumption. Confirm each one "
    "you agree with, giving your reason, to finalize the verdict as contradicted; dismiss the "
    "rest."
)
NOT_AUDITED = "Not audited"
LABELING_INCOMPLETE = "Labeling incomplete"
NOT_TESTED = "Unproven, not tested"
RULES_PENDING = "Unproven (rules not written yet)"

AGAINST = (Stance.CONTRADICTS, Stance.COMPLICATES)

# Why an unproven claim is unproven, in plain words: one line per kind of core assumption the
# rules found not covered. Read from the stored verdict's coverage; it decides nothing. The
# overview and the report print the same words. Absence wording says the search could not show
# it, never that something did not happen.
GAP_TOPICS: dict[AssumptionKind, str] = {
    AssumptionKind.MEANING: "Meaning of words",
    AssumptionKind.IDENTITY: "Who is behind an account",
    AssumptionKind.EVENT: "Event or role",
    AssumptionKind.TIME: "Time",
    AssumptionKind.COMPLETENESS: "Search coverage",
}
GAP_TEXT: dict[AssumptionKind, str] = {
    AssumptionKind.MEANING: (
        "No passing check or expert-accepted record shows the words mean what the claim says."
    ),
    AssumptionKind.IDENTITY: (
        "No passing check, confirmed stipulation or expert-accepted record ties the account to "
        "the person the claim names."
    ),
    AssumptionKind.EVENT: (
        "No passing check or expert-accepted record shows the event or role the claim states."
    ),
    AssumptionKind.TIME: (
        "No passing check or expert-accepted record places it at the time the claim states."
    ),
    AssumptionKind.COMPLETENESS: (
        "The sources searched cannot show the absence the claim states; the claim page lists "
        "what was searched and each source's coverage."
    ),
}


@dataclass
class ClaimState:
    claim: Claim
    where: str  # "page 1, paragraph 4"
    name: str  # what the screen and report call it: "¶4.2" for a proposed claim, else its id
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
    open_against: int = 0  # other contradicting or complicating items with no expert decision
    # contradicting items on a core assumption with no expert decision (rule 1b, rules 0.3.0)
    open_contradicts: int = 0
    expert_decided: int = 0
    decided_after_run: bool = False  # an expert decided one of its items after the run
    edited_after_run: bool = False  # the expert changed the claim text after the run
    unlabeled: str | None = None  # why the run did not send this claim's evidence to the model
    not_tested: str | None = None  # why nothing was checked: the claim got no core assumption
    incomplete: bool = False  # the run shown has not finished labeling this claim

    @property
    def awaiting_expert(self) -> bool:
        return (
            self.decision is not None
            and self.decision.verdict == Verdict.UNPROVEN
            and self.decision.override_note is None
            and (self.ai_accepted + self.open_support) > 0
        )

    def to_confirm(self, item: EvidenceItem) -> bool:
        """A contradicting item on a core assumption with no expert decision: confirming it
        (accepting it) finalizes the verdict as contradicted (rule 1b)."""
        if item.stance != Stance.CONTRADICTS or item.status == EvidenceStatus.DISMISSED:
            return False
        if self.last_reviewer.get(item.id) == "expert" and item.status != EvidenceStatus.OPEN:
            return False
        return any(a.id == item.assumption_id and a.is_core for a in self.assumptions)

    @property
    def contradiction_found(self) -> bool:
        return (
            self.decision is not None
            and self.decision.verdict == Verdict.UNPROVEN
            and self.decision.override_note is None
            and self.open_contradicts > 0
        )

    @property
    def untested(self) -> bool:
        """No core assumption, so nothing was checked; an expert override says otherwise."""
        return (
            self.not_tested is not None
            and self.decision is not None
            and self.decision.override_note is None
        )

    def gaps(self) -> list[AssumptionKind]:
        """The kinds of core assumption the rules found not covered, in claim order, for an
        unproven verdict nobody overrode, leaving out an assumption whose supporting evidence
        still waits on the expert. Empty for any other claim."""
        d = self.decision
        if (
            d is None
            or d.verdict != Verdict.UNPROVEN
            or d.override_note is not None
            or self.incomplete
            or self.untested
            or pipeline.RULES_PENDING_REASON in d.reasons
        ):
            return []
        uncovered = {cv.assumption_id for cv in d.coverage if not cv.covered}
        # support still waiting on the expert is the expert's step ("Support found"), not a gap
        pending = {
            e.assumption_id
            for e in self.evidence
            if e.stance == Stance.SUPPORTS
            and e.status != EvidenceStatus.DISMISSED
            and not (self.last_reviewer.get(e.id) == "expert" and e.status != EvidenceStatus.OPEN)
        }
        out: list[AssumptionKind] = []
        for a in self.assumptions:
            if a.is_core and a.id in uncovered and a.id not in pending and a.kind not in out:
                out.append(a.kind)
        return out

    @property
    def label(self) -> str:
        if self.incomplete:
            return LABELING_INCOMPLETE
        if self.untested:
            return NOT_TESTED
        return verdict_label(self.decision, self.awaiting_expert, self.contradiction_found)[0]

    @property
    def css(self) -> str:
        if self.incomplete:
            return "v-unp"
        return verdict_label(self.decision, self.awaiting_expert, self.contradiction_found)[1]

    @property
    def verdict_reviewed(self) -> bool:
        return self.decision is not None and self.decision.confirmed_by is not None

    def needs(self) -> list[tuple[int, str]]:
        """(priority, what the expert should do), most urgent first. Empty when done."""
        out: list[tuple[int, str]] = []
        if self.incomplete:
            return [
                (
                    8,
                    "Labeling incomplete: the audit has not finished this claim. It appears for "
                    "review once all its candidates are labeled.",
                )
            ]
        if self.decision is None:
            return [(8, "Not audited yet. Run the audit to check this claim.")]
        if self.edited_after_run:
            out.append((0, "Claim text changed after the audit. Run the full audit again."))
        if self.untested:
            out.append(
                (
                    1,
                    "Not tested: Baker could not set up what to check, so no record was "
                    "searched. Check this claim yourself, then confirm or override the verdict.",
                )
            )
        more = self.decision.verdict == Verdict.SUPPORTED  # already carried; review is optional
        if self.contradiction_found:
            out.append(
                (
                    1,
                    f"{CONTRADICTION_FOUND}. {CONFIRM_STEP.format(n=self.open_contradicts)}",
                )
            )
        if self.ai_accepted:
            out.append(
                (
                    5 if more else 1,
                    f"{self.ai_accepted} supporting item(s) the AI reviewer accepted. "
                    "Accept the ones you agree with and dismiss the rest.",
                )
            )
        if self.open_support:
            out.append(
                (
                    5 if more else 2,
                    f"Baker found {self.open_support} record(s) it reads as support. Check each "
                    "one: accept the ones you agree with and dismiss the rest.",
                )
            )
        against = self.open_against + (0 if self.contradiction_found else self.open_contradicts)
        if against:
            out.append((3, f"{against} contradicting or complicating item(s) to review."))
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


def verdict_label(
    decision: VerdictDecision | None, awaiting: bool = False, contradiction: bool = False
) -> tuple[str, str]:
    """(display text, css class) for a stored verdict. contradiction: an unproven claim has a
    contradicting item on a core assumption that waits for the expert's confirm."""
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
    if decision.verdict == Verdict.UNPROVEN and contradiction:
        return CONTRADICTION_FOUND, "v-confirm"
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


def claim_name(conn: sqlite3.Connection, claim_id: str, paragraph_id: str) -> str:
    """A short name for the screen and the report. Proposed claims have ids like
    'claim:para:<hash>:1:7:2' (core/claims/extract.py); they are named by the paragraph's printed
    label and their number in it, "¶6.2". Claims the expert numbered keep their own id."""
    prefix = f"claim:{paragraph_id}:"
    if not claim_id.startswith(prefix) or not claim_id[len(prefix) :].isdigit():
        return claim_id
    r = conn.execute(
        "SELECT para_no, label FROM govdoc_paragraphs WHERE id = ?", (paragraph_id,)
    ).fetchone()
    if r is None:
        return claim_id
    return f"\u00b6{r[1] if r[1] else '#' + str(r[0])}.{claim_id[len(prefix) :]}"


def edited_after(conn: sqlite3.Connection, since: str) -> set[str]:
    out: set[str] = set()
    for (payload,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'claim.status' AND at_utc > ?", (since,)
    ):
        p = json.loads(payload)
        if p.get("text") is not None:
            out.add(p["claim_id"])
    return out


HOLDINGS = (
    "Baker checks claims against records on the phones. When it could not set up a check, "
    "compare the claim with what this case holds:"
)


def case_holdings(conn: sqlite3.Connection) -> list[str]:
    """One line per imported extraction source, with the devices it holds, exactly as imported.

    Shown next to a claim Baker could not test, so the expert can check a claim about the
    case's own material ("based on extraction reports for two phones") against it at a glance.
    """
    devices: dict[str, list[str]] = {}
    for source_id, label, model, os_version in conn.execute(
        "SELECT source_id, label, model, os_version FROM devices ORDER BY id"
    ):
        what = model or label
        devices.setdefault(source_id, []).append(f"{what}, {os_version}" if os_version else what)
    out = []
    for sid, kind, fidelity, extraction, name, sha in conn.execute(
        "SELECT id, kind, fidelity, extraction_type, file_name, sha256 FROM sources"
        " WHERE kind != 'govdoc' ORDER BY id"
    ):
        held = "; ".join(devices.get(sid, [])) or "no device recorded"
        out.append(
            f"{name}: {held} ({kind.replace('_', ' ')}, {fidelity.replace('_', ' ')}, "
            f"{extraction.replace('_', ' ')} extraction, SHA-256 {sha[:12]}…)"
        )
    return out


def claim_states(
    conn: sqlite3.Connection, include_removed: bool = False, run: dict | None = None
) -> list[ClaimState]:
    """One state per claim, in claim id order, against pipeline.view_run() unless run is given."""
    run = pipeline.view_run(conn) if run is None else run
    edited = edited_after(conn, run["started_at_utc"]) if run else set()
    return [_state(conn, c, run, edited) for c in pipeline.load_claims(conn, include_removed)]


def claim_state(conn: sqlite3.Connection, claim_id: str) -> ClaimState | None:
    run = pipeline.view_run(conn)
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
        name=claim_name(conn, claim.id, claim.paragraph_id),
        paragraph_text=ptext,
        run_id=run["run_id"] if run else None,
        decision=decision,
    )
    order = (run or {}).get("claim_order") or ()
    if (run or {}).get("partial") and claim.id in order and decision is None:
        st.incomplete = True
    if not items or decision is None:
        return st
    st.unlabeled = (run or {}).get("unlabeled", {}).get(claim.id)
    st.assumptions = pipeline.load_assumptions(conn, items["assumptions"])
    if not any(a.is_core for a in st.assumptions):
        # Runs before this was recorded have no reason stored; the claim is untested either way.
        st.not_tested = (run or {}).get("not_tested", {}).get(claim.id) or pipeline.NOT_TESTED
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
            if st.to_confirm(e):
                st.open_contradicts += 1
            else:
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
