"""Cloud check for the other two model steps: claim proposal and assumption filling on Claude.

EVAL ONLY, synthetic case01 only. It answers one question for Arsh (decision of 2026-10-15,
"Yes, after a check"): can claim proposal and assumption filling go cloud first like stance
labeling (PR #68)? It runs the product's own code paths with core.llm.cloud.ClaudeModel:

1. Claim proposal: `baker claims propose` on the case01 mock affidavit, scored by
   eval/probe/claim_recall.py against the 20 gold claims.
2. The whole audit with no assumption sheet: the model fills the assumptions (the real
   core/audit/assumption_filler.py), the model labels stance, then the simulated expert and
   the merge-gate scoring, as eval/bench/claude_bench.py does with the sheet.

Decision rule, fixed before the run (2026-10-15):
  a. claim proposal recall >= 90% (the 14B's measured recall, eval/probe/README.md), and
  b. the sheet-free audit has 0 false supported and verdict accuracy >= 0.80 (the merge gate).
Both pass: the two steps move to cloud first with the local fallback. Either fails: they stay
local, and the result says which bar.

Usage:
  env -u ANTHROPIC_BASE_URL BAKER_ANTHROPIC_API_KEY="$BAKER_BENCH_API_KEY" \\
      python -m eval.bench.cloud_steps [--model claude-opus-5-5] [--effort medium]
      [--skip-claims] [--skip-audit] [--out eval/out/bench-steps]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from core.llm import cloud
from eval.bench.claude_bench import PRICES_PER_MTOK, check_case

CASE = "case01"
RECALL_BAR = 0.90
ACCURACY_BAR = 0.80


class Metered:
    """A ClaudeModel that counts tokens and seconds, for the cost line."""

    def __init__(self, model: cloud.ClaudeModel) -> None:
        self._m = model
        self.name, self.sha256, self.params, self.where = (
            model.name, model.sha256, model.params, model.where
        )  # fmt: skip
        self.calls = self.errors = self.input_tokens = self.output_tokens = 0
        self.seconds = 0.0

    def generate_json(self, prompt: str, schema: Any, params: Any = None) -> Any:
        self.calls += 1
        try:
            out = self._m.generate_json(prompt, schema, params)
        except cloud.CloudError:
            self.errors += 1
            raise
        self.input_tokens += out.prompt_tokens
        self.output_tokens += out.completion_tokens
        self.seconds += out.seconds
        return out

    def usage(self) -> dict[str, Any]:
        inp, outp = PRICES_PER_MTOK.get(self.name, (0.0, 0.0))
        cost = (self.input_tokens * inp + self.output_tokens * outp) / 1_000_000
        return {"calls": self.calls, "errors": self.errors, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "seconds": round(self.seconds, 1),
                "cost_usd": round(cost, 2)}  # fmt: skip


def claims_step(model: Metered, out: Path) -> dict[str, Any]:
    from eval.probe.claim_recall import recall_for

    before = model.usage()
    res = recall_for(model, CASE, out)
    after = model.usage()
    res["usage"] = {k: round(after[k] - before[k], 2) for k in after}
    return res


def audit_step(model: Metered, out: Path) -> dict[str, Any]:
    from core.contracts import GoldClaim
    from eval import run_pipeline as rp
    from eval.run_eval import load_jsonl, score

    before = model.usage()
    start = time.perf_counter()
    preds = rp.run_once(CASE, "real", "accept", out, None, "simulated", labeler_model=model,
                        filler_model=model)  # fmt: skip
    wall = time.perf_counter() - start
    gold = load_jsonl(rp.gold_path(CASE), GoldClaim)
    s = score(gold, preds)
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    after = model.usage()
    return {
        "verdict_accuracy": round(s.verdict_accuracy, 3),
        "n_false_supported": s.n_false_supported,
        "confusion": s.confusion,
        "verdicts": run.get("verdicts"),
        "dropped_labels": run.get("dropped_labels"),
        "wall_seconds": round(wall, 1),
        "usage": {k: round(after[k] - before[k], 2) for k in after},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=cloud.DEFAULT_MODEL)
    ap.add_argument("--effort", default=cloud.DEFAULT_EFFORT, choices=cloud.EFFORTS)
    ap.add_argument("--skip-claims", action="store_true")
    ap.add_argument("--skip-audit", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("eval/out/bench-steps"))
    args = ap.parse_args(argv)
    check_case(CASE)
    cfg = cloud.load_config()
    model = Metered(cloud.ClaudeModel(cloud.CloudConfig(
        api_key=cfg.api_key, model=args.model, effort=args.effort)))  # fmt: skip
    args.out.mkdir(parents=True, exist_ok=True)
    res: dict[str, Any] = {"model": args.model, "effort": args.effort, "case": CASE}
    if not args.skip_claims:
        print("claims: proposing", file=sys.stderr, flush=True)
        res["claims"] = claims_step(model, args.out / "claims")
    if not args.skip_audit:
        print("audit: filling assumptions and labeling", file=sys.stderr, flush=True)
        res["audit"] = audit_step(model, args.out / "audit")
    c, a = res.get("claims"), res.get("audit")
    res["bars"] = {
        "claim_recall": None if c is None else c["recall"] >= RECALL_BAR,
        "audit_gate": None
        if a is None
        else a["n_false_supported"] == 0 and a["verdict_accuracy"] >= ACCURACY_BAR,
    }
    res["usage_total"] = model.usage()
    (args.out / "result.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    brief = {k: res[k] for k in ("model", "effort", "bars", "usage_total")}
    if c:
        brief["claims"] = {k: c[k] for k in ("recall", "matched", "gold_claims", "proposed")}
    if a:
        brief["audit"] = {k: a[k] for k in ("verdict_accuracy", "n_false_supported", "verdicts")}
    print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
