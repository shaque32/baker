"""Families on Baker's contact template: a contact row on the named phone.

bk_contact_row: the row has exactly the saved name and the number the assumption gives
(supports). bk_contact_row_differs: the row has that name with another number, or that number
under a name with another first name (complicates: one row cannot show the named entry is
absent). A contact row stands alone: no time, no context.
"""

from __future__ import annotations

import random
from typing import Any

from eval.train.baker_cues import SURNAMES
from eval.train.baker_fam_sender import cap
from eval.train.baker_kit import Draft
from eval.train.baker_scene import MSG_APPS, Acc, Cast, Ev, Phone, Scene, items, render
from eval.train.baker_text import combo, salt_of, split_ru
from eval.train.names import (
    FEMALE_ROLES,
    MALE_ROLES,
    PEOPLE_EN,
    PEOPLE_RU,
    ROLES_EN,
    ROLES_RU,
    Person,
)

# How owners save names: {First}, a role word ({Role} as saved, {role} lowercased), a surname.
FORMS = {
    "en": ("{First}", "{First} {Role}", "{First} ({role})", "{Role} {First}", "{First} {Sur}",
           "{First} {S}."),
    "ru": ("{First}", "{First} {role}", "{role} {First}"),
}  # fmt: skip
PEOPLE = {"en": PEOPLE_EN, "ru": PEOPLE_RU}
ROLES = {"en": ROLES_EN, "ru": ROLES_RU}


def saved_name(rng: random.Random, p: Person, form: str) -> str:
    """A contact name in one of the FORMS, with a role word that fits the person's gender."""
    skip = MALE_ROLES if p.pron == "she" else FEMALE_ROLES
    role = rng.choice([r for r in ROLES[p.lang] if r not in skip])
    sur = cap(rng.choice(SURNAMES))
    for slot, value in (("{First}", p.name), ("{Role}", role), ("{role}", role.lower()),
                        ("{Sur}", sur), ("{S}", sur[0])):  # fmt: skip
        form = form.replace(slot, value)
    return form


def _name(rng: random.Random, k: int, family: str) -> tuple[str, Person, str]:
    """The k-th saved name of a family: no two of its items share one. One in ten is Russian."""
    ru, ordinal = split_ru(k)
    lang = "ru" if ru else "en"
    f, i = combo(ordinal, (len(FORMS[lang]), len(PEOPLE[lang])), salt_of(f"{family}|{lang}"))
    p = PEOPLE[lang][i]
    return saved_name(rng, p, FORMS[lang][f]), p, lang


def _phone(rng: random.Random, lang: str) -> tuple[Phone, Cast]:
    cast = Cast(rng)
    return cast.phone(items(rng, 1)[0], (rng.choice(MSG_APPS),), lang), cast


def _row(phone: Phone, name: str, number: str) -> tuple[Scene, Ev, str]:
    scene = Scene((phone,))
    ev = Ev(None, Acc("Phone", number), name, "contact")
    return scene, ev, render(scene, phone, ev).text


def contact_row(rng: random.Random, k: int) -> Draft:
    family = "bk_contact_row"
    name, _, lang = _name(rng, k, family)
    phone, cast = _phone(rng, lang)
    number = cast.number()
    scene, ev, row = _row(phone, name, number)
    params: dict[str, Any] = {"device_ids": (phone.dev,), "quoted_text": name,
                              "account_ids": (phone.aid(ev.frm),)}  # fmt: skip
    rationale = (f"The contact row on {phone.dev} reads \"{row}\": exactly the saved name and "
                 "the number the assumption gives.")  # fmt: skip
    return Draft(family, "contact_entry", params, scene, phone, [ev], 0, row, rationale)


def contact_row_differs(rng: random.Random, k: int) -> Draft:
    """Even k: the row has the named name and another number. Odd k: the named number under a
    name with another first name."""
    family = "bk_contact_row_differs"
    name, person, lang = _name(rng, k, family)
    phone, cast = _phone(rng, lang)
    number, other = cast.number(), cast.number()
    acc = Acc("Phone", number)
    params: dict[str, Any] = {"device_ids": (phone.dev,), "quoted_text": name,
                              "account_ids": (phone.aid(acc),)}  # fmt: skip
    if k % 2 == 0:
        scene, ev, row = _row(phone, name, other)
        rationale = (f"The contact row on {phone.dev} has the saved name \"{name}\" with another "
                     f"number, {other}; one row cannot show the phone has no entry \"{name}\" "
                     "with the named number.")  # fmt: skip
    else:
        firsts = [p for p in PEOPLE[lang] if p.name != person.name]
        alias = saved_name(rng, rng.choice(firsts), rng.choice(FORMS[lang]))
        scene, ev, row = _row(phone, alias, number)
        rationale = (f"The contact row on {phone.dev} has the named number under another name, "
                     f"\"{alias}\"; one row cannot show the phone has no entry \"{name}\" for "
                     "it.")  # fmt: skip
    return Draft(family, "contact_entry", params, scene, phone, [ev], 0, row, rationale)
