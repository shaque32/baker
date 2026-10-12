"""Build the label review sheet: a random sample of generated items for Arsh to check.

    python -m eval.stancedata.review_sheet --train eval/out/stancedata/train.jsonl \
        --heldout eval/out/stancedata/heldout_test.jsonl --out <sheet.md>

The sample is fixed by SEED, drawn evenly across families, so every family gets looked at. Each
item shows what the model will see (assumption, the chat with the record marked) and the answer
the generator assigned; Arsh ticks agree or writes the right answer. LABELING_GUIDE.md says what
happens next: more than 2% wrong in either sample and the generator is fixed and rebuilt.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

from eval.stancedata.chat import read_jsonl, sha256_file

SEED = 20261009
TRAIN_SAMPLE = 200
HELDOUT_SAMPLE = 100


def sample(rows: list[dict], k: int, seed: int) -> list[dict]:
    """k items spread as evenly as possible over families, then by a fixed shuffle."""
    rng = random.Random(seed)  # noqa: S311 - a fixed sample, not security
    by_family: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_family[row["family"]].append(row)
    pools = {f: rng.sample(items, len(items)) for f, items in sorted(by_family.items())}
    picked: list[dict] = []
    while len(picked) < k and any(pools.values()):
        for f in sorted(pools):
            if pools[f] and len(picked) < k:
                picked.append(pools[f].pop())
    return sorted(picked, key=lambda r: r["probe_id"])


def render_item(row: dict) -> list[str]:
    lines = list(row["context"])
    lines.insert(row["target_index"], {**row["target"], "marked": True})
    trap = f", trap: {row['trap']}" if row.get("trap") else ""
    out = [f"### {row['probe_id']}: {row['gold_stance']}{trap} ({row['lang']})", ""]
    out.append(f"**Assumption:** {row['assumption']}")
    out.append("")
    for line in lines:
        mark = "**>>**" if line.get("marked") else "  "
        out.append(f"- {mark} `{line['local_time']}` {line['sender']}: {line['text']}")
    out.append("")
    out.append(f'**Answer:** {row["gold_stance"]}. **Quote:** "{row["proposed_quote"]}"')
    out.append(f"**Why:** {row['rationale']}")
    if row.get("disputed"):
        out.append(f"**Disputed:** {row['disputed']}")
    out.append("")
    out.append("[ ] agree   [ ] change to: ________   note: ________")
    out.append("")
    return out


def build(train: Path | None, heldout: Path | None) -> str:
    out = [
        "# Label review sheet: generated stance data",
        "",
        "SYNTHETIC. For Arsh to check. Each item shows the assumption, the chat with the record",
        "marked **>>**, and the answer the generator gave it. Tick agree, or write the answer you",
        "would give. More than 2% wrong in either part (more than 4 of 200, or more than 2 of 100)",
        "means the generator is fixed, everything is rebuilt and a new sample is drawn.",
        "",
        "The rules are in eval/stancedata/LABELING_GUIDE.md. In short: supports only when the",
        "record plainly shows the assumption; contradicts when it shows something that cannot be",
        "true with it; complicates when it bears on it but leaves it open; irrelevant otherwise.",
        "",
    ]
    parts = [("Part 1: training examples", train, TRAIN_SAMPLE, SEED),
             ("Part 2: held-out test examples", heldout, HELDOUT_SAMPLE, SEED + 1)]  # fmt: skip
    for title, path, k, seed in parts:
        if path is None:
            continue
        rows = read_jsonl(path)
        picked = sample(rows, k, seed)
        out += [f"## {title}", ""]
        out.append(f"{len(picked)} of {len(rows)} items from `{path.name}` (SHA-256 "
                   f"`{sha256_file(path)[:16]}`), sample seed {seed}.")  # fmt: skip
        out.append("")
        for row in picked:
            out += render_item(row)
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--train", type=Path, default=None)
    ap.add_argument("--heldout", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(args.train, args.heldout), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
