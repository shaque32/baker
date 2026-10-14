"""bk_unrelated: a record that does not bear on the assumption, over Baker's twelve templates.

The record is a message, an attachment, a call or a contact row between the phone's owner and
a partner. The assumption is built around it: the record holds none of its quoted words (no
excerpt line shares a content word with them), is not between its named parties (the second
party is an account no line shows), mentions none of its handles, is not a row with its contact
name or number, and is not from its named account; a role or event names a person no line
carries in brackets. Only a sender or time assumption may name the record's own sender.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from eval.stancedata import bakerform as bf
from eval.train.baker_cues import VAGUE
from eval.train.baker_days import DAYS_EN, PLANS, PLANS_RU, V_RU
from eval.train.baker_fam_contact import FORMS, PEOPLE, _name, saved_name
from eval.train.baker_fam_count import file_name
from eval.train.baker_fam_people import _handle
from eval.train.baker_kit import (
    ORDINARY,
    Draft,
    Setup,
    any_time,
    chat,
    lang_of,
    lang_of_text,
    pick_kind,
    quoted_words,
    record_text,
    setup,
    slug,
)
from eval.train.baker_parties import RANGES, call_context, call_event, name_account, strangers
from eval.train.baker_scene import MSG_APPS, Acc, Ev, render
from eval.train.baker_text import fill, words
from eval.train.baker_time import wall, win_day, win_on
from eval.train.names import PEOPLE_EN, STEMS

FAMILY = "bk_unrelated"
TEMPLATES = ("sender", "record_time", "message_count", "no_contact", "same_account",
             "contact_entry", "weekday_date", "meaning", "authorship", "person_identity", "role",
             "event")  # fmt: skip
KINDS = ("msg", "msg", "msg", "msg", "msg", "att", "att", "call", "call", "contact")
Draw = Callable[[], tuple[str, str]]


@dataclass
class Ctx:
    k: int
    s: Setup
    evs: list[Ev]
    target: int
    lines: list[bf.Line]
    lang: str  # "en" or "ru": the language quoted words are drawn in

    @property
    def rec(self) -> Ev:
        return self.evs[self.target]

    @property
    def day(self) -> date:
        utc = self.rec.utc or self.evs[0].utc
        if utc is None:
            return date(2025, 6, 2) + timedelta(days=self.k % 400)  # a contact row has no time
        return wall(utc, self.s.phone.zone).date()

    def window(self, rng: random.Random) -> Any:
        """A date window near the record's day; where the record falls does not matter."""
        d = self.day + timedelta(days=rng.choice((0, 0, -3, 2, 9)))
        return win_on(d, self.s.phone.zone, rng.random() < 0.2).tw

    def shows(self, ident: str) -> bool:
        return any(ident in f"{ln.sender} {ln.account_id} {ln.text}" for ln in self.lines)


def _record(rng: random.Random, k: int) -> Ctx:
    """A message or attachment in the owner's chat with the partner, a call between them among
    the phone's other chats, or the partner's contact row."""
    kind = rng.choice(KINDS)
    text, _ = record_text(rng, k, FAMILY)
    lang = lang_of_text(text) if kind == "msg" else "ru" if rng.random() < 0.1 else "en"
    s = setup(rng, pick_kind(rng), lang=lang)
    utc = any_time(rng, s.phone.zone)
    if kind == "contact":
        evs, target = [Ev(None, s.you_phone, _name(rng, k, FAMILY)[0], "contact")], 0
    elif kind == "call":
        call = call_event(rng, s, utc, rng.random() < 0.5, rng.randint(12, 1500))
        evs, target = call_context(rng, s, call, lang, with_partner=False)
    else:
        if kind == "att":
            text = file_name(rng, k, FAMILY, wall(utc, s.phone.zone), rng.random() < 0.5)
        evs, target = chat(rng, s, text, utc, rng.random() < 0.5, lang, kind=kind)
    lines = [render(s.scene, s.phone, e) for e in evs]
    return Ctx(k, s, evs, target, lines, "ru" if lang_of(lines, target) == "ru" else "en")


def _apart(rng: random.Random, c: Ctx, draw: Draw) -> str:
    """Quoted words that share no content word with any excerpt line."""
    seen = set().union(*(words(ln.text) for ln in c.lines))
    for _ in range(300):
        quoted = quoted_words(rng, *draw())
        if words(quoted) and not words(quoted) & seen:
            return quoted
    raise RuntimeError("no quoted words apart from the excerpt")


def _stranger(rng: random.Random, c: Ctx, app: str) -> str:
    """The account id, on the record's phone, of someone no line shows."""
    for _ in range(50):
        who = strangers(rng, c.s, 1, c.lang)[0]
        acc = who.acc(app)
        if not c.shows(acc.ident):
            return c.s.phone.aid(acc)
    raise RuntimeError("no stranger apart from the excerpt")


def _unbracketed(rng: random.Random, c: Ctx) -> str:
    """A person id no line carries: a named surname with no link, or another phone's owner."""
    if rng.random() < 0.3:
        used = {p.item for p in c.s.scene.phones}
        return bf.owner_person(rng.choice([n for n in range(1, 10) if n not in used]))
    for _ in range(50):
        pid = slug(rng)
        if not c.shows(pid):
            return pid
    raise RuntimeError("no free person id")


def _pair(rng: random.Random, c: Ctx) -> dict[str, Any]:
    """Two parties the record is not between: one end of its chat and an unseen account."""
    pids = [c.s.phone.person] + ([c.s.you_pid] if c.s.you_pid else [])
    return {"person_ids": (rng.choice(pids),), "account_ids": (_stranger(rng, c, c.s.app),)}


def _plan(rng: random.Random, lang: str) -> tuple[str, str, int]:
    wd = rng.randrange(7)
    if lang == "ru":
        line = rng.choice(PLANS_RU).replace("{na}", "{v}").replace("{v}", V_RU[wd])
    else:
        line = rng.choice(PLANS).replace("{wd}", DAYS_EN[wd])
    return (*fill(rng, line), wd)


def _quoted(rng: random.Random, c: Ctx, template: str) -> dict[str, Any]:
    """sender, record_time (message), meaning, weekday_date: words the excerpt does not hold."""
    if template == "weekday_date":
        days: list[int] = []

        def draw() -> tuple[str, str]:
            text, core, wd = _plan(rng, c.lang)
            days.append(wd)
            return text, core

        quoted = _apart(rng, c, draw)
        gap = (days[-1] - c.day.weekday()) % 7 or 7
        window = win_day(c.day + timedelta(days=gap), c.s.phone.zone)
        return {"quoted_text": quoted, "window": window.tw}
    pool = ORDINARY[c.lang]
    if template == "meaning" and c.lang == "en" and rng.random() < 0.5:
        pool = VAGUE
    params: dict[str, Any] = {"quoted_text": _apart(rng, c, lambda: fill(rng, rng.choice(pool)))}
    own = c.rec.frm if c.rec.kind in ("msg", "att") else c.s.me
    if template == "sender" or (template == "record_time" and rng.random() < 0.5):
        params |= name_account(rng, c.s, own)
    if template == "record_time":
        params["window"] = c.window(rng)
    return params


def _handles(rng: random.Random, c: Ctx) -> dict[str, Any]:
    app = rng.choice(("Telegram", "Instagram"))
    stems = [x for x in (*(p.name.lower() for p in PEOPLE_EN), *STEMS) if not c.shows(x)]
    out: list[str] = []
    while len(out) < 2:
        h = _handle(rng, app, rng.choice(stems))
        if h not in out and not c.shows(h[1:]):
            out.append(h)
    return {"channels": (app,), "handles": tuple(out)}


def _contact(rng: random.Random, c: Ctx) -> dict[str, Any]:
    seen = set().union(*(words(ln.text) for ln in c.lines))
    for _ in range(100):
        name = saved_name(rng, rng.choice(PEOPLE[c.lang]), rng.choice(FORMS[c.lang]))
        acc = Acc("Phone", strangers(rng, c.s, 1, c.lang)[0].number)
        if not words(name) & seen and not c.shows(acc.ident):
            return {"device_ids": (c.s.phone.dev,), "quoted_text": name,
                    "account_ids": (c.s.phone.aid(acc),)}  # fmt: skip
    raise RuntimeError("no contact apart from the excerpt")


def unrelated(rng: random.Random, k: int) -> Draft:
    template = TEMPLATES[k % 12]
    c = _record(rng, k)
    why = "holds none of the quoted words"
    if template == "record_time" and (k // 12) % 2 == 1:
        params = {"person_ids": (c.s.phone.person,),
                  "account_ids": (_stranger(rng, c, "Phone"),), "channels": ("call",),
                  "window": c.window(rng)}  # fmt: skip
        if rng.random() < 0.3:
            params["duration_s"] = rng.choice(RANGES)
        why = "is not a call between the named parties"
    elif template in ("sender", "record_time", "meaning", "weekday_date"):
        params = _quoted(rng, c, template)
    elif template in ("message_count", "no_contact"):
        params = _pair(rng, c) | {"window": c.window(rng)}
        if template == "message_count":
            params |= {"device_ids": (c.s.phone.dev,), "count_op": rng.choice(("eq", "ge", "le")),
                       "expected_count": rng.randint(2, 60)}  # fmt: skip
        elif rng.random() < 0.4:
            params["device_ids"] = (c.s.phone.dev,)
        why = "is not between the named parties"
    elif template == "same_account":
        params, why = _handles(rng, c), "mentions neither handle"
    elif template == "contact_entry":
        params, why = _contact(rng, c), "is not a contact row with that name or that number"
    elif template in ("authorship", "person_identity"):
        app = rng.choice([a for a in MSG_APPS if a != c.s.app] or [c.s.app])
        params = {"person_ids": (_unbracketed(rng, c),), "account_ids": (_stranger(rng, c, app),)}
        why = "is not from the named account"
    else:  # role, event
        params = {"person_ids": (_unbracketed(rng, c),)}
        if template == "event" and rng.random() < 0.5:
            params["window"] = c.window(rng)
        why = "neither comes from nor goes to an account bracketed with a named person"
    rationale = f"The record {why}, so it does not bear on the assumption."
    return Draft(FAMILY, template, params, c.s.scene, c.s.phone, c.evs, c.target,
                 c.lines[c.target].text, rationale)  # fmt: skip
