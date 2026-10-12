"""Record templates and the walk that hands each item a record nobody else in the set has.

A template is one chat line with slots ({n}, {place}, {day}, {name}, {t}, ...) plus the fact it
establishes, written for the assumption. Expanding a template over its slot values gives
concrete entries; the walk hands them out in a fixed order (test split first, then dev), each
entry at most once, so no two items in either split share a record and the two splits share
none. The order is a fixed table of this generator version, never of the wall clock.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from eval.heldout import GENERATOR
from eval.heldout.pools import (
    CLOCKS,
    MENTIONED_EN,
    MENTIONED_RU,
    PLACES,
    SINCE_EN,
    SINCE_RU,
    WEEKDAYS_EN,
    WEEKDAYS_RU,
)
from eval.heldout.text import normalized, render, slots_used

MAX_COMBOS = 48
FACT_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# Slot families: every slot of one base takes its value from one choice, in different forms
# ({name} nominative, {name_g} genitive ... ; {day} "on tuesday", {day_since} "since tuesday").
_BASES = {
    "n": "n",
    "m": "m",
    "t": "t",
    "place": "place",
    "place2": "place2",
    "day": "day",
    "day_since": "day",
    "day2": "day2",
    "name": "name",
    "name_g": "name",
    "name_d": "name",
    "name_i": "name",
}

Choice = dict[str, tuple[object, object]]  # slot name -> (record form, fact form)


@dataclass(frozen=True)
class Tpl:
    """One record template: the line, the fact it shows, and any extra lines a family needs."""

    sit: str
    lang: str  # language of the record text: en or ru
    text: str
    tags: frozenset[str]
    vp: str = ""  # fact as a verb phrase whose subject is the sender: "unloaded {n} pallets"
    that: str = ""  # fact as a clause: "the lift at {place} was down"
    quote: str = ""  # the part of text the stance rests on; "" means the whole line
    n: tuple[int, int] = (2, 12)  # inclusive range for {n}; {m} draws from the same range
    extra: tuple[tuple[str, str], ...] = ()  # named extra templates, e.g. ("q", "did u ...?")
    g: str = ""  # m or f when a Russian first-person verb fixes the sender's gender

    def x(self, name: str) -> str:
        for key, value in self.extra:
            if key == name:
                return value
        raise KeyError(f"template has no extra {name!r}: {self.text!r}")

    def has(self, name: str) -> bool:
        return any(key == name for key, _ in self.extra)

    def all_slots(self) -> set[str]:
        """Slots the registry fills. {s}, {r} and x-slots ({xdate}, {xwd2}) are the writer's."""
        parts = [self.text, self.vp, self.that, self.quote] + [v for _, v in self.extra]
        out: set[str] = set()
        for p in parts:
            out |= slots_used(p)
        return {s for s in out if s not in ("s", "r") and not s.startswith("x")}


@dataclass(frozen=True)
class Entry:
    """A template with its slot values fixed: rec values for the chat, fact values for English."""

    tpl: Tpl
    rec: dict[str, object] = field(default_factory=dict)
    fact: dict[str, object] = field(default_factory=dict)

    def text(self) -> str:
        return render(self.tpl.text, self.rec)

    def quote(self) -> str:
        return render(self.tpl.quote or self.tpl.text, self.rec)

    def part(self, name: str) -> str:
        return render(self.tpl.x(name), self.rec)

    def vp(self) -> str:
        return render(self.tpl.vp, self.fact)

    def that(self) -> str:
        return render(self.tpl.that, self.fact)


def _choices(base: str, tpl: Tpl) -> list[Choice]:
    """The values one slot base can take, each with every form of that base."""
    lo, hi = tpl.n
    ru = tpl.lang == "ru"
    if base in ("n", "m"):
        return [{base: (i, i)} for i in range(lo, hi + 1)]
    if base in ("place", "place2"):
        return [{base: (p, p)} for p in PLACES[tpl.sit]]
    if base == "day":
        days, since = (WEEKDAYS_RU, SINCE_RU) if ru else (WEEKDAYS_EN, SINCE_EN)
        return [
            {"day": (days[i], FACT_DAYS[i]), "day_since": (since[i], FACT_DAYS[i])}
            for i in range(7)
        ]
    if base == "day2":
        days = WEEKDAYS_RU if ru else WEEKDAYS_EN
        return [{"day2": (days[i], FACT_DAYS[i])} for i in range(7)]
    if base == "name":
        if ru:
            return [
                {
                    "name": (nom, f'{lat} ("{nom}")'),
                    "name_g": (gen, lat),
                    "name_d": (dat, lat),
                    "name_i": (ins, lat),
                }
                for nom, gen, dat, ins, lat in MENTIONED_RU
            ]
        return [{f: (c, c) for f in ("name", "name_g", "name_d", "name_i")} for c in MENTIONED_EN]
    if base == "t":
        return [{"t": (c, c)} for c in CLOCKS]
    raise ValueError(f"unknown slot base {base!r} in {tpl.text!r}")


def _bases(tpl: Tpl) -> list[str]:
    bases: set[str] = set()
    for name in tpl.all_slots():
        if name not in _BASES:
            raise ValueError(f"unknown slot {name!r} in {tpl.text!r}")
        bases.add(_BASES[name])
    return sorted(bases)


def expand(tpl: Tpl) -> list[Entry]:
    """Concrete entries of one template, in a fixed shuffled order, at most MAX_COMBOS."""
    bases = _bases(tpl)
    if not bases:
        return [Entry(tpl)]
    pools = {b: _choices(b, tpl) for b in bases}
    rng = random.Random(f"{GENERATOR}|expand|{tpl.lang}|{tpl.text}")  # noqa: S311 - fixed table
    combos: list[Entry] = []
    seen: set[tuple] = set()
    attempts = 0
    limit = min(MAX_COMBOS, _combo_count(pools))
    while len(combos) < limit and attempts < 50 * limit:
        attempts += 1
        rec: dict[str, object] = {}
        fact: dict[str, object] = {}
        for base in bases:
            for slot, (r, f) in rng.choice(pools[base]).items():
                rec[slot], fact[slot] = r, f
        if _clashes(rec):
            continue
        key = tuple(rec[b] for b in bases)
        if key in seen:
            continue
        seen.add(key)
        combos.append(Entry(tpl, rec, fact))
    return combos


def _combo_count(pools: dict[str, list]) -> int:
    total = 1
    for values in pools.values():
        total *= len(values)
    return total


def _numbered(place: object) -> bool:
    """'unit 118', 'dock 4', '4 East': a place named by a number, as against a named one."""
    return re.match(r"(unit|dock) |\d+ ", str(place)) is not None


def _clashes(rec: dict[str, object]) -> bool:
    for a, b in (("n", "m"), ("place", "place2"), ("day", "day2")):
        if a in rec and b in rec and rec[a] == rec[b]:
            return True
    if "place" in rec and "place2" in rec and _numbered(rec["place"]) != _numbered(rec["place2"]):
        return True  # a unit number is replaced by another unit number, a lot by another lot
    return False


class Walk:
    """Hands out entries in a fixed order. Each entry goes to one item in the whole set, and no
    two entries handed out render the same record text (normalized), whatever their template."""

    def __init__(self, templates: Iterable[Tpl]) -> None:
        self.templates: list[Tpl] = list(templates)
        self.entries: dict[int, list[Entry]] = {}
        self.used: dict[int, int] = {}
        self.order: dict[str, list[int]] = {}
        self.cursor: dict[tuple[str, str], int] = {}
        self.seen: set[str] = set()
        for lang in ("en", "ru"):
            idx = [i for i, t in enumerate(self.templates) if t.lang == lang]
            random.Random(f"{GENERATOR}|walk|{lang}").shuffle(idx)  # noqa: S311 - fixed table
            self.order[lang] = idx

    def _entries(self, i: int) -> list[Entry]:
        if i not in self.entries:
            self.entries[i] = expand(self.templates[i])
        return self.entries[i]

    def _take(self, i: int) -> Entry | None:
        """The template's next entry whose record text was not handed out yet, or None."""
        entries = self._entries(i)
        used = self.used.get(i, 0)
        while used < len(entries):
            entry = entries[used]
            used += 1
            key = normalized(entry.text())
            if key not in self.seen:
                self.seen.add(key)
                self.used[i] = used
                return entry
        self.used[i] = used
        return None

    def claim(
        self,
        lang: str,
        tags: Sequence[str],
        family: str,
        pred: Callable[[Tpl], bool] | None = None,
    ) -> Entry:
        """The next unused entry in `lang` whose template carries one of `tags` and passes pred."""
        order = self.order[lang]
        key = (family, lang)
        start = self.cursor.get(key, 0)
        wanted = set(tags)
        for step in range(len(order)):
            pos = (start + step) % len(order)
            i = order[pos]
            tpl = self.templates[i]
            if not (tpl.tags & wanted) or (pred is not None and not pred(tpl)):
                continue
            entry = self._take(i)
            if entry is None:
                continue
            self.cursor[key] = pos + 1
            return entry
        raise RuntimeError(f"no {lang} template left for {family} with tags {sorted(wanted)}")

    def capacity(self, lang: str, tags: Sequence[str]) -> int:
        wanted = set(tags)
        return sum(
            len(self._entries(i))
            for i, t in enumerate(self.templates)
            if t.lang == lang and t.tags & wanted
        )


def tpl(
    sit: str,
    lang: str,
    text: str,
    *tags: str,
    vp: str = "",
    that: str = "",
    quote: str = "",
    n: tuple[int, int] = (2, 12),
    g: str = "",
    **extra: str,
) -> Tpl:
    """Short constructor for the data tables."""
    return Tpl(
        sit=sit,
        lang=lang,
        text=text,
        tags=frozenset(tags),
        vp=vp,
        that=that,
        quote=quote,
        n=n,
        extra=tuple(sorted(extra.items())),
        g=g,
    )
