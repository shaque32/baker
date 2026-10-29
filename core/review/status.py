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
  as Mabillon's finding put to the expert, never as a verdict: the verdict stays unproven, and under
  rules 0.2.0 an AI acceptance alone never makes a claim supported; the expert decides.
- "Contradiction found, confirm to finalize" when the verdict is unproven and a contradicting
  item on a core assumption has no expert decision yet. Under rules 0.3.0 a model's
  "contradicts" counts only once an expert accepts it, so this is the step that finalizes the
  verdict: one confirm (with the expert's reason) makes the claim contradicted on the next
  verdict run. It takes precedence over "Support found", since an open contradiction blocks
  supported anyway. Under rules 0.4.0 the same holds for a failed check on a core assumption
  the testability step proposed (`agent_fails`, core/audit/testability.py): it counts once the
  expert confirms that failure, and the expert may reject the agent's proposal instead.
- "Labeling incomplete" when the run shown is an audit that has not finished (still running, or
  stopped) and has not finished this claim. Such a claim has no verdict and no evidence on
  screen or in the report; it appears for review only once all its candidates are labeled.

Withheld rationales (core/review/withheld.py): `withheld` lists the claim's evidence items whose
model rationale uses a forbidden word, with whether the expert has acknowledged each. It never
changes the label or the verdict; it adds a step to needs(), and the verdict cannot be confirmed
or overridden until every one is acknowledged.

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
    CheckOutcome,
    CheckResult,
    Claim,
    EvidenceItem,
    EvidenceStatus,
    Stance,
    SupportedBasis,
    Verdict,
    VerdictDecision,
)
from core.review import device_names
from core.review import withheld as withheld_rationales
from core.review.withheld import Withheld

SUPPORTED_AI = "Supported (AI-reviewed)"
SUPPORTED_EXPERT = "Supported (expert-confirmed)"
AWAITING_EXPERT = "Support found: do you agree?"
CONTRADICTION_FOUND = "Contradiction found, confirm to finalize"
# what the expert does about it, worded the same on the screen and in the report
CONFIRM_STEP = (
    "Mabillon found {n} record(s) it reads as contradicting a core assumption. Confirm each one "
    "you agree with, giving your reason, to finalize the verdict as contradicted; dismiss the "
    "rest."
)
# what the expert does about a failed check on an agent's assumption (rules 0.4.0)
AGENT_FAIL_STEP = (
    "{n} check(s) failed on an assumption the testability agent proposed and an examiner "
    "accepted. A failure there counts only once you confirm it, since the agent may have named "
    "the wrong phone or time window. Confirm each failure you agree with, giving your reason, "
    "to finalize the verdict as contradicted, or reject the agent's proposal so the next audit "
    "does not use it."
)
AGENT_STEP = (
    "Proposed by agent: the testability agent proposed assumptions that would make this claim "
    "testable. Accept or reject them on the claim page; nothing is used until you accept."
)
# the step a withheld rationale adds, worded the same on the screen and in the report
WITHHELD_STEP = (
    "{n} model rationale(s) withheld: each uses a word Mabillon does not print. Read each "
    "item's record and quote yourself, then acknowledge it; the verdict cannot be confirmed or "
    "overridden until you do."
)
NOT_AUDITED = "Not audited"
LABELING_INCOMPLETE = "Labeling incomplete"
NOT_TESTED = "Unproven, not tested"
RULES_PENDING = "Unproven (rules not written yet)"

AGAINST = (Stance.CONTRADICTS, Stance.COMPLICATES)

# Why an unproven claim is unproven, in plain words: one line per kind of core assumption the
# rules found not covered. Read from the stored verdict's coverage; it decides nothing. The
# overview and the report print the same words. Each line says only that the part is not
# established, never why in detail (the rule reasons do that) and never that something did not
# happen.
GAP_TOPICS: dict[AssumptionKind, str] = {
    AssumptionKind.MEANING: "Meaning of words",
    AssumptionKind.IDENTITY: "Who is behind an account",
    AssumptionKind.EVENT: "Event or role",
    AssumptionKind.TIME: "Time",
    AssumptionKind.COMPLETENESS: "Search coverage",
}
OTHER_RULE = (
    "Other verdict rule",
    "No coverage gap; another verdict rule keeps it unproven. The rule's reasons are listed "
    "with the claim.",
)
STALE = (
    "Not current",
    "Something this verdict rests on changed after the run. Re-run the verdicts, or the full "
    "audit after a claim edit or an identity or person change, to see what is still not "
    "established.",
)
GAP_TEXT: dict[AssumptionKind, str] = {
    AssumptionKind.MEANING: "What the words mean, as the claim reads them, is not established.",
    AssumptionKind.IDENTITY: "The identity link the claim states is not established.",
    AssumptionKind.EVENT: "The event or role the claim states is not established.",
    AssumptionKind.TIME: "The time the claim states is not established.",
    AssumptionKind.COMPLETENESS: (
        "What the claim states about the records is not established by the searches; the "
        "searches and each source's coverage are listed with the claim."
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
    # a stipulation, person or identity-link decision was made after the run (case-wide)
    case_changed_after_run: bool = False
    unlabeled: str | None = None  # why the run did not send this claim's evidence to the model
    not_tested: str | None = None  # why nothing was checked: the claim got no core assumption
    incomplete: bool = False  # the run shown has not finished labeling this claim
    # the testability step proposed assumptions for this untested claim and no expert has
    # accepted or rejected them yet (core/audit/testability.py; the claim page's card)
    agent_waiting: bool = False
    # failed checks on a core assumption the shown audit took from the testability step that no
    # expert has confirmed (rules 0.4.0, rule 1a): each keeps the claim unproven until confirmed
    agent_fails: list[CheckResult] = field(default_factory=list)
    # evidence items whose rationale is withheld for a forbidden word (core/review/withheld.py)
    withheld: list[Withheld] = field(default_factory=list)

    @property
    def withheld_waiting(self) -> int:
        """Withheld rationales the expert has not acknowledged yet."""
        return sum(1 for w in self.withheld if not w.acknowledged)

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
            and (self.open_contradicts > 0 or bool(self.agent_fails))
        )

    def confirm_steps(self) -> list[str]:
        """What the expert does to finalize a contradiction found, worded the same on the screen
        and in the report: the contradicting items, then the failed checks on agent assumptions."""
        if not self.contradiction_found:
            return []
        out = [CONFIRM_STEP.format(n=self.open_contradicts)] if self.open_contradicts else []
        if self.agent_fails:
            out.append(AGENT_FAIL_STEP.format(n=len(self.agent_fails)))
        return out

    @property
    def untested(self) -> bool:
        """No core assumption, so nothing was checked; an expert override says otherwise."""
        return (
            self.not_tested is not None
            and self.decision is not None
            and self.decision.override_note is None
        )

    @property
    def stale(self) -> bool:
        """Something the verdict rests on changed after the run: an evidence decision, the claim
        text, or a case-wide stipulation, person or identity-link decision. Case-wide changes
        mark every claim, which only asks for a re-run that is cheap (rules only, no model)."""
        return self.decided_after_run or self.edited_after_run or self.case_changed_after_run

    def _explainable(self) -> bool:
        """An unproven verdict nobody overrode, whose stored coverage is still current."""
        d = self.decision
        return not (
            d is None
            or d.verdict != Verdict.UNPROVEN
            or d.override_note is not None
            or self.incomplete
            or self.untested
            or self.stale
            or pipeline.RULES_PENDING_REASON in d.reasons
        )

    def gaps(self) -> list[AssumptionKind]:
        """The kinds of core assumption the stored verdict found not covered, in claim order, for
        an unproven verdict nobody overrode. Each is "not established" whatever else waits on the
        expert. Empty for any other claim, and while the verdict is stale."""
        if not self._explainable():
            return []
        d = self.decision
        if d is None:
            return []
        uncovered = {cv.assumption_id for cv in d.coverage if not cv.covered}
        out: list[AssumptionKind] = []
        for a in self.assumptions:
            if a.is_core and a.id in uncovered and a.kind not in out:
                out.append(a.kind)
        return out

    def explain_lines(self) -> list[tuple[str, str]]:
        """(topic, text) lines for the overview and the report: "Not current" for any verdict
        nobody overrode that a later change made stale; else for an unproven claim one line per
        gap, or, when every core assumption is covered and nothing waits on the expert, one line
        pointing to the other rule that holds it."""
        d = self.decision
        if (
            self.stale
            and d is not None
            and d.override_note is None
            and not (self.incomplete or self.untested)
            and pipeline.RULES_PENDING_REASON not in d.reasons  # nothing was decided
        ):
            return [STALE]
        kinds = self.gaps()
        if kinds:
            return [(GAP_TOPICS[k], GAP_TEXT[k]) for k in kinds]
        if self._explainable() and not (self.awaiting_expert or self.contradiction_found):
            return [OTHER_RULE]
        return []

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
        if self.untested and self.agent_waiting:
            out.append((1, AGENT_STEP))
        if self.untested:
            out.append(
                (
                    1,
                    "Not tested: Mabillon could not set up what to check, so no record was "
                    "searched. Check this claim yourself, then confirm or override the verdict.",
                )
            )
        if self.withheld_waiting:
            out.append((1, WITHHELD_STEP.format(n=self.withheld_waiting)))
        more = self.decision.verdict == Verdict.SUPPORTED  # already carried; review is optional
        if self.contradiction_found:
            out.append((1, f"{CONTRADICTION_FOUND}. {' '.join(self.confirm_steps())}"))
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
                    f"Mabillon found {self.open_support} record(s) it reads as support. Check each "
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
    "Mabillon checks claims against records on the phones. When it could not set up a check, "
    "compare the claim with what this case holds:"
)


def case_holdings(conn: sqlite3.Connection) -> list[str]:
    """One line per imported extraction source, with the devices it holds, exactly as imported.

    Shown next to a claim Mabillon could not test, so the expert can check a claim about the
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
    changed = case_changed_after(conn, run) if run else False
    waiting = agent_waiting(conn, run)
    agent = _agent(conn, run)
    return [
        _state(conn, c, run, edited, changed, waiting, agent)
        for c in pipeline.load_claims(conn, include_removed)
    ]


def claim_state(conn: sqlite3.Connection, claim_id: str) -> ClaimState | None:
    run = pipeline.view_run(conn)
    edited = edited_after(conn, run["started_at_utc"]) if run else set()
    changed = case_changed_after(conn, run) if run else False
    for c in pipeline.load_claims(conn, include_removed=True):
        if c.id == claim_id:
            return _state(
                conn, c, run, edited, changed, agent_waiting(conn, run), _agent(conn, run)
            )
    return None


def agent_waiting(conn: sqlite3.Connection, run: dict | None) -> frozenset[str]:
    """Claims with a testability proposal in the run's audit that no expert has decided."""
    from core.audit import testability

    return frozenset(c for c, x in testability.proposals(conn, run).items() if x.decided is None)


@dataclass(frozen=True)
class _Agent:
    """Read once per page: the testability proposals the shown audit used (rules 0.4.0's
    agent_proposed), and the claims whose verdict an agent decision after the run may change:
    a confirmed failed check, or a rejection of the proposal that undoes an earlier confirm
    (testability.confirmed_fails), so a verdict re-run would no longer count that failure."""

    accepted: dict[str, tuple[list[str], str]] = field(default_factory=dict)
    confirmed_after: frozenset[str] = frozenset()


def _agent(conn: sqlite3.Connection, run: dict | None) -> _Agent:
    from core.audit import testability

    if run is None:
        return _Agent()
    confirmed: set[str] = set()
    later: set[str] = set()
    for action, at, p in conn.execute(
        "SELECT action, at_utc, payload_json FROM audit_log WHERE action IN (?, ?) ORDER BY seq",
        (testability.CONFIRM_ACTION, testability.REJECT_ACTION),
    ):
        cid = str(json.loads(p).get("claim_id"))
        after = at > run["started_at_utc"]
        if action == testability.CONFIRM_ACTION:
            confirmed.add(cid)
            if after:
                later.add(cid)
        elif cid in confirmed:  # a rejection clears the confirms before it
            confirmed.discard(cid)
            if after:
                later.add(cid)
    return _Agent(testability.accepted_in(conn, run), frozenset(later))


def case_changed_after(conn: sqlite3.Connection, run: dict) -> bool:
    """A stipulation, person, identity-link or device-name decision the run's verdicts did not
    see: case-wide, read once. A rules-only re-run reloads stipulations but reuses the
    assumptions, checks and searches of the full audit it came from, so identity, person and
    device-name changes count from that audit's start. A proposed link counts too: it confirms
    nothing, but it widens what the audit searches."""
    since = run["started_at_utc"]
    built = since
    source = run.get("evidence_from_run")
    if source and source != run.get("run_id"):
        row = conn.execute(
            "SELECT started_at_utc FROM pipeline_runs WHERE id = ?", (source,)
        ).fetchone()
        built = row[0] if row else since
    return (
        conn.execute(
            "SELECT 1 FROM audit_log WHERE (action LIKE 'stipulation.%' AND at_utc > ?)"
            " OR ((action LIKE 'identity.%' OR action LIKE 'person.%' OR action = ?)"
            " AND at_utc > ?) LIMIT 1",
            (since, device_names.ACTION, built),
        ).fetchone()
        is not None
    )


def _state(
    conn: sqlite3.Connection,
    claim: Claim,
    run: dict | None,
    edited: set[str],
    changed: bool = False,
    waiting: frozenset[str] = frozenset(),
    agent: _Agent | None = None,
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
    st.case_changed_after_run = changed
    st.unlabeled = (run or {}).get("unlabeled", {}).get(claim.id)
    st.assumptions = pipeline.load_assumptions(conn, items["assumptions"])
    if not any(a.is_core for a in st.assumptions):
        # Runs before this was recorded have no reason stored; the claim is untested either way.
        st.not_tested = (run or {}).get("not_tested", {}).get(claim.id) or pipeline.NOT_TESTED
        st.agent_waiting = claim.id in waiting
    st.checks = pipeline.load_checks(conn, items["checks"])
    agent = agent or _Agent()
    if claim.id in agent.accepted and any(c.outcome is CheckOutcome.FAIL for c in st.checks):
        from core.audit import testability

        st.agent_fails = testability.awaiting(
            conn, agent.accepted, claim.id, st.assumptions, st.checks
        )
    st.evidence = pipeline.load_evidence(conn, items["evidence"])
    st.last_reviewer = last_reviewers(conn, [e.id for e in st.evidence])
    st.withheld = withheld_rationales.for_items(conn, st.evidence)
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
    st.decided_after_run = st.decided_after_run or claim.id in agent.confirmed_after
    st.edited_after_run = claim.id in edited
    return st


def queue(conn: sqlite3.Connection) -> list[ClaimState]:
    """Claims sorted by what needs the expert most, then by claim id."""
    return sorted(claim_states(conn), key=lambda s: (s.priority, s.claim.id))
