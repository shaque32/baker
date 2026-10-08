"""The model-free merge gate and its simulated expert (eval/simulated_expert.py)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.contracts import (
    ClaimType,
    EvidenceCandidate,
    EvidenceItem,
    EvidenceStatus,
    GoldClaim,
    Prediction,
    ProvenanceTier,
    SourceRef,
    Stance,
    SupportedBasis,
    Verdict,
)
from core.db import connect
from eval import run_pipeline
from eval.run_eval import load_jsonl, passes, score
from eval.simulated_expert import SIM_EXPERT, GoldKey, ReplayLabeler

GOLD = Path("eval/gold/case01/gold.jsonl")
DRAFT_SHEET = Path("eval/probe_draft/case01_assumptions.jsonl")


def gold_row(claim_id: str, verdict: Verdict, key: tuple[str, ...]) -> GoldClaim:
    return GoldClaim(
        claim_id=claim_id,
        page=1,
        para_no=1,
        text="t",
        claim_type=ClaimType.COMMUNICATION,
        cross_device=False,
        gold_verdict=verdict,
        core_assumptions=(),
        key_evidence=key,
        trap=None,
        rationale="r",
        labeled_by="test",
        labeled_at=datetime(2026, 10, 6, tzinfo=UTC),
    )


def item(record_id: str, stance: Stance) -> EvidenceItem:
    return EvidenceItem(
        id=f"ev:{record_id}:{stance.value}",
        assumption_id="asm:x",
        record_id=record_id,
        ref=SourceRef(source_id="item1", locator="Chats!1"),
        stance=stance,
        quote="q",
        quote_verified=True,
        rationale="",
        tier=ProvenanceTier.OBSERVED,
        status=EvidenceStatus.OPEN,
        model_run_id="mr:x",
    )


def test_expert_accepts_only_signed_key_evidence_in_the_gold_direction():
    g = GoldKey(
        [
            gold_row("S", Verdict.SUPPORTED, ("msg:a",)),
            gold_row("X", Verdict.CONTRADICTED, ("msg:b",)),
            gold_row("U", Verdict.UNPROVEN, ("msg:c",)),
        ]
    )
    assert g.accepts("S", item("msg:a", Stance.SUPPORTS))
    assert not g.accepts("S", item("msg:a", Stance.CONTRADICTS))
    assert not g.accepts("S", item("msg:z", Stance.SUPPORTS))
    assert g.accepts("X", item("msg:b", Stance.CONTRADICTS))
    assert not g.accepts("X", item("msg:b", Stance.SUPPORTS))
    # a gold-unproven claim never gets an acceptance, key evidence or not
    for stance in Stance:
        assert not g.accepts("U", item("msg:c", stance))
    assert not g.accepts("unknown", item("msg:a", Stance.SUPPORTS))


def test_zero_false_supported_is_a_count_not_only_a_rate():
    g = [gold_row(f"S{i}", Verdict.SUPPORTED, ()) for i in range(40)]
    g += [gold_row(f"U{i}", Verdict.UNPROVEN, ()) for i in range(40)]
    p = [
        Prediction(
            claim_id=r.claim_id,
            verdict=r.gold_verdict,
            supported_basis=SupportedBasis.CONFIRMED
            if r.gold_verdict is Verdict.SUPPORTED
            else None,
        )
        for r in g
    ]
    p[-1] = Prediction(
        claim_id="U39", verdict=Verdict.SUPPORTED, supported_basis=SupportedBasis.CONFIRMED
    )
    s = score(g, p)
    assert s.false_supported_rate <= 0.05 and s.verdict_accuracy >= 0.80
    assert not passes(s)


@pytest.fixture(scope="module")
def gate_run(tmp_path_factory) -> tuple[Path, list[Prediction]]:
    out = tmp_path_factory.mktemp("model_free")
    preds = run_pipeline.run_once(
        "case01", "model-free", "accept", out, DRAFT_SHEET, expert="simulated"
    )
    return out, preds


@pytest.fixture
def gate_db(gate_run) -> sqlite3.Connection:
    c = connect(gate_run[0] / "case01.db")
    yield c
    c.close()


def test_model_free_gate_passes_on_case01(gate_run):
    _, preds = gate_run
    s = score(load_jsonl(GOLD, GoldClaim), preds)
    assert s.n_false_supported == 0
    assert passes(s), s


def test_every_supported_verdict_is_expert_confirmed(gate_run):
    _, preds = gate_run
    supported = [p for p in preds if p.verdict is Verdict.SUPPORTED]
    assert supported
    assert all(p.supported_basis is SupportedBasis.CONFIRMED for p in supported)


def test_unreviewed_run_has_nothing_supported(gate_run):
    out, _ = gate_run
    unreviewed = load_jsonl(out / "unreviewed" / "predictions.jsonl", Prediction)
    assert len(unreviewed) == 20
    assert not [p for p in unreviewed if p.verdict is Verdict.SUPPORTED]


def test_expert_decisions_go_through_the_expert_actions_and_the_log(gate_db):
    reviews = gate_db.execute(
        "SELECT reviewer_kind, reviewer, status, model_run_id FROM evidence_reviews"
    ).fetchall()
    assert reviews
    assert {r[:2] for r in reviews} == {("expert", SIM_EXPERT)}
    assert all(r[3] is None for r in reviews)
    logged = gate_db.execute(
        "SELECT count(*) FROM audit_log WHERE action = 'evidence.decide' AND actor = ?",
        (SIM_EXPERT,),
    ).fetchone()[0]
    assert logged == len(reviews)


def test_no_acceptance_on_a_claim_gold_does_not_call_supported_or_contradicted(gate_db):
    gold = {g.claim_id: g for g in load_jsonl(GOLD, GoldClaim)}
    rows = gate_db.execute(
        "SELECT a.claim_id, e.record_id, e.stance FROM evidence_reviews r"
        " JOIN evidence_items e ON e.id = r.evidence_id"
        " JOIN assumptions a ON a.id = e.assumption_id WHERE r.status = 'accepted'"
    ).fetchall()
    assert rows
    for claim_id, record_id, stance in rows:
        g = gold[claim_id]
        assert g.gold_verdict is not Verdict.UNPROVEN
        assert record_id in g.key_evidence
        want = "supports" if g.gold_verdict is Verdict.SUPPORTED else "contradicts"
        assert stance == want


def test_run_summary_reports_readiness_and_sheet_status(gate_run):
    out, _ = gate_run
    s = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert s["assumption_sheet"]["status"].startswith("draft")
    r = s["readiness"]
    assert r["key_evidence"] == sum(len(g.key_evidence) for g in load_jsonl(GOLD, GoldClaim))
    assert 0 < r["key_evidence_recall_retrieved"] <= 1
    assert r["key_evidence_recall_surfaced"] <= r["key_evidence_recall_retrieved"]
    assert s["unreviewed_verdicts"].get("supported", 0) == 0


def test_sheet_people_resolve_to_the_stipulated_owners(gate_db):
    people = run_pipeline.sheet_people(gate_db)
    assert people["person:petrov"] == "person:dev:item1:owner"
    assert people["person:reyes"] == "person:dev:item2:owner"
    assert "person:sokolov" not in people  # nobody stipulated: stays unresolved


def test_checks_see_the_owners_so_time_and_sender_checks_can_fail(gate_db):
    failed = {
        r[0]
        for r in gate_db.execute(
            "SELECT a.claim_id FROM check_results k JOIN assumptions a ON a.id = k.assumption_id"
            " WHERE k.outcome = 'fail'"
        )
    }
    assert {"C04", "C10", "C11", "C14"} <= failed


def test_replay_labeler_returns_the_stored_label_and_drops_the_rest(gate_db):
    eid, aid, rid, stance, quote = gate_db.execute(
        "SELECT id, assumption_id, record_id, stance, quote FROM evidence_items ORDER BY id LIMIT 1"
    ).fetchone()
    from core.pipeline import load_assumptions

    (a,) = load_assumptions(gate_db, [aid])
    cand = EvidenceCandidate(
        record_id=rid,
        ref=SourceRef(source_id="item1", locator="x"),
        text="",
        tier=ProvenanceTier.OBSERVED,
        retrieval_score=1.0,
    )
    label = ReplayLabeler(gate_db).label(a, cand)
    assert (label.stance.value, label.quote) == (stance, quote)
    with pytest.raises(LookupError):
        ReplayLabeler(gate_db).label(a, cand.model_copy(update={"record_id": "msg:none"}))


def test_repeat_model_free_runs_are_identical(gate_run, tmp_path):
    _, first = gate_run
    again = run_pipeline.run_once(
        "case01", "model-free", "accept", tmp_path, DRAFT_SHEET, expert="simulated"
    )
    assert again == first
