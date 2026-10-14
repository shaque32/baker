"""Convert thread 3's probe set (eval/probe_draft/*.jsonl) into the runner's item files.

Usage: python -m eval.probe.from_draft <probe_draft.jsonl> [--out eval/out/probe_items]

Reads the JSON lines directly, so it works before that branch merges. Items are converted
as they are; nothing is edited to help a model pass.

An item in Baker's own wording (eval/stancedata, one that names its record's phone) reads as
Baker shows a case's records: each sender as core.audit.readable prints it, without the
internal account id, a chat record's context opening with its members line, and the claim
carried for a stance prompt that has a {claim} slot (eval/probe/run_probe.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from core.audit.readable import members_line


def fmt(line: dict[str, Any], baker: bool = False) -> str:
    """One context line. A Baker-form sender already prints its app and identifier; its
    account_id is Baker's internal id, which the product never shows a model."""
    if baker:
        return f"[{line['local_time']}] {line['sender']}: {line['text']}"
    return f"[{line['local_time']}] {line['sender']} ({line['account_id']}): {line['text']}"


def convert(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    baker = bool(item.get("device_id"))
    lines = list(item["context"])
    lines.insert(item["target_index"], item["target"])
    shown = [fmt(x, baker) for x in lines]
    if item.get("baker_members"):
        shown.insert(0, members_line(item["baker_members"]))
    context = "\n".join(shown)
    common = {"id": item["probe_id"], "category": item["category"], "trap": item.get("trap"),
              "lang": item["lang"], "assumption": item["assumption"],
              "context": context, "disputed": item.get("disputed"),
              "labeled_by": item.get("labeled_by")}  # fmt: skip
    reviewer = {**common, "overreach": item["category"] == "overreach",
                "quote": item["proposed_quote"], "expected": item["gold_review"]}  # fmt: skip
    stance = {**common, "record_text": item["target"]["text"],
              "record": fmt(item["target"], baker), "expected": item["gold_stance"]}  # fmt: skip
    if item.get("baker_claim"):
        stance["claim"] = item["baker_claim"]
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
