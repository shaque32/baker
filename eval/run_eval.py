"""Score pipeline predictions against gold verdicts. This is the merge gate.

Usage: python -m eval.run_eval [--case eval/gold/case01] [--predictions <path>]
Predictions default to eval/out/<case>/predictions.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from core.contracts import GoldClaim, Prediction, Verdict

# Gate thresholds. Human-owned: change only with Arsh's sign-off.
MIN_VERDICT_ACCURACY = 0.80
MAX_FALSE_SUPPORTED_RATE = 0.05


@dataclass(frozen=True)
class Scores:
    n_gold: int
    n_predicted: int
    verdict_accuracy: float
    false_supported_rate: float  # gold is not 'supported' but prediction says 'supported'
    confusion: dict[str, dict[str, int]]  # gold verdict -> predicted verdict ('missing' if absent)


def load_jsonl[T: (GoldClaim, Prediction)](path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [model.model_validate(json.loads(line)) for line in lines if line.strip()]


def score(gold: list[GoldClaim], predictions: list[Prediction]) -> Scores:
    ids = [g.claim_id for g in gold]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate claim_id in gold")
    by_id = {p.claim_id: p for p in predictions}

    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    not_supported = 0
    false_supported = 0
    for g in gold:
        pred = by_id.get(g.claim_id)
        got = pred.verdict.value if pred else "missing"
        row = confusion.setdefault(g.gold_verdict.value, {})
        row[got] = row.get(got, 0) + 1
        if pred and pred.verdict == g.gold_verdict:
            correct += 1
        if g.gold_verdict != Verdict.SUPPORTED:
            not_supported += 1
            if pred and pred.verdict == Verdict.SUPPORTED:
                false_supported += 1

    return Scores(
        n_gold=len(gold),
        n_predicted=sum(1 for g in gold if g.claim_id in by_id),
        verdict_accuracy=correct / len(gold) if gold else 0.0,
        false_supported_rate=false_supported / not_supported if not_supported else 0.0,
        confusion=confusion,
    )


def passes(s: Scores) -> bool:
    return (
        s.verdict_accuracy >= MIN_VERDICT_ACCURACY
        and s.false_supported_rate <= MAX_FALSE_SUPPORTED_RATE
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=Path("eval/gold/case01"))
    parser.add_argument("--predictions", type=Path, default=None)
    args = parser.parse_args(argv)

    predictions_path = args.predictions or Path("eval/out") / args.case.name / "predictions.jsonl"
    gold = load_jsonl(args.case / "gold.jsonl", GoldClaim)
    predictions = load_jsonl(predictions_path, Prediction)

    if not gold:
        print(f"eval: {args.case} has no gold labels yet; nothing to score.")
        return 0
    if not predictions:
        print(f"eval: {len(gold)} gold claims, no predictions at {predictions_path}.")
        return 0

    s = score(gold, predictions)
    print(json.dumps(s.__dict__, indent=2))
    ok = passes(s)
    print(
        f"eval: {'PASS' if ok else 'FAIL'} "
        f"(accuracy {s.verdict_accuracy:.2f} >= {MIN_VERDICT_ACCURACY}, "
        f"false-supported {s.false_supported_rate:.2f} <= {MAX_FALSE_SUPPORTED_RATE})"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
