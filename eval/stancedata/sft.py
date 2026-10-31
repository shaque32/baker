"""Chat training records for a fine-tuned local stance model. SYNTHETIC.

    python -m eval.stancedata.sft --items eval/out/stancedata/train.jsonl \
        --out eval/out/stancedata/train.sft.jsonl [--prompt core/audit/prompts/stance.md]

Each generated training item (eval/train, ids T...) becomes one chat. The user turn is the stance
prompt eval.probe.run_probe sends for that item (layout product_members: records shown as Baker
shows a case's records, a group chat's members line first, the claim where the template takes
it), so a model learns on the text it will be asked. The assistant turn is the answer in the
product's JSON: the item's gold stance, its quote and the generator's rationale. No model writes
any of it.

An item is left out, and counted by reason, when its answer would fail the product's own
checks: the answer must validate as a stance output (core.audit.stance), a quote must be
verbatim in the record (core.audit.quotes.verify_quote), and the rationale must not use the words
the tool never says (families.BANNED_WORDS). Held-out items (ids D... and H...) are refused:
training on them would spend the sets that judge the model.

Writes the chats (one JSON line each, byte-identical for the same input) and
`<out>.manifest.json`: the items file's and the prompt's SHA-256, counts by stance, family and
reason left out, and prompt sizes in characters. Nothing here trains a model or loads one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.audit import stance
from core.audit.quotes import verify_quote
from eval.probe import prompts
from eval.probe.from_draft import convert
from eval.stancedata.families import BANNED_WORDS

VERSION = "1.0.0"
LAYOUT = "product_members"  # how the probe and the v1.3 and v1.4 tests show items


def prompt_for(row: dict[str, Any], path: Path) -> str:
    """The stance prompt eval.probe.run_probe.score_stance sends for this item."""
    _, it = convert(row, LAYOUT)
    record = it.get("record") or prompts.record_line(it["record_text"], it["context"])
    claim = (
        (it.get("claim") or prompts.NO_CLAIM) if prompts.has_placeholder(path, "claim") else None
    )
    return prompts.stance_prompt(it["assumption"], record, it["context"], path, claim)


def answer_for(row: dict[str, Any]) -> tuple[str | None, str | None]:
    """The JSON answer the item should get, or (None, why) when it would fail the product's
    checks."""
    gold = row["gold_stance"]
    quote = "" if gold == "irrelevant" else row["proposed_quote"]
    obj = {"stance": gold, "quote": quote, "rationale": row.get("rationale") or ""}
    try:
        stance.validate_stance_output(obj)
    except stance.BadModelOutput:
        return None, "not a valid stance answer"
    if quote and not verify_quote(quote, row["target"]["text"]):
        return None, "quote not verbatim in the record"
    words = obj["rationale"].lower()
    if any(w in words for w in BANNED_WORDS):
        return None, "rationale uses a word the tool never says"
    return json.dumps(obj, ensure_ascii=False), None


def chats(rows: Iterable[dict[str, Any]], path: Path) -> tuple[list[dict[str, Any]], Counter]:
    out: list[dict[str, Any]] = []
    left_out: Counter[str] = Counter()
    for row in rows:
        if not row["probe_id"].startswith("T"):
            raise SystemExit(f"{row['probe_id']}: only training items (ids T...) become chats")
        answer, why = answer_for(row)
        if answer is None:
            left_out[why or "unknown"] += 1
            continue
        out.append(
            {
                "id": row["probe_id"],
                "family": row["family"],
                "stance": row["gold_stance"],
                "generator": row["generator"],
                "messages": [
                    {"role": "user", "content": prompt_for(row, path)},
                    {"role": "assistant", "content": answer},
                ],
            }
        )
    return out, left_out


def manifest(
    items: Path, path: Path, out: list[dict[str, Any]], left_out: Counter[str]
) -> dict[str, Any]:
    sizes = [len(c["messages"][0]["content"]) for c in out]
    return {
        "sft": VERSION,
        "layout": LAYOUT,
        "items": str(items),
        "items_sha256": hashlib.sha256(items.read_bytes()).hexdigest(),
        "prompt": str(path),
        "prompt_version": prompts.prompt_version(path),
        "chats": len(out),
        "left_out": dict(sorted(left_out.items())),
        "by_stance": dict(sorted(Counter(c["stance"] for c in out).items())),
        "by_family": dict(sorted(Counter(c["family"] for c in out).items())),
        "prompt_chars": {
            "mean": round(statistics.fmean(sizes)) if sizes else 0,
            "max": max(sizes, default=0),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--prompt", type=Path, default=prompts.STANCE_PROMPT)
    args = ap.parse_args(argv)
    rows = [json.loads(x) for x in args.items.read_text(encoding="utf-8").splitlines() if x]
    out, left_out = chats(rows, args.prompt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in out), encoding="utf-8"
    )
    m = manifest(args.items, args.prompt, out, left_out)
    side = args.out.with_name(args.out.name + ".manifest.json")
    side.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: m[k] for k in ("chats", "left_out", "by_stance", "prompt_chars")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
