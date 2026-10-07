"""Convert thread 3's probe set (eval/probe_draft/*.jsonl) into the runner's item files.

Usage: python -m eval.probe.from_draft <probe_draft.jsonl> [--out eval/out/probe_items]

Reads the JSON lines directly, so it works before that branch merges. Items are converted
as they are; nothing is edited to help a model pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def fmt(line: dict[str, Any]) -> str:
    return f"[{line['local_time']}] {line['sender']} ({line['account_id']}): {line['text']}"


def convert(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    lines = list(item["context"])
    lines.insert(item["target_index"], item["target"])
    context = "\n".join(fmt(x) for x in lines)
    common = {"id": item["probe_id"], "category": item["category"], "trap": item.get("trap"),
              "lang": item["lang"], "assumption": item["assumption"],
              "context": context}  # fmt: skip
    reviewer = {**common, "overreach": item["category"] == "overreach",
                "quote": item["proposed_quote"], "expected": item["gold_review"]}  # fmt: skip
    stance = {**common, "record_text": item["target"]["text"], "record": fmt(item["target"]),
              "expected": item["gold_stance"]}  # fmt: skip
    return reviewer, stance


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("draft", type=Path)
    ap.add_argument("--out", type=Path, default=Path("eval/out/probe_items"))
    args = ap.parse_args(argv)
    rows = [json.loads(x) for x in args.draft.read_text(encoding="utf-8").splitlines() if x.strip()]
    args.out.mkdir(parents=True, exist_ok=True)
    with (
        (args.out / "reviewer.jsonl").open("w", encoding="utf-8", newline="\n") as rf,
        (args.out / "stance.jsonl").open("w", encoding="utf-8", newline="\n") as sf,
    ):
        for row in rows:
            r, s = convert(row)
            rf.write(json.dumps(r, ensure_ascii=False) + "\n")
            sf.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{len(rows)} items -> {args.out}/reviewer.jsonl, stance.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
