"""Families on Baker's identity, authorship and same-account templates.

bk_identity_named: the named account's message gives the named person's name (complicates: a
name in a chat never shows who holds an account). bk_account_silent: an everyday message from
the named account (irrelevant). bk_author_cue: the named account's message says who is typing
(complicates). bk_handles_said: a message says two or three handles are one account
(complicates: a message shows what was said, not the platform's records).
"""

from __future__ import annotations

import random
import re
from typing import Any

from eval.stancedata import bakerform as bf
from eval.train.baker_cues import (
    AUTHOR_CUES,
    AUTHOR_CUES_RU,
    HANDLES_SAID,
    HANDLES_SAID_3,
    HANDLES_SAID_RU,
    ID_CUES,
    RELS,
    SURNAMES,
)
from eval.train.baker_fam_sender import called_by, cap
from eval.train.baker_kit import (
    ORDINARY,
    Draft,
    any_time,
    chat,
    lang_of_text,
    record_text,
    setup,
    slug,
)
from eval.train.baker_scene import render
from eval.train.baker_text import combo, fill, salt_of, split_ru
from eval.train.names import PEOPLE_EN, PEOPLE_RU, STEMS, TAGS

SELF = re.compile(r"\b(?:my|i)\b|\{e\}")  # a handle line the account itself speaks


def identity_named(rng: random.Random, k: int) -> Draft:
    """The partner's message gives a full name; the assumption ties its account to that
    surname. Sometimes the owner first calls the partner by it."""
    family = "bk_identity_named"
    t, si = combo(k, (len(ID_CUES), len(SURNAMES)), salt_of(family))
    sur = SURNAMES[si]
    s = setup(rng, "third")
    cue = ID_CUES[t].replace("{first}", s.partner.person.name).replace("{Sur}", cap(sur))
    text, core = fill(rng, cue)
    lead = called_by(rng, s, sur) if rng.random() < 0.3 else ""
    evs, target = chat(rng, s, text, any_time(rng, s.phone.zone), False, "en", lead=lead)
    rec = evs[target]
    pid = bf.named_person(sur)
    params: dict[str, Any] = {"person_ids": (pid,), "account_ids": (s.phone.aid(rec.frm),)}
    line = render(s.scene, s.phone, rec)
    rationale = (f"The record from {line.sender} has its sender giving the name {cap(sur)}, but "
                 f"a name typed in a chat does not show that {pid} holds the account.")  # fmt: skip
    return Draft(family, "person_identity", params, s.scene, s.phone, evs, target, core,
                 rationale)  # fmt: skip


def account_silent(rng: random.Random, k: int) -> Draft:
    """An everyday message from the named account: a third party's, tied to a named surname,
    or (authorship only) the owner's own account, tied to the owner."""
    family = "bk_account_silent"
    template = ("person_identity", "authorship")[k % 2]
    text, _ = record_text(rng, k, family)
    lang = lang_of_text(text)
    own = template == "authorship" and rng.random() < 0.3
    s = setup(rng, "third", lang=lang)
    evs, target = chat(rng, s, text, any_time(rng, s.phone.zone), own, lang)
    rec = evs[target]
    pid = s.phone.person if own else slug(rng)
    params: dict[str, Any] = {"person_ids": (pid,), "account_ids": (s.phone.aid(rec.frm),)}
    line = render(s.scene, s.phone, rec)
    what = "who holds the account" if template == "person_identity" else "who typed it"
    rationale = (
        f"The record from {line.sender} is an everyday message; it says nothing about {what}."
    )
    return Draft(family, template, params, s.scene, s.phone, evs, target, line.text, rationale)


def author_cue(rng: random.Random, k: int) -> Draft:
    """The named account's message says someone other than its usual user is typing, or is
    signed; the account is a third party's (tied to a named surname) or the owner's own."""
    family = "bk_author_cue"
    ru, ordinal = split_ru(k)
    lang = "ru" if ru else "en"
    pool, people = (AUTHOR_CUES_RU, PEOPLE_RU) if ru else (AUTHOR_CUES, PEOPLE_EN)
    t, f = combo(ordinal, (len(pool), len(people)), salt_of(f"{family}|{lang}"))
    typist = people[f]
    own = rng.random() < 0.4
    s = setup(rng, "third", lang=lang, taken=(typist.name,))
    holder = (s.phone.owner if own else s.partner).person
    cue = pool[t]
    if "{ordinary}" in cue:
        cue = cue.replace("{ordinary}", fill(rng, rng.choice(ORDINARY[lang]))[0])
    for slot, value in (("{first}", typist.name), ("{other}s", possessive(rng, holder.name)),
                        ("{other}", holder.name),
                        ("{pron}", holder.pron), ("{poss}", holder.poss), ("{e}", holder.end),
                        ("{rel}", rng.choice(RELS[typist.pron]))):  # fmt: skip
        cue = cue.replace(slot, value)
    text, core = fill(rng, cue)
    evs, target = chat(rng, s, text, any_time(rng, s.phone.zone), own, lang)
    rec = evs[target]
    pid = s.phone.person if own else slug(rng)
    params: dict[str, Any] = {"person_ids": (pid,), "account_ids": (s.phone.aid(rec.frm),)}
    line = render(s.scene, s.phone, rec)
    rationale = (f"The record from {line.sender} carries a cue about who is typing (\"{core}\"); "
                 "one record cannot show who typed what the account sent.")  # fmt: skip
    return Draft(family, "authorship", params, s.scene, s.phone, evs, target, core, rationale)


def possessive(rng: random.Random, name: str) -> str:
    """How a text writes "Bea's": "Beas" or "Bea's"; "Ines'" for a name ending in s."""
    if name.endswith("s"):
        return name + "'"
    return name + rng.choice(("s", "'s"))


def _handle(rng: random.Random, app: str, stem: str) -> str:
    """'@ana_nails', '@bramcuts', '@lina.studio', '@dev42': Telegram allows no dots."""
    for _ in range(50):
        if rng.random() < 0.3:
            h = f"{stem}{rng.randrange(10, 100)}"
        else:
            seps = ("_", "") if app == "Telegram" else ("_", ".", "")
            h = f"{stem}{rng.choice(seps)}{rng.choice(TAGS)}"
        if len(h) >= 5:
            return f"@{h}"
    raise RuntimeError("no handle long enough")


def handles_said(rng: random.Random, k: int) -> Draft:
    """A Telegram or Instagram message says the handles are one account. A line the account
    speaks itself comes from the partner; on Instagram its current handle is its identifier."""
    family = "bk_handles_said"
    ru, _ = split_ru(k)
    lang = "ru" if ru else "en"
    app = rng.choice(("Telegram", "Instagram"))
    s = setup(rng, rng.choice(("third", "third", "phones")), app=app, lang=lang)
    three = not ru and rng.random() < 0.15
    cue = rng.choice(HANDLES_SAID_RU if ru else HANDLES_SAID_3 if three else HANDLES_SAID)
    speaks = bool(SELF.search(cue))
    from_me = False if speaks else rng.random() < 0.5
    names = {p.owner.ig for p in s.scene.phones} | {s.partner.ig}
    stems = [x for x in (*(p.name.lower() for p in PEOPLE_EN), *STEMS)
             if not any(n.startswith(x) for n in names)]  # fmt: skip
    taken = {"@" + n for n in names}
    handles: list[str] = []
    if speaks and app == "Instagram":
        handles = ["@" + s.partner.ig]  # the account's own handle now: the newest one
    while len(handles) < (3 if three else 2):
        stem = handles[-1][1:].split("_")[0] if handles and rng.random() < 0.4 else None
        h = _handle(rng, app, stem or rng.choice(stems))
        if h not in taken and h not in handles:
            handles.append(h)
    order = handles[::-1] if speaks and app == "Instagram" else handles  # oldest first
    for i, h in enumerate(order, 1):
        cue = cue.replace(f"{{h{i}}}", h)
    speaker = s.partner if not from_me else s.phone.owner
    text, core = fill(rng, cue.replace("{e}", speaker.person.end))
    evs, target = chat(rng, s, text, any_time(rng, s.phone.zone), from_me, lang)
    rec = evs[target]
    named = tuple(rng.sample(order, len(order))) if rng.random() < 0.3 else tuple(order)
    params: dict[str, Any] = {"channels": (app,), "handles": named}
    line = render(s.scene, s.phone, rec)
    listing = ", ".join(order[:-1]) + f" and {order[-1]}"
    rationale = (f"The record from {line.sender} says the handles {listing} belong to one "
                 "account; a message shows what was said, not the platform's records.")  # fmt: skip
    return Draft(family, "same_account", params, s.scene, s.phone, evs, target, core, rationale)
