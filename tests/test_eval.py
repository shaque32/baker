import json
from datetime import UTC, datetime

from core.contracts import ClaimType, GoldClaim, Prediction, Verdict
from eval.run_eval import main, passes, score


def gold(claim_id: str, verdict: Verdict) -> GoldClaim:
    return GoldClaim(
        claim_id=claim_id,
        page=1,
        para_no=1,
        text="t",
        claim_type=ClaimType.COMMUNICATION,
        cross_device=False,
        gold_verdict=verdict,
        core_assumptions=(),
        key_evidence=(),
        trap=None,
        rationale="r",
        labeled_by="test",
        labeled_at=datetime(2026, 10, 6, tzinfo=UTC),
    )


def test_false_supported_counts_only_non_supported_gold():
    g = [
        gold("C1", Verdict.SUPPORTED),
        gold("C2", Verdict.UNPROVEN),
        gold("C3", Verdict.CONTRADICTED),
    ]
    p = [
        Prediction(claim_id="C1", verdict=Verdict.SUPPORTED, supported_basis="ai_reviewed"),
        Prediction(claim_id="C2", verdict=Verdict.SUPPORTED, supported_basis="ai_reviewed"),
        Prediction(claim_id="C3", verdict=Verdict.CONTRADICTED),
    ]
    s = score(g, p)
    assert s.verdict_accuracy == 2 / 3
    assert s.false_supported_rate == 1 / 2
    assert not passes(s)


def test_missing_prediction_is_wrong_not_supported():
    g = [gold("C1", Verdict.UNPROVEN)]
    s = score(g, [])
    assert s.verdict_accuracy == 0.0
    assert s.false_supported_rate == 0.0
    assert s.confusion == {"unproven": {"missing": 1}}


def test_main_with_no_gold_exits_zero(tmp_path):
    assert main(["--case", str(tmp_path)]) == 0


def test_main_fails_below_threshold(tmp_path):
    (tmp_path / "gold.jsonl").write_text(gold("C1", Verdict.UNPROVEN).model_dump_json() + "\n")
    preds = tmp_path / "p.jsonl"
    preds.write_text(
        json.dumps({"claim_id": "C1", "verdict": "supported", "supported_basis": "confirmed"})
        + "\n"
    )
    assert main(["--case", str(tmp_path), "--predictions", str(preds)]) == 1


def test_report_only_never_gates(tmp_path):
    (tmp_path / "gold.jsonl").write_text(gold("C1", Verdict.UNPROVEN).model_dump_json() + "\n")
    preds = tmp_path / "p.jsonl"
    preds.write_text(
        json.dumps({"claim_id": "C1", "verdict": "supported", "supported_basis": "ai_reviewed"})
        + "\n"
    )
    assert main(["--case", str(tmp_path), "--predictions", str(preds), "--report-only"]) == 0


def test_false_supported_is_split_by_basis():
    g = [gold("C1", Verdict.UNPROVEN), gold("C2", Verdict.CONTRADICTED)]
    p = [
        Prediction(claim_id="C1", verdict=Verdict.SUPPORTED, supported_basis="ai_reviewed"),
        Prediction(claim_id="C2", verdict=Verdict.SUPPORTED, supported_basis="confirmed"),
    ]
    s = score(g, p)
    assert s.n_false_supported == 2
    assert s.false_supported_by_basis == {"ai_reviewed": 1, "confirmed": 1}
