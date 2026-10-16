"""Families on Baker's sender template, and named persons no line shows.

bk_sender_shown: the quoted words come from the named sender, shown by its account or by a
person id in its line's brackets (supports); a third of them sit on the scene's other phone,
from the first phone's user's own number, whose line shows no "(owner)" but carries that user in
brackets (guide rule 26). bk_sender_other: they come from another account or person,
so one record cannot show the named sender never sent them too (complicates).
bk_party_unshown: the assumption names a person:<surname> that no line carries in brackets, on
the sender, time, no-contact or count template (complicates); in a third of them the chat calls
the sender by that person's first name, a nickname of it or the full name, which still shows
no one (rule 26). The answer rests on the record's sender or time, so the quote is the record's
full text (guide rule 22).
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any

from eval.stancedata import bakerform as bf
from eval.train.baker_cast import cap, first_of
from eval.train.baker_cues import CALLED_BY_NAME
from eval.train.baker_fam_count import KIND_WORD, _count, file_name
from eval.train.baker_fam_time import other_zone, when
from eval.train.baker_kit import (
    Draft,
    Setup,
    any_time,
    chat,
    lang_of_text,
    named_slug,
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
from eval.train.baker_words_ru import agree
from eval.train.names import Person

# The owner calls the partner by name just before the partner's record; {n} is that name.
NAME_LEADS = ("{n} u there?", "hey {n}", "{n} did u get my msg", "thx {n}",
              "{n} hope ur week is going ok", "ok {n} lmk", "{n} quick question", "{n} got a sec?",
              "{n} r u around today", "hi {n}, its me")  # fmt: skip
NAME_LEADS_RU = ("{n}, ты тут?", "привет, {n}", "{n}, набери, когда сможешь", "спасибо, {n}",
                 "{n}, вопрос есть", "{n}, ты где?")  # fmt: skip
# Nicknames a chat uses, all starting A to M like the names they come from.
NICKS = {"Gabi": "gabs", "Imani": "mani", "Kenji": "ken", "Gideon": "gid", "Harriet": "hattie",
         "Ellie": "el", "Aria": "ari", "Greta": "gret", "Celia": "ceci", "Jonah": "jo",
         "Hollis": "holl", "Lina": "li", "Esme": "ez", "Mateo": "matty", "Dina": "dee",
         "Jada": "jay"}  # fmt: skip
NICKS_RU = {"Катя": "Кать", "Дима": "Дим", "Лена": "Лен", "Ира": "Ир", "Даша": "Даш",
            "Гриша": "Гриш", "Боря": "Борь", "Галя": "Галь", "Лёша": "Лёш", "Лёня": "Лёнь",
            "Аня": "Ань", "Женя": "Жень"}  # fmt: skip


def _named(params: dict[str, Any]) -> str:
    """The party a sender assumption names, as its text writes it."""
    if "person_ids" in params:
        return params["person_ids"][0]
    return "/".join(params["account_ids"])


def sender_shown(rng: random.Random, k: int) -> Draft:
    text, core = record_text(rng, k, "bk_sender_shown")
    lang = lang_of_text(text)
    if k % 3 == 0:
        return _shown_elsewhere(rng, text, core, lang)
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
    return Draft("bk_sender_shown", "sender", params, s.scene, s.phone, evs, target, text,
                 rationale)  # fmt: skip


def _shown_elsewhere(rng: random.Random, text: str, core: str, lang: str) -> Draft:
    """The record is on the scene's second phone, sent to its user from the first phone's
    user's own number; the assumption names that user."""
    app = rng.choice(("SMS", "SMS", "WhatsApp", "Signal"))
    first = setup(rng, "phones", app=app, lang=lang)
    if first.other is None:
        raise ValueError("a two-phone scene needs its second phone")
    s = Setup(first.scene, first.other, first.phone.owner, app, first.phone.person, first.phone)
    quoted = quoted_words(rng, text, core)
    utc = any_time(rng, s.phone.zone)
    evs, target = chat(rng, s, text, utc, False, lang, avoid=quoted)
    params: dict[str, Any] = {"quoted_text": quoted, "person_ids": (first.phone.person,)}
    if rng.random() < 0.3:
        params["channels"] = (app,)
    line = render(s.scene, s.phone, evs[target])
    rationale = (f"The record holding the quoted words, on {s.phone.dev}, comes from "
                 f"{line.sender}: its brackets carry {first.phone.person}, the named "
                 "sender.")  # fmt: skip
    return Draft("bk_sender_shown", "sender", params, s.scene, s.phone, evs, target, text,
                 rationale, {"elsewhere": True})  # fmt: skip


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
    return Draft("bk_sender_other", "sender", params, s.scene, s.phone, evs, target, text,
                 rationale, {"named": named})  # fmt: skip


def called_by(rng: random.Random, s: Setup, surname: str) -> str:
    """A line from the owner that calls the partner by a full name; an Instagram chat has no
    phone number to mention."""
    line = rng.choice([x for x in CALLED_BY_NAME if s.app != "Instagram" or "number" not in x])
    line = line.replace("{first}", s.partner.person.name).replace("{Sur}", cap(surname))
    return fill(rng, line)[0]


def by_name(rng: random.Random, s: Setup, surname: str) -> tuple[str, str]:
    """(a line from the owner calling the partner by the first name, a nickname of it or the
    full name, the name it uses); the partner's first name must have a Latin form A to M."""
    p: Person = s.partner.person
    if first_of(p) is None:
        raise ValueError("the partner's name has no Latin form starting A to M")
    if p.lang == "ru":
        n = rng.choice([p.name, NICKS_RU.get(p.name, p.name)])
        return rng.choice(NAME_LEADS_RU).replace("{n}", n), n
    if rng.random() < 0.3:
        line, full = called_by(rng, s, surname), f"{p.name} {cap(surname)}"
        return line, full if full in line else cap(surname)  # "Fenwick? its about the van"
    n = rng.choice([p.name.lower(), NICKS.get(p.name, p.name.lower())])
    return rng.choice(NAME_LEADS).replace("{n}", n), n


def party_unshown(rng: random.Random, k: int) -> Draft:
    """The record fits the assumption except that the person:<surname> it names is on no
    line's brackets: the record comes from, or is with, a third party with no brackets."""
    family = "bk_party_unshown"
    template = ("sender", "record_time", "no_contact", "message_count")[k % 4]
    text, core = record_text(rng, k, family)
    lang = lang_of_text(text)
    s = setup(rng, "third", lang=lang)
    named = k % 3 == 0  # the chat calls the sender by the person's name
    pid = named_slug(rng, s.partner.person) if named else slug(rng)
    quoted = quoted_words(rng, text, core)
    win = None
    if template == "sender":
        utc = any_time(rng, s.phone.zone)
    else:
        tz = other_zone(rng, s.phone.zone) if rng.random() < 0.2 else s.phone.zone
        win, utc = inside(rng, s.phone.zone, tz, fuzzy=0.25 if template == "record_time" else 0.0)
    by_message = template in ("sender", "record_time")
    lead = n = ""
    if named:
        lead, n = by_name(rng, s, surname_of(pid))
    kind = "att" if not by_message and rng.random() < 0.25 else "msg"
    if kind == "att":
        text = core = file_name(rng, k, family, wall(utc, s.phone.zone), rng.random() < 0.5)
    from_me = not by_message and not named and rng.random() < 0.5
    evs, target = chat(rng, s, text, utc, from_me, lang, avoid=quoted if by_message else "",
                       kind=kind, lead=lead)  # fmt: skip
    if named and lang == "ru":  # the name shows the partner's gender, and the lines follow it
        end = s.partner.person.end
        evs = [replace(e, text=agree(e.text, end)) if e.frm == s.you else e for e in evs]
        text, quoted = evs[target].text, agree(quoted, end)
    rec = evs[target]
    line = render(s.scene, s.phone, rec)
    partner = bf.sender_line(s.you.app, s.you.ident)
    unshown = f"no line carries {pid} in brackets, so nothing shown ties {partner} to {pid}"
    if named:
        unshown = f'the chat addresses {partner} as "{n}", but ' + unshown
    names = {pid: f"{first_of(s.partner.person)} {cap(surname_of(pid))}"} if named else {}
    if by_message:
        params: dict[str, Any] = {"quoted_text": quoted, "person_ids": (pid,)}
        d = Draft(family, template, params, s.scene, s.phone, evs, target, text, "", names=names)
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
    d = Draft(family, template, params, s.scene, s.phone, evs, target, line.text, "", names=names)
    if template == "message_count":
        _count(rng, d, win, s, s.phone.dev)
    owner = bf.sender_line(s.me.app, s.me.ident, owner=True, persons=(s.phone.person,))
    at = when(line.local_time, win, utc, s.phone.zone)
    d.rationale = (f"The record is {KIND_WORD[kind]} between {owner} and {partner} at {at}, "
                   f"inside \"{win.raw}\" ({win.tz}); {unshown}.")  # fmt: skip
    return d
