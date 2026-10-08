"""The speed test, the claim recall matcher and the expert-confirms probe score (no model)."""

from __future__ import annotations

from datetime import UTC, datetime

from core.contracts import Claim, ClaimStatus, ClaimType, GoldClaim, GovDocParagraph, Verdict
from eval.probe import claim_recall, time_case
from eval.probe.run_probe import StanceScore, expert_confirms


def test_dry_run_counts_every_stance_call(tmp_path):
    d = time_case.dry_run("case01", time_case.default_spec(), tmp_path)
    assert d["stance_calls"] > 0
    assert sum(d["calls_per_claim"].values()) == d["stance_calls"]
    assert sum(d["stance_calls_by_assumption_kind"].values()) == d["stance_calls"]
    md = time_case.markdown({"case": "case01", "machine": {}, "assumption_spec": "x", "dry_run": d})
    assert f"{d['stance_calls']} stance calls" in md


def _score(confusion: dict[str, dict[str, int]]) -> StanceScore:
    s = StanceScore(confusion=confusion)
    s.n = s.valid = sum(sum(r.values()) for r in confusion.values())
    s.gold_supports = sum(confusion.get("supports", {}).values())
    s.true_supports_predicted = confusion.get("supports", {}).get("supports", 0)
    s.predicted_supports = sum(r.get("supports", 0) for r in confusion.values())
    return s


def test_expert_confirms_passes_a_cautious_labeler():
    m = expert_confirms(
        _score(
            {
                "supports": {"supports": 10},
                "contradicts": {"contradicts": 4, "complicates": 2},
                "complicates": {"supports": 5, "complicates": 5},
            }
        )
    )
    assert m["supports_recall"] == 1.0 and m["contradicts_precision"] == 1.0
    assert m["expert_load_supports_shown"] == 15  # the expert dismisses the 5 extra
    assert m["passes_all"]


def test_expert_confirms_fails_contradiction_shown_as_support():
    m = expert_confirms(
        _score({"supports": {"supports": 10}, "contradicts": {"supports": 1, "contradicts": 3}})
    )
    assert m["contradicts_shown_as_supports"] == 1
    assert not m["bars"]["no_contradicts_shown_as_supports"] and not m["passes_all"]


def test_expert_confirms_fails_missed_support_and_false_contradiction():
    m = expert_confirms(
        _score(
            {
                "supports": {"supports": 8, "dropped": 2},
                "irrelevant": {"contradicts": 1},
                "contradicts": {"contradicts": 4},
            }
        )
    )
    assert m["supports_recall"] == 0.8 and m["contradicts_precision"] == 0.8
    assert not m["bars"]["supports_recall_90"] and not m["bars"]["contradicts_precision_90"]


def _gold(cid: str, para_no: int, text: str) -> GoldClaim:
    return GoldClaim(
        claim_id=cid,
        page=1,
        para_no=para_no,
        text=text,
        claim_type=ClaimType.COMMUNICATION,
        cross_device=False,
        gold_verdict=Verdict.SUPPORTED,
        core_assumptions=(),
        key_evidence=(),
        trap=None,
        rationale="",
        labeled_by="test",
        labeled_at=datetime(2026, 10, 8, tzinfo=UTC),
    )


def _para(i: int) -> GovDocParagraph:
    return GovDocParagraph(
        id=f"p{i}", govdoc_id="g", page=1, para_no=i, label=str(i), char_start=0,
        char_end=1, text="x",
    )  # fmt: skip


def _claim(cid: str, para: str, text: str) -> Claim:
    return Claim(
        id=cid, paragraph_id=para, text=text, claim_type=ClaimType.COMMUNICATION,
        status=ClaimStatus.PROPOSED, model_run_id="r",
    )  # fmt: skip


def test_recall_matches_one_proposal_per_gold_claim_in_its_paragraph():
    gold = [
        _gold("C01", 4, 'At 2:31 a.m. on March 5, 2026, PETROV texted REYES "its done".'),
        _gold("C02", 4, "PETROV and REYES agreed to meet on Monday, March 9, 2026."),
        _gold("C03", 5, "PETROV texted REYES at 2:31 a.m."),
    ]
    proposed = [
        _claim("a", "p4", 'PETROV texted REYES "its done" at 2:31 a.m. on March 5, 2026.'),
        _claim("b", "p4", "PETROV and REYES agreed to meet on Monday, March 8."),  # wrong date
        _claim("c", "p6", "PETROV texted REYES at 2:31 a.m."),  # right words, wrong paragraph
    ]
    rows = {r["claim_id"]: r for r in claim_recall.match(gold, proposed, [_para(4), _para(5)])}
    assert rows["C01"]["matched"] and rows["C01"]["proposal_id"] == "a"
    assert not rows["C02"]["matched"] and not rows["C02"]["numbers_kept"]
    assert not rows["C03"]["matched"] and rows["C03"]["proposal_id"] is None
