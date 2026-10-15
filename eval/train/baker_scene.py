"""Scenes for the Baker-wording items: phones, their stipulated owners and accounts, third
parties, expert-confirmed links, and the excerpt lines Baker's adapter prints for them.

Brackets come from the scene alone (guide rule 26): an account carries person:dev:itemN:owner
when its app and identifier are one of phone N's own accounts, on any phone, since Baker matches
accounts across phones; and person:<surname> when the scene records an expert-confirmed link.
Items show those people by name (eval/train/baker_cast.py); phone users and linked people are
cast with first names that have a Latin form starting A to M.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from eval.stancedata import bakerform as bf
from eval.stancedata.chat import fictional_phone
from eval.train.baker_cast import first_of
from eval.train.names import AREA_CODES, PEOPLE_EN, PEOPLE_RU, Person, telegram_id, username

MSG_APPS = ("SMS", "SMS", "SMS", "WhatsApp", "Telegram", "Signal", "Instagram")


@dataclass(frozen=True)
class Acc:
    app: str
    ident: str


@dataclass(frozen=True)
class Who:
    """A person in a scene: who they are in chat text, and the identifiers they use."""

    person: Person
    number: str
    tg: str
    ig: str

    def acc(self, app: str) -> Acc:
        if app == "Telegram":
            return Acc(app, self.tg)
        if app == "Instagram":
            return Acc(app, self.ig)
        return Acc(app, self.number)


@dataclass(frozen=True)
class Phone:
    item: int
    zone: str
    owner: Who
    own: tuple[Acc, ...]

    @property
    def dev(self) -> str:
        return bf.device_id(self.item)

    @property
    def person(self) -> str:
        return bf.owner_person(self.item)

    def aid(self, a: Acc) -> str:
        return bf.account_id(self.item, a.app, a.ident)


@dataclass(frozen=True)
class Scene:
    phones: tuple[Phone, ...]
    links: tuple[tuple[Acc, str], ...] = ()  # expert-confirmed: account -> person:<surname>
    people: tuple[tuple[str, Person], ...] = ()  # a linked person id -> the chat person it is

    @property
    def owners(self) -> dict[str, Person]:
        return {p.person: p.owner.person for p in self.phones}

    def persons(self, a: Acc) -> tuple[str, ...]:
        """The person ids Baker holds as confirmed for an account, as its brackets show them."""
        out = {p.person for p in self.phones if a in p.own}
        out |= {pid for acc, pid in self.links if acc == a}
        return tuple(sorted(out))

    def speaker(self, a: Acc) -> Person | None:
        """Whom the item shows by name for an account: a phone's user or a linked person."""
        for p in self.phones:
            if a in p.own:
                return p.owner.person
        people = dict(self.people)
        return next((people.get(pid) for acc, pid in self.links if acc == a), None)

    def holders(self, pid: str) -> frozenset[Acc]:
        """Every account Baker ties to a person id: a phone's own accounts, or linked ones."""
        own = {a for p in self.phones if p.person == pid for a in p.own}
        return frozenset(own | {acc for acc, x in self.links if x == pid})


class Cast:
    """Draws people for one scene, never two with the same first name or identifier."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.taken: set[str] = set()

    def who(self, lang: str = "en", named: bool = False) -> Who:
        """A new person; `named` ones (phone users, linked people) get a full name in items, so
        their first name has a Latin form starting A to M."""
        rng = self.rng
        pool = [p for p in (PEOPLE_RU if lang == "ru" else PEOPLE_EN)
                if p.name not in self.taken and (first_of(p) or not named)]  # fmt: skip
        person = rng.choice(pool)
        self.taken.add(person.name)
        number = self._new(lambda: fictional_phone(rng, AREA_CODES))
        tg = self._new(lambda: telegram_id(rng))
        return Who(person, number, tg, self._new(lambda: username(rng, person)))

    def number(self) -> str:
        """A phone number no one in the scene has."""
        return self._new(lambda: fictional_phone(self.rng, AREA_CODES))

    def _new(self, draw: Callable[[], str]) -> str:
        for _ in range(500):
            x = draw()
            if x not in self.taken:
                self.taken.add(x)
                return x
        raise RuntimeError("identifier pool exhausted")

    def phone(self, item: int, apps: tuple[str, ...], lang: str = "en") -> Phone:
        """Phone item<n> in a random zone; its owner's own accounts are `apps` plus the
        phone's number (Phone), sometimes SMS: one to three in all."""
        owner = self.who(lang, named=True)
        own = list(dict.fromkeys((*apps, "Phone")))
        if len(own) < 3 and "SMS" not in own and self.rng.random() < 0.6:
            own.append("SMS")
        return Phone(item, self.rng.choice(bf.ZONES), owner, tuple(owner.acc(a) for a in own[:3]))


def items(rng: random.Random, n: int) -> list[int]:
    """Phone item numbers from 1 to 9."""
    return rng.sample(range(1, 10), n)


@dataclass(frozen=True)
class Ev:
    """One record or context line before rendering: a message, an attachment (its file name
    as the text), a call, or a contact row (text = the saved name, frm = the number)."""

    utc: datetime | None
    frm: Acc
    text: str = ""
    kind: str = "msg"
    to: Acc | None = None  # a message's chat partner, a call's other number
    direction: str = ""
    dur: int = 0
    offset: int = 0  # minutes: the offset the report printed the call's time in

    def between(self, a: frozenset[Acc], b: frozenset[Acc]) -> bool:
        ends = {self.frm, self.to}
        return bool(ends & a) and bool(ends & b) and self.to is not None


def render(scene: Scene, phone: Phone, ev: Ev) -> bf.Line:
    """The line Baker's adapter prints for this event on this phone; a message lists its chat
    partner as its recipient, as a report does."""
    if ev.kind == "contact":
        return bf.contact_line(phone.item, ev.text or None, ev.frm.ident)
    if ev.utc is None:
        raise ValueError("only a contact row has no time")
    own, persons = ev.frm in phone.own, scene.persons(ev.frm)
    if ev.kind == "call":
        if ev.to is None:
            raise ValueError("a call needs its other number")
        return bf.call_line(phone.item, ev.utc, phone.zone, ev.direction, ev.frm.ident,
                            ev.to.ident, ev.dur, owner=own, persons=persons,
                            report_offset_min=ev.offset)  # fmt: skip
    to = () if ev.to is None else (sender(scene, phone, ev.to),)
    return bf.message_line(phone.item, ev.frm.app, ev.frm.ident, ev.utc, phone.zone, ev.text,
                           owner=own, persons=persons, recipients=to)  # fmt: skip


def sender(scene: Scene, phone: Phone, a: Acc) -> str:
    """An account as a line on this phone prints it."""
    return bf.sender_line(a.app, a.ident, owner=a in phone.own, persons=scene.persons(a))


def thread(
    rng: random.Random, rec: Ev, before: list[str], after: list[str], spread_s: int = 900
) -> tuple[list[Ev], int]:
    """The record's own chat: `before` and `after` lines around it, each from the record's
    sender or its partner, at least one from the partner; gaps of up to `spread_s` seconds."""
    if rec.utc is None or rec.to is None:
        raise ValueError("a message record needs a time and a chat partner")
    me, you = rec.frm, rec.to
    out: list[Ev] = []
    for side, texts in ((-1, before), (1, after)):
        t, last = rec.utc, me
        for text in texts:
            t = t + side * timedelta(seconds=rng.randint(25, spread_s))
            back = rng.random() < (0.8 if last == me else 0.3)
            last = you if back else me
            out.append(Ev(t, last, text, to=me if last == you else you))
    if out and all(e.frm == me for e in out):
        i = min(range(len(out)), key=lambda j: abs(_t(out[j]) - rec.utc))
        out[i] = Ev(out[i].utc, you, out[i].text, to=me)
    out.append(rec)
    out.sort(key=_t)
    return out, out.index(rec)


def _t(e: Ev) -> datetime:
    if e.utc is None:
        raise ValueError("a timed line has no time")
    return e.utc


def around(
    rng: random.Random,
    rec: Ev,
    chats: list[tuple[Acc, Acc]],
    before: list[str],
    after: list[str],
    spread_s: int = 2400,
) -> tuple[list[Ev], int]:
    """A call (or any record) among messages from the phone's chats near its time; each chat
    is (the owner's account, the partner's), and either side may send."""
    if rec.utc is None:
        raise ValueError("the record needs a time")
    out = [rec]
    for side, texts in ((-1, before), (1, after)):
        t = rec.utc
        for text in texts:
            t = t + side * timedelta(seconds=rng.randint(60, spread_s))
            a, b = rng.choice(chats)
            frm, to = (a, b) if rng.random() < 0.5 else (b, a)
            out.append(Ev(t, frm, text, to=to))
    out.sort(key=_t)
    return out, out.index(rec)
