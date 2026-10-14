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

from core.audit.readable import members_line
from eval.stancedata.chat import read_jsonl, sha256_file

# 20261009 drew the first sheet, which Arsh sent back on 2026-10-13; a rebuild draws a new one.
SEED = 20261013
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
    if row.get("baker_claim"):
        out.append(f"**Claim (shown with the assumption):** {row['baker_claim']}")
        out.append("")
    out.append(f"**Assumption:** {row['assumption']}")
    out.append("")
    device = row.get("device_id")
    phone = f" (record from {device.removeprefix('dev:')})" if device else ""
    if row.get("baker_members"):
        out.append(f"- {members_line(row['baker_members'])}")
    for line in lines:
        mark = f"**>>**{phone}" if line.get("marked") else "  "
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
        "The full rules are in eval/stancedata/LABELING_GUIDE.md (draft v0.3). The ones a",
        "reader most needs:",
        "",
        "- **supports**: the record, read in its context, plainly shows what the assumption",
        "  states, with no slang, code word, unresolved pronoun or outside fact needed.",
        "- **contradicts**: what the record says cannot be true together with the assumption,",
        "  with no unstated fact needed: not where home is, not whether it could still happen",
        "  later that day. The quote itself must carry the contradiction.",
        "- **complicates**: the record bears on the assumption but leaves it open.",
        "- **irrelevant**: the record does not bear on the assumption.",
        "- **Context explains, never reverses.** The chat may tell what the quoted words refer to,",
        "  but when a later message corrects the record, the record is complicates and the",
        "  correcting message is the contradicting one.",
        "- **One record cannot prove a message does not exist.** The same words on another date or",
        "  from another account leave the assumption open, unless the assumption itself excludes",
        '  other messages ("first contact on", "no contact between").',
        "- **Slang never supports.** A Russian record that needs a slang or loose reading is",
        "  complicates, because the claim then rests on a translation the record does not settle.",
        '- **Rationales claim only what is shown.** A "lol" leaves sincerity open; a denial',
        "  conflicts in what it says, which does not make it true.",
        "- **Baker's own wording** (rules 25 to 29). Some assumptions are Baker's template text",
        '  with the case\'s names: `item3` is a phone, "Lena Okafor (the user of item3)" the',
        "  person an expert stipulated as its user, a name alone a person the document names,",
        '  "Telegram 5550147" an account (the same account on every phone). A line shows',
        "  \"(owner)\" for the record's own phone's account and, in brackets, the people Baker",
        "  holds as confirmed for that account; a person in no bracket is not shown, whatever",
        "  the chat calls anyone. A message's chat opens with the accounts seen in it, so a",
        "  line with the owner's account and one other is a chat between those two; a member",
        "  who never sent and was never listed is missing. A call's text prints the report's",
        "  time (often UTC); the line's local time decides. For the meaning, role and event",
        "  templates the claim is shown: only the words' own user explaining them, or the",
        "  claimed message or call itself, supports; only a named person's own denial or alibi,",
        "  from an account bracketed with them, contradicts; another meaning from the words'",
        "  own user is complicates, since it says nothing about the claim's other messages.",
        '- **Time words as Baker reads them.** "At about 9 p.m." is 8:52 to 9:08 p.m. "This',
        '  Saturday" is plain only for a later day of the same Monday-to-Saturday week; sent on',
        '  any other day, which date it means is open, as with "next Saturday" or a bare',
        "  weekday sent on that same weekday.",
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
