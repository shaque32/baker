"""The audit pipeline: claims -> assumptions -> checks -> retrieval -> stance -> quote check
-> AI review -> verdict rules -> invariants -> stored verdict.

Every step is a component that implements a protocol from core/contracts.py. The pipeline
only moves data between them, stores it, and refuses anything that breaks a rule:

- A stance label whose quote fails verification is dropped and never stored as evidence. The
  quote must pass Components.verify_quote and, whatever that verifier is, the product's own
  rule: verbatim and word-aligned at a place that takes in the record's own fields, not only
  Baker's words or a placeholder such as "(no name)" (core.audit.quotes.cites_record). The model
  calls components record (component.recorder.calls) are stored in model_calls, and the call
  behind a failed quote is stored as quote_failed. Every run records the quote check that ran
  in its config, as it records the rule version (quote_check_version).
- A label that names a different assumption or record than the one it was asked about is
  dropped.
- The AI reviewer is optional and off by default (real_components(ai_review=False)): under
  rules 0.2.0 an AI acceptance decides nothing, it only sorts evidence for the expert, and it
  costs one model call per supporting item. With no reviewer every item stays open for the
  expert.
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
  rolls back that claim's work, marks the pipeline run failed, and stops.
- A claim that gets no core assumption is not tested: nothing is checked or searched, and
  rule 3a keeps it unproven. That happens when the assumption filler refuses every proposal
  (a value it cannot tie to the document or the case data fails closed). The claim's audit-log
  entry and the run's entry list it under `not_tested` with the refusals, and the report and
  review screen say "Not tested" instead of a plain unproven.
- A claim whose core check already failed is not sent to the stance model: rule 1a makes it
  contradicted whatever its evidence says, so labels could not change its verdict, and they
  cost model calls (about a fifth of case01's). The run's audit-log entry lists these claims
  under `unlabeled` with the reason, and the report and review screen say so.
  Components.label_settled turns labeling back on for them (`baker audit --label-all`).

Saving. Each claim is committed when it finishes, together with an audit-log entry naming
what it considered (CLAIM_ACTION), with SHA-256 digests of the model calls stored for it
(calls_digest), of the rows its verdict rests on, with the records they cite and the model runs
they name (rows_digest), and of the claim (claim_digest), and the verdict's time. The run's
entry (RUN_ACTION) records a digest of its pipeline_runs row's fixed columns (run_digest).
The model work for a claim (assumptions, labels, AI review) runs before anything is written, and
the claim's rows are then written in one short transaction, so a long run never holds the
database locked while the model works: the expert can review finished claims on the screen
while the audit runs. If a run stops part way (a crash, a closed laptop, a missing model, an
invariant violation, the expert's Stop), the claims already finished keep their stored model
outputs, so the next run reuses them (core/audit/_local_model.py) instead of calling the model
again.

Which run is read. Predictions, the eval and redecide read only completed runs (last_run()).
The review screen and the report read view_run(): the latest completed run, unless a newer
full audit has not finished but has finished at least one claim. Then they show that run's
finished claims, each decided by the rules and checked by the invariants like any other, and
mark every claim it has not finished "Labeling incomplete" (core/review/status.py). A claim it
has not finished never shows a verdict, and an unfinished run is never scored.

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

import hashlib
import importlib
import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core import build, db
from core.audit import invariants, quotes, rules, stance
from core.audit._llm_json import ModelUnavailable
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
from core.enrich.records import get_record, kind_of
from core.ingest import forwarded
from core.review import audit_log

PIPELINE_VERSION = "0.1.0"
RUN_ACTION = "pipeline.run"
CLAIM_ACTION = "pipeline.claim"  # one per finished claim, written with the claim's rows
HALT_ACTION = "pipeline.halted"


def _stored(conn: sqlite3.Connection, table: str, where: str, params: tuple) -> list[dict]:
    cur = conn.execute(f"SELECT * FROM {table} WHERE {where}", params)  # noqa: S608 - fixed names
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur]


def calls_digest(conn: sqlite3.Connection, ids: Sequence[str]) -> dict[str, object]:
    """What a claim's audit-log entry records about the model calls stored while it ran: their
    ids and one SHA-256 over each call's whole stored row (model run, seq, subject, prompt, raw
    output, outcome, error, time), in order. core/bundle/verify.py recomputes it."""
    rows = [r for cid in ids for r in _stored(conn, "model_calls", "id = ?", (cid,))]
    return {"ids": list(ids), "sha256": _sha(canonical_json(rows))}


def claim_digest(conn: sqlite3.Connection, claim_id: str) -> str:
    """One SHA-256 over the claim's stored row (text, type, status, paragraph, model run) when
    its audit-log entry is written. A later change is the expert's and is logged (claim.status),
    so core/bundle/verify.py can tell it from an edit made outside Baker."""
    return _sha(canonical_json(_stored(conn, "claims", "id = ?", (claim_id,))))


_RECORD_TABLES = {
    "message": "messages",
    "call": "calls",
    "contact": "contacts",
    "attachment": "attachments",
}


def _cited(conn: sqlite3.Connection, record_id: str) -> dict[str, object]:
    """A cited record as stored (every column: body, sender, direction, times, locator) and as
    the labeler and the report read it (text and time, which name accounts and, for an
    attachment, its message)."""
    table = _RECORD_TABLES.get(kind_of(record_id) or "")
    rec = get_record(conn, record_id)
    return {
        "id": record_id,
        "row": _stored(conn, table, "id = ?", (record_id,)) if table else [],
        "text": rec.text if rec else None,
        "ts_utc": rec.ts_utc if rec else None,
    }


def claim_rows(
    conn: sqlite3.Connection,
    manifest: dict[str, list[str]],
    claim_id: str,
    call_ids: Sequence[str] = (),
) -> dict[str, list]:
    """The rows a claim's verdict rests on, as stored: its assumptions, check results and
    evidence items (every column: text, parameters, outcomes, source and locator, rationale,
    model run), the AI reviews of those items, the records the items cite, and the model runs
    (model, file hash, prompt, settings, seed) that the items, reviews, claim and the claim's
    model calls name. Expert decisions are bound by their own entries (evidence.decide)."""
    one = {
        "assumptions": "assumptions",
        "checks": "check_results",
        "evidence": "evidence_items",
    }
    rows: dict[str, list] = {
        key: [r for i in manifest.get(key, []) for r in _stored(conn, table, "id = ?", (i,))]
        for key, table in one.items()
    }
    rows["ai_reviews"] = [
        r
        for eid in manifest.get("evidence", [])
        for r in _stored(
            conn,
            "evidence_reviews",
            "evidence_id = ? AND reviewer_kind = 'ai' ORDER BY seq",
            (eid,),
        )
    ]
    rows["records"] = [_cited(conn, str(e["record_id"])) for e in rows["evidence"]]
    calls = [r for cid in call_ids for r in _stored(conn, "model_calls", "id = ?", (cid,))]
    claim = _stored(conn, "claims", "id = ?", (claim_id,))
    named = {
        r["model_run_id"]
        for r in (*rows["evidence"], *rows["ai_reviews"], *calls, *claim)
        if r.get("model_run_id")
    }
    rows["model_runs"] = [
        r for mid in sorted(named) for r in _stored(conn, "model_runs", "id = ?", (mid,))
    ]
    return rows


def rows_digest(
    conn: sqlite3.Connection,
    manifest: dict[str, list[str]],
    claim_id: str,
    call_ids: Sequence[str] = (),
) -> str:
    """One SHA-256 over claim_rows() when a claim's audit-log entry is written. The entry
    records it, so core/bundle/verify.py can tell a row edited later from the one the rules
    read."""
    return _sha(canonical_json(claim_rows(conn, manifest, claim_id, call_ids)))


def run_digest(conn: sqlite3.Connection, run_id: str) -> str:
    """One SHA-256 over a pipeline run's fixed columns (start time, versions, configuration
    with build, cloud decision and quote check), which its pipeline.run entry records."""
    rows = [
        {k: r[k] for k in _RUN_FIXED} for r in _stored(conn, "pipeline_runs", "id = ?", (run_id,))
    ]
    return _sha(canonical_json(rows))


_RUN_FIXED = (
    "id",
    "started_at_utc",
    "baker_version",
    "contracts_version",
    "rule_version",
    "config_json",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


RULES_PENDING_REASON = (
    "Verdict rules are not written yet (core/audit/rules.py is a stub). No verdict was decided; "
    "the claim stays unproven."
)

ContextBuilder = Callable[[sqlite3.Connection, Assumption, EvidenceItem], str]
Clock = Callable[[], datetime]


class ComponentsMissing(Exception):
    pass


class RunStopped(Exception):
    """Raised by a progress callback to stop a run between claims (the screen's Stop button).
    The run is stored as stopped, not failed; every finished claim keeps its work."""


def _always(item: EvidenceItem) -> bool:
    return True


@dataclass
class Components:
    assumptions: AssumptionBuilder
    retriever: Retriever
    labeler: StanceLabeler
    verify_quote: QuoteVerifier
    reviewer: EvidenceReviewer | None  # None: no AI review pass; items stay open for the expert
    context: ContextBuilder
    checks: Sequence[DeterministicCheck] = ()
    rule: VerdictRule = rules.decide_verdict  # type: ignore[assignment]
    rule_version: str = rules.RULE_VERSION
    model_runs: Sequence[ModelRun] = ()
    k: int = 20
    reviewable: Callable[[EvidenceItem], bool] = _always
    # Other model-backed parts whose recorder.calls the pipeline stores (the assumption filler).
    recorders: Sequence[object] = ()
    # Label claims a failed core check already decides (rule 1a) too. Off: their labels could
    # not change the verdict, so they are skipped to save model calls.
    label_settled: bool = False
    # The case's cloud choice (core/casework/cloud.py CloudChoice.record()), kept in the run's
    # config so the report says why this run's stance labels came from where they did.
    cloud: dict[str, object] | None = None

    def names(self) -> dict[str, str]:
        def name(obj: object) -> str:
            if obj is None:
                return "none"
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


def quote_check_version(components: Components) -> str:
    """The quote check a run applies: core.audit.quotes.VERSION with the product's verifier.
    Another verifier (the eval's stand-ins) runs beside quotes.cites_record, which already
    implies quotes.verify_quote, so it can only refuse more quotes; the version names it."""
    if components.verify_quote is quotes.verify_quote:
        return quotes.VERSION
    return f"{quotes.VERSION} and {components.names()['verify_quote']}"


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
    ai_review: bool = False,
    cloud: object | None = None,
) -> Components:
    """The product's components. Each module exposes create(conn).

    ai_review adds the local AI reviewer pass (core.audit.review). It is off by default: under
    rules 0.2.0 it only sorts evidence for the expert. A reviewer given in replace is used
    whatever ai_review says.

    replace supplies some components directly (the eval's hostile mode swaps in a worst-case
    labeler and reviewer); those modules are not imported. filler is handed to
    core.audit.assumptions.create(conn, filler=...): the local model's template filler, or an
    expert's (or the signed eval spec's) entries. With none given, the local model's filler
    from core.audit.assumption_filler is used; it resolves names only to persons already in
    the case, so the expert records device-owner stipulations before the audit runs.

    cloud is the case's CloudChoice (core/casework/cloud.py). When it allows cloud, the stance
    labeler is the cloud model with the local model behind it (core/audit/stance.py create);
    every other part stays local.
    """
    built: dict[str, object] = dict(replace or {})
    use_cloud = cloud is not None and bool(getattr(cloud, "use", False))
    if use_cloud and "labeler" not in built:
        from core.audit import stance as stance_mod

        built["labeler"] = stance_mod.create(conn, cloud=getattr(cloud, "config", None))
    if not ai_review:
        built.setdefault("reviewer", None)
    missing: list[str] = []
    if filler is None:
        try:
            filler_mod = importlib.import_module("core.audit.assumption_filler")
        except ModuleNotFoundError:
            missing.append("core.audit.assumption_filler")
        else:
            try:
                filler = filler_mod.create(conn)
            except Exception as e:  # noqa: BLE001 - e.g. the signed prompt or model is missing
                raise ComponentsMissing(f"assumption filler not ready: {e}") from e
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
        model_runs=tuple(
            r for c in (*built.values(), filler) for r in getattr(c, "model_runs", ())
        ),
        reviewable=reviewable,
        recorders=(filler,) if hasattr(filler, "recorder") else (),
        cloud=cloud.record() if cloud is not None and hasattr(cloud, "record") else None,
    )


@dataclass
class RunResult:
    run_id: str
    fake: bool
    decisions: list[VerdictDecision] = field(default_factory=list)
    dropped_labels: int = 0
    stored_items: int = 0
    reviewer_failures: int = 0
    model_outputs_reused: int = 0
    manifest: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    unlabeled: dict[str, str] = field(default_factory=dict)  # claim id -> why it was not labeled
    not_tested: dict[str, str] = field(default_factory=dict)  # claim id -> why nothing was checked


# ---------------------------------------------------------------- helpers

NOT_TESTED = (
    "Not tested: Baker could not set up what to check for this claim, so no record was "
    "searched and the claim stays unproven."
)


def not_tested_reason(refused: Sequence[str], limit: int = 4) -> str:
    """The sentence the screen and report show for a claim with no core assumption."""
    seen = list(dict.fromkeys(r.strip() for r in refused if r and r.strip()))
    if not seen:
        return NOT_TESTED
    more = f" (and {len(seen) - limit} more)" if len(seen) > limit else ""
    return f"{NOT_TESTED} Refused: {'; '.join(seen[:limit])}{more}."


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


def finished_claims(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    """The CLAIM_ACTION payloads of one run, in the order its claims finished."""
    out = []
    for (payload_json,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq", (CLAIM_ACTION,)
    ):
        payload = json.loads(payload_json)
        if payload.get("run_id") == run_id:
            out.append(payload)
    return out


def latest_attempt(conn: sqlite3.Connection) -> dict | None:
    """The newest full audit that has not completed (running, stopped or failed), if it is newer
    than the latest completed run. Rules-only re-decides are never partial and never count."""
    done = conn.execute(
        "SELECT started_at_utc, id FROM pipeline_runs WHERE status = 'completed'"
        " ORDER BY started_at_utc DESC, id DESC LIMIT 1"
    ).fetchone()
    for r in conn.execute(
        "SELECT id, started_at_utc, finished_at_utc, status, baker_version, contracts_version,"
        " rule_version, config_json, note FROM pipeline_runs WHERE status != 'completed'"
        " ORDER BY started_at_utc DESC, id DESC"
    ):
        if done is not None and (r[1], r[0]) <= tuple(done):
            return None
        config = json.loads(r[7])
        if config.get("mode") == "rules_only":
            continue
        finished = finished_claims(conn, r[0])
        order = config.get("claim_order")
        last = finished[-1] if finished else {}
        return {
            "run_id": r[0],
            "partial": True,
            "status": r[3],
            "note": r[8],
            "fake": bool(config.get("fake")),
            "rules_pending": False,
            "started_at_utc": r[1],
            "finished_at_utc": r[2],
            "baker_version": r[4],
            "contracts_version": r[5],
            "rule_version": r[6],
            "config": config,
            "claim_order": list(order) if order is not None else None,
            "manifest": {p["claim_id"]: p["manifest"] for p in finished},
            "unlabeled": {p["claim_id"]: p["unlabeled"] for p in finished if p.get("unlabeled")},
            "not_tested": {p["claim_id"]: p["not_tested"] for p in finished if p.get("not_tested")},
            "components": config.get("components", {}),
            "stored_items": last.get("stored_items", 0),
            "dropped_labels": last.get("dropped_labels", 0),
            "reviewer_failures": last.get("reviewer_failures", 0),
        }
    return None


def mark_stale_runs_stopped(conn: sqlite3.Connection, clock: Clock | None = None) -> list[str]:
    """Runs still marked running when nothing in this process runs them (the app was closed or
    the computer slept through a crash) become stopped. Their finished claims keep their work.
    Call only when no audit is running on this case."""
    stale = [r[0] for r in conn.execute("SELECT id FROM pipeline_runs WHERE status = 'running'")]
    if stale:
        with conn:
            for run_id in stale:
                conn.execute(
                    "UPDATE pipeline_runs SET status = 'stopped', finished_at_utc = ?, note = ?"
                    " WHERE id = ?",
                    (iso(_now(clock)), "found still marked running when Baker started", run_id),
                )
                conn.execute(
                    "UPDATE run_claims SET state = 'failed', candidates_labeled = 0,"
                    " finished_at_utc = ? WHERE pipeline_run_id = ? AND state = 'labeling'",
                    (iso(_now(clock)), run_id),
                )
                audit_log.append(
                    conn,
                    _now(clock),
                    "system",
                    HALT_ACTION,
                    {"run_id": run_id, "error": "found still marked running", "stopped": True},
                )
    return stale


DEMO_LABELER = "eval.demo."


def scripted_demo(run: dict | None) -> bool:
    """True for an audit, or a verdict re-run of one, whose labels came from the demo case's
    scripted labeler (eval/demo.py) rather than a model."""
    labeler = ((run or {}).get("components") or {}).get("labeler", "")
    return isinstance(labeler, str) and labeler.startswith(DEMO_LABELER)


def view_run(conn: sqlite3.Connection) -> dict | None:
    """The run the review screen and the report show.

    The latest completed run, unless a newer full audit has not completed and has finished at
    least one claim: then that partial run (partial=True), whose manifest holds only the claims
    it finished. A newer audit with no finished claim yet is not shown; the run before it stays
    on screen. Predictions, the eval and redecide never read a partial run (last_run())."""
    attempt = latest_attempt(conn)
    if attempt is not None and attempt["manifest"]:
        return attempt
    return last_run(conn)


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


def settled_by_check(
    assumptions: Sequence[Assumption], checks: Sequence[CheckResult]
) -> str | None:
    """Why this claim's evidence need not be labeled, or None if it must be.

    Under rules 0.2.0, rule 1a makes a claim contradicted when a deterministic check failed on
    one of its core assumptions, and rule 1 is applied first. Evidence can only add more
    contradictions to it, never remove the failed check, so no label can change the verdict
    and labeling would only spend model calls. Redecide reuses the stored check, so expert
    review cannot change it either; a new full audit runs the checks again. The test in
    tests/test_fewer_calls.py holds this against the real rules with every stance, review
    status and tier, so a rule change that breaks it fails there.
    """
    core = {a.id: a for a in assumptions if a.is_core}
    for r in checks:
        if r.outcome is CheckOutcome.FAIL and r.assumption_id in core:
            return (
                f"Evidence was not sent to the stance model: check {r.check_name} failed on the"
                f" core assumption '{core[r.assumption_id].text}', so rule 1a decides this claim"
                " (contradicted) whatever the evidence says. The check's cited records are the"
                " evidence. `baker audit --label-all` labels it anyway."
            )
    return None


def _new_calls(c: Components) -> int:
    """Model calls made so far in this process that were not answered from stored outputs."""
    ports = {
        id(p): p for p in (getattr(x, "model", None) for x in (c.labeler, c.reviewer, *c.recorders))
    }
    return sum(
        sum(1 for st in getattr(p, "stats", ()) if not getattr(st, "reused", False))
        for p in ports.values()
        if isinstance(getattr(p, "stats", None), list)
    )


class _Progress:
    """Keeps run_claims current while a claim works, so the screen can show it.

    Each update is its own short transaction, written only while no claim rows are pending.
    Progress is for display: a progress write that cannot get the database (the expert's
    decision is being saved at that moment) is skipped, never allowed to stop the audit. The
    claim's 'done' row is the exception: it is written in the claim's own transaction."""

    def __init__(self, conn: sqlite3.Connection, run_id: str, c: Components, clock: Clock | None):
        self.conn, self.run_id, self.c, self.clock = conn, run_id, c, clock
        self.calls_at_start = 0
        self.total = 0

    def _update(self, claim_id: str, sql: str, params: tuple, commit: bool = True) -> None:
        try:
            self.conn.execute(
                f"UPDATE run_claims SET {sql} WHERE pipeline_run_id = ? AND claim_id = ?",  # noqa: S608
                (*params, self.run_id, claim_id),
            )
            if commit:
                self.conn.commit()
        except db.OperationalError:
            if not commit:
                raise
            self.conn.rollback()

    def started(self, claim_id: str) -> None:
        self.calls_at_start = _new_calls(self.c)
        self.total = 0
        self._update(claim_id, "state = 'labeling', started_at_utc = ?", (iso(_now(self.clock)),))

    def retrieved(self, claim_id: str, total: int) -> None:
        self.total = total
        self._update(claim_id, "candidates_total = ?", (total,))

    def labeled(self, claim_id: str, n: int) -> None:
        calls = _new_calls(self.c) - self.calls_at_start
        self._update(claim_id, "candidates_labeled = ?, model_calls = ?", (n, calls))

    def done(self, claim_id: str) -> None:
        """Inside the claim's write transaction: the claim and its 'done' row commit together."""
        self._update(
            claim_id,
            "state = 'done', candidates_total = ?, candidates_labeled = ?, model_calls = ?,"
            " finished_at_utc = ?",
            (
                self.total,
                self.total,
                _new_calls(self.c) - self.calls_at_start,
                iso(_now(self.clock)),
            ),
            commit=False,
        )

    def failed(self, claim_id: str) -> None:
        self._update(
            claim_id,
            "state = 'failed', candidates_labeled = 0, finished_at_utc = ?",
            (iso(_now(self.clock)),),
        )


class _Run:
    """State for one pipeline run."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        c: Components,
        now: datetime,
        result: RunResult,
        clock: Clock | None = None,
    ):
        self.conn = conn
        self.c = c
        self.now = now
        self.clock = clock
        self.progress = _Progress(conn, result.run_id, c, clock)
        self.result = result
        self.run_id = result.run_id
        self.flushed: dict[int, int] = {}
        self.review_run = next((m.id for m in c.model_runs if m.purpose == "review"), None)
        # Rows a claim's model work produces wait here until the claim's model work is done,
        # so no write transaction is open while the model runs (see the module docstring).
        self.pending: list[tuple[str, tuple]] | None = None
        self.forwarded = forwarded.affected(conn)
        # The model calls stored while the current claim ran, bound into its audit-log entry
        # (calls_digest), so a stored call edited later no longer matches.
        self.claim_calls: list[str] = []

    def _write(self, sql: str, params: tuple) -> None:
        if self.pending is None:
            self.conn.execute(sql, params)
        else:
            self.pending.append((sql, params))

    def _write_pending(self) -> None:
        pending, self.pending = self.pending or [], None
        for sql, params in pending:
            self.conn.execute(sql, params)

    # -- model calls

    def flush_calls(self, quote_failed: set[str] = frozenset()) -> None:  # type: ignore[assignment]
        """Store the ModelCall rows components recorded (component.recorder.calls).

        A call whose label was dropped because its quote failed is stored as quote_failed.
        """
        for comp in (self.c.labeler, self.c.reviewer, *self.c.recorders):
            recorder = getattr(comp, "recorder", None)
            calls = getattr(recorder, "calls", None)
            if calls is None:
                continue
            done = self.flushed.get(id(comp), 0)
            for call in calls[done:]:
                if call.id in quote_failed:
                    call = call.model_copy(update={"outcome": ModelCallOutcome.QUOTE_FAILED})
                self.claim_calls.append(call.id)
                self._write(
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
        except ModelUnavailable:
            raise  # no model at all stops the run; it is not a dropped label
        except Exception:  # noqa: BLE001 - bad model output is dropped, never guessed at
            self.flush_calls()
            return self._drop()
        if label.assumption_id != a.id or label.record_id != cand.record_id:
            self.flush_calls()
            return self._drop()
        rec = get_record(self.conn, cand.record_id)
        text = rec.text if rec else None
        if (
            rec is None
            or text is None
            or not self.c.verify_quote(label.quote, text)
            or not quotes.cites_record(label.quote, text, rec.own)
        ):
            self.flush_calls({label.model_call_id} if label.model_call_id else set())
            return self._drop()
        self.flush_calls()
        stance_ = stance.subject_stance(a, text, label.stance)
        rationale = label.rationale
        if stance_ is not label.stance:  # the model call log keeps the raw label
            rationale = stance.NOT_THE_MESSAGE + rationale
        if cand.record_id in self.forwarded and stance_ in (Stance.SUPPORTS, Stance.CONTRADICTS):
            # fail closed: forwarded words can neither support nor contradict (forwarded.py)
            rationale = f"{forwarded.STANCE_NOTE}{stance_.value}. {rationale}"
            stance_ = Stance.COMPLICATES
        return EvidenceItem(
            id=evidence_id(a.id, cand.record_id, stance_, label.quote),
            assumption_id=a.id,
            record_id=cand.record_id,
            ref=cand.ref,
            stance=stance_,
            quote=label.quote,
            quote_verified=True,
            rationale=rationale,
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
        self._write(
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
        if self.c.reviewer is None:
            return  # no AI review pass: the item stays open for the expert
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
        except ModelUnavailable:
            raise
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
        self.progress.started(claim.id)
        self.pending = []  # nothing is written until this claim's model work is done
        assumptions = list(c.assumptions.build(claim))
        if not any(a.is_core for a in assumptions):
            refused = getattr(c.assumptions, "refused", None)
            self.result.not_tested[claim.id] = not_tested_reason(
                refused(claim.id) if callable(refused) else []
            )
        for a in assumptions:
            if a.claim_id != claim.id:
                raise invariants.InvariantViolation(f"assumption {a.id} built for {a.claim_id}")
            self._write(
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
                self._write(
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

        settled = None
        if c.rule is rules.decide_verdict and not (c.label_settled or c.rules_pending()):
            settled = settled_by_check(assumptions, checks)
        if settled is not None:
            self.result.unlabeled[claim.id] = settled
        # Retrieval first (no model), so the screen knows how many candidates there are.
        todo: list[tuple[Assumption, object]] = []
        for a in assumptions if settled is None else ():
            seen: set[str] = set()
            for cand in c.retriever.retrieve(a, conn, c.k):
                if cand.record_id not in seen:
                    seen.add(cand.record_id)
                    todo.append((a, cand))
        self.progress.retrieved(claim.id, len(todo))
        for n, (a, cand) in enumerate(todo, 1):
            item = self._label(a, cand)
            if item is not None and item.id not in evidence_ids:
                self._write(
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
                # The same item (assumption, record, stance, quote) from another model, as when a
                # case switches between cloud and local: the row names the model of this run.
                self._write(
                    "UPDATE evidence_items SET model_run_id = ?, rationale = ?"
                    " WHERE id = ? AND model_run_id IS NOT ?",
                    (item.model_run_id, item.rationale, item.id, item.model_run_id),
                )
                self._review(a, item.model_copy(update={"status": evidence_status(conn, item.id)}))
                evidence_ids.append(item.id)
                self.result.stored_items += 1
            self.progress.labeled(claim.id, n)

        self.flush_calls()  # calls a component made after the last label (the filler's)
        self._write_pending()  # the claim's write transaction starts here
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
            # rules.py stamps the wall clock; the run's clock decides, so a run is repeatable.
            decision = decision.model_copy(update={"decided_at_utc": _now(self.clock)})
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
        self.progress.done(claim.id)
        self.result.manifest[claim.id] = {
            "assumptions": [a.id for a in assumptions],
            "checks": [r.id for r in checks],
            "evidence": evidence_ids,
        }
        return decision


def _reused(c: Components) -> int:
    """Calls answered from stored outputs (core/audit/_local_model.py) in this run."""
    ports = {
        id(p): p for p in (getattr(x, "model", None) for x in (c.labeler, c.reviewer, *c.recorders))
    }
    counts = (getattr(p, "reused", 0) for p in ports.values())
    return sum(n for n in counts if isinstance(n, int))


def _new_run_id(conn: sqlite3.Connection, now: datetime) -> str:
    base = "run:" + now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id, n = base, 1
    while conn.execute("SELECT 1 FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone():
        n += 1
        run_id = f"{base}-{n}"
    return run_id


Progress = Callable[[int, int, VerdictDecision], None]


def run_audit(
    conn: sqlite3.Connection,
    components: Components,
    clock: Clock | None = None,
    claim_ids: Sequence[str] | None = None,
    config: dict[str, str | int | float | bool | None] | None = None,
    progress: Progress | None = None,
) -> RunResult:
    """Audit every claim that is not removed, in claim id order, or just claim_ids, in the
    order given (the expert's order on the screen).

    Each claim is committed when it finishes, with a CLAIM_ACTION audit-log entry, so a stopped
    run keeps the model outputs of the claims it finished and the next run reuses them. The run
    is scored only once it completes; until then only the screen and the report show its
    finished claims (view_run()). progress(done, total, decision) is called after each claim is
    saved; an exception it raises stops the run there (the screen's Stop button)."""
    now = _now(clock)
    result = RunResult(run_id=_new_run_id(conn, now), fake=components.fake())
    claims = load_claims(conn)
    if claim_ids is not None:
        by_id = {cl.id: cl for cl in claims}
        claims = [by_id[i] for i in dict.fromkeys(claim_ids) if i in by_id]
    cfg = {
        "k": components.k,
        "fake": result.fake,
        "label_settled": components.label_settled,
        "claim_order": [cl.id for cl in claims],
        "components": components.names(),
        **({"cloud": components.cloud} if components.cloud is not None else {}),
        **(config or {}),
        "quote_check": quote_check_version(components),  # a caller's config cannot restate it
        "build": build.build_info(),  # release and git commit; nor this
    }
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
        conn.executemany(
            "INSERT INTO run_claims (pipeline_run_id, claim_id, position, state)"
            " VALUES (?, ?, ?, 'queued')",
            [(result.run_id, cl.id, n) for n, cl in enumerate(claims, 1)],
        )
    current: str | None = None
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
        run = _Run(conn, components, now, result, clock)
        reused_before = _reused(components)
        for n, claim in enumerate(claims, 1):
            current = claim.id
            run.claim_calls = []
            with conn:  # one claim per transaction: a stop keeps every finished claim's work
                decision = run.claim(claim, stipulations)
                audit_log.append(  # inside the claim's write transaction, after its rows
                    conn,
                    _now(clock),
                    "system",
                    CLAIM_ACTION,
                    {
                        "run_id": result.run_id,
                        "claim_id": claim.id,
                        "done": n,
                        "total": len(claims),
                        "verdict_id": decision.id,
                        "manifest": result.manifest[claim.id],
                        "unlabeled": result.unlabeled.get(claim.id),
                        "not_tested": result.not_tested.get(claim.id),
                        # running totals, so an unfinished run's report can print them
                        "stored_items": result.stored_items,
                        "dropped_labels": result.dropped_labels,
                        "reviewer_failures": result.reviewer_failures,
                        "model_calls": calls_digest(conn, run.claim_calls),
                        "rows_sha256": rows_digest(
                            conn, result.manifest[claim.id], claim.id, run.claim_calls
                        ),
                        "decided_at_utc": iso(decision.decided_at_utc),
                        "claim_sha256": claim_digest(conn, claim.id),
                    },
                )
            current = None
            result.decisions.append(decision)
            if progress is not None:
                progress(n, len(claims), decision)
        result.model_outputs_reused = _reused(components) - reused_before
        with conn:
            # The UPDATE opens the write transaction before the log reads its last entry, so a
            # decision the expert records at the same moment cannot take the same log seq.
            finished = iso(_now(clock))
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at_utc = ? WHERE id = ?",
                (PipelineRunStatus.COMPLETED.value, finished, result.run_id),
            )
            audit_log.append(
                conn,
                now,
                "system",
                RUN_ACTION,
                {
                    "run_id": result.run_id,
                    "run_sha256": run_digest(conn, result.run_id),
                    "finished_at_utc": finished,
                    "fake": result.fake,
                    "rules_pending": components.rules_pending(),
                    "components": components.names(),
                    "manifest": result.manifest,
                    "dropped_labels": result.dropped_labels,
                    "stored_items": result.stored_items,
                    "reviewer_failures": result.reviewer_failures,
                    "model_outputs_reused": result.model_outputs_reused,
                    "unlabeled": result.unlabeled,
                    "not_tested": result.not_tested,
                    "rejected_assumptions": [
                        {"template_id": r.proposal.template_id, "reason": r.reason}
                        for r in getattr(components.assumptions, "rejected", ())
                    ],
                },
            )
    except Exception as e:
        conn.rollback()
        stopped = isinstance(e, RunStopped)
        status = PipelineRunStatus.STOPPED if stopped else PipelineRunStatus.FAILED
        with conn:
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at_utc = ?, note = ? WHERE id = ?",
                (status.value, iso(_now(clock)), str(e)[:2000], result.run_id),
            )
            if current is not None:  # its work was rolled back
                conn.execute(
                    "UPDATE run_claims SET state = 'failed', candidates_labeled = 0,"
                    " finished_at_utc = ? WHERE pipeline_run_id = ? AND claim_id = ?",
                    (iso(_now(clock)), result.run_id, current),
                )
            audit_log.append(
                conn,
                now,
                "system",
                HALT_ACTION,
                {"run_id": result.run_id, "error": str(e), "stopped": stopped},
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
