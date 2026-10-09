"""People, accounts and the way an assumption names them.

Training pools use Latin first letters A to M and Cyrillic А to Л (the held-out generator uses the
rest), area codes 212, 347, 646, 718, 917, 929, 516 and 631, and Telegram ids of seven digits
starting with 3 or 4. A Person carries grammar only (pronoun, Russian past-tense ending); what
the phone shows is the Account's label, and an assumption names the account as the phone shows
it, never the person behind it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from eval.stancedata.chat import Account, fictional_phone, pretty_phone

AREA_CODES = ("212", "347", "646", "718", "917", "929", "516", "631")
APPS_PHONE = ("SMS", "WhatsApp", "Signal")


@dataclass(frozen=True)
class Person:
    name: str  # first name as a saved label would show it
    pron: str  # "he", "she" or "they" (an account with no saved name)
    lang: str  # "en" or "ru"
    end: str = ""  # Russian past-tense ending for this speaker: "" or "а"

    @property
    def obj(self) -> str:
        return {"he": "him", "she": "her"}.get(self.pron, "them")

    @property
    def poss(self) -> str:
        return {"he": "his", "she": "her"}.get(self.pron, "their")


_EN = (
    ("Ana", "she"),
    ("Abe", "he"),
    ("Aria", "she"),
    ("Bo", "he"),
    ("Bea", "she"),
    ("Bram", "he"),
    ("Ciro", "he"),
    ("Cleo", "she"),
    ("Cal", "he"),
    ("Dev", "he"),
    ("Dina", "she"),
    ("Dara", "she"),
    ("Ellie", "she"),
    ("Eli", "he"),
    ("Enzo", "he"),
    ("Fitz", "he"),
    ("Faye", "she"),
    ("Finn", "he"),
    ("Gabi", "she"),
    ("Gus", "he"),
    ("Greta", "she"),
    ("Hollis", "he"),
    ("Hana", "she"),
    ("Hugo", "he"),
    ("Imani", "she"),
    ("Ike", "he"),
    ("Ines", "she"),
    ("Jules", "he"),
    ("Jada", "she"),
    ("Joss", "he"),
    ("Kenji", "he"),
    ("Kira", "she"),
    ("Kofi", "he"),
    ("Lupe", "she"),
    ("Leo", "he"),
    ("Lina", "she"),
    ("Mateo", "he"),
    ("Mara", "she"),
    ("Milo", "he"),
    ("Celia", "she"),
    ("Dante", "he"),
    ("Esme", "she"),
    ("Gideon", "he"),
    ("Harriet", "she"),
    ("Jonah", "he"),
    ("Luca", "he"),
    ("Maya", "she"),
    ("Beck", "he"),
)
_RU = (
    ("Алина", "she", "а"),
    ("Антон", "he", ""),
    ("Аня", "she", "а"),
    ("Артём", "he", ""),
    ("Боря", "he", ""),
    ("Белла", "she", "а"),
    ("Вера", "she", "а"),
    ("Витя", "he", ""),
    ("Влад", "he", ""),
    ("Глеб", "he", ""),
    ("Галя", "she", "а"),
    ("Гриша", "he", ""),
    ("Даша", "she", "а"),
    ("Дима", "he", ""),
    ("Денис", "he", ""),
    ("Егор", "he", ""),
    ("Женя", "he", ""),
    ("Жора", "he", ""),
    ("Жанна", "she", "а"),
    ("Зоя", "she", "а"),
    ("Захар", "he", ""),
    ("Игорь", "he", ""),
    ("Ира", "she", "а"),
    ("Илья", "he", ""),
    ("Катя", "she", "а"),
    ("Коля", "he", ""),
    ("Кира", "she", "а"),
    ("Лёня", "he", ""),
    ("Лена", "she", "а"),
    ("Лёша", "he", ""),
    ("Лида", "she", "а"),
    ("Арина", "she", "а"),
)
PEOPLE_EN = tuple(Person(n, p, "en") for n, p in _EN)
PEOPLE_RU = tuple(Person(n, p, "ru", e) for n, p, e in _RU)

# Role words a saved contact name often carries ("Bo Plumber", "Катя салон").
ROLES_EN = (
    "Plumber",
    "Garage",
    "Movers",
    "Nails",
    "Barber",
    "Landlord",
    "Gym",
    "HVAC",
    "Cuts",
    "Bar",
    "Tile Guy",
    "Mom",
    "Dad",
    "Sis",
    "Work",
    "Rides",
    "Laptop",
    "DJ",
    "Realtor",
    "Daycare",
    "Coach",
    "Pizza",
    "Cousin",
    "Upstairs",
    "Auntie",
)
ROLES_RU = (
    "сантехник",
    "гараж",
    "грузчик",
    "салон",
    "барбер",
    "хозяин кв",
    "зал",
    "мастер",
    "мама",
    "папа",
    "сестра",
    "работа",
    "ремонт",
    "нотариус",
    "сосед",
)

# Usernames and handles carry the person's own first name (Latin names) or no name at all
# (Cyrillic names), so a shown handle never names a different person than the one an assumption
# attaches to the account (guide rule 4 and the handle-owner trap). Stems start with A-M.
TAGS = ("dj", "nails", "cuts", "cakes", "movers", "rides", "hvac", "lashes", "bar", "events",
        "barber", "mv", "garage", "fixes", "tattoo", "moto", "flowers", "braids", "laptops",
        "sound", "fit", "van", "cars", "tile", "decor", "pizza", "bk", "nyc", "li", "718", "917",
        "7", "99", "x", "official", "shop", "studio", "auto", "beauty", "wrench")  # fmt: skip
STEMS = ("bk", "garage", "cuts", "cakes", "flowers", "lashes", "fix", "moto", "events", "braids",
         "auto", "home", "glam", "detail", "barber", "clean", "deli", "keys", "lux", "mint", "iron",
         "jet", "hvac", "flat", "dj", "brow", "color", "dacha", "euro", "grill", "kraft", "limo",
         "mebel", "master", "beauty", "city", "fresh", "hair", "glow", "lady")  # fmt: skip


def username(rng: random.Random, p: Person) -> str:
    """An Instagram username: the person's first name plus a tag, or a name-free stem."""
    stem = rng.choice(STEMS) if p.lang == "ru" else p.name.lower()
    if rng.random() < 0.25:
        return f"{stem}{rng.randrange(10, 100)}"
    return f"{stem}{rng.choice(('.', '_', ''))}{rng.choice(TAGS)}"


def handle(rng: random.Random, p: Person) -> str:
    """A Telegram handle label under the same rule as `username`."""
    stem = rng.choice(STEMS) if p.lang == "ru" else p.name.lower()
    if rng.random() < 0.2:
        return f"@{stem}{rng.randrange(10, 100)}"
    return f"@{stem}_{rng.choice(TAGS)}"


LAST_NAMES = (
    "Vance",
    "Okafor",
    "Petrov",
    "Lindqvist",
    "Marsh",
    "Delgado",
    "Haas",
    "Brennan",
    "Castellano",
    "Ferreira",
    "Novak",
    "Adeyemi",
    "Kowalski",
    "Ruiz",
    "Tanaka",
    "Moreau",
    "Whitfield",
    "Oyelaran",
    "Sandoval",
    "Grigoryan",
    "Baptiste",
    "Nakamura",
)
LAST_NAMES_RU = (
    "Громова",
    "Самойлов",
    "Ткаченко",
    "Лебедева",
    "Зайцев",
    "Орлова",
    "Мельник",
    "Сорокин",
    "Карпова",
    "Назаров",
    "Фролова",
    "Белов",
)


def person(rng: random.Random, lang: str) -> Person:
    return rng.choice(PEOPLE_RU if lang == "ru" else PEOPLE_EN)


def full_name(rng: random.Random, p: Person) -> str:
    """A real-person name for an identity claim; first name under the same letter rule."""
    last = rng.choice(LAST_NAMES_RU if p.lang == "ru" else LAST_NAMES)
    if p.lang == "ru" and p.pron == "he" and last.endswith("а"):
        last = last[:-1]  # Громова -> Громов
    elif p.lang == "ru" and p.pron == "she" and last.endswith(("ов", "ев", "ин")):
        last += "а"  # Сорокин -> Сорокина; Мельник and Ткаченко do not change
    return f"{p.name} {last}"


def telegram_id(rng: random.Random) -> str:
    return f"{rng.choice('34')}{rng.randrange(10**6):06d}"


FEMALE_ROLES = {"Mom", "Sis", "Auntie", "мама", "сестра"}
MALE_ROLES = {"Dad", "папа", "хозяин кв", "сосед"}


def saved_label(rng: random.Random, p: Person) -> str:
    """The name as the owner saved it: bare, or with a role that fits the person's gender."""
    roll = rng.random()
    if roll < 0.55:
        return p.name
    skip = MALE_ROLES if p.pron == "she" else FEMALE_ROLES
    role = rng.choice([r for r in (ROLES_RU if p.lang == "ru" else ROLES_EN) if r not in skip])
    return f"{p.name} {role}" if roll < 0.9 else f"{p.name} ({role.lower()})"


@dataclass(frozen=True)
class Party:
    """One participant: the account as the phone shows it plus the grammar of its writer."""

    account: Account
    person: Person

    @property
    def who(self) -> str:
        """How an assumption names this account: as the phone shows it, never as a person."""
        a = self.account
        if a.owner:
            return "the owner"
        if a.app == "Telegram":
            shown = f" (shown as {a.label})" if a.label else ""
            return f"Telegram user {a.identifier}{shown}"
        if a.app == "Instagram":
            return f"the Instagram account {a.identifier}"
        if a.label:
            return f"the contact saved as {a.label}"
        return pretty_phone(a.identifier)

    @property
    def pron(self) -> str:
        return self.person.pron if self.account.owner or self.account.label else "they"

    @property
    def end(self) -> str:
        return self.person.end


def cast(rng: random.Random, lang: str, extra: int = 0) -> tuple[str, Party, list[Party]]:
    """The app, the owner and 1 + extra contacts of one chat, all on that app."""
    app = rng.choice(APPS_PHONE + ("Telegram", "Instagram", "WhatsApp", "SMS"))
    people = rng.sample(PEOPLE_RU if lang == "ru" else PEOPLE_EN, 2 + extra)
    taken: set[str] = set()

    def ident(p: Person) -> str:
        while True:
            if app == "Telegram":
                x = telegram_id(rng)
            elif app == "Instagram":
                x = username(rng, p)
            else:
                x = fictional_phone(rng, AREA_CODES)
            if x not in taken:
                taken.add(x)
                return x

    owner = Party(Account(app, ident(people[0]), owner=True), people[0])
    contacts: list[Party] = []
    labels: set[str] = set()
    for p in people[1:]:
        roll = rng.random()
        if app == "Telegram":
            label = None if roll < 0.3 else handle(rng, p) if roll < 0.55 else p.name
        elif app == "Instagram":
            label = None if roll < 0.7 else p.name
        else:
            label = None if roll < 0.2 else saved_label(rng, p)
        if label in labels:  # two members never share a handle; fall back to the saved name
            label = p.name
        if label:
            labels.add(label)
        contacts.append(Party(Account(app, ident(p), label), p))
    return app, owner, contacts
