"""Scenes for items in Baker's own wording: phones, accounts, confirmed persons and excerpts.

A scene is one or two phones (dev:item1 to dev:item9), each with a stipulated owner and one to
three own accounts, plus third-party accounts and the links an expert confirmed. Every line is
printed by eval.stancedata.bakerform, and its brackets come from the scene by one rule, applied
to every line: the owner person of every phone in the scene that holds the account (same app and
identifier) as its own, plus the named person an expert confirmed for that account.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from eval.heldout.bk_names import NEUTRAL_IG
from eval.heldout.pools import AREA_CODES
from eval.stancedata import bakerform as bf
from eval.stancedata.chat import fictional_phone

NUMBER_APPS = ("SMS", "WhatsApp", "Signal", "Phone")
CHAT_WEIGHTS = (("Signal", 24), ("Telegram", 22), ("WhatsApp", 20), ("SMS", 18), ("Instagram", 16))
CHAT_WEIGHTS_RU = (("Telegram", 45), ("WhatsApp", 35), ("Signal", 10), ("SMS", 10))


@dataclass(frozen=True)
class Acct:
    app: str
    ident: str

    def on(self, app: str) -> Acct:
        """The same number on another number app (a person's SMS and Phone accounts)."""
        if self.app not in NUMBER_APPS or app not in NUMBER_APPS:
            raise ValueError(f"{self.app} and {app} do not share numbers")
        return Acct(app, self.ident)


@dataclass
class Phone:
    item: int
    tz: str
    own: tuple[Acct, ...]

    @property
    def dev(self) -> str:
        return bf.device_id(self.item)

    @property
    def owner(self) -> str:
        return bf.owner_person(self.item)

    def aid(self, a: Acct) -> str:
        return bf.account_id(self.item, a.app, a.ident)

    def mine(self, app: str) -> Acct:
        for a in self.own:
            if a.app == app:
                return a
        raise KeyError(f"dev:item{self.item} has no own {app} account")


@dataclass
class Scene:
    phones: list[Phone] = field(default_factory=list)
    links: dict[Acct, str] = field(default_factory=dict)  # expert-confirmed: account -> person
    taken: set[str] = field(default_factory=set)
    names: dict[str, str] = field(default_factory=dict)  # person id -> the name the case gives

    def persons(self, a: Acct) -> list[str]:
        out = [p.owner for p in self.phones if a in p.own]
        if a in self.links:
            out.append(self.links[a])
        return out

    def owner_phone(self, a: Acct) -> Phone | None:
        return next((p for p in self.phones if a in p.own), None)

    def msg(self, ph: Phone, a: Acct, utc: datetime, text: str) -> bf.Line:
        return bf.message_line(
            ph.item, a.app, a.ident, utc, ph.tz, text, owner=a in ph.own, persons=self.persons(a)
        )

    def call(
        self, ph: Phone, utc: datetime, direction: str, frm: Acct, to: Acct, dur: int, off: int = 0
    ) -> bf.Line:
        """A call on ph; its line shows the calling number's account, as Baker's context does."""
        if frm.app != "Phone" or to.app != "Phone":
            raise ValueError("a call is between Phone accounts")
        return bf.call_line(ph.item, utc, ph.tz, direction, frm.ident, to.ident, dur,
                            owner=frm in ph.own, persons=self.persons(frm),
                            report_offset_min=off)  # fmt: skip

    def contact(self, ph: Phone, name: str, number: str) -> bf.Line:
        return bf.contact_line(ph.item, name, number)

    # ------------------------------------------------------------ new identifiers

    def number(self, rng: random.Random) -> str:
        for _ in range(500):
            n = fictional_phone(rng, AREA_CODES)
            if n not in self.taken:
                self.taken.add(n)
                return n
        raise RuntimeError("no free number")

    def tg_id(self, rng: random.Random) -> str:
        for _ in range(500):
            ident = f"{rng.choice('89')}{rng.randrange(10**6):06d}"
            if ident not in self.taken:
                self.taken.add(ident)
                return ident
        raise RuntimeError("no free Telegram id")

    def ig(self, rng: random.Random) -> str:
        free = [h for h in NEUTRAL_IG if h not in self.taken]
        ident = rng.choice(free)
        self.taken.add(ident)
        return ident

    def new(self, rng: random.Random, app: str) -> Acct:
        """A fresh account on app (a number, a Telegram id or an Instagram username)."""
        if app in NUMBER_APPS:
            return Acct(app, self.number(rng))
        if app == "Telegram":
            return Acct(app, self.tg_id(rng))
        if app == "Instagram":
            return Acct(app, self.ig(rng))
        raise ValueError(f"unknown app {app!r}")

    def phone(self, rng: random.Random, item: int, tz: str, apps: tuple[str, ...]) -> Phone:
        """A phone whose owner has an account on each app; number apps share one number."""
        number = None
        own = []
        for app in dict.fromkeys(apps):
            if app in NUMBER_APPS:
                number = number or self.number(rng)
                own.append(Acct(app, number))
            else:
                own.append(self.new(rng, app))
        ph = Phone(item, tz, tuple(own))
        self.phones.append(ph)
        return ph


def weighted(rng: random.Random, table: tuple[tuple[str, int], ...]) -> str:
    return rng.choices([n for n, _ in table], weights=[w for _, w in table], k=1)[0]


def chat_app(rng: random.Random, lang: str = "en", numbers_only: bool = False) -> str:
    table = CHAT_WEIGHTS_RU if lang != "en" else CHAT_WEIGHTS
    if numbers_only:
        table = tuple(row for row in table if row[0] in NUMBER_APPS)
    return weighted(rng, table)


def items(rng: random.Random, n: int) -> list[int]:
    """Distinct phone item numbers from 1 to 9."""
    return rng.sample(range(1, 10), n)


def zone(rng: random.Random) -> str:
    return rng.choice(bf.ZONES)


def other_zone(rng: random.Random, tz: str) -> str:
    return rng.choice([z for z in bf.ZONES if z != tz])


# ------------------------------------------------------------------ excerpts


@dataclass
class Excerpt:
    lines: list[bf.Line]
    target: int

    @property
    def record(self) -> bf.Line:
        return self.lines[self.target]


def gaps(rng: random.Random, n: int, lo: int = 20, hi: int = 1500) -> list[timedelta]:
    return [timedelta(seconds=rng.randint(lo, hi)) for _ in range(n)]


def chat(
    rng: random.Random,
    sc: Scene,
    ph: Phone,
    me: Acct,
    other: Acct,
    rec_utc: datetime,
    rec_text: str,
    rec_mine: bool,
    before: list[tuple[bool, str]],
    after: list[tuple[bool, str]],
    spread: tuple[int, int] = (20, 1500),
) -> Excerpt:
    """A one-to-one chat on ph between me (an own account of ph) and other, with the record
    and the context lines (mine?, text) before and after it, in time order."""
    lines: list[bf.Line] = []
    t = rec_utc
    for mine, text in reversed(before):
        t -= gaps(rng, 1, *spread)[0]
        lines.insert(0, sc.msg(ph, me if mine else other, t, text))
    target = len(lines)
    lines.append(sc.msg(ph, me if rec_mine else other, rec_utc, rec_text))
    t = rec_utc
    for mine, text in after:
        t += gaps(rng, 1, *spread)[0]
        lines.append(sc.msg(ph, me if mine else other, t, text))
    return Excerpt(lines, target)


def around(
    rng: random.Random,
    sc: Scene,
    ph: Phone,
    rec: bf.Line,
    before: list[tuple[Acct, str]],
    after: list[tuple[Acct, str]],
    spread: tuple[int, int] = (60, 2400),
) -> Excerpt:
    """A call (or any timed line) among messages from any chats on the same phone."""
    if rec.utc is None:
        raise ValueError("the record needs a time")
    lines: list[bf.Line] = []
    t = rec.utc
    for a, text in reversed(before):
        t -= gaps(rng, 1, *spread)[0]
        lines.insert(0, sc.msg(ph, a, t, text))
    target = len(lines)
    lines.append(rec)
    t = rec.utc
    for a, text in after:
        t += gaps(rng, 1, *spread)[0]
        lines.append(sc.msg(ph, a, t, text))
    return Excerpt(lines, target)


def sides(rng: random.Random, n_before: int, n_after: int, rec_mine: bool) -> list[bool]:
    """Who sends each context line (True: the owner side), in time order. The sides take
    turns outward from the record: the line after it always comes from the other side, the
    line before it usually does, so both sides are on screen."""
    other = not rec_mine
    near_before = other if rng.random() < 0.65 else rec_mine
    near_after = other
    before = [near_before if (n_before - 1 - i) % 2 == 0 else not near_before
              for i in range(n_before)]  # fmt: skip
    after = [near_after if i % 2 == 0 else not near_after for i in range(n_after)]
    marks = before + after
    if marks and all(m == rec_mine for m in marks):
        marks[n_before - 1 if n_before else 0] = other
    return marks


def split_counts(rng: random.Random, lo: int = 1, hi: int = 5) -> tuple[int, int]:
    """How many context lines go before and after the record: lo to hi in all, 3 at most on
    either side."""
    total = rng.randint(lo, hi)
    before = rng.randint(max(0, total - 3), min(3, total))
    return before, total - before
