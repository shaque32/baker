"""The walk that hands every Baker-wording slot wording nobody else in the held-out set has.

Each claim takes the next unused entry of a fixed table; a record text (normalized) is handed
out at most once, and so is every handle pair, saved contact name and role person.
"""

from __future__ import annotations

import random
from collections import deque

from eval.heldout import bk_acts as acts
from eval.heldout import bk_cues as cues
from eval.heldout import bk_meanings as mn
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
    surname,
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
        self.phrases = {"en": deque(_rng("phrases").sample(mn.PHRASES, len(mn.PHRASES))),
                        "ru": deque(_rng("phrases|ru").sample(mn.PHRASES_RU,
                                                              len(mn.PHRASES_RU)))}  # fmt: skip
        self.used_words: set[str] = set()

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

    # ------------------------------------------------------------ claims (guide rule 29)

    def meaning(self, lang: str, form: str) -> tuple[str, str, str, str, str, str]:
        """(situation, words, the claim's meaning, the plain meaning, a usage line, record) for
        the meaning template. form: open (the record uses the words), open_q (it asks about
        them), said or other (their user explains them), bare (no record). No two items, in
        either split, use the same words."""
        ru = lang in ("ru", "mixed")
        pool = self.phrases["ru" if ru else "en"]
        used = self.used_words
        for _ in range(2 * len(pool)):
            row = pool.popleft()
            pool.append(row)
            sit, words = row[0], row[1]
            if words in used:
                continue
            plain = "" if ru else row[2]
            code = mn.CODES[self._next("code", len(mn.CODES))]
            spots = cues.SPOTS_RU if ru else cues.SPOTS
            spot = spots[sit][self._next("mspot", 2)]
            uses = mn.USAGE_RU if ru else mn.USAGE
            verbs = {} if ru else mn.agree(words)
            usage = cues.fill(uses[self._next(f"use|{ru}", len(uses))], p=words, spot=spot,
                              **verbs)  # fmt: skip
            record = ""
            if form == "open":
                record = usage
            elif form == "open_q":
                asks = mn.USAGE_Q_RU if ru else mn.USAGE_Q
                record = cues.fill(asks[self._next(f"useq|{ru}", len(asks))], p=words,
                                   spot=spot, **verbs)  # fmt: skip
            elif form in ("said", "other"):
                table = mn.SAID if form == "said" else mn.OTHER
                record = cues.fill(table[self._next(form, len(table))], p=words, m=code,
                                   a=plain, **verbs)  # fmt: skip
            if record and not self._fresh(record):
                continue
            used.add(words)
            return sit, words, code, plain, usage, record
        raise RuntimeError(f"the {lang} meaning words ran out")

    def act(self, kind: str, form: str, z: str) -> tuple[str, str, dict[str, str], str]:
        """(situation, key, slot values, record) for a claimed act (kind 'act') or role (kind
        'role') involving person:<z>; form picks the record's lines from the table (plan, did,
        ask, tell, from, to, deny), or '' for no record."""
        table = acts.ACTS if kind == "act" else acts.ROLES
        keys = sorted(table)
        for _ in range(200):
            key = keys[self._next(f"{kind}|key", len(keys))]
            sit = SITS[self._next(f"{kind}|sit", len(SITS))]
            v = self._next(f"{kind}|v|{sit}", 2)
            values = {"z": surname(z).lower(), "Z": surname(z), "spot": cues.SPOTS[sit][v],
                      "thing": cues.THINGS[sit][v],
                      "hh": acts.HOURS[self._next("hh", len(acts.HOURS))]}  # fmt: skip
            if not form:
                return sit, key, values, ""
            lines = table[key][form]
            record = cues.fill(lines[self._next(f"{kind}|{form}|{key}", len(lines))], **values)
            if self._fresh(record):
                return sit, key, values, record
        raise RuntimeError(f"no unused {kind} {form} record")
