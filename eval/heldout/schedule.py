"""The fixed plan of both splits: which family, language and record template each item gets.

The test split has the exact composition below; the dev split has half of every number. Items of
one family are spread through the file, Russian records fall on a fixed pattern (about one item
in five, plus one in fifteen with mixed-language context) and each item's record template is
claimed from the shared walk in schedule order, test split first, so no record text repeats.

Volume (GO_BAR.md): the test split keeps at least 1,000 gated items and at least 440 gold
contradicts (the bar needs 420; ovr_translation items are disputed and never gated). Under guide
v0.4 contradicts come only from con_denial, con_other_value, con_other_state, con_in_window,
con_correction, con_never_told and ovr_negation; the time, sender, speaker and later-correction
traps, told frames and undated denials are complicates.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Iterable
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
    "con_denial": 70,
    "con_other_value": 100,
    "con_other_state": 40,
    "con_in_window": 80,
    "con_correction": 100,
    "con_never_told": 40,
    "ovr_negation": 60,
    "ovr_time_mismatch": 32,
    "ovr_sender_mismatch": 28,
    "ovr_speaker_mismatch": 30,
    "ovr_later_correction": 30,
    "ovr_told_frame": 40,
    "ovr_undated_denial": 30,
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
    "sup_time_window": ("stmt",),
    "sup_contact": ("stmt",),
    "sup_account_shared": ("stmt",),
    "sup_injection": ("stmt",),
    "con_denial": ("deny",),
    "con_other_value": ("value",),
    "con_other_state": ("state",),
    "con_in_window": ("any",),
    "con_correction": ("corr",),
    "con_never_told": ("stmt",),
    "ovr_negation": ("neg",),
    "ovr_time_mismatch": ("any",),
    "ovr_sender_mismatch": ("any",),
    "ovr_speaker_mismatch": ("stmt",),
    "ovr_later_correction": ("corr",),
    "ovr_told_frame": ("deny", "neg", "value"),
    "ovr_undated_denial": ("deny", "neg"),
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

# An answer that opens on a bare "no," (or ends on one) denies a question; a family that shows
# the record without that question never draws it, so no denial stands with nothing to deny.
_BARE_DENIAL = re.compile(r"^\s*(?:no|nope|nah|нет|неа)\s*,|,\s*(?:no|nope|нет)\W*$", re.IGNORECASE)


def _no_bare_denial(t: Tpl) -> bool:
    return not _BARE_DENIAL.search(t.text)


def reportable(t: Tpl) -> bool:
    """Whether the template's fact can follow "X told the owner that": an act of the sender's
    (vp) or a fact with no "the sender" in it, which only a message frame can carry. A report
    never names the message itself (guide v0.4, ovr_told_frame)."""
    return bool(t.vp) or bool(t.that and "the sender" not in t.that)


# A time a record, its question or its fact names: a weekday, a clock time, a relative day or
# part of the day, a digit. An undated denial has none of them in any of its lines or in the
# act it denies (guide v0.4, ovr_undated_denial: "naming no time and answering no question
# that names one"). {n} counts things, never a time.
_NAMES_A_TIME = re.compile(
    r"\{(?:day\w*|day2|t|x\w+)\}|\d"
    r"|\b(?:yesterday|today|tonight|tomorrow|morning|night|evening|afternoon|noon|week|month"
    r"|weekend|last|this|ago|earlier|since|until|before|after|monday|tuesday|wednesday"
    r"|thursday|friday|saturday|sunday)\b"
    r"|вчера|сегодня|завтра|утр|вечер|ноч|днём|недел|месяц|после|понедельник|вторник|сред"
    r"|четверг|пятниц|суббот|воскресен",
    re.IGNORECASE,
)


def undated(t: Tpl) -> bool:
    """A past-tense denial that names no time, of an act that names none, answering no
    question that names one."""
    parts = [t.text, t.quote, t.vp, t.that] + [v for k, v in t.extra if k == "ask"]
    return not any(_NAMES_A_TIME.search(p) for p in parts)


PREDICATES: dict[str, Callable[[Tpl], bool]] = {
    "ovr_speaker_mismatch": lambda t: bool(t.vp),  # the act must be attributable to a member
    "sup_account_shared": lambda t: bool(t.that or t.vp),
    "sup_verbatim": _no_bare_denial,
    "con_in_window": _no_bare_denial,
    "ovr_time_mismatch": _no_bare_denial,
    "ovr_sender_mismatch": _no_bare_denial,
    "con_never_told": reportable,
    "ovr_told_frame": reportable,
    "ovr_undated_denial": undated,
}


def _fact(e: Entry) -> list[str]:
    return ["fact: " + (e.that() if e.tpl.that else e.vp())]


def _fix_and_fact(e: Entry) -> list[str]:
    return [e.part("fix"), *_fact(e)]


# More texts a claimed entry uses up (registry.Walk.claim): the correcting message, which is a
# record for con_correction, and the fact a plain-fact assumption states, which carries no date
# or account of its own when the record names none ("7 bags were dropped at the Halsted site").
KEYS: dict[str, Callable[[Entry], Iterable[str]]] = {
    "con_denial": _fact,
    "con_other_value": _fact,
    "con_correction": _fix_and_fact,
    "ovr_negation": _fact,
    "ovr_later_correction": _fix_and_fact,
    "ovr_told_frame": _fact,
    "ovr_undated_denial": _fact,
}

# The four traps whose record has the assumption's words but leaves it open (guide v0.3): the
# proposed deciding bar is zero of them shown as supports, on both test sets.
MISMATCH_TRAPS = (
    "ovr_time_mismatch",
    "ovr_sender_mismatch",
    "ovr_speaker_mismatch",
    "ovr_later_correction",
)
CONTRADICTS_FAMILIES = (
    "con_denial",
    "con_other_value",
    "con_other_state",
    "con_in_window",
    "con_correction",
    "con_never_told",
    "ovr_negation",
)
# The two traps guide v0.4 added (told frames and undated denials): the go bar counts them
# with the four above among the moved traps shown as supports (GO_BAR.md bars 2 and 3).
REPORT_TRAPS = ("ovr_told_frame", "ovr_undated_denial")


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
            keys = KEYS.get(slot.family)
            slot.entry = walk.claim(slot.record_lang, tags, slot.family, pred, keys)
        out[split] = slots
    return out
