"""Scenes the family writers share: a one-to-one chat on a phone, a call between two named
parties, and the parameters that name a party the way the scene's lines show it."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_common import RU_SITS, SITS, chat_excerpt, own_apps
from eval.heldout.bk_scene import Acct, Excerpt, Phone, Scene, chat_app, items, zone
from eval.heldout.bk_schedule import BkSlot
from eval.stancedata import bakerform as bf


def scene_lang(s: BkSlot) -> str:
    """The language that picks a chat app: a Russian or mixed record sits in a Russian chat."""
    return "en" if s.lang == "en" else "ru"


def any_sit(rng: random.Random, s: BkSlot) -> str:
    """The slot's situation, or one for its language when its wording named none."""
    return s.sit or rng.choice(SITS if s.lang == "en" else RU_SITS)


def link(sc: Scene, a: Acct, slug: str) -> str:
    """Record an expert-confirmed link from account a to person:<slug>; its lines then carry it."""
    person = bf.named_person(slug)
    sc.links[a] = person
    return person


@dataclass
class Pair:
    """A one-to-one chat on phone p between its owner's account me and the account other; q is
    the second phone when other is that phone's owner's own account."""

    sc: Scene
    p: Phone
    me: Acct
    other: Acct
    q: Phone | None = None
    linked: str = ""  # the person id an expert confirmed for other, if any

    def sender(self, mine: bool) -> Acct:
        return self.me if mine else self.other

    def chat(
        self,
        rng: random.Random,
        s: BkSlot,
        utc: datetime,
        text: str,
        mine: bool,
        **kw: Any,
    ) -> Excerpt:
        sit = kw.pop("sit", "") or any_sit(rng, s)
        lang = kw.pop("lang", s.lang)
        return chat_excerpt(rng, self.sc, self.p, self.me, self.other, utc, text, mine, sit,
                            lang, **kw)  # fmt: skip


def pair(
    rng: random.Random,
    s: BkSlot,
    cross: bool = False,
    linked: bool = False,
    numbers_only: bool = False,
    app: str | None = None,
) -> Pair:
    """A chat on a fresh phone between its owner and a third party, or (cross) the owner of a
    second phone in the scene; `linked` confirms the third party as person:<s.person>."""
    sc = Scene()
    app = app or chat_app(rng, scene_lang(s), numbers_only)
    n1, n2 = items(rng, 2)
    p = sc.phone(rng, n1, zone(rng), own_apps(rng, app))
    if cross:
        q = sc.phone(rng, n2, zone(rng), own_apps(rng, app))
        return Pair(sc, p, p.mine(app), q.mine(app), q)
    pr = Pair(sc, p, p.mine(app), sc.new(rng, app))
    if linked:
        pr.linked = link(sc, pr.other, s.person)
    return pr


def acct_ids(pr: Pair, a: Acct, rng: random.Random, both: bool = False) -> list[str]:
    """Account ids for a: as the record's phone lists it and, with `both`, as the phone that
    holds it as its own lists it too (rule 25: the same app and identifier is one account)."""
    ids = [pr.p.aid(a)]
    holder = pr.sc.owner_phone(a)
    if both and holder is not None and holder is not pr.p:
        ids.append(holder.aid(a))
        rng.shuffle(ids)
    return ids


# ------------------------------------------------------------------ calls

CALL_FORMS = ("out_person", "in_linked", "cross_out", "cross_in")


@dataclass
class Call:
    """A call on phone p from frm to to. The call line shows frm, whose brackets carry
    `person`; the other side is named by its Phone account id `acct_id`, its number being in
    the call text. The assumption never names both sides by person id."""

    sc: Scene
    p: Phone
    frm: Acct
    to: Acct
    direction: str
    person: str
    acct_id: str
    q: Phone | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def params(self) -> dict[str, Any]:
        return {"person_ids": [self.person], "account_ids": [self.acct_id]}

    def line(self, rng: random.Random, utc: datetime, dur: int) -> bf.Line:
        off = bt.report_offset(rng, utc, self.p.tz)
        return self.sc.call(self.p, utc, self.direction, self.frm, self.to, dur, off)

    def excerpt(self, rng: random.Random, utc: datetime, dur: int, where: str = "both") -> Excerpt:
        return pk.call_excerpt(rng, self.sc, self.p, self.line(rng, utc, dur), where=where)

    def said(self) -> str:
        """The call as a rationale names it."""
        return f"the {self.direction} call from {self.frm.ident} to {self.to.ident}"


def call_scene(rng: random.Random, s: BkSlot, form: str) -> Call:
    """A call between the two parties a call form names (CALL_FORMS)."""
    sc = Scene()
    lang = scene_lang(s)
    n1, n2 = items(rng, 2)
    p = pk.call_phone(rng, sc, n1, zone(rng), lang)
    mine = p.mine("Phone")
    if form.startswith("cross"):
        q = pk.call_phone(rng, sc, n2, zone(rng), lang)
        them = q.mine("Phone")
        if form == "cross_out":
            aid = rng.choice((p, q)).aid(them)
            return Call(sc, p, mine, them, "outgoing", p.owner, aid, q)
        return Call(sc, p, them, mine, "incoming", q.owner, p.aid(mine), q)
    them = sc.new(rng, "Phone")
    if form == "out_person":
        return Call(sc, p, mine, them, "outgoing", p.owner, p.aid(them))
    if form == "in_linked":
        person = link(sc, them, s.person)
        return Call(sc, p, them, mine, "incoming", person, p.aid(mine))
    raise ValueError(f"unknown call form {form!r}")


def shown_as(sc: Scene, ph: Phone, a: Acct) -> str:
    """The sender text a line on phone ph prints for account a."""
    return bf.sender_line(a.app, a.ident, owner=a in ph.own, persons=sc.persons(a))


def owner_style(rng: random.Random, pr: Pair) -> dict[str, list[str]]:
    """The owner as one party: the stipulated person, or the owner's account on this chat."""
    if rng.random() < 0.5:
        return {"person_ids": [pr.p.owner]}
    return {"account_ids": [pr.p.aid(pr.me)]}


def merge(*parts: dict[str, list[str]]) -> dict[str, list[str]]:
    """Party parameters joined; person ids add up, account ids form one party."""
    out: dict[str, list[str]] = {}
    for part in parts:
        for key, vals in part.items():
            out.setdefault(key, []).extend(vals)
    if sum("account_ids" in part for part in parts) > 1:
        raise ValueError("two parties named by account ids read as one party")
    return out


def channel(rng: random.Random, app: str, share: float = 0.3) -> dict[str, list[str]]:
    """Now and then the line's own app as the assumption's channel."""
    return {"channels": [app]} if rng.random() < share else {}


def inside_time(rng: random.Random, win: bt.Win, phone_tz: str) -> datetime:
    return bt.place_inside(rng, win, phone_tz)


COUNTS = (3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40)


def count_params(rng: random.Random, visible: int, op: str | None = None) -> dict[str, object]:
    """A stated count above the number of chat lines on screen, so what is shown can neither
    reach nor pass it."""
    n = rng.choice(COUNTS)
    n = n if n > visible else visible + rng.randint(2, 9)
    return {"expected_count": n, "count_op": op or rng.choice(("eq", "ge", "le"))}


def extra_phone(rng: random.Random, sc: Scene, lang: str = "en") -> Phone:
    """Another phone in the scene, with an item number no phone in it has."""
    used = {ph.item for ph in sc.phones}
    item = rng.choice([n for n in range(1, 10) if n not in used])
    return sc.phone(rng, item, zone(rng), own_apps(rng, chat_app(rng, lang)))


def two_parties(
    rng: random.Random, s: BkSlot, style: str | None = None
) -> tuple[Pair, dict[str, list[str]]]:
    """A chat and the two parties an assumption names for it: the owner and the third party
    ("owner_acct"), a linked third party and the owner ("linked"), or the owners of two
    phones ("cross")."""
    style = style or rng.choice(("owner_acct", "linked", "cross"))
    if style == "cross":
        pr = pair(rng, s, cross=True)
        persons = [pr.p.owner, pr.q.owner if pr.q else ""]
        rng.shuffle(persons)
        return pr, {"person_ids": persons}
    if style == "linked":
        pr = pair(rng, s, linked=True)
        return pr, merge({"person_ids": [pr.linked]}, owner_style(rng, pr))
    pr = pair(rng, s)
    return pr, {"person_ids": [pr.p.owner], "account_ids": [pr.p.aid(pr.other)]}
