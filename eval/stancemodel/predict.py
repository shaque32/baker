"""Label probe-format items with an exported small stance model, in eval.stancedata.score format.

    python -m eval.stancemodel.predict --model <exported dir> \
        --items eval/out/stancedata/heldout_dev.jsonl \
        --out eval/out/stancemodel/<run>/dev.predictions.jsonl

One line per item: {"probe_id", "stance", "quote", "probs"}. The quote is cut from the record by
the span head and kept only if core.audit.quotes.verify_quote passes; otherwise the whole record
text is the quote when it passes, and when nothing passes the quote is empty, so the scorer drops
the label (it can never count as "supports"). "irrelevant" needs no quote. The decision policy is
the one stored with the model unless --policy names another file. Local files only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from eval.stancedata.chat import read_jsonl
from eval.stancemodel.encode import Encoded, best_quote, encode
from eval.stancemodel.policy import Policy, decide


def label_items(
    encs: Sequence[Encoded], scores: Sequence[dict[str, Any]], policy: Policy
) -> list[dict[str, Any]]:
    """One row per item. span_quote is kept for every item, so a policy tuned later (tune.py)
    can move a label without running the model again."""
    out = []
    for e, s in zip(encs, scores, strict=True):
        stance = decide(s["probs"], policy)
        span_quote = best_quote(e, s["start"], s["end"]) or ""
        out.append({
            "probe_id": e.probe_id, "stance": stance,
            "quote": "" if stance == "irrelevant" else span_quote,
            "probs": s["probs"], "span_quote": span_quote,
        })  # fmt: skip
    return out


def write_jsonl(rows: Sequence[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    import torch

    from eval.stancemodel.model import load_exported, score_items

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, required=True, help="exported model folder")
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--policy", type=Path, default=None, help="JSON policy; default: the model's")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args(argv)

    torch.set_num_threads(args.threads)
    model, tok, meta = load_exported(args.model)
    policy = Policy.from_dict(
        json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else meta.get("policy")
    )
    items = read_jsonl(args.items)
    t0 = time.perf_counter()
    encs = [encode(it, tok, meta["max_len"]) for it in items]
    scores = score_items(model, encs, tok.pad_token_id, batch_size=args.batch_size)
    rows = label_items(encs, scores, policy)
    secs = time.perf_counter() - t0
    write_jsonl(rows, args.out)
    print(
        f"labeled {len(rows)} items in {secs:.1f} s ({secs / max(1, len(rows)):.3f} s per item, "
        f"batch {args.batch_size}, {args.threads} threads); model sha256 {meta['model_sha256']}; "
        f"policy {policy.to_dict()}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
