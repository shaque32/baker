"""The walk that hands every Baker-wording slot wording nobody else in the held-out set has.

Each claim takes the next unused entry of a fixed table; a record text (normalized) is handed
out at most once, and so is every handle pair, saved contact name and role person.
"""

from __future__ import annotations

import random
from collections import deque

from eval.heldout import bk_cues as cues
from eval.heldout.bk_common import BK_GENERATOR, RU_SITS, SAY, SITS
from eval.heldout.bk_lines_ru import SAY_RU
from eval.heldout.bk_names import (
    CONTACT_TAGS,
    CONTACT_TAGS_RU,
    FIRSTS,
    HANDLE_PAIRS,
    ROLE_SLUGS,
    RU_FIRSTS,
    RU_PEOPLE,
    SLUGS,
)
from eval.heldout.text import normalized

_MONEY = ("$", "dollar", "bucks", "руб", "бакс")


def _rng(tag: str) -> random.Random:
    return random.Random(f"{BK_GENERATOR}|{tag}")  # noqa: S311 - a fixed table, not security


def _turns(pools: dict[str, tuple[str, ...]], tag: str) -> deque[tuple[str, str]]:
    """Every line once, situations taking turns, in a fixed shuffled order."""
    rng = _rng(tag)
    sits = list(pools)
    rng.shuffle(sits)
    lines = {s: rng.sample(pools[s], len(pools[s])) for s in sits}
    out: deque[tuple[str, str]] = deque()
    for i in range(max(len(v) for v in lines.values())):
        out.extend((s, lines[s][i]) for s in sits if i < len(lines[s]))
    return out


class Walk:
    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.say = {"en": _turns(SAY, "say|en"), "ru": _turns(SAY_RU, "say|ru")}
        self.n: dict[str, int] = {}
        self.wk_combos = {"en": self._wk_combos("en"), "ru": self._wk_combos("ru")}
        contacts = [(f, t) for t in sorted({x for v in CONTACT_TAGS.values() for x in v})
                    for f in FIRSTS]  # fmt: skip
        _rng("contacts").shuffle(contacts)
        self.contacts = deque(f"{f} {t}" for f, t in contacts)
        ru_contacts = [f"{f} {t}" for t in sorted({x for v in CONTACT_TAGS_RU.values() for x in v})
                       for f in RU_FIRSTS]  # fmt: skip
        _rng("contacts|ru").shuffle(ru_contacts)
        self.ru_contacts = deque(ru_contacts)

    def _next(self, key: str, size: int) -> int:
        i = self.n.get(key, 0)
        self.n[key] = i + 1
        return i % size

    def _fresh(self, text: str) -> bool:
        key = normalized(text)
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    # ------------------------------------------------------------ lines

    def say_line(self, lang: str, no_money: bool = False) -> tuple[str, str]:
        """(situation, text): the next unused update line in the record's language."""
        pool = self.say["ru" if lang in ("ru", "mixed") else "en"]
        for _ in range(len(pool)):
            sit, text = pool.popleft()
            if no_money and any(m in text.lower() for m in _MONEY):
                pool.append((sit, text))
                continue
            if self._fresh(text):
                return sit, text
        raise RuntimeError(f"the {lang} update lines ran out")

    def _wk_combos(self, lang: str) -> deque[tuple[int, str, int, int]]:
        templates = cues.WEEKDAY_RU if lang == "ru" else cues.WEEKDAY_EN
        sits = RU_SITS if lang == "ru" else SITS
        combos = [(t, s, v, d) for t in range(len(templates)) for s in sits for v in (0, 1)
                  for d in range(7)]  # fmt: skip
        _rng(f"wk|{lang}").shuffle(combos)
        return deque(combos)

    def weekday(self, lang: str, mod: str, day: int | None = None) -> tuple[str, str, int]:
        """(situation, text, weekday): a plan naming one weekday, with "next "/"this " or none.
        `day` asks for one weekday (Monday 0)."""
        ru = lang in ("ru", "mixed")
        pool = self.wk_combos["ru" if ru else "en"]
        for _ in range(len(pool)):
            t, sit, v, d = pool.popleft()
            if day is not None and d != day:
                pool.append((t, sit, v, d))
                continue
            if ru:
                text = cues.fill(
                    cues.WEEKDAY_RU[t],
                    acc=cues.DAYS_RU[mod][d],
                    spot=cues.SPOTS_RU[sit][v],
                    thing=cues.THINGS_RU[sit][v],
                )
            else:
                text = cues.fill(
                    cues.WEEKDAY_EN[t],
                    mod=mod,
                    day=cues.DAYS_EN[d],
                    spot=cues.SPOTS[sit][v],
                    thing=cues.THINGS[sit][v],
                )
            if self._fresh(text):
                return sit, text, d
        raise RuntimeError("the weekday plans ran out")

    def marked(self, templates: tuple[str, ...], key: str, **values: str) -> tuple[str, str]:
        """(text, cue) from the next template of a cue table that renders an unused text."""
        for _ in range(len(templates)):
            marked = cues.fill(templates[self._next(key, len(templates))], **values)
            text, cue = cues.cue_split(marked)
            if self._fresh(text):
                return text, cue
        raise RuntimeError(f"no unused {key} text")

    # ------------------------------------------------------------ names

    def person(self) -> str:
        return SLUGS[self._next("person", len(SLUGS))]

    def role_person(self) -> str:
        i = self.n.get("role", 0)
        if i >= len(ROLE_SLUGS):
            raise RuntimeError("the role persons ran out")
        self.n["role"] = i + 1
        return ROLE_SLUGS[i]

    def ru_person(self) -> tuple[str, str, str]:
        return RU_PEOPLE[self._next("ru_person", len(RU_PEOPLE))]

    def first(self, avoid: str = "") -> str:
        for _ in range(len(FIRSTS)):
            name = FIRSTS[self._next("first", len(FIRSTS))]
            if name != avoid:
                return name
        raise RuntimeError("no first name")

    def ru_first(self) -> str:
        return RU_FIRSTS[self._next("ru_first", len(RU_FIRSTS))]

    def handle_pair(self) -> tuple[str, str, str]:
        i = self.n.get("handles", 0)
        if i >= len(HANDLE_PAIRS):
            raise RuntimeError("the handle pairs ran out")
        self.n["handles"] = i + 1
        return HANDLE_PAIRS[i]

    def contact(self, lang: str) -> str:
        pool = self.ru_contacts if lang == "ru" else self.contacts
        while pool:
            name = pool.popleft()
            if self._fresh(name):
                return name
        raise RuntimeError("the contact names ran out")
