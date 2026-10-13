"""Pick the decision policy on the dev split (ids D...) only, never on a test set.

    python -m eval.stancemodel.tune --items eval/out/stancedata/heldout_dev.jsonl \
        --predictions <dev predictions with probs> --out <policy.json>

Reads the four probabilities predict.py stored per item and replays every policy on a grid
through eval.stancedata.score, so a policy is scored exactly as the go bar scores it. The rule,
fixed before any dev result was seen:

1. Keep the policies that clear the go bar's three accuracy bars on the dev split with a margin:
   zero contradicting records shown as "supports", supports recall at least 95% and contradicts
   precision at least 95% (the bars are 90%).
2. Among those, take the strictest "supports": the highest supports_min, then the lowest
   supports_max_contradicts. Then the highest contradicts_min that keeps contradicts recall
   within 2 points of its best among the kept policies.
3. If no policy clears step 1, report the closest ones and write nothing: the model is not ready.

The quotes are the ones predict.py cut (span_quote); a policy only moves labels between stances.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

from eval.stancedata.chat import read_jsonl
from eval.stancedata.score import load_predictions, score
from eval.stancemodel.policy import Policy, decide

GRID_SUPPORTS_MIN = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99)
GRID_SUPPORTS_MAX_CONTRA = (1.0, 0.3, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002)
GRID_CONTRADICTS_MIN = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99)
MARGIN = {"supports_recall": 0.95, "contradicts_precision": 0.95}


def replay(
    items: list[dict[str, Any]], preds: dict[str, dict[str, Any]], policy: Policy
) -> dict[str, Any]:
    rows = {}
    for it in items:
        p = preds[it["probe_id"]]
        stance = decide(p["probs"], policy)
        quote = "" if stance == "irrelevant" else p["span_quote"]
        rows[it["probe_id"]] = {"stance": stance, "quote": quote}
    m = score(items, rows)["undisputed"]
    keep = ("supports_recall", "contradicts_precision", "contradicts_recall",
            "contradicts_shown_as_supports", "overreach_shown_as_supports",
            "expert_load_precision")  # fmt: skip
    return {k: m.get(k) for k in keep}


def feasible(m: dict[str, Any]) -> bool:
    return (
        m["contradicts_shown_as_supports"] == 0
        and (m["supports_recall"] or 0) >= MARGIN["supports_recall"]
        and (m["contradicts_precision"] or 0) >= MARGIN["contradicts_precision"]
    )


def choose(rows: list[tuple[Policy, dict[str, Any]]]) -> Policy | None:
    ok = [(p, m) for p, m in rows if feasible(m)]
    if not ok:
        return None
    best_s = max(ok, key=lambda pm: (pm[0].supports_min, -pm[0].supports_max_contradicts))[0]
    same_s = [
        (p, m)
        for p, m in ok
        if (p.supports_min, p.supports_max_contradicts)
        == (best_s.supports_min, best_s.supports_max_contradicts)
    ]
    top_recall = max(m["contradicts_recall"] or 0 for _, m in same_s)
    near = [(p, m) for p, m in same_s if (m["contradicts_recall"] or 0) >= top_recall - 0.02]
    return max(near, key=lambda pm: pm[0].contradicts_min)[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    items = read_jsonl(args.items)
    if any(not it["probe_id"].startswith("D") for it in items):
        raise SystemExit("policies are tuned on the dev split only (ids D...)")
    preds = load_predictions(args.predictions)
    rows = []
    for s_min, s_max_c, c_min in itertools.product(
        GRID_SUPPORTS_MIN, GRID_SUPPORTS_MAX_CONTRA, GRID_CONTRADICTS_MIN
    ):
        pol = Policy(supports_min=s_min, supports_max_contradicts=s_max_c, contradicts_min=c_min)
        rows.append((pol, replay(items, preds, pol)))
    default = replay(items, preds, Policy())
    print("default policy:", json.dumps(default))
    chosen = choose(rows)
    if chosen is None:
        near = sorted(rows, key=lambda pm: (pm[1]["contradicts_shown_as_supports"],
                                            -(pm[1]["supports_recall"] or 0)))[:5]  # fmt: skip
        for p, m in near:
            print("closest:", json.dumps(p.to_dict()), json.dumps(m))
        print("no policy clears the dev bars with margin; nothing written")
        return 1
    m = replay(items, preds, chosen)
    print("chosen:", json.dumps(chosen.to_dict()), json.dumps(m))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(chosen.to_dict(), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
