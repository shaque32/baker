"""The names an item in Baker's own wording reads by (guide rule 25).

Items keep Baker's ids while they are built. At the end every person the item involves gets a
name: a phone's stipulated user one from bk_names.OWNERS, a person the document names their
first name and the surname their slug stands for. The rationale is then turned from ids into
those names exactly as core/audit/readable.py prints them ("Nadine Pardoe (the user of
item3)", "Telegram 8812345", "item3"), so it reads like the item it explains. No name may
appear in a line's text or identifier unless the family means it to (`BkDraft.mentions`).
"""

from __future__ import annotations

import random
import re

from eval.heldout.bk_common import BkDraft
from eval.heldout.bk_names import FIRSTS, OWNERS, RU_LATIN, surname
from eval.heldout.bk_scene import Phone, Scene
from eval.heldout.bk_schedule import BkSlot
from eval.stancedata import bakerform as bf
from eval.stancedata.names import case_names

_OWNER_ID = re.compile(r"person:dev:item\d+:owner")
_PERSON_ID = re.compile(r"person:[a-z][a-z0-9_]*")
_ACCT_ID = re.compile(r"acct:item\d+:([A-Za-z]+):([A-Za-z0-9+_.]*[A-Za-z0-9_])")
_DEV_ID = re.compile(r"\bdev:(item\d+)")
_BRACKET = re.compile(r"\[(person:[^\[\]]+)\]")
_BRACKETS = re.compile(r" \[[^\[\]]+\]$")
_WORD = re.compile(r"[a-zа-яё]+")


def sur(person: str) -> str:
    """The surname of a person the document names, from their id."""
    return surname(person.removeprefix("person:"))


def full_name(first: str, slug: str) -> str:
    return f"{RU_LATIN.get(first, first)} {surname(slug)}"


def words(*texts: str) -> set[str]:
    return {w for t in texts for w in _WORD.findall(t.lower())}


def name_owner(rng: random.Random, sc: Scene, ph: Phone) -> str:
    """The stipulated user of phone ph, named once per scene."""
    if ph.owner not in sc.names:
        used = set(sc.names.values())
        sc.names[ph.owner] = rng.choice([f"{f} {s}" for f, s in OWNERS if f"{f} {s}" not in used])
    return sc.names[ph.owner]


def owner_sur(rng: random.Random, sc: Scene, ph: Phone) -> str:
    return name_owner(rng, sc, ph).split()[-1]


def _ids(text: str) -> set[str]:
    return {*_OWNER_ID.findall(text), *(p for p in _PERSON_ID.findall(text) if p != "person:dev")}


def name_people(rng: random.Random, s: BkSlot, d: BkDraft) -> dict[str, str]:
    """A name for every person in the draft's scene, its parameters and its rationale."""
    sc = d.scene
    lines = d.ex.lines
    heads = (_BRACKETS.sub("", ln.sender) for ln in lines)  # ids in brackets are not words
    shown = words(*(ln.text for ln in lines), *heads)
    for ph in sc.phones:
        name_owner(rng, sc, ph)
    persons = {*d.params.get("person_ids", ()), *sc.links.values(), *_ids(d.rationale)}
    main = bf.named_person(s.person) if s.person else ""
    for pid in sorted(persons - set(sc.names)):
        if _OWNER_ID.fullmatch(pid):
            raise ValueError(f"{pid} belongs to no phone in the scene")
        first = s.first
        if pid != main or (pid not in d.mentions and first.lower() in shown):
            used = {n.split()[0] for n in sc.names.values()} | {s.first, s.first2}
            first = rng.choice([f for f in FIRSTS if f.lower() not in shown and f not in used])
        sc.names[pid] = full_name(first, pid.removeprefix("person:"))
    for pid, name in sc.names.items():
        if pid not in d.mentions and words(name) & shown:
            raise ValueError(f"{d.family}: a line names {name} ({pid}), which it should not")
    if len({n.casefold() for n in sc.names.values()}) != len(sc.names):
        raise ValueError(f"{d.family}: two people share a name: {sc.names}")
    return dict(sc.names)


def readable(text: str, names: dict[str, str]) -> str:
    """Text written with Baker's ids, read by the names: brackets and people as
    core.audit.readable prints them, an account as '<App> <identifier>', a phone as 'item3'."""
    cn = case_names(names)

    def person(pid: str) -> str:
        label = cn.person(pid)
        if label == pid:
            raise ValueError(f"no name for {pid}")
        return label

    def bracket(m: re.Match[str]) -> str:
        return "[" + ", ".join(sorted(person(p) for p in m.group(1).split(", "))) + "]"

    out = _BRACKET.sub(bracket, text)
    out = _OWNER_ID.sub(lambda m: person(m.group(0)), out)
    out = _PERSON_ID.sub(lambda m: person(m.group(0)), out)
    out = _ACCT_ID.sub(r"\1 \2", out)
    out = _DEV_ID.sub(r"\1", out)
    if any(i in out for i in ("person:", "acct:", "dev:")):
        raise ValueError(f"an id is left in {out!r}")
    return out
