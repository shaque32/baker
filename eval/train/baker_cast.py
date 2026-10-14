"""Names for the people an item involves, as the case gives them (guide rules 25 and 26).

Baker shows a model names, not ids: a phone's stipulated user reads "Gabi Fontaine (the user of
item3)", a person the document names "Gabi Fontaine", an account "SMS +12125550123", a phone
"item3". Writers keep building params and lines with ids. `cast` gives every person an item
involves an invented full name; `readable` turns the ids a rationale uses into what the item
shows, and `fill_claim` writes a claim's people by name ("{{person:fontaine}}" for the full
name, "{{person:fontaine|last}}" for the surname alone).

Names follow eval/train's rule: first names and surnames start with A to M. A phone's user keeps
the first name the chats use (a Russian speaker's in the Latin form a document writes: Катя is
Ekaterina); a person linked to a chat partner keeps the partner's first name; person:<surname>
keeps that surname, and a numbered stand-in (person:doe_0142) gets any name. No two people of
an item share a first name or a surname, and a name drawn at random appears on no line.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable, Mapping

from eval.stancedata.names import case_names
from eval.train.baker_cues import SURNAMES
from eval.train.names import PEOPLE_EN, Person

# A Russian first name as a US document writes it, for the names whose Latin form starts with A
# to M. The others (Вера, Витя, Влад, Жанна, Зоя, Захар, Коля) are never cast as a phone's user
# or a linked person.
FORMAL_RU = {
    "Алина": "Alina", "Антон": "Anton", "Аня": "Anna", "Артём": "Artyom", "Боря": "Boris",
    "Белла": "Bella", "Глеб": "Gleb", "Галя": "Galina", "Гриша": "Grigory", "Даша": "Darya",
    "Дима": "Dmitry", "Денис": "Denis", "Егор": "Egor", "Женя": "Evgeny", "Жора": "Georgy",
    "Игорь": "Igor", "Ира": "Irina", "Илья": "Ilya", "Катя": "Ekaterina", "Кира": "Kira",
    "Лёня": "Leonid", "Лена": "Elena", "Лёша": "Alexei", "Лида": "Lidia", "Арина": "Arina",
}  # fmt: skip
# Russian surnames in Latin letters, (a man's form, a woman's form); Cyrillic forms start А to Л.
SURNAMES_RU = (
    ("Abramov", "Abramova"), ("Aksyonov", "Aksyonova"), ("Belov", "Belova"),
    ("Bogdanov", "Bogdanova"), ("Borisov", "Borisova"), ("Bykov", "Bykova"),
    ("Gavrilov", "Gavrilova"), ("Golubev", "Golubeva"), ("Gusev", "Guseva"),
    ("Davydov", "Davydova"), ("Danilov", "Danilova"), ("Demidov", "Demidova"),
    ("Dorokhov", "Dorokhova"), ("Egorov", "Egorova"), ("Efimov", "Efimova"),
    ("Isaev", "Isaeva"), ("Ilyin", "Ilyina"), ("Kazakov", "Kazakova"), ("Kalinin", "Kalinina"),
    ("Karpov", "Karpova"), ("Kiselev", "Kiseleva"), ("Komarov", "Komarova"),
    ("Kotov", "Kotova"), ("Kozlov", "Kozlova"), ("Laptev", "Lapteva"), ("Lebedev", "Lebedeva"),
    ("Larionov", "Larionova"), ("Klimenko", "Klimenko"), ("Bondarenko", "Bondarenko"),
)  # fmt: skip
FIRSTS_EN = tuple(p.name for p in PEOPLE_EN)
PID = re.compile(r"person:(?:dev:item\d+:owner|[a-z0-9_]+)")
SLOT = re.compile(r"\{\{(person:[^{}|]+)(?:\|(first|last))?\}\}")
_BRACKETS = re.compile(r"\[(person:[^\[\]]+)\]")
_ACCOUNT = re.compile(r"acct:item\d+:([A-Za-z]+):([^\s,;/\"()]*[^\s,;/\"().])")
_PHONE = re.compile(r"\bdev:item(\d+)\b")


def cap(surname: str) -> str:
    """'calder' -> 'Calder', 'mccall' -> 'McCall'."""
    if surname.startswith("mc") and len(surname) > 2:
        return "Mc" + surname[2:].capitalize()
    return surname.capitalize()


def first_of(p: Person) -> str | None:
    """The first name a document gives a chat person, if it starts with A to M."""
    return p.name if p.lang == "en" else FORMAL_RU.get(p.name)


def _free(name: str, used: set[str], shown: str) -> bool:
    return name.casefold() not in used and name.casefold() not in shown


def _pick(rng: random.Random, pool: Iterable[str], used: set[str], shown: str) -> str:
    free = [x for x in pool if _free(x, used, shown)]
    if not free:
        raise ValueError("no free name left for this item")
    return rng.choice(free)


def _surnames(p: Person | None) -> list[str]:
    if p is not None and p.lang == "ru":
        return [pair[1 if p.end else 0] for pair in SURNAMES_RU]
    return [cap(s) for s in SURNAMES]


def cast(
    rng: random.Random,
    pids: Iterable[str],
    preset: Mapping[str, str],
    owners: Mapping[str, Person],
    linked: Mapping[str, Person],
    shown: str,
) -> dict[str, str]:
    """A full name for every person id: `preset` ones as given; a phone's user (`owners`) by
    the first name the chats use; a linked person by the linked partner's. `shown` is every
    line's sender and text, lowercased: a name drawn at random never appears in it."""
    names = dict(preset)
    todo = sorted(set(pids) - set(names))
    people = {**linked, **owners}
    firsts = {pid: f for pid in todo if pid in people and (f := first_of(people[pid]))}
    drawn = ("person:dev:", "person:doe_")  # surnames drawn at random
    lasts = {pid: cap(pid.split(":", 1)[1]) for pid in todo if not pid.startswith(drawn)}
    fixed = [*firsts.values(), *lasts.values()]
    used = {part.casefold() for n in names.values() for part in n.split(" ", 1)}
    if len({x.casefold() for x in fixed}) < len(fixed) or used & {x.casefold() for x in fixed}:
        raise ValueError("two people of an item would share a name")
    used |= {x.casefold() for x in fixed}
    for pid in todo:
        first = firsts.get(pid) or _pick(rng, FIRSTS_EN, used, shown)
        used.add(first.casefold())
        last = lasts.get(pid) or _pick(rng, _surnames(people.get(pid)), used, shown)
        used.add(last.casefold())
        names[pid] = f"{first} {last}"
    return names


def pids_in(text: str) -> set[str]:
    return set(PID.findall(text)) | {m.group(1) for m in SLOT.finditer(text)}


def fill_claim(text: str, names: Mapping[str, str]) -> str:
    def one(m: re.Match[str]) -> str:
        first, last = names[m.group(1)].split(" ", 1)
        return {"first": first, "last": last}.get(m.group(2) or "", f"{first} {last}")

    return SLOT.sub(one, text)


def readable(text: str, names: Mapping[str, str]) -> str:
    """A rationale with Baker's ids printed as the item shows them."""
    pids = sorted(pids_in(text) | set(names))
    shown = case_names({p: names[p] for p in pids if p in names})

    def bracket(m: re.Match[str]) -> str:
        return "[" + ", ".join(sorted(shown.person(p) for p in m.group(1).split(", "))) + "]"

    text = _BRACKETS.sub(bracket, text)
    text = PID.sub(lambda m: shown.person(m.group(0)), text)
    text = _ACCOUNT.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
    text = _PHONE.sub(lambda m: f"item{m.group(1)}", text)
    if any(i in text for i in ("person:", "acct:", "dev:")):
        raise ValueError(f"an id is left in {text!r}")
    return text
