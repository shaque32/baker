"""Families on Baker's sender template, and named persons no line shows.

bk_sender_shown: the quoted words come from the named sender, shown by its account or by a
person id in its line's brackets (supports). bk_sender_other: they come from another account or
person, so one record cannot show the named sender never sent them too (complicates).
bk_party_unshown: the assumption names a person:<surname> that no line carries in brackets, on
the sender, time, no-contact or count template (complicates).
"""

from __future__ import annotations

import random
from typing import Any

from eval.stancedata import bakerform as bf
from eval.train.baker_cues import CALLED_BY_NAME
from eval.train.baker_fam_count import KIND_WORD, _count, file_name
from eval.train.baker_fam_time import other_zone, when
from eval.train.baker_kit import (
    Draft,
    Setup,
    any_time,
    chat,
    lang_of_text,
    pick_kind,
    quoted_words,
    record_text,
    setup,
    slug,
    surname_of,
)
from eval.train.baker_parties import name_account, strangers
from eval.train.baker_place import inside
from eval.train.baker_scene import render
from eval.train.baker_text import fill
from eval.train.baker_time import wall


def _named(params: dict[str, Any]) -> str:
    """The party a sender assumption names, as its text writes it."""
    if "person_ids" in params:
        return params["person_ids"][0]
    return "/".join(params["account_ids"])


def sender_shown(rng: random.Random, k: int) -> Draft:
    text, core = record_text(rng, k, "bk_sender_shown")
    lang = lang_of_text(text)
    s = setup(rng, pick_kind(rng), lang=lang)
    quoted = quoted_words(rng, text, core)
    utc = any_time(rng, s.phone.zone)
    evs, target = chat(rng, s, text, utc, rng.random() < 0.5, lang, avoid=quoted)
    rec = evs[target]
    params: dict[str, Any] = {"quoted_text": quoted} | name_account(rng, s, rec.frm, 0.55)
    if rng.random() < 0.3:
        params["channels"] = (rec.frm.app,)
    line = render(s.scene, s.phone, rec)
    if "person_ids" in params:
        why = f"whose brackets carry {params['person_ids'][0]}, the named sender"
    else:
        why = "the named account"
    rationale = f"The record holding the quoted words comes from {line.sender}, {why}."
    return Draft("bk_sender_shown", "sender", params, s.scene, s.phone, evs, target, quoted,
                 rationale)  # fmt: skip


def sender_other(rng: random.Random, k: int) -> Draft:
    """The named sender is the chat's other end (by account, or by a person id its lines
    carry), or an account no line shows; never the record's own account on another app."""
    text, core = record_text(rng, k, "bk_sender_other")
    lang = lang_of_text(text)
    s = setup(rng, pick_kind(rng), lang=lang)
    quoted = quoted_words(rng, text, core)
    utc = any_time(rng, s.phone.zone)
    evs, target = chat(rng, s, text, utc, rng.random() < 0.5, lang, avoid=quoted)
    rec = evs[target]
    if rec.to is None:
        raise ValueError("a message needs its chat partner")
    if rng.random() < 0.25:
        acc = strangers(rng, s, 1, lang)[0].acc(rec.frm.app)
        params: dict[str, Any] = {"account_ids": (s.phone.aid(acc),)}
    else:
        params = name_account(rng, s, rec.to, 0.5)
    params["quoted_text"] = quoted
    if rng.random() < 0.2:
        params["channels"] = (rec.frm.app,)
    line = render(s.scene, s.phone, rec)
    named = _named(params)
    rationale = (f"The record holding the quoted words comes from {line.sender}, not from "
                 f"{named}; one record cannot show that {named} never sent them too.")  # fmt: skip
    return Draft("bk_sender_other", "sender", params, s.scene, s.phone, evs, target, quoted,
                 rationale, {"named": named})  # fmt: skip


def called_by(rng: random.Random, s: Setup, surname: str) -> str:
    """A line from the owner that calls the partner by a full name."""
    line = rng.choice(CALLED_BY_NAME)
    line = line.replace("{first}", s.partner.person.name).replace("{Sur}", cap(surname))
    return fill(rng, line)[0]


def cap(surname: str) -> str:
    """'calder' -> 'Calder', 'mccall' -> 'McCall'."""
    if surname.startswith("mc") and len(surname) > 2:
        return "Mc" + surname[2:].capitalize()
    return surname.capitalize()


def party_unshown(rng: random.Random, k: int) -> Draft:
    """The record fits the assumption except that the person:<surname> it names is on no
    line's brackets: the record comes from, or is with, a third party with no brackets."""
    family = "bk_party_unshown"
    template = ("sender", "record_time", "no_contact", "message_count")[k % 4]
    text, core = record_text(rng, k, family)
    lang = lang_of_text(text)
    s = setup(rng, "third", lang=lang)
    pid = slug(rng)
    quoted = quoted_words(rng, text, core)
    win = None
    if template == "sender":
        utc = any_time(rng, s.phone.zone)
    else:
        tz = other_zone(rng, s.phone.zone) if rng.random() < 0.2 else s.phone.zone
        win, utc = inside(rng, s.phone.zone, tz)
    by_message = template in ("sender", "record_time")
    lead = ""
    if by_message and lang == "en" and not pid.startswith("person:doe_") and rng.random() < 0.25:
        lead = called_by(rng, s, surname_of(pid))
    kind = "att" if not by_message and rng.random() < 0.25 else "msg"
    if kind == "att":
        text = core = file_name(rng, k, family, wall(utc, s.phone.zone), rng.random() < 0.5)
    from_me = not by_message and rng.random() < 0.5
    evs, target = chat(rng, s, text, utc, from_me, lang, avoid=quoted if by_message else "",
                       kind=kind, lead=lead)  # fmt: skip
    rec = evs[target]
    line = render(s.scene, s.phone, rec)
    partner = bf.sender_line(s.you.app, s.you.ident)
    unshown = f"no line carries {pid} in brackets, so nothing shown ties {partner} to {pid}"
    if by_message:
        params: dict[str, Any] = {"quoted_text": quoted, "person_ids": (pid,)}
        d = Draft(family, template, params, s.scene, s.phone, evs, target, quoted, "")
        d.rationale = f"The record holding the quoted words comes from {partner}"
        if win is not None:
            params["window"] = win.tw
            at = when(line.local_time, win, utc, s.phone.zone)
            d.rationale += f', sent {at}, inside "{win.raw}" ({win.tz})'
        d.rationale += f"; {unshown}."
        return d
    if win is None:
        raise ValueError("a no-contact or count assumption needs a window")
    if rng.random() < 0.5:
        params = {"person_ids": tuple(rng.sample((s.phone.person, pid), 2))}
    else:
        params = {"person_ids": (pid,), "account_ids": (s.phone.aid(s.me),)}
    params["window"] = win.tw
    d = Draft(family, template, params, s.scene, s.phone, evs, target, line.text, "")
    if template == "message_count":
        _count(rng, d, win, s, s.phone.dev)
    owner = bf.sender_line(s.me.app, s.me.ident, owner=True, persons=(s.phone.person,))
    at = when(line.local_time, win, utc, s.phone.zone)
    d.rationale = (f"The record is {KIND_WORD[kind]} between {owner} and {partner} at {at}, "
                   f"inside \"{win.raw}\" ({win.tz}); {unshown}.")  # fmt: skip
    return d
