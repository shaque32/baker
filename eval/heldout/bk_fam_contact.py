"""Writers for the contact-row families: bk_contact_row and bk_contact_row_differs."""

from __future__ import annotations

import random

from eval.heldout.bk_common import BkDraft, own_apps, pick
from eval.heldout.bk_names import CONTACT_TAGS, CONTACT_TAGS_RU, FIRSTS, RU_FIRSTS
from eval.heldout.bk_scene import Acct, Excerpt, Phone, Scene, chat_app, items, zone
from eval.heldout.bk_schedule import BkSlot


def contact_phone(rng: random.Random, lang: str) -> tuple[Scene, Phone]:
    sc = Scene()
    return sc, sc.phone(rng, items(rng, 1)[0], zone(rng), own_apps(rng, chat_app(rng, lang)))


def other_name(rng: random.Random, name: str, ru: bool, share_one: bool) -> str:
    """Another saved name: with `share_one`, the same first name or the same tag as `name`;
    otherwise neither."""
    first, tag = name.split(" ", 1)
    firsts = RU_FIRSTS if ru else FIRSTS
    tags = sorted({t for v in (CONTACT_TAGS_RU if ru else CONTACT_TAGS).values() for t in v})
    new_first = rng.choice([f for f in firsts if f != first])
    new_tag = rng.choice([t for t in tags if t != tag])
    if not share_one:
        return f"{new_first} {new_tag}"
    return f"{first} {new_tag}" if rng.random() < 0.5 else f"{new_first} {tag}"


def row(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_contact_row: the contact row on the named phone with exactly that name and number."""
    sc, p = contact_phone(rng, "ru" if s.lang == "ru" else "en")
    number = sc.number(rng)
    rec = sc.contact(p, s.contact, number)
    aid = p.aid(Acct("Phone", number))
    params = {"device_ids": [p.dev], "quoted_text": s.contact, "account_ids": [aid]}
    why = pick(
        rng,
        f'The contact row on {p.dev} reads "{rec.text}": the saved name and the number the '
        "assumption gives.",
        f'{p.dev} holds the row "{rec.text}", with exactly the saved name "{s.contact}" and the '
        f"number of {aid}.",
    )
    return BkDraft(s.family, "contact_entry", params, Excerpt([rec], 0), rec.text, why, p,
                   s.lang, sc, facts={"variant": s.variant})  # fmt: skip


def row_differs(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_contact_row_differs: a row on the named phone with the name and another number, or
    the number under another name."""
    ru = s.lang == "ru"
    sc, p = contact_phone(rng, "ru" if ru else "en")
    number = sc.number(rng)
    aid = p.aid(Acct("Phone", number))
    if s.variant == "other_number":
        shown = sc.number(rng)
        rec = sc.contact(p, s.contact, shown)
        name = s.contact
        why = pick(
            rng,
            f'The row on {p.dev} has the name "{name}" but the number {shown}, not {number}; '
            "one row cannot show the phone holds no other entry under that name.",
            f'"{name}" is saved here with {shown}; the assumption gives {number}, and a second '
            "entry under the same name may exist, so the row leaves it open.",
        )
    else:
        rec = sc.contact(p, s.contact, number)
        name = other_name(rng, s.contact, ru, share_one=True)
        why = pick(
            rng,
            f'The row holds the number {number} saved as "{s.contact}", not "{name}"; one row '
            f"cannot show {p.dev} has no other entry for that number.",
            f'{p.dev} saves {number} as "{s.contact}"; the assumption names "{name}", and the '
            "phone may hold that entry too, so the row leaves it open.",
        )
    params = {"device_ids": [p.dev], "quoted_text": name, "account_ids": [aid]}
    return BkDraft(s.family, "contact_entry", params, Excerpt([rec], 0), rec.text, why, p,
                   s.lang, sc, facts={"variant": s.variant})  # fmt: skip
