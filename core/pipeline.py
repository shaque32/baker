"""The audit pipeline: claims -> assumptions -> checks -> retrieval -> stance -> quote check
-> AI review -> verdict rules -> invariants -> stored verdict.

Every step is a component that implements a protocol from core/contracts.py. The pipeline
only moves data between them, stores it, and refuses anything that breaks a rule:

- A stance label whose quote fails verification is dropped and never stored as evidence. The
  model calls components record (component.recorder.calls) are stored in model_calls, and the
  call behind a failed quote is stored as quote_failed.
- A label that names a different assumption or record than the one it was asked about is
  dropped.
- The AI reviewer sees supporting items only, and never sees the labeler's rationale. A
  reviewer error, or an answer other than ai_accepted or dismissed, counts as a dismissal.
  An item the reviewer cannot review (Components.reviewable, for example a quote in a script
  it cannot read) is not shown to it and stays open for the expert.
- Each evidence item is reviewed once. After an expert decision, the AI never reviews the item
  again, so a human decision always overrides the AI reviewer (evidence_reviews is append-only
  and the latest row is the status).
- The verdict comes from the rule (core/audit/rules.py). While the rules are a stub, the claim
  is stored as unproven with a reason saying no verdict was decided.
- core/audit/invariants.py re-checks every decision against the stored records. A violation
  rolls back the run's work, marks the pipeline run failed, and stops.

Runs. Each run_audit call is one pipeline_runs row. Verdicts belong to a run. Assumptions,
check results and evidence items have content-derived ids (core/contracts.py), so a re-run on
the same inputs reuses the same rows and their reviews. The audit log entry for a completed run
lists, per claim, the assumption, check and evidence ids that run considered; reports and
predictions read the latest completed run through that manifest.

Plugging in a module. A real component lives in the module ARCHITECTURE.md names and exposes
`create(conn) -> <implementation>` (for checks, a list). real_components() imports them and
names anything missing. Fakes for the skeleton live in eval/pipeline_fakes.py, and any component
whose module is under eval/ marks the run as fake, which the report and the eval print plainly.
"""

from __future__ import annotations

import importlib
import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.audit import invariants, rules
from core.contracts import (
    CONTRACTS_VERSION,
    Assumption,
    AssumptionBuilder,
    AssumptionCoverage,
    AssumptionKind,
    AssumptionParams,
    CheckOutcome,
    CheckResult,
    Claim,
    ClaimExtractor,
    ClaimStatus,
    ClaimType,
    DeterministicCheck,
    EvidenceItem,
    EvidenceReviewer,
    EvidenceStatus,
    GovDocParagraph,
    ModelCallOutcome,
    ModelRun,
    PipelineRunStatus,
    Prediction,
    ProvenanceTier,
    QuoteVerifier,
    Retriever,
    ReviewDecision,
    ReviewerKind,
    SourceRef,
    Stance,
    StanceLabeler,
    Stipulation,
    StipulationKind,
    StipulationStatus,
    SupportedBasis,
    Verdict,
    VerdictDecision,
    VerdictRule,
    canonical_json,
    evidence_id,
    review_id,
    verdict_id,
)
from core.review import audit_log

PIPELINE_VERSION = "0.1.0"
RUN_ACTION = "pipeline.run"
HALT_ACTION = "pipeline.halted"
RULES_PENDING_REASON = (
    "Verdict rules are not written yet (core/audit/rules.py is a stub). No verdict was decided; "
    "the claim stays unproven."
)

ContextBuilder = Callable[[sqlite3.Connection, Assumption, EvidenceItem], str]
Clock = Callable[[], datetime]


class ComponentsMissing(Exception):
    pass


def _always(item: EvidenceItem) -> bool:
    return True


@dataclass
class Components:
    assumptions: AssumptionBuilder
    retriever: Retriever
    labeler: StanceLabeler
    verify_quote: QuoteVerifier
    reviewer: EvidenceReviewer
    context: ContextBuilder
    checks: Sequence[DeterministicCheck] = ()
    rule: VerdictRule = rules.decide_verdict  # type: ignore[assignment]
    rule_version: str = rules.RULE_VERSION
    model_runs: Sequence[ModelRun] = ()
    k: int = 20
    reviewable: Callable[[EvidenceItem], bool] = _always

    def names(self) -> dict[str, str]:
        def name(obj: object) -> str:
            t = obj if callable(obj) and hasattr(obj, "__qualname__") else type(obj)
            return f"{t.__module__}.{t.__qualname__}"

        out = {
            "assumptions": name(self.assumptions),
            "retriever": name(self.retriever),
            "labeler": name(self.labeler),
            "verify_quote": name(self.verify_quote),
            "reviewer": name(self.reviewer),
            "context": name(self.context),
            "rule": name(self.rule),
        }
        for c in self.checks:
            out[f"check:{c.name}@{c.version}"] = name(c)
        return out

    def fake(self) -> bool:
        return any(v.startswith("eval.") for v in self.names().values())

    def rules_pending(self) -> bool:
        return self.rule is rules.decide_verdict and rules.RULE_VERSION.endswith("-stub")


REAL_MODULES = {
    "assumptions": "core.audit.assumptions",
    "retriever": "core.audit.retrieval",
    "labeler": "core.audit.stance",
    "verify_quote": "core.audit.quotes",
    "reviewer": "core.audit.review",
    "context": "core.audit.context",
    "checks": "core.audit.checks",
}


def real_components(
    conn: sqlite3.Connection,
    replace: dict[str, object] | None = None,
    filler: object | None = None,
) -> Components:
    """The product's components. Each module exposes create(conn).

    replace supplies some components directly (the eval's hostile mode swaps in a worst-case
    labeler and reviewer); those modules are not imported. filler is handed to
    core.audit.assumptions.create(conn, filler=...): the local model's template filler, or an
    expert's (or the signed eval spec's) entries. With no filler the builder proposes nothing,
    so every claim stays unproven.
    """
    built: dict[str, object] = dict(replace or {})
    missing: list[str] = []
    reviewable: Callable[[EvidenceItem], bool] = _always
    for key, module in REAL_MODULES.items():
        if key in built:
            continue
        try:
            mod = importlib.import_module(module)
        except ModuleNotFoundError:
            missing.append(module)
            continue
        create = getattr(mod, "create", None)
        if create is None:
            missing.append(f"{module}.create")
            continue
        built[key] = (
            create(conn, filler=filler) if key == "assumptions" and filler else create(conn)
        )
        if key == "reviewer" and hasattr(mod, "is_reviewable"):
            reviewable = mod.is_reviewable
    if missing:
        raise ComponentsMissing("not built yet: " + ", ".join(missing))
    return Components(
        assumptions=built["assumptions"],  # type: ignore[arg-type]
        retriever=built["retriever"],  # type: ignore[arg-type]
        labeler=built["labeler"],  # type: ignore[arg-type]
        verify_quote=built["verify_quote"],  # type: ignore[arg-type]
        reviewer=built["reviewer"],  # type: ignore[arg-type]
        context=built["context"],  # type: ignore[arg-type]
        checks=tuple(built["checks"]),  # type: ignore[call-overload]
        model_runs=tuple(r for c in built.values() for r in getattr(c, "model_runs", ())),
        reviewable=reviewable,
    )


@dataclass
class RunResult:
    run_id: str
    fake: bool
    decisions: list[VerdictDecision] = field(default_factory=list)
    dropped_labels: int = 0
    stored_items: int = 0
    reviewer_failures: int = 0
    manifest: dict[str, dict[str, list[str]]] = field(default_factory=dict)


# ---------------------------------------------------------------- helpers


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


def _now(clock: Clock | None) -> datetime:
    return (clock or (lambda: datetime.now(UTC)))()


# ---------------------------------------------------------------- loading


def load_claims(conn: sqlite3.Connection, include_removed: bool = False) -> list[Claim]:
    rows = conn.execute(
        "SELECT id, paragraph_id, text, claim_type, status, model_run_id FROM claims ORDER BY id"
    )
    claims = [
        Claim(
            id=r[0],
            paragraph_id=r[1],
            text=r[2],
            claim_type=ClaimType(r[3]),
            status=ClaimStatus(r[4]),
            model_run_id=r[5],
        )
        for r in rows
    ]
    return [c for c in claims if include_removed or c.status != ClaimStatus.REMOVED]


def _assumption(r: tuple) -> Assumption:
    return Assumption(
        id=r[0],
        claim_id=r[1],
        kind=AssumptionKind(r[2]),
        template_id=r[3],
        template_version=r[4],
        params=AssumptionParams.model_validate_json(r[5]),
        text=r[6],
        is_core=bool(r[7]),
        tier=ProvenanceTier(r[8]),
    )


_ASSUMPTION_COLS = (
    "id, claim_id, kind, template_id, template_version, params_json, text, is_core, tier"
)


def load_assumptions(conn: sqlite3.Connection, ids: Sequence[str]) -> list[Assumption]:
    out = []
    for aid in ids:
        r = conn.execute(
            f"SELECT {_ASSUMPTION_COLS} FROM assumptions WHERE id = ?",  # noqa: S608
            (aid,),
        ).fetchone()
        if r is not None:
            out.append(_assumption(r))
    return out


def evidence_status(conn: sqlite3.Connection, eid: str) -> EvidenceStatus:
    r = conn.execute("SELECT status FROM evidence_status WHERE evidence_id = ?", (eid,)).fetchone()
    return EvidenceStatus(r[0]) if r else EvidenceStatus.OPEN


def load_evidence(conn: sqlite3.Connection, ids: Sequence[str]) -> list[EvidenceItem]:
    out = []
    for eid in ids:
        r = conn.execute(
            "SELECT e.id, e.assumption_id, e.record_id, e.source_id, e.locator, e.stance,"
            " e.quote, e.rationale, e.tier, s.status, e.model_run_id FROM evidence_items e"
            " JOIN evidence_status s ON s.evidence_id = e.id WHERE e.id = ?",
            (eid,),
        ).fetchone()
        if r is None:
            continue
        out.append(
            EvidenceItem(
                id=r[0],
                assumption_id=r[1],
                record_id=r[2],
                ref=SourceRef(source_id=r[3], locator=r[4]),
                stance=Stance(r[5]),
                quote=r[6],
                quote_verified=True,
                rationale=r[7],
                tier=ProvenanceTier(r[8]),
                status=EvidenceStatus(r[9]),
                model_run_id=r[10],
            )
        )
    return out


def load_checks(conn: sqlite3.Connection, ids: Sequence[str]) -> list[CheckResult]:
    out = []
    for cid in ids:
        r = conn.execute(
            "SELECT id, assumption_id, check_name, check_version, outcome, searched,"
            " record_ids_json, source_ids_json, detail FROM check_results WHERE id = ?",
            (cid,),
        ).fetchone()
        if r is None:
            continue
        out.append(
            CheckResult(
                id=r[0],
                assumption_id=r[1],
                check_name=r[2],
                check_version=r[3],
                outcome=CheckOutcome(r[4]),
                searched=r[5],
                record_ids=tuple(json.loads(r[6])),
                source_ids=tuple(json.loads(r[7])),
                detail=r[8],
            )
        )
    return out


def load_stipulations(conn: sqlite3.Connection) -> list[Stipulation]:
    rows = conn.execute(
        "SELECT id, kind, subject_id, person_id, statement, status, decided_by, decided_at_utc"
        " FROM stipulations ORDER BY id"
    )
    return [
        Stipulation(
            id=r[0],
            kind=StipulationKind(r[1]),
            subject_id=r[2],
            person_id=r[3],
            statement=r[4],
            status=StipulationStatus(r[5]),
            decided_by=r[6],
            decided_at_utc=_dt(r[7]),
        )
        for r in rows
    ]


def load_verdict(conn: sqlite3.Connection, claim_id: str, run_id: str) -> VerdictDecision | None:
    r = conn.execute(
        "SELECT id, claim_id, pipeline_run_id, verdict, supported_basis, rule_version,"
        " reasons_json, coverage_json, cited_json, decided_at_utc, confirmed_by, override_note"
        " FROM verdicts WHERE claim_id = ? AND pipeline_run_id = ?",
        (claim_id, run_id),
    ).fetchone()
    if r is None:
        return None
    cited = json.loads(r[8])
    return VerdictDecision(
        id=r[0],
        claim_id=r[1],
        pipeline_run_id=r[2],
        verdict=Verdict(r[3]),
        supported_basis=SupportedBasis(r[4]) if r[4] else None,
        rule_version=r[5],
        reasons=tuple(json.loads(r[6])),
        coverage=tuple(AssumptionCoverage.model_validate(c) for c in json.loads(r[7])),
        cited_evidence_ids=tuple(cited.get("evidence", ())),
        cited_check_ids=tuple(cited.get("checks", ())),
        cited_stipulation_ids=tuple(cited.get("stipulations", ())),
        decided_at_utc=_dt(r[9]),  # type: ignore[arg-type]
        confirmed_by=r[10],
        override_note=r[11],
    )


def last_run(conn: sqlite3.Connection) -> dict | None:
    """The latest completed run: the pipeline_runs row plus its audit-log manifest."""
    r = conn.execute(
        "SELECT id, started_at_utc, finished_at_utc, baker_version, contracts_version,"
        " rule_version, config_json FROM pipeline_runs WHERE status = 'completed'"
        " ORDER BY started_at_utc DESC, id DESC LIMIT 1"
    ).fetchone()
    if r is None:
        return None
    for (payload_json,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq DESC", (RUN_ACTION,)
    ):
        payload = json.loads(payload_json)
        if payload["run_id"] == r[0]:
            break
    else:
        raise invariants.InvariantViolation(f"{r[0]} completed but has no audit-log manifest")
    return {
        **payload,
        "started_at_utc": r[1],
        "finished_at_utc": r[2],
        "baker_version": r[3],
        "contracts_version": r[4],
        "rule_version": r[5],
        "config": json.loads(r[6]),
    }


# ---------------------------------------------------------------- claims step


def extract_claims(
    conn: sqlite3.Connection, extractor: ClaimExtractor, paragraphs: list[GovDocParagraph]
) -> list[Claim]:
    """Store the extractor's proposals. The expert then accepts, edits or removes each one."""
    claims = extractor.extract(paragraphs)
    para_ids = {p.id for p in paragraphs}
    with conn:
        for c in claims:
            if c.paragraph_id not in para_ids:
                raise ValueError(f"{c.id} cites paragraph {c.paragraph_id}, which was not given")
            if c.status != ClaimStatus.PROPOSED:
                raise ValueError(f"{c.id}: an extractor only proposes claims")
            conn.execute(
                "INSERT INTO claims (id, paragraph_id, text, claim_type, status, model_run_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (c.id, c.paragraph_id, c.text, c.claim_type.value, c.status.value, c.model_run_id),
            )
    return claims


# ---------------------------------------------------------------- audit step


class _Run:
    """State for one pipeline run."""

    def __init__(self, conn: sqlite3.Connection, c: Components, now: datetime, result: RunResult):
        self.conn = conn
        self.c = c
        self.now = now
        self.result = result
        self.run_id = result.run_id
        self.flushed: dict[int, int] = {}
        self.review_run = next((m.id for m in c.model_runs if m.purpose == "review"), None)

    # -- model calls

    def flush_calls(self, quote_failed: set[str] = frozenset()) -> None:  # type: ignore[assignment]
        """Store the ModelCall rows components recorded (component.recorder.calls).

        A call whose label was dropped because its quote failed is stored as quote_failed.
        """
        for comp in (self.c.labeler, self.c.reviewer):
            recorder = getattr(comp, "recorder", None)
            calls = getattr(recorder, "calls", None)
            if calls is None:
                continue
            done = self.flushed.get(id(comp), 0)
            for call in calls[done:]:
                if call.id in quote_failed:
                    call = call.model_copy(update={"outcome": ModelCallOutcome.QUOTE_FAILED})
                self.conn.execute(
                    "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt,"
                    " raw_output, outcome, error, at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        call.id,
                        call.model_run_id,
                        call.seq,
                        canonical_json(list(call.subject_ids)),
                        call.prompt,
                        call.raw_output,
                        call.outcome.value,
                        call.error,
                        iso(call.at_utc),
                    ),
                )
            self.flushed[id(comp)] = len(calls)

    # -- stance

    def _label(self, a: Assumption, cand) -> EvidenceItem | None:  # noqa: ANN001
        try:
            label = self.c.labeler.label(a, cand)
        except Exception:  # noqa: BLE001 - bad model output is dropped, never guessed at
            self.flush_calls()
            return self._drop()
        if label.assumption_id != a.id or label.record_id != cand.record_id:
            self.flush_calls()
            return self._drop()
        text = invariants.record_text(self.conn, cand.record_id)
        if text is None or not self.c.verify_quote(label.quote, text):
            self.flush_calls({label.model_call_id} if label.model_call_id else set())
            return self._drop()
        self.flush_calls()
        return EvidenceItem(
            id=evidence_id(a.id, cand.record_id, label.stance, label.quote),
            assumption_id=a.id,
            record_id=cand.record_id,
            ref=cand.ref,
            stance=label.stance,
            quote=label.quote,
            quote_verified=True,
            rationale=label.rationale,
            tier=cand.tier,
            status=EvidenceStatus.OPEN,
            model_run_id=label.model_run_id,
        )

    def _drop(self) -> None:
        self.result.dropped_labels += 1
        return None

    # -- review

    def _next_seq(self, eid: str) -> int:
        return (
            self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM evidence_reviews WHERE evidence_id = ?", (eid,)
            ).fetchone()[0]
            + 1
        )

    def _insert_review(self, d: ReviewDecision) -> None:
        self.conn.execute(
            "INSERT INTO evidence_reviews (id, evidence_id, seq, reviewer_kind, reviewer, status,"
            " reason, model_run_id, model_call_id, decided_at_utc)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                d.id,
                d.evidence_id,
                d.seq,
                d.reviewer_kind.value,
                d.reviewer,
                d.status.value,
                d.reason,
                d.model_run_id,
                d.model_call_id,
                iso(d.decided_at_utc),
            ),
        )

    def _review(self, a: Assumption, item: EvidenceItem) -> None:
        """One AI review per item, never after any earlier review. Fails closed."""
        if item.stance != Stance.SUPPORTS or self._next_seq(item.id) > 1:
            return
        if not self.c.reviewable(item):
            return  # stays open for the expert
        seq = 1
        blind = item.model_copy(update={"rationale": ""})  # the reviewer never sees it
        try:
            d = self.c.reviewer.review(a, blind, self.c.context(self.conn, a, blind))
            self.flush_calls()
            ok = (
                isinstance(d, ReviewDecision)
                and d.evidence_id == item.id
                and d.reviewer_kind == ReviewerKind.AI
                and d.status in (EvidenceStatus.AI_ACCEPTED, EvidenceStatus.DISMISSED)
            )
            if not ok:
                raise ValueError(f"reviewer returned {d!r}")
            d = d.model_copy(update={"id": review_id(item.id, seq), "seq": seq})
        except Exception as e:  # noqa: BLE001 - any reviewer failure is a dismissal
            self.result.reviewer_failures += 1
            run = getattr(self.c.reviewer, "model_run_id", None) or self.review_run
            if run is None:
                return  # no AI run to attribute a dismissal to; the item stays open
            d = ReviewDecision(
                id=review_id(item.id, seq),
                evidence_id=item.id,
                seq=seq,
                reviewer_kind=ReviewerKind.AI,
                reviewer="ai:reviewer-error",
                status=EvidenceStatus.DISMISSED,
                reason=f"Reviewer failed, counted as a dismissal: {type(e).__name__}",
                model_run_id=run,
                decided_at_utc=self.now,
            )
        self._insert_review(d)
        self.flush_calls()

    # -- claim

    def claim(self, claim: Claim, stipulations: list[Stipulation]) -> VerdictDecision:
        conn, c = self.conn, self.c
        assumptions = list(c.assumptions.build(claim))
        for a in assumptions:
            if a.claim_id != claim.id:
                raise invariants.InvariantViolation(f"assumption {a.id} built for {a.claim_id}")
            conn.execute(
                f"INSERT OR IGNORE INTO assumptions ({_ASSUMPTION_COLS})"  # noqa: S608
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    a.id,
                    a.claim_id,
                    a.kind.value,
                    a.template_id,
                    a.template_version,
                    canonical_json(a.params),
                    a.text,
                    int(a.is_core),
                    a.tier.value,
                ),
            )

        checks: list[CheckResult] = []
        evidence_ids: list[str] = []
        for a in assumptions:
            for chk in c.checks:
                applies = getattr(chk, "applies_to", None)
                if applies is not None and not applies(a):
                    continue
                r = chk.run(a, conn)
                if r.assumption_id != a.id:
                    raise invariants.InvariantViolation(f"check {r.id} answered {r.assumption_id}")
                conn.execute(
                    "INSERT OR REPLACE INTO check_results (id, assumption_id, check_name,"
                    " check_version, outcome, searched, record_ids_json, source_ids_json, detail)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        r.id,
                        r.assumption_id,
                        r.check_name,
                        r.check_version,
                        r.outcome.value,
                        r.searched,
                        canonical_json(list(r.record_ids)),
                        canonical_json(list(r.source_ids)),
                        r.detail,
                    ),
                )
                checks.append(r)

            seen: set[str] = set()
            for cand in c.retriever.retrieve(a, conn, c.k):
                if cand.record_id in seen:
                    continue
                seen.add(cand.record_id)
                item = self._label(a, cand)
                if item is None or item.id in evidence_ids:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO evidence_items (id, assumption_id, source_id, locator,"
                    " record_id, stance, quote, rationale, tier, model_run_id)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.id,
                        item.assumption_id,
                        item.ref.source_id,
                        item.ref.locator,
                        item.record_id,
                        item.stance.value,
                        item.quote,
                        item.rationale,
                        item.tier.value,
                        item.model_run_id,
                    ),
                )
                self._review(a, item.model_copy(update={"status": evidence_status(conn, item.id)}))
                evidence_ids.append(item.id)
                self.result.stored_items += 1

        evidence = load_evidence(conn, evidence_ids)
        if c.rules_pending():
            decision = VerdictDecision(
                id=verdict_id(claim.id, self.run_id),
                claim_id=claim.id,
                pipeline_run_id=self.run_id,
                verdict=Verdict.UNPROVEN,
                rule_version=c.rule_version,
                reasons=(RULES_PENDING_REASON,),
                decided_at_utc=self.now,
            )
        else:
            decision = c.rule(claim, assumptions, evidence, checks, stipulations, self.run_id)  # type: ignore[call-arg]
        invariants.check_decision(
            conn, claim, assumptions, evidence, checks, stipulations, decision, self.run_id
        )
        conn.execute(
            "INSERT INTO verdicts (id, claim_id, pipeline_run_id, verdict, supported_basis,"
            " rule_version, reasons_json, coverage_json, cited_json, decided_at_utc,"
            " confirmed_by, override_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
            (
                decision.id,
                decision.claim_id,
                decision.pipeline_run_id,
                decision.verdict.value,
                decision.supported_basis.value if decision.supported_basis else None,
                decision.rule_version,
                canonical_json(list(decision.reasons)),
                canonical_json([cv.model_dump(mode="json") for cv in decision.coverage]),
                canonical_json(
                    {
                        "evidence": list(decision.cited_evidence_ids),
                        "checks": list(decision.cited_check_ids),
                        "stipulations": list(decision.cited_stipulation_ids),
                    }
                ),
                iso(decision.decided_at_utc),
            ),
        )
        self.result.manifest[claim.id] = {
            "assumptions": [a.id for a in assumptions],
            "checks": [r.id for r in checks],
            "evidence": evidence_ids,
        }
        return decision


def _new_run_id(conn: sqlite3.Connection, now: datetime) -> str:
    base = "run:" + now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id, n = base, 1
    while conn.execute("SELECT 1 FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone():
        n += 1
        run_id = f"{base}-{n}"
    return run_id


def run_audit(
    conn: sqlite3.Connection,
    components: Components,
    clock: Clock | None = None,
    claim_ids: Sequence[str] | None = None,
    config: dict[str, str | int | float | bool | None] | None = None,
) -> RunResult:
    """Audit every claim that is not removed (or just claim_ids). All or nothing."""
    now = _now(clock)
    result = RunResult(run_id=_new_run_id(conn, now), fake=components.fake())
    cfg = {"k": components.k, "fake": result.fake, **(config or {})}
    with conn:
        conn.execute(
            "INSERT INTO pipeline_runs (id, started_at_utc, finished_at_utc, status, baker_version,"
            " contracts_version, rule_version, config_json, note)"
            " VALUES (?, ?, NULL, ?, ?, ?, ?, ?, NULL)",
            (
                result.run_id,
                iso(now),
                PipelineRunStatus.RUNNING.value,
                PIPELINE_VERSION,
                CONTRACTS_VERSION,
                components.rule_version,
                canonical_json(cfg),
            ),
        )
    claims = load_claims(conn)
    if claim_ids is not None:
        wanted = set(claim_ids)
        claims = [cl for cl in claims if cl.id in wanted]
    try:
        with conn:
            for m in components.model_runs:
                conn.execute(
                    "INSERT OR IGNORE INTO model_runs (id, pipeline_run_id, purpose, model_name,"
                    " model_sha256, prompt_version, prompt_sha256, params_json, seed,"
                    " started_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        m.id,
                        m.pipeline_run_id or result.run_id,
                        m.purpose,
                        m.model_name,
                        m.model_sha256,
                        m.prompt_version,
                        m.prompt_sha256,
                        canonical_json(m.params),
                        m.seed,
                        iso(m.started_at_utc),
                    ),
                )
            stipulations = load_stipulations(conn)
            run = _Run(conn, components, now, result)
            for claim in claims:
                result.decisions.append(run.claim(claim, stipulations))
            audit_log.append(
                conn,
                now,
                "system",
                RUN_ACTION,
                {
                    "run_id": result.run_id,
                    "fake": result.fake,
                    "rules_pending": components.rules_pending(),
                    "components": components.names(),
                    "manifest": result.manifest,
                    "dropped_labels": result.dropped_labels,
                    "stored_items": result.stored_items,
                    "reviewer_failures": result.reviewer_failures,
                    "rejected_assumptions": [
                        {"template_id": r.proposal.template_id, "reason": r.reason}
                        for r in getattr(components.assumptions, "rejected", ())
                    ],
                },
            )
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at_utc = ? WHERE id = ?",
                (PipelineRunStatus.COMPLETED.value, iso(_now(clock)), result.run_id),
            )
    except Exception as e:
        with conn:
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at_utc = ?, note = ? WHERE id = ?",
                (PipelineRunStatus.FAILED.value, iso(_now(clock)), str(e)[:2000], result.run_id),
            )
            audit_log.append(
                conn, now, "system", HALT_ACTION, {"run_id": result.run_id, "error": str(e)}
            )
        raise
    return result


# ---------------------------------------------------------------- outputs


def predictions(conn: sqlite3.Connection) -> list[Prediction]:
    """One Prediction per claim in the latest completed run."""
    run = last_run(conn)
    if run is None:
        return []
    out = []
    for claim_id, items in sorted(run["manifest"].items()):
        v = load_verdict(conn, claim_id, run["run_id"])
        if v is None:
            continue
        cited = sorted(
            {
                e.record_id
                for e in load_evidence(conn, items["evidence"])
                if e.stance != Stance.IRRELEVANT and e.status != EvidenceStatus.DISMISSED
            }
        )
        out.append(
            Prediction(
                claim_id=claim_id,
                verdict=v.verdict,
                supported_basis=v.supported_basis,
                cited_record_ids=tuple(cited),
            )
        )
    return out
