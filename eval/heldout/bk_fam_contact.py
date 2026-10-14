"""Writers for the contact-row families (bk_contact_row, bk_contact_row_differs) and for
bk_claim_unseen, whose meaning, role and event templates point to a claim the stance step is
not shown."""

from __future__ import annotations

import random

from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import pair, shown_as
from eval.heldout.bk_common import BkDraft, clause, own_apps, pick, window_words
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


def claim(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_claim_unseen: the record holds the quoted words (meaning), or comes from or goes to
    an account bracketed with a named person (role; event inside its window, if any)."""
    v = s.variant
    if v == "meaning":
        pr = pair(rng, s)
        ex = pr.chat(rng, s, pk.some_time(rng, pr.p.tz), s.text, rng.random() < 0.5)
        q = clause(rng, s.text)
        why = pick(
            rng,
            "The record holds the quoted words, but what the claim says they mean is not shown "
            "here, so the record cannot settle it.",
            "The words are in the record, yet the claim's reading of them is not shown, so "
            "the record leaves their meaning under the claim open.",
        )
        return BkDraft(s.family, "meaning", {"quoted_text": q}, ex, q, why, pr.p, s.lang, pr.sc,
                       facts={"variant": v})  # fmt: skip
    pr = pair(rng, s, linked=True)
    mine = rng.random() < 0.5
    params: dict[str, object] = {"person_ids": [pr.linked]}
    win = None
    if v == "event" and rng.random() < 0.7:
        win = pk.pick_window(rng, pr.p.tz, (*pk.DATE_KINDS, "between"))
        params["window"] = win.tw()
    utc = bt.place_inside(rng, win, pr.p.tz) if win else pk.some_time(rng, pr.p.tz)
    ex = pr.chat(rng, s, utc, s.text, mine)
    acct = shown_as(pr.sc, pr.p, pr.other)
    way = "goes to" if mine else "comes from"
    if v == "role":
        why = (f"The record {way} {acct}, whose line carries {pr.linked}, but nothing shown says "
               "what role the claim states.")
        template = "role"
    else:
        inside = f", inside {window_words(win)}" if win else ""
        why = (f"The record {way} {acct}{inside}, but nothing shown says what event the claim "
               "states.")
        template = "event"
    return BkDraft(s.family, template, params, ex, s.text, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": v})  # fmt: skip
