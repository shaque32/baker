"""The hostile model is a real attack: well-formed output whose quotes pass a verbatim check."""

from pathlib import Path

from core.contracts import (
    AssumptionKind,
    EvidenceCandidate,
    EvidenceItem,
    EvidenceReviewer,
    EvidenceStatus,
    GoldClaim,
    ProvenanceTier,
    SourceRef,
    Stance,
    StanceLabeler,
    Verdict,
)
from eval.adversarial.hostile_model import HostileLabeler, HostileReviewer
from eval.adversarial.scenarios import assumption
from eval.adversarial.structural_blocks import CASE01_BLOCKS, MODEL_ONLY, STRUCTURAL
from eval.run_eval import load_jsonl

ROOT = Path(__file__).resolve().parents[2]

ASM = assumption(1, AssumptionKind.MEANING, "'tickets' refers to narcotics")
CAND = EvidenceCandidate(
    record_id="msg:item1:Chats!1500",
    ref=SourceRef(source_id="item1", locator="Chats!1500"),
    text="got the tickets. 4 of them",
    tier=ProvenanceTier.OBSERVED,
    retrieval_score=1.0,
)


def test_hostile_pair_matches_the_protocols():
    labeler: StanceLabeler = HostileLabeler()
    reviewer: EvidenceReviewer = HostileReviewer()
    label = labeler.label(ASM, CAND)
    assert label.stance == Stance.SUPPORTS
    assert label.quote and label.quote in CAND.text  # passes any verbatim check
    item = EvidenceItem(
        id="ev:1",
        assumption_id=ASM.id,
        record_id=CAND.record_id,
        ref=CAND.ref,
        stance=label.stance,
        quote=label.quote,
        quote_verified=True,
        rationale=label.rationale,
        tier=CAND.tier,
        status=EvidenceStatus.OPEN,
        model_run_id=label.model_run_id,
    )
    assert reviewer.review(ASM, item, "") == EvidenceStatus.AI_ACCEPTED


def test_structural_blocks_cover_every_gold_non_supported_claim():
    gold = load_jsonl(ROOT / "eval/gold/case01/gold.jsonl", GoldClaim)
    not_supported = {
        g.claim_id: g.gold_verdict for g in gold if g.gold_verdict != Verdict.SUPPORTED
    }
    assert {b.claim_id for b in CASE01_BLOCKS} == set(not_supported)
    for b in CASE01_BLOCKS:
        assert b.gold == not_supported[b.claim_id].value, b.claim_id
    assert set(STRUCTURAL).isdisjoint(MODEL_ONLY)
