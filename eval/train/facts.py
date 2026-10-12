"""A fact a chat message can state, with the surface forms the families need.

A Fact is one ordinary act with a value slot ("paid the plumber {v}"). From it the writers derive
the record forms each family needs: stated, exclusive ("exactly {v}"), negated, planned,
conditional, asked, hedged, reported second hand. English forms are derived from `act` and
`acted`; Russian facts spell every form out because the past tense carries the speaker's gender
("{l}" is the speaker's ending, "{m}" the addressee's, "{k}" the third person's).

A money fact's record carries a currency marker ("$300", "5000 руб") only some of the time, and
the assumption keeps the marker ("$300", "5,000 rubles") only when the record shows one.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Fact:
    key: str
    scene: str
    lang: str  # "en" or "ru"
    act: str  # base verb phrase with {v}: "pay the plumber {v}"
    acted: str  # first-person past with {v}: "paid the plumber {v}"
    claim: str  # assumption predicate, third person past, with {v}: "paid the plumber ${v}"
    claim_base: str  # base form for "did not ..." and "would ...": "pay the plumber ${v}"
    values: tuple[str, ...]  # at least two, so a different value exists
    shown: tuple[str, ...] = ()  # the values as an English assumption writes them, if different
    exact: tuple[str, ...] = ()  # record forms that exclude any other value: "exactly {v}"
    extra: tuple[str, ...] = ()  # a second fact the record never shows: "tipped the plumber 40"
    general: tuple[str, ...] = ()  # a generalization of the act: "paid the plumber every month"
    done: tuple[str, ...] = ()  # explicit record forms (Russian); else derived from acted
    neg: tuple[str, ...] = ()
    plan: tuple[str, ...] = ()
    cond: tuple[str, ...] = ()
    q: tuple[str, ...] = ()
    hedge: tuple[str, ...] = ()
    hear: tuple[str, ...] = ()  # "{n}" is the third person's name

    def other_value(self, rng: random.Random, v: str) -> str:
        return rng.choice([x for x in self.values if x != v])

    @property
    def money(self) -> bool:
        return "${v}" in self.claim or "{v} rubles" in self.claim


# Conditions for "if ..., ill ...": the record form and the third-person form an assumption
# uses. "{n}" is a third party's first name as the record writes it, "{N}" as the assumption
# does; "{p}" and "{poss}" are the sender's pronouns and "{o}" the other party.
CONDITIONS = (
    ("{n} shows up", "{N} showed up"),
    ("i get paid friday", "{p} got paid friday"),
    ("the price is right", "the price was right"),
    ("{n} is there by 6", "{N} was there by 6"),
    ("{n} brings the receipt", "{N} brought the receipt"),
    ("my check clears", "{poss} check cleared"),
    ("{n} calls back", "{N} called back"),
    ("the rain stops", "the rain stopped"),
    ("they open early", "they opened early"),
    ("i can get the car", "{p} could get the car"),
    ("{n} answers", "{N} answered"),
    ("the spot is still open", "the spot was still open"),
    ("the super is there", "the super was there"),
    ("my shift ends on time", "{poss} shift ended on time"),
)
CONDITIONS_RU = (
    "если {n} придёт",
    "если получу зарплату в пятницу",
    "если будет время",
    "если {n} перезвонит",
    "если дождь кончится",
    "если успею после смены",
    "если {n} привезёт чек",
    "если цена норм",
)

MARKER = re.compile(r"\$|\b(dollars?|bucks|rubles?)\b|\bруб\w*|₽")


def has_marker(text: str) -> bool:
    """Whether a record shows a currency marker, so an assumption may show one too."""
    return MARKER.search(text) is not None


def mark(f: Fact, v: str) -> str:
    """The value as a record writes it with a currency marker."""
    return f"{v} руб" if f.lang == "ru" else f"${v}"


def _fill(s: str, **kw: str) -> str:
    return s.format(**kw)


def stated(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    """The record form that states the fact."""
    if f.done:
        return _fill(rng.choice(f.done), v=v, l=end)
    a = _fill(f.acted, v=v)
    return rng.choice((a, a, f"i {a}", f"just {a}", f"yep {a}", f"i {a}"))


def exact(f: Fact, rng: random.Random, v: str, end: str = "") -> str | None:
    """A record form that rules out any other value, or None if the fact has none."""
    if not f.exact:
        return None
    return _fill(rng.choice(f.exact), v=v, l=end)


def negated(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    if f.neg:
        return _fill(rng.choice(f.neg), v=v, l=end)
    act, acted = _fill(f.act, v=v), _fill(f.acted, v=v)
    return rng.choice(
        (
            f"didnt {act}",
            f"never {acted}",
            f"i did not {act}",
            f"did not {act}",
            f"i didnt {act}, no",
            f"nope, never {acted}",
        )
    )


DATED = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|\bon the \d+(st|nd|rd|th)\b"
)


def planned(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    """A plan; an act that names its own day takes no second time word ("on friday tmrw")."""
    if f.plan:
        return _fill(rng.choice(f.plan), v=v, l=end)
    act = _fill(f.act, v=v)
    if DATED.search(act):
        return rng.choice(
            (
                f"gonna {act}",
                f"will {act}",
                f"ill {act}",
                f"planning to {act}",
                f"ima {act}",
                f"ill {act} for sure",
                f"gonna {act}, promise",
                f"will {act}, dont worry",
            )
        )
    return rng.choice(
        (
            f"gonna {act} tmrw",
            f"will {act} later",
            f"ill {act} after work",
            f"planning to {act} this weekend",
            f"ill {act} tmrw",
            f"ima {act} tonight",
            f"gonna {act} first thing",
            f"ill {act} when i get there",
        )
    )


def conditional(f: Fact, rng: random.Random, v: str, end: str = "", n: str = "") -> str:
    """A conditional record; Russian facts carry their own forms, built on CONDITIONS_RU."""
    if f.cond:
        return _fill(rng.choice(f.cond), v=v, l=end, n=n)
    act, c = _fill(f.act, v=v), rng.choice(CONDITIONS)[0].format(n=n)
    return rng.choice(
        (f"if {c} ill {act}", f"ill {act} if {c}", f"only if {c} do i {act}", f"if {c} i can {act}")
    )


def _second_person(s: str) -> str:
    return re.sub(r"\bmy\b", "ur", re.sub(r"\bme\b", "u", s))


def asked(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    """A question to the other party about whether they did the act."""
    if f.q:
        return _fill(rng.choice(f.q), v=v, m=end)
    act, acted = _second_person(_fill(f.act, v=v)), _second_person(_fill(f.acted, v=v))
    return rng.choice(
        (
            f"did u {act}?",
            f"u {acted}?",
            f"did you {act}",
            f"wait did u {act}??",
            f"so did u {act} or not",
            f"{acted}? yes or no",
        )
    )


def hedged(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    if f.hedge:
        return _fill(rng.choice(f.hedge), v=v, l=end)
    acted = _fill(f.acted, v=v)
    return rng.choice(
        (
            f"pretty sure i {acted}",
            f"i think i {acted}",
            f"{acted} i think",
            f"{acted}, like 90% sure",
            f"if i remember right i {acted}",
            f"probably {acted}, cant really remember tbh",
            f"i believe i {acted}, not certain",
        )
    )


def reported(f: Fact, rng: random.Random, v: str, n: str, pron: str, end: str = "") -> str:
    """The sender reports what a third person (n) said or did."""
    if f.hear:
        return _fill(rng.choice(f.hear), v=v, n=n, k=end)
    poss, obj = {"he": ("his", "him"), "she": ("her", "her")}.get(pron, ("their", "them"))
    acted = re.sub(r"\bmy\b", poss, re.sub(r"\bme\b", obj, _fill(f.acted, v=v)))
    return rng.choice(
        (
            f"{n} says {pron} {acted}",
            f"{n} said {pron} {acted}",
            f"heard from {n} that {pron} {acted}",
            f"{n} told me {pron} {acted}",
            f"according to {n} {pron} {acted}",
            f"{n} swears {pron} {acted}",
        )
    )


def shown(f: Fact, v: str) -> str:
    """The value as an English assumption or rationale writes it."""
    return f.shown[f.values.index(v)] if f.shown else v


def _money(template: str, money: bool) -> str:
    return template if money else template.replace("${v}", "{v}").replace("{v} rubles", "{v}")


def claim(f: Fact, v: str, money: bool = False) -> str:
    """The assumption predicate; the currency marker stays only when the record shows one."""
    s = shown(f, v)
    return _fill(_money(f.claim, money), v=s, V=s.capitalize())


def claim_base(f: Fact, v: str, money: bool = False) -> str:
    s = shown(f, v)
    return _fill(_money(f.claim_base, money), v=s, V=s.capitalize())


def general(f: Fact, rng: random.Random, v: str, money: bool = False) -> str | None:
    """A generalization of the act with the record's value, or None if the fact has none."""
    if not f.general:
        return None
    return _fill(_money(rng.choice(f.general), money), v=shown(f, v))
