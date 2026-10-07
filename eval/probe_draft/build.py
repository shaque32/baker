"""Build the probe draft outputs from items.py.

    python -m eval.probe_draft.build

Writes eval/probe_draft/probe_draft.jsonl (one ProbeItem per line, for thread 2's runner) and
eval/probe_draft/PROBE_REVIEW.md (for Arsh to sign line by line). Output is deterministic.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from eval.probe_draft.items import ITEMS
from eval.probe_draft.model import DRAFT_LABEL, SIGNED_LABEL, ProbeCategory, ProbeItem

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

HEADER = f"""# Probe set

**P001-P088 are signed** (`{SIGNED_LABEL}`): Arsh adopted the second outside review as his
labels. **P089-P097 are drafts** (`{DRAFT_LABEL}`), added after that review to break label cues,
and wait for his sign-off. Items marked **disputed** have a reasonable competing label; they are
scored and reported on their own and never count toward a pass bar. All data is synthetic and
fictional.

## What signing means

Each item is one decision: one assumption, one message shown in its surrounding messages, and the
right answer. Tick **agree** when a careful defense forensic expert, reading only the lines shown,
would give the same stance and the same reviewer decision. Tick **change to** and write the
stance (supports, contradicts, complicates, irrelevant) when you disagree; drop an item you find
debatable. Signed items are copied into `eval/gold/` by the frozen-files thread with
`labeled_by` set to you. Agreement with a cloud model never makes an item right.

## How to read an item

- All lines of an item come from one phone and one chat (1:1 unless it says group). Items come
  from different phones, so owner ids can differ between items.
- `(owner)` marks the phone's own account. "The owner" in an assumption means that account. An
  assumption that names a person ("Dan wrote...", "Kaz told...") is about the human who typed;
  an account name alone does not show who that was.
- Contacts are named as the phone saved them. A saved name or handle is a label, not proof of
  identity.
- Times are the phone's local time, with the offset shown on each line; follow the offset shown
  (US Eastern moved to EDT on 2026-03-08 and back to EST on 2025-11-02). Dates in assumptions
  are local dates.
- ▶ marks the message being labeled. "Quote" is what a labeler would cite as support.
- Stances: **supports** = the message, in context, plainly establishes the assumption.
  **contradicts** = it asserts or shows the opposite (other sender, date, count, or an explicit
  statement or correction). **complicates** = it bears on the assumption but neither establishes
  it nor asserts the opposite. **irrelevant** = it does not bear on the assumption.
- An assumption with several parts is supported only if every part is.
- Read words in light of the lines shown: a pronoun, "outside" or "ok works" resolves against
  the conversation. A slang or code reading counts as established only when the conversation
  itself confirms it.
- An assumption that something happened (not that someone said it) is supported by a firsthand
  report of it in the message. A plan, promise, prediction or secondhand report complicates.
- Wrong person: when the record attributes the words to a different account, or, by quotation,
  to a different person than the assumption names, the stance is **contradicts**.
- Sarcasm about a fact ("sure, I was there") leaves the fact unsettled: **complicates**. When
  the assumption is about what the message does (praise, thanks) and the context shows it does
  the opposite, the stance is **contradicts**.
- Coded readings (a benchmark convention, not a general relevance judgment): when the message
  holds the words the assumption reads as code ("tickets", "the white", "shot") and the context
  points elsewhere, the stance is **complicates**: context makes another meaning likely but
  does not rule the code reading out. When the message does not touch the assumption's words or
  subject, it is **irrelevant**.
- A bare amount ("300", "2k") is read as dollars.
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
    ]
    if it.disputed:
        out += [f"**Disputed:** {it.disputed}", ""]
    if it.labeled_by == SIGNED_LABEL:
        out += [f"Signed: {it.labeled_by}", ""]
    else:
        out += ["Arsh: [ ] agree  [ ] change to ____", ""]
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
