"""Go-bar condition 5 for the small stance model: Baker's real pipeline on the hidden case02.

    python -m eval.stancemodel.hidden_case_bar --model <exported model folder with its policy>

The model is Baker's stance labeler (time_case01.ClassifierLabeler) on case02 with the case's
assumption sheet, Baker's retrieval, quote check, checks and rules, then the simulated expert and
the merge-gate scoring, as `make eval-real` scores case01 for the 14B (GO_BAR.md, condition 5).
The bar: 0 false supported, 0 false contradicted (a claim decided contradicted whose gold verdict
is supported or unproven) and a verdict accuracy of at least 0.80.

case02 is the hidden case. This prints and keeps aggregate numbers only; nobody reads the
per-claim files the pipeline writes under eval/out/case02/. It runs once per finished candidate:
a model whose SHA-256 already has a result is refused. Log the result in
eval/stancedata/TEST_LOG.md with that candidate's test-split scoring. SYNTHETIC; nothing leaves
the machine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.contracts import GoldClaim, Prediction
from eval import run_pipeline as rp
from eval.run_eval import load_jsonl, score

CASE = "case02"
OUT = Path("eval/out/case02/stancemodel")
MIN_VERDICT_ACCURACY = 0.80


def bar_numbers(gold: list[GoldClaim], preds: list[Prediction]) -> dict[str, Any]:
    """The aggregate numbers condition 5 decides on, and nothing per claim."""
    s = score(gold, preds)
    false_contradicted = sum(
        row.get("contradicted", 0) for verdict, row in s.confusion.items()
        if verdict != "contradicted"
    )  # fmt: skip
    return {
        "claims": len(gold),
        "verdict_accuracy": round(s.verdict_accuracy, 3),
        "false_supported": s.n_false_supported,
        "false_contradicted": false_contradicted,
    }


def passes(n: dict[str, Any]) -> bool:
    return (
        n["false_supported"] == 0
        and n["false_contradicted"] == 0
        and n["verdict_accuracy"] >= MIN_VERDICT_ACCURACY
    )


def run(model_dir: Path, out_root: Path = OUT) -> dict[str, Any]:
    from eval.stancemodel.time_case01 import ClassifierLabeler

    meta = json.loads((model_dir / "stancemodel.json").read_text(encoding="utf-8"))
    sha = meta["model_sha256"]
    out = out_root / sha[:16]
    result_path = out / "bar.json"
    if result_path.exists():
        raise SystemExit(f"model {sha[:16]} already has a case02 result; it runs once per model")
    out.mkdir(parents=True, exist_ok=True)
    labelers: list[ClassifierLabeler] = []

    def factory(conn: Any) -> ClassifierLabeler:
        labeler = ClassifierLabeler(conn, model_dir)
        labelers.append(labeler)
        return labeler

    spec = rp.assumption_sheet(CASE)
    preds = rp.run_once(CASE, "real", "accept", out, spec, "simulated", labeler_factory=factory)
    gold = load_jsonl(rp.gold_path(CASE), GoldClaim)
    numbers = bar_numbers(gold, preds)
    summary = {
        "case": CASE,
        "model_dir": str(model_dir),
        "model_sha256": sha,
        "policy": meta.get("policy"),
        "stance_calls": sum(len(lb.seconds) for lb in labelers),
        **numbers,
        "passes": passes(numbers),
    }
    result_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, required=True, help="exported model folder")
    args = ap.parse_args(argv)
    summary = run(args.model)
    print(json.dumps(summary, indent=2))
    return 0 if summary["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
