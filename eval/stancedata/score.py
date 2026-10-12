"""Score any stance labeler's predictions on probe-format items with the go-bar definitions.

    python -m eval.stancedata.score --items eval/gold/probe/probe.jsonl \
        --predictions eval/out/candidate/probe.predictions.jsonl

A prediction line is {"probe_id": "...", "stance": "...", "quote": "..."}; a missing or
malformed line counts as invalid output. This is how a model that is not a llama.cpp chat model
(the small classifier) is scored. Every rule matches eval.probe.run_probe.score_stance and its
"Expert confirms" bars exactly (a test runs both on the same outputs): a quote that is not
verbatim in the record drops the label, so it can never count as "supports"; an irrelevant label
needs no quote.

Gated items are signed and undisputed (run_probe.is_gated). Generated items carry a DRAFT label
until Arsh signs a sample, so before that the held-out bars are reported as provisional, on the
undisputed items, and decide nothing (GO_BAR.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from eval.probe.run_probe import StanceScore, expert_confirms, is_gated
from eval.stancedata.chat import read_jsonl

STANCES = ("supports", "contradicts", "complicates", "irrelevant")


def add_prediction(s: StanceScore, item: dict[str, Any], pred: dict[str, Any] | None) -> str:
    """Count one item the way run_probe.score_stance does; return the label as scored."""
    expected = item["gold_stance"]
    record_text = item["target"]["text"]
    s.n += 1
    s.repeat_identical += 1  # one deterministic pass; repeat checks belong to run_probe
    s.gold_supports += expected == "supports"
    if not pred or pred.get("stance") not in STANCES or not isinstance(pred.get("quote", ""), str):
        row = s.confusion.setdefault(expected, {})
        row["invalid"] = row.get("invalid", 0) + 1
        s.failures.append({"id": item["probe_id"], "error": "invalid output"})
        return "invalid"
    s.valid += 1
    quote = pred.get("quote", "")
    quote_ok = bool(quote) and quote in record_text
    s.quote_verified += quote_ok
    stance = pred["stance"] if quote_ok else "dropped"
    shown = "irrelevant" if pred["stance"] == "irrelevant" else stance
    row = s.confusion.setdefault(expected, {})
    row[shown] = row.get(shown, 0) + 1
    s.correct += stance == expected
    if stance == "supports":
        s.predicted_supports += 1
        s.true_supports_predicted += expected == "supports"
    if stance != expected:
        s.failures.append({"id": item["probe_id"], "category": item["category"],
                           "expected": expected, "got": stance, "quote": quote[:200]})  # fmt: skip
    return shown


def score(items: list[dict[str, Any]], preds: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Bars on gated items, plus the same bars on every undisputed item (provisional view)."""
    views = {
        "gated": [i for i in items if is_gated(i)],
        "undisputed": [i for i in items if not i.get("disputed")],
        "disputed": [i for i in items if i.get("disputed")],
    }
    out: dict[str, Any] = {"items": len(items)}
    for name, subset in views.items():
        s = StanceScore()
        shown_by_item = {}
        for it in subset:
            shown_by_item[it["probe_id"]] = add_prediction(s, it, preds.get(it["probe_id"]))
        m = expert_confirms(s) if subset else {"passes_all": None}
        m["n"] = len(subset)
        overreach = [i for i in subset if i["category"] == "overreach"]
        m["overreach_items"] = len(overreach)
        m["overreach_shown_as_supports"] = sum(
            shown_by_item[i["probe_id"]] == "supports" for i in overreach
        )
        m["gold_contradicts"] = sum(i["gold_stance"] == "contradicts" for i in subset)
        m["by_family"] = _by_key(subset, shown_by_item, "family")
        m["by_lang"] = _by_key(subset, shown_by_item, "lang")
        m["failures"] = s.failures
        out[name] = m
    return out


def _by_key(items: list[dict], shown: dict[str, str], key: str) -> dict[str, dict[str, int]]:
    table: dict[str, Counter] = {}
    for it in items:
        k = str(it.get(key) or it.get("category"))
        table.setdefault(k, Counter())[f"{it['gold_stance']}->{shown[it['probe_id']]}"] += 1
    return {k: dict(sorted(v.items())) for k, v in sorted(table.items())}


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # counts as invalid for whichever item it was meant for
        if isinstance(row, dict) and isinstance(row.get("probe_id"), str):
            if row["probe_id"] in out:
                raise ValueError(f"{path}:{n}: second prediction for {row['probe_id']}")
            out[row["probe_id"]] = row
    return out


def summary_table(result: dict[str, Any]) -> str:
    cols = ["n", "stance_valid_output", "supports_recall", "contradicts_precision",
            "contradicts_shown_as_supports", "gold_contradicts", "overreach_shown_as_supports",
            "overreach_items", "expert_load_precision", "passes_all"]  # fmt: skip
    lines = ["| view | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for view in ("gated", "undisputed", "disputed"):
        m = result[view]
        cells = []
        for c in cols:
            v = m.get(c)
            cells.append(f"{v:.1%}" if isinstance(v, float) else "n/a" if v is None else str(v))
        lines.append(f"| {view} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None, help="write the full result as JSON")
    args = ap.parse_args(argv)
    result = score(read_jsonl(args.items), load_predictions(args.predictions))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(summary_table(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
