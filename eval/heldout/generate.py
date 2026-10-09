"""Generate the held-out stance set: two JSONL splits and a manifest.

    python -m eval.heldout.generate --out-dir eval/out/stancedata

Item i of a split is built from `item_rng(GENERATOR, seed, i)` and the fixed schedule alone, so
the output is byte-identical from run to run and from machine to machine.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from eval.heldout import GENERATOR, ID_PREFIX, SEEDS, SOURCE
from eval.heldout import writers_a as wa
from eval.heldout import writers_b as wb
from eval.heldout.scene import finish
from eval.heldout.schedule import COMPOSITION, schedule
from eval.stancedata.chat import item_rng, write_jsonl
from eval.stancedata.families import family
from eval.stancedata.model import GenItem

WRITERS: dict[str, Callable] = {
    "sup_verbatim": wa.sup_verbatim,
    "sup_plain": wa.sup_plain,
    "sup_answer": wa.sup_answer,
    "sup_time_window": wa.sup_time_window,
    "sup_contact": wa.sup_contact,
    "sup_account_shared": wa.sup_account_shared,
    "sup_injection": wa.sup_injection,
    "con_denial": wa.con_denial,
    "con_other_value": wa.con_other_value,
    "con_other_state": wa.con_other_state,
    "con_in_window": wa.con_in_window,
    "con_other_speaker": wa.con_other_speaker,
    "ovr_time_mismatch": wb.ovr_time_mismatch,
    "ovr_sender_mismatch": wb.ovr_sender_mismatch,
    "ovr_later_correction": wb.ovr_later_correction,
    "ovr_negation": wb.ovr_negation,
    "ovr_handle_owner": wb.ovr_handle_owner,
    "ovr_shared_account": wb.ovr_shared_account,
    "ovr_pronoun": wb.ovr_pronoun,
    "ovr_code_word": wb.ovr_code_word,
    "ovr_different_topic": wb.ovr_different_topic,
    "ovr_hypothetical": wb.ovr_hypothetical,
    "ovr_plan": wb.ovr_plan,
    "ovr_question": wb.ovr_question,
    "ovr_joke": wb.ovr_joke,
    "ovr_partial": wb.ovr_partial,
    "ovr_count": wb.ovr_count,
    "ovr_translation": wb.ovr_translation,
    "ovr_injection_related": wb.ovr_injection_related,
    "ovr_injection_unrelated": wb.ovr_injection_unrelated,
    "cpl_hedge": wb.cpl_hedge,
    "cpl_disputed_claim": wb.cpl_disputed_claim,
    "cpl_inference": wb.cpl_inference,
    "cpl_hearsay": wb.cpl_hearsay,
    "cpl_relative_time": wb.cpl_relative_time,
    "irr_other_topic": wb.irr_other_topic,
    "irr_pleasantry": wb.irr_pleasantry,
}
assert set(WRITERS) == set(COMPOSITION), "every scheduled family needs a writer"  # noqa: S101


def generate(split: str) -> list[GenItem]:
    """All items of one split (test or dev), in id order."""
    seed = SEEDS[split]
    prefix = ID_PREFIX[split]
    items: list[GenItem] = []
    for slot in schedule()[split]:
        rng = item_rng(GENERATOR, seed, slot.index)
        probe_id = f"{prefix}{slot.index:06d}"
        draft = WRITERS[slot.family](slot, rng)
        items.append(finish(draft, probe_id, slot.family, slot.lang))
    return items


def _counts(items: list[GenItem]) -> dict[str, dict[str, int]]:
    def tally(key: Callable[[GenItem], object]) -> dict[str, int]:
        c = Counter(str(key(it)) for it in items)
        return dict(sorted(c.items()))

    return {
        "family": tally(lambda it: it.family),
        "category": tally(lambda it: family(it.family).category),
        "gold_stance": tally(lambda it: it.gold_stance),
        "lang": tally(lambda it: it.lang),
        "kind": tally(lambda it: it.assumption_kind),
        "disputed": tally(lambda it: it.disputed is not None),
    }


def render_item(it: GenItem) -> str:
    """One item as the text a reviewer reads: assumption, chat with the record marked, gold."""
    out = [f"[{it.probe_id}] {it.family} lang={it.lang} kind={it.assumption_kind}"]
    out.append(f"  ASSUMPTION: {it.assumption}")
    lines = list(it.context)
    lines.insert(it.target_index, it.target)
    for i, line in enumerate(lines):
        mark = ">>" if i == it.target_index else "  "
        out.append(f"  {mark} {line.local_time} {line.sender}: {line.text}")
    gold = f"{it.gold_stance} ({it.category}, trap={it.trap})"
    out.append(f"  GOLD: {gold}  quote={it.proposed_quote!r}  disputed={it.disputed!r}")
    out.append(f"  WHY: {it.rationale}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=Path("eval/out/stancedata"))
    parser.add_argument(
        "--show",
        type=int,
        default=0,
        metavar="N",
        help="print every Nth test item instead of writing files",
    )
    args = parser.parse_args(argv)
    if args.show:
        for it in generate("test")[:: args.show]:
            print(render_item(it))
            print()
        return 0
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"generator": GENERATOR, "source": SOURCE, "seeds": SEEDS}
    files: dict[str, object] = {}
    for split in ("test", "dev"):
        items = generate(split)
        name = f"heldout_{split}.jsonl"
        digest = write_jsonl(items, out_dir / name)
        files[name] = {"sha256": digest, "items": len(items), "counts": _counts(items)}
        print(f"wrote {out_dir / name}: {len(items)} items, sha256 {digest[:12]}")
    manifest["files"] = files
    path = out_dir / "heldout.manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
