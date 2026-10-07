"""Build the probe draft outputs from items.py.

    python -m eval.probe_draft.build

Writes eval/probe_draft/probe_draft.jsonl (one ProbeItem per line, for thread 2's runner) and
eval/probe_draft/PROBE_REVIEW.md (for Arsh to sign line by line). Output is deterministic.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from eval.probe_draft.items import ITEMS
from eval.probe_draft.model import DRAFT_LABEL, ProbeCategory, ProbeItem

HERE = Path(__file__).resolve().parent
JSONL = HERE / "probe_draft.jsonl"
REVIEW = HERE / "PROBE_REVIEW.md"

CATEGORY_ORDER = [
    ProbeCategory.CLEAR_SUPPORT,
    ProbeCategory.OVERREACH,
    ProbeCategory.CONTRADICTS,
    ProbeCategory.COMPLICATES,
    ProbeCategory.IRRELEVANT,
]
CATEGORY_TITLE = {
    ProbeCategory.CLEAR_SUPPORT: "Clear support (reviewer should accept)",
    ProbeCategory.OVERREACH: "Overreach traps (any reviewer accept is a hard fail)",
    ProbeCategory.CONTRADICTS: "Contradicts",
    ProbeCategory.COMPLICATES: "Complicates",
    ProbeCategory.IRRELEVANT: "Irrelevant",
}

HEADER = f"""# Probe set: DRAFT for Arsh's line-by-line review

**Not gold.** Every item below is labeled `{DRAFT_LABEL}`. All data is synthetic and fictional.

## What signing means

Each item is one decision: one assumption, one message shown in its surrounding messages, and the
right answer. Tick **agree** when a careful defense forensic expert, reading only the lines shown,
would give the same stance and the same reviewer decision. Tick **change to** and write the
stance (supports, contradicts, complicates, irrelevant) when you disagree; drop an item you find
debatable. Signed items are copied into `eval/gold/` by the frozen-files thread with
`labeled_by` set to you. Agreement with a cloud model never makes an item right.

## How to read an item

- All lines of an item come from one phone and one chat (1:1 unless it says group).
- `(owner)` marks the phone's own account. "The owner" in an assumption means that account.
- Contacts are named as the phone saved them. A saved name or handle is a label, not proof of
  identity.
- Times are the phone's local time. Dates in assumptions are local dates.
- ▶ marks the message being labeled. "Quote" is what a labeler would cite as support.
- Stances: **supports** = the message, in context, plainly establishes the assumption.
  **contradicts** = it asserts or shows the opposite (other sender, date, count, or an explicit
  statement or correction). **complicates** = it bears on the assumption but neither establishes
  it nor asserts the opposite. **irrelevant** = it does not bear on the assumption.
- Review: the AI reviewer is shown the quote as a "supports" label. **accept** is right only
  when the stance is supports; otherwise the right answer is **dismiss**.

## Pass bars for a candidate local model

- precision of "supports" >= 95%
- recall of "supports" >= 90%
- **zero reviewer accepts on overreach items**
"""


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ") or "(empty)"


def _summary(items: list[ProbeItem]) -> list[str]:
    cats = Counter(i.category for i in items)
    out = [
        "## Summary",
        "",
        "| Category | Items | en | ru | mixed | from case01 |",
        "|---|---|---|---|---|---|",
    ]
    for c in CATEGORY_ORDER:
        sub = [i for i in items if i.category == c]
        langs = Counter(i.lang for i in sub)
        case01 = sum(1 for i in sub if i.source == "case01")
        out.append(
            f"| {c.value} | {cats[c]} | {langs['en']} | {langs['ru']} | {langs['mixed']} "
            f"| {case01} |"
        )
    langs = Counter(i.lang for i in items)
    case01 = sum(1 for i in items if i.source == "case01")
    out.append(
        f"| **total** | {len(items)} | {langs['en']} | {langs['ru']} | {langs['mixed']} "
        f"| {case01} |"
    )
    traps = Counter(i.trap for i in items if i.category == ProbeCategory.OVERREACH)
    out += ["", "Overreach traps: " + ", ".join(f"{t} {n}" for t, n in sorted(traps.items())), ""]
    return out


def _block(it: ProbeItem) -> list[str]:
    head = f"### {it.probe_id}"
    meta = [it.category.value, it.lang, it.assumption_kind.value, it.source]
    if it.trap:
        meta.insert(1, f"trap: {it.trap}")
    out = [head, "", f"*{' · '.join(meta)}*", "", f"**Assumption:** {it.assumption}", ""]
    out += ["| | Time (local) | Sender | Text |", "|---|---|---|---|"]
    for i, line in enumerate(it.lines()):
        mark = "▶" if i == it.target_index else ""
        out.append(f"| {mark} | {line.local_time} | {_cell(line.sender)} | {_cell(line.text)} |")
    out += [
        "",
        f"**Quote:** `{it.proposed_quote}`  ",
        f"**Gold:** {it.gold_stance.value} / review {it.gold_review}  ",
        f"**Why:** {it.rationale}",
        "",
        "Arsh: [ ] agree  [ ] change to ____",
        "",
    ]
    return out


def render_jsonl(items: list[ProbeItem]) -> str:
    return "".join(i.model_dump_json() + "\n" for i in items)


def render_review(items: list[ProbeItem]) -> str:
    out = HEADER.splitlines() + [""] + _summary(items)
    for c in CATEGORY_ORDER:
        out += [f"## {CATEGORY_TITLE[c]}", ""]
        for it in items:
            if it.category == c:
                out += _block(it)
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    JSONL.write_text(render_jsonl(ITEMS), encoding="utf-8")
    REVIEW.write_text(render_review(ITEMS), encoding="utf-8")
    print(f"{len(ITEMS)} probe items -> {JSONL.name}, {REVIEW.name}")


if __name__ == "__main__":
    main()
