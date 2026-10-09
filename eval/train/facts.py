"""A fact a chat message can state, with the surface forms the families need.

A Fact is one ordinary act with a value slot ("paid the plumber {v}"). From it the writers derive
the record forms each family needs: stated, exclusive ("{v} total"), negated, planned,
conditional, asked, hedged, reported second hand. English forms are derived from `act` and
`acted`; Russian facts spell every form out because the past tense carries the speaker's gender
("{l}" is the speaker's ending, "{m}" the addressee's, "{k}" the third person's).
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Fact:
    key: str
    scene: str
    lang: str  # "en" or "ru"
    act: str  # base verb phrase with {v}: "pay the plumber {v}"
    acted: str  # first-person past with {v}: "paid the plumber {v}"
    claim: str  # assumption predicate, third person past, with {v}: "paid the plumber ${v}"
    claim_base: str  # base form for "did not ..." and "planned to ...": "pay the plumber ${v}"
    values: tuple[str, ...]  # at least two, so a different value exists
    shown: tuple[str, ...] = ()  # the values as an English assumption writes them, if different
    exact: tuple[str, ...] = ()  # record forms that exclude any other value: "{v} total"
    extra: tuple[str, ...] = ()  # a second fact the record never shows: "tipped him $40"
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


CONDITIONS = (
    "he shows up",
    "i get paid friday",
    "the price is right",
    "ur there by 6",
    "he brings the receipt",
    "my check clears",
    "she calls back",
    "the rain stops",
    "they open early",
    "i can get the car",
    "he answers",
    "its still available",
    "the super lets me in",
    "my shift ends on time",
)
CONDITIONS_RU = (
    "если он придёт",
    "если получу зарплату в пятницу",
    "если будет время",
    "если она перезвонит",
    "если дождь кончится",
    "если успею после смены",
    "если он привезёт чек",
    "если цена норм",
)


def _fill(s: str, **kw: str) -> str:
    return s.format(**kw)


def stated(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    """The record form that states the fact."""
    if f.done:
        return _fill(rng.choice(f.done), v=v, l=end)
    a = _fill(f.acted, v=v)
    return rng.choice((a, a, f"i {a}", f"just {a}", f"yeah {a}", f"i {a}"))


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


def planned(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    if f.plan:
        return _fill(rng.choice(f.plan), v=v, l=end)
    act = _fill(f.act, v=v)
    return rng.choice(
        (
            f"gonna {act} tmrw",
            f"will {act} later",
            f"ill {act} after work",
            f"planning to {act} this weekend",
            f"about to {act}",
            f"ima {act} tonight",
            f"gonna {act} first thing",
            f"ill {act} when i get there",
        )
    )


def conditional(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    if f.cond:
        return _fill(rng.choice(f.cond), v=v, l=end)
    act, c = _fill(f.act, v=v), rng.choice(CONDITIONS)
    return rng.choice(
        (f"if {c} ill {act}", f"ill {act} if {c}", f"only if {c} do i {act}", f"if {c} i can {act}")
    )


def asked(f: Fact, rng: random.Random, v: str, end: str = "") -> str:
    """A question to the other party about whether they did the act."""
    if f.q:
        return _fill(rng.choice(f.q), v=v, m=end)
    act, acted = _fill(f.act, v=v), _fill(f.acted, v=v)
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
            f"probably {acted}, cant remember tbh",
            f"i believe i {acted}, not certain",
        )
    )


def reported(f: Fact, rng: random.Random, v: str, n: str, pron: str, end: str = "") -> str:
    """The sender reports what a third person (n) said or did."""
    if f.hear:
        return _fill(rng.choice(f.hear), v=v, n=n, k=end)
    acted = _fill(f.acted, v=v)
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


def claim(f: Fact, v: str) -> str:
    s = shown(f, v)
    return _fill(f.claim, v=s, V=s.capitalize())


def claim_base(f: Fact, v: str) -> str:
    s = shown(f, v)
    return _fill(f.claim_base, v=s, V=s.capitalize())
