"""Re-run the verdict rules after expert review, without calling any model.

Under rules 0.2.0 a claim becomes supported only after the expert accepts its key evidence, so
the expert's decisions must reach the verdicts. A full audit re-labels every candidate with the
local model, which takes hours on a laptop. Nothing the model produced changes when the expert
reviews evidence, so this re-decides instead:

- It starts a new pipeline run (config mode 'rules_only') that reuses the latest completed run's
  assumptions, check results and evidence items, exactly as stored.
- Each item's status is read again (the latest evidence_reviews row), so expert decisions made
  since the run count. Stipulations are read again too.
- core/audit/rules.py decides every verdict and core/audit/invariants.py re-checks each one,
  exactly as in a full run. A violation rolls back and marks the run failed.
- Claims removed since the run are skipped. Claims whose text the expert edited since the run,
  and claims added since, are left out with a reason: their assumptions were built from other
  text, or never built, so only a full audit can check them.
- The run's audit-log entry has the same shape as a full run's, plus mode, from_run,
  evidence_from_run and requested_by, so reports and predictions read it the same way. A run
  re-decided from a test run with stand-in components stays marked as a test run.

No model is called, nothing is retrieved and no AI review happens here.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core import pipeline
from core.audit import invariants, rules
from core.contracts import CONTRACTS_VERSION, PipelineRunStatus, VerdictDecision, canonical_json
from core.review import audit_log
from core.review.actions import ReviewError, _expert
from core.review.status import edited_after

Clock = Callable[[], datetime]
MODE = "rules_only"
RULE_COMPONENT = f"{rules.decide_verdict.__module__}.{rules.decide_verdict.__qualname__}"


@dataclass
class RedecideResult:
    run_id: str
    from_run: str
    fake: bool
    decisions: list[VerdictDecision] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # claim id -> why


def _new_run_id(conn: sqlite3.Connection, now: datetime) -> str:
    base = "run:" + now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id, n = base, 1
    while conn.execute("SELECT 1 FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone():
        n += 1
        run_id = f"{base}-{n}"
    return run_id


def redecide(
    conn: sqlite3.Connection, requested_by: str, clock: Clock | None = None
) -> RedecideResult:
    """Re-decide every audited claim from stored evidence and current reviews. All or nothing."""
    _expert(requested_by)
    if rules.RULE_VERSION.endswith("-stub"):
        raise ReviewError("the verdict rules are not written yet")
    src = pipeline.last_run(conn)
    if src is None:
        raise ReviewError("no completed audit to re-decide; run the audit first")
    now = (clock or (lambda: datetime.now(UTC)))()
    result = RedecideResult(
        run_id=_new_run_id(conn, now), from_run=src["run_id"], fake=bool(src.get("fake"))
    )
    evidence_from = src.get("evidence_from_run", src["run_id"])
    cfg = {
        "mode": MODE,
        "from_run": src["run_id"],
        "evidence_from_run": evidence_from,
        "fake": result.fake,
        "requested_by": requested_by,
    }
    with conn:
        conn.execute(
            "INSERT INTO pipeline_runs (id, started_at_utc, finished_at_utc, status, baker_version,"
            " contracts_version, rule_version, config_json, note)"
            " VALUES (?, ?, NULL, ?, ?, ?, ?, ?, NULL)",
            (
                result.run_id,
                pipeline.iso(now),
                PipelineRunStatus.RUNNING.value,
                pipeline.PIPELINE_VERSION,
                CONTRACTS_VERSION,
                rules.RULE_VERSION,
                canonical_json(cfg),
            ),
        )
    manifest_in: dict[str, dict[str, list[str]]] = src["manifest"]
    edited = edited_after(conn, src["started_at_utc"])
    manifest: dict[str, dict[str, list[str]]] = {}
    try:
        with conn:
            stipulations = pipeline.load_stipulations(conn)
            for claim in pipeline.load_claims(conn):
                items = manifest_in.get(claim.id)
                if items is None:
                    result.skipped[claim.id] = "added after the audit; run the full audit"
                    continue
                if claim.id in edited:
                    result.skipped[claim.id] = "text edited after the audit; run the full audit"
                    continue
                assumptions = pipeline.load_assumptions(conn, items["assumptions"])
                checks = pipeline.load_checks(conn, items["checks"])
                evidence = pipeline.load_evidence(conn, items["evidence"])
                decision = rules.decide_verdict(
                    claim, assumptions, evidence, checks, stipulations, result.run_id
                )
                invariants.check_decision(
                    conn,
                    claim,
                    assumptions,
                    evidence,
                    checks,
                    stipulations,
                    decision,
                    result.run_id,
                )
                _store(conn, decision)
                manifest[claim.id] = items
                result.decisions.append(decision)
            components = {**src["components"], "rule": RULE_COMPONENT}
            audit_log.append(
                conn,
                now,
                "system",
                pipeline.RUN_ACTION,
                {
                    "run_id": result.run_id,
                    "fake": result.fake,
                    "rules_pending": False,
                    "components": components,
                    "manifest": manifest,
                    "dropped_labels": 0,
                    "stored_items": 0,
                    "reviewer_failures": 0,
                    "mode": MODE,
                    "from_run": src["run_id"],
                    "evidence_from_run": evidence_from,
                    "requested_by": requested_by,
                    "skipped": result.skipped,
                },
            )
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at_utc = ? WHERE id = ?",
                (PipelineRunStatus.COMPLETED.value, pipeline.iso(now), result.run_id),
            )
    except Exception as e:
        with conn:
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, finished_at_utc = ?, note = ? WHERE id = ?",
                (PipelineRunStatus.FAILED.value, pipeline.iso(now), str(e)[:2000], result.run_id),
            )
            audit_log.append(
                conn,
                now,
                "system",
                pipeline.HALT_ACTION,
                {"run_id": result.run_id, "error": str(e)},
            )
        raise
    return result


def _store(conn: sqlite3.Connection, d: VerdictDecision) -> None:
    """The same verdicts row a full run writes (core/pipeline.py, _Run.claim)."""
    conn.execute(
        "INSERT INTO verdicts (id, claim_id, pipeline_run_id, verdict, supported_basis,"
        " rule_version, reasons_json, coverage_json, cited_json, decided_at_utc,"
        " confirmed_by, override_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
        (
            d.id,
            d.claim_id,
            d.pipeline_run_id,
            d.verdict.value,
            d.supported_basis.value if d.supported_basis else None,
            d.rule_version,
            canonical_json(list(d.reasons)),
            canonical_json([cv.model_dump(mode="json") for cv in d.coverage]),
            canonical_json(
                {
                    "evidence": list(d.cited_evidence_ids),
                    "checks": list(d.cited_check_ids),
                    "stipulations": list(d.cited_stipulation_ids),
                }
            ),
            pipeline.iso(d.decided_at_utc),
        ),
    )
