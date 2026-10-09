"""The fixed plan of both splits: which family, language and record template each item gets.

The test split has the exact composition below; the dev split has half of every number. Items of
one family are spread through the file, Russian records fall on a fixed pattern (about one item
in five, plus one in fifteen with mixed-language context) and each item's record template is
claimed from the shared walk in schedule order, test split first, so no record text repeats.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass

from eval.heldout.data_complicates import DISPUTES, HEARSAY, HEDGES, INFERENCES, RELATIVE
from eval.heldout.data_contra import CORRECTIONS, DENIALS, NEGATIONS, STATES, VALUES
from eval.heldout.data_overreach import (
    CODEWORDS,
    CONDITIONS,
    COUNTS,
    IDIOMS,
    JOKES,
    PARTIALS,
    PLANS,
    PRONOUNS,
    QUESTIONS,
    TOPICS,
)
from eval.heldout.data_support import QA, STATEMENTS
from eval.heldout.pools import PLEASANTRY_EN, PLEASANTRY_RU, SITUATIONS, UNRELATED_EN, UNRELATED_RU
from eval.heldout.registry import Entry, Tpl, Walk, tpl

# Test split counts per family. Every number is even so the dev split is exactly half.
COMPOSITION: dict[str, int] = {
    "sup_verbatim": 30,
    "sup_plain": 34,
    "sup_answer": 30,
    "sup_time_window": 28,
    "sup_contact": 26,
    "sup_account_shared": 22,
    "sup_injection": 30,
    "con_denial": 64,
    "con_other_value": 70,
    "con_other_state": 56,
    "con_in_window": 56,
    "con_other_speaker": 54,
    "ovr_time_mismatch": 40,
    "ovr_sender_mismatch": 34,
    "ovr_later_correction": 32,
    "ovr_negation": 34,
    "ovr_handle_owner": 14,
    "ovr_shared_account": 12,
    "ovr_pronoun": 12,
    "ovr_code_word": 14,
    "ovr_different_topic": 12,
    "ovr_hypothetical": 12,
    "ovr_plan": 12,
    "ovr_question": 12,
    "ovr_joke": 12,
    "ovr_partial": 12,
    "ovr_count": 12,
    "ovr_injection_related": 12,
    "ovr_injection_unrelated": 12,
    "ovr_translation": 20,
    "cpl_hedge": 26,
    "cpl_disputed_claim": 24,
    "cpl_inference": 24,
    "cpl_hearsay": 24,
    "cpl_relative_time": 22,
    "irr_other_topic": 44,
    "irr_pleasantry": 36,
}

# Which record templates each family draws, by tag; a predicate narrows further.
POOL_TAGS: dict[str, tuple[str, ...]] = {
    "sup_verbatim": ("any",),
    "sup_plain": ("stmt",),
    "sup_answer": ("qa",),
    "sup_time_window": ("any",),
    "sup_contact": ("any",),
    "sup_account_shared": ("stmt",),
    "sup_injection": ("stmt",),
    "con_denial": ("deny",),
    "con_other_value": ("value",),
    "con_other_state": ("state",),
    "con_in_window": ("any",),
    "con_other_speaker": ("stmt",),
    "ovr_time_mismatch": ("any",),
    "ovr_sender_mismatch": ("any",),
    "ovr_later_correction": ("corr",),
    "ovr_negation": ("neg",),
    "ovr_handle_owner": ("stmt",),
    "ovr_shared_account": ("stmt",),
    "ovr_pronoun": ("pron",),
    "ovr_code_word": ("code",),
    "ovr_different_topic": ("topic",),
    "ovr_hypothetical": ("cond",),
    "ovr_plan": ("plan",),
    "ovr_question": ("ask",),
    "ovr_joke": ("joke",),
    "ovr_partial": ("partial",),
    "ovr_count": ("count",),
    "ovr_translation": ("idiom",),
    "ovr_injection_related": ("plan", "hedge", "cond"),
    "ovr_injection_unrelated": ("unrel",),
    "cpl_hedge": ("hedge",),
    "cpl_disputed_claim": ("dispute",),
    "cpl_inference": ("infer",),
    "cpl_hearsay": ("hearsay",),
    "cpl_relative_time": ("reltime",),
    "irr_other_topic": ("unrel",),
    "irr_pleasantry": ("pleas",),
}

PREDICATES: dict[str, Callable[[Tpl], bool]] = {
    "con_other_speaker": lambda t: bool(t.vp),  # the act must be attributable to a member
    "sup_account_shared": lambda t: bool(t.that or t.vp),
}

FOUR_TRAPS = ("ovr_time_mismatch", "ovr_sender_mismatch", "ovr_later_correction", "ovr_negation")


def _misc_templates() -> list[Tpl]:
    out: list[Tpl] = []
    for n, text in enumerate(UNRELATED_EN):
        out.append(tpl(SITUATIONS[n % len(SITUATIONS)], "en", text, "unrel"))
    for n, text in enumerate(UNRELATED_RU):
        out.append(tpl(SITUATIONS[n % len(SITUATIONS)], "ru", text, "unrel"))
    for n, text in enumerate(PLEASANTRY_EN):
        out.append(tpl(SITUATIONS[n % len(SITUATIONS)], "en", text, "pleas"))
    for n, text in enumerate(PLEASANTRY_RU):
        out.append(tpl(SITUATIONS[n % len(SITUATIONS)], "ru", text, "pleas"))
    return out


ALL_TEMPLATES: tuple[Tpl, ...] = (
    STATEMENTS
    + QA
    + VALUES
    + CORRECTIONS
    + DENIALS
    + NEGATIONS
    + STATES
    + HEDGES
    + DISPUTES
    + INFERENCES
    + HEARSAY
    + RELATIVE
    + PRONOUNS
    + CODEWORDS
    + TOPICS
    + CONDITIONS
    + PLANS
    + QUESTIONS
    + JOKES
    + PARTIALS
    + COUNTS
    + IDIOMS
    + tuple(_misc_templates())
)


@dataclass
class Slot:
    """One planned item: its position, family, language and claimed record template."""

    index: int  # 1-based position in the split; the id number
    split: str
    family: str
    k: int  # position within the family's items
    lang: str  # en, ru or mixed
    entry: Entry | None = None

    @property
    def record_lang(self) -> str:
        return "ru" if self.lang in ("ru", "mixed") else "en"


def lang_for(family: str, k: int) -> str:
    if family == "ovr_translation":
        return "mixed" if k % 4 == 3 else "ru"
    if k % 5 == 2:
        return "ru"
    if k % 15 == 9:
        return "mixed"
    return "en"


def counts(split: str) -> dict[str, int]:
    if split == "test":
        return dict(COMPOSITION)
    if split == "dev":
        return {f: n // 2 for f, n in COMPOSITION.items()}
    raise ValueError(f"unknown split {split!r}; use 'test' or 'dev'")


def _plain_slots(split: str) -> list[Slot]:
    seq: list[tuple[float, int, str, int]] = []
    for order, family in enumerate(COMPOSITION):
        n = counts(split)[family]
        for k in range(n):
            seq.append(((k + 0.5) / n, order, family, k))
    seq.sort()
    return [Slot(i + 1, split, fam, k, lang_for(fam, k)) for i, (_, _, fam, k) in enumerate(seq)]


@functools.lru_cache(maxsize=1)
def schedule() -> dict[str, list[Slot]]:
    """Both splits with their record templates claimed, test first; a fixed table."""
    walk = Walk(ALL_TEMPLATES)
    out: dict[str, list[Slot]] = {}
    for split in ("test", "dev"):
        slots = _plain_slots(split)
        for slot in slots:
            tags = POOL_TAGS[slot.family]
            pred = PREDICATES.get(slot.family)
            slot.entry = walk.claim(slot.record_lang, tags, slot.family, pred)
        out[split] = slots
    return out
