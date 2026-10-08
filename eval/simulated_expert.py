"""The simulated expert, and the stand-ins the model-free eval runs with. Eval only.

Under rules 0.2.0 no claim is SUPPORTED until an expert accepts its key evidence, so an
unreviewed run can never be scored against gold. The merge gate (Arsh, 2026-10-08, Wave 3
plan, decision 2) runs the audit, lets a simulated expert review every surfaced evidence item
through the product's own expert actions (core/review/actions.py, so the hash-chained log
records each decision), runs the audit again, and scores what the rules decide.

The simulated expert knows only what Arsh signed in eval/gold/<case>/gold.jsonl. It ACCEPTS an
item when, and only when:
- the item's record is in the claim's signed key_evidence, and
- the item's label points the way the gold verdict does: supports for a supported claim,
  contradicts for a contradicted one.
It DISMISSES every other labeled item, including every item on a gold-unproven claim.
Irrelevant labels are not evidence and are left alone.

Approximation, stated plainly: key_evidence is signed per claim, not per assumption, so the
simulated expert accepts a key record on whichever assumption of the claim it was retrieved
for. A real expert would accept it only where it bears on that assumption.

What this gate can and cannot show. It shows whether retrieval surfaces the signed key
evidence, whether the checks and the assumption sheet are right, and whether the rules land
on the gold verdict once the right evidence is accepted. Because the simulated expert never
accepts support on a claim that is not gold-supported, a false SUPPORTED here can only come
from a broken rule or invariant: the zero-false-supported gate is a regression guard, not a
measurement of the model. The model is measured separately (make eval-real, and the probe set).

Components:
- GoldDirectionLabeler: the model-free stance stand-in. It labels every retrieved record the
  way the claim's gold verdict points (supports for supported and unproven claims, contradicts
  for contradicted ones), quoting the record's whole citable text so the real quote check
  runs on it. It stands for a labeler that never misses direction; the simulated expert then
  sorts key evidence from everything else.
- ReplayLabeler: hands back the labels stored on the first pass, so the second pass after the
  expert's review re-runs retrieval, checks and rules without calling any model again.
- RecordingRetriever: wraps the real retriever and records what it returned, for the
  key-evidence recall the eval reports.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.audit.invariants import record_text
from core.contracts import (
    Assumption,
    EvidenceCandidate,
    EvidenceItem,
    EvidenceStatus,
    GoldClaim,
    ModelRun,
    Retriever,
    Stance,
    StanceLabel,
    Verdict,
)

SIM_EXPERT = "expert:eval-simulated"
SIM_TIME = datetime(2026, 10, 7, tzinfo=UTC)

GOLD_DIRECTION_RUN = ModelRun(
    id="mr:eval-gold-direction",
    purpose="stance",
    model_name="gold-direction-stand-in",
    model_sha256="0" * 64,
    prompt_version="none",
    params={"stand_in": True, "model_free": True},
    seed=0,
    started_at_utc=SIM_TIME,
)

_DIRECTION = {Verdict.SUPPORTED: Stance.SUPPORTS, Verdict.CONTRADICTED: Stance.CONTRADICTS}


def direction(verdict: Verdict) -> Stance | None:
    """The stance an accepted key item must carry for this gold verdict. None for unproven."""
    return _DIRECTION.get(verdict)


class GoldKey:
    """The signed gold rows, by claim id."""

    def __init__(self, gold: Sequence[GoldClaim]) -> None:
        self.by_claim = {g.claim_id: g for g in gold}

    def key(self, claim_id: str) -> frozenset[str]:
        g = self.by_claim.get(claim_id)
        return frozenset(g.key_evidence) if g else frozenset()

    def wanted(self, claim_id: str) -> Stance | None:
        g = self.by_claim.get(claim_id)
        return direction(g.gold_verdict) if g else None

    def accepts(self, claim_id: str, item: EvidenceItem) -> bool:
        want = self.wanted(claim_id)
        return want is not None and item.stance is want and item.record_id in self.key(claim_id)


# ---------------------------------------------------------------- stand-ins


class GoldDirectionLabeler:
    """StanceLabeler stand-in for the model-free run. See the module docstring."""

    model_runs = (GOLD_DIRECTION_RUN,)

    def __init__(self, conn: sqlite3.Connection, gold: GoldKey) -> None:
        self.conn = conn
        self.gold = gold

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        text = record_text(self.conn, candidate.record_id)
        if not text:
            raise LookupError(f"{candidate.record_id} has no citable text")
        stance = self.gold.wanted(assumption.claim_id) or Stance.SUPPORTS
        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=stance,
            quote=text,
            rationale="Model-free stand-in: labeled the way the gold verdict points.",
            model_run_id=GOLD_DIRECTION_RUN.id,
        )


class ReplayLabeler:
    """StanceLabeler that returns the label stored for (assumption, record) on an earlier pass.
    A record with no stored label (its first label was dropped) is dropped again."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        rows = self.conn.execute(
            "SELECT stance, quote, rationale, model_run_id FROM evidence_items"
            " WHERE assumption_id = ? AND record_id = ? ORDER BY id",
            (assumption.id, candidate.record_id),
        ).fetchall()
        if len(rows) != 1:
            raise LookupError(
                f"{len(rows)} stored labels for {assumption.id} on {candidate.record_id}"
            )
        stance, quote, rationale, run = rows[0]
        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance(stance),
            quote=quote,
            rationale=rationale,
            model_run_id=run,
        )


class RecordingRetriever:
    """Wraps a Retriever and records, per claim, every record id it returned."""

    def __init__(self, inner: Retriever) -> None:
        self.inner = inner
        self.retrieved: dict[str, set[str]] = defaultdict(set)

    def retrieve(
        self, assumption: Assumption, conn: sqlite3.Connection, k: int
    ) -> list[EvidenceCandidate]:
        out = self.inner.retrieve(assumption, conn, k)
        self.retrieved[assumption.claim_id].update(c.record_id for c in out)
        return out


# ---------------------------------------------------------------- the expert


@dataclass
class ExpertReview:
    accepted: dict[str, list[str]] = field(default_factory=dict)  # claim -> evidence ids
    dismissed: dict[str, int] = field(default_factory=dict)  # claim -> count

    def summary(self) -> dict[str, object]:
        return {
            "actor": SIM_EXPERT,
            "accepted": sum(len(v) for v in self.accepted.values()),
            "dismissed": sum(self.dismissed.values()),
            "claims_with_an_acceptance": sorted(c for c, v in self.accepted.items() if v),
        }


def review(
    conn: sqlite3.Connection,
    gold: GoldKey,
    manifest: dict[str, dict[str, list[str]]],
    clock: Callable[[], datetime],
) -> ExpertReview:
    """Decide every labeled item the run surfaced, as the simulated expert."""
    from core.pipeline import load_evidence
    from core.review import actions

    out = ExpertReview()
    for claim_id in sorted(manifest):
        out.accepted[claim_id] = []
        out.dismissed[claim_id] = 0
        for e in load_evidence(conn, manifest[claim_id]["evidence"]):
            if e.stance is Stance.IRRELEVANT:
                continue
            if gold.accepts(claim_id, e):
                actions.decide_evidence(
                    conn,
                    e.id,
                    EvidenceStatus.ACCEPTED,
                    SIM_EXPERT,
                    "Simulated expert: signed key evidence for this claim, label matches gold.",
                    clock,
                )
                out.accepted[claim_id].append(e.id)
            else:
                actions.decide_evidence(
                    conn,
                    e.id,
                    EvidenceStatus.DISMISSED,
                    SIM_EXPERT,
                    "Simulated expert: not signed key evidence in the gold direction.",
                    clock,
                )
                out.dismissed[claim_id] += 1
    return out


# ---------------------------------------------------------------- readiness


def readiness(
    gold: GoldKey,
    retrieved: dict[str, set[str]],
    conn: sqlite3.Connection,
    manifest: dict[str, dict[str, list[str]]],
) -> dict[str, object]:
    """Key-evidence recall: how much of each claim's signed key evidence the run put in front
    of the expert. 'retrieved' means the retriever returned the record for some assumption of
    the claim; 'surfaced' means it became a labeled evidence item (its quote verified) the
    expert could accept."""
    from core.pipeline import load_evidence

    per_claim: dict[str, dict[str, object]] = {}
    n_key = n_retrieved = n_surfaced = 0
    all_retrieved: list[str] = []
    any_surfaced: list[str] = []
    for claim_id in sorted(gold.by_claim):
        key = gold.key(claim_id)
        got = key & retrieved.get(claim_id, set())
        items = load_evidence(conn, manifest.get(claim_id, {}).get("evidence", []))
        shown = key & {e.record_id for e in items if e.stance is not Stance.IRRELEVANT}
        n_key += len(key)
        n_retrieved += len(got)
        n_surfaced += len(shown)
        if key and got == key:
            all_retrieved.append(claim_id)
        if shown:
            any_surfaced.append(claim_id)
        per_claim[claim_id] = {
            "key": len(key),
            "retrieved": len(got),
            "surfaced": len(shown),
            "missed": sorted(key - got),
        }
    return {
        "key_evidence": n_key,
        "key_evidence_recall_retrieved": round(n_retrieved / n_key, 4) if n_key else 0.0,
        "key_evidence_recall_surfaced": round(n_surfaced / n_key, 4) if n_key else 0.0,
        "claims_all_key_retrieved": all_retrieved,
        "claims_ready_for_expert": any_surfaced,
        "per_claim": per_claim,
    }
