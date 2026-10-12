"""Chats: accounts as the phone shows them, local clocks, message timing and item assembly."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.contracts import AssumptionKind
from eval.heldout import GENERATOR, SOURCE
from eval.heldout.pools import (
    AREA_CODES,
    CYRILLIC_NAMES,
    FILLER_EN,
    FILLER_RU,
    INSTAGRAM_USERNAMES,
    LATIN_NAMES,
    NEUTRAL_EN,
    NEUTRAL_MIXED,
    NEUTRAL_RU,
    ROLE_LABELS_BY_SIT,
    RU_ZONES,
    TELEGRAM_HANDLES,
    US_ZONES,
)
from eval.heldout.text import casual, typo
from eval.stancedata.chat import (
    Account,
    Msg,
    NonexistentLocalTime,
    at_local,
    build_item,
    fictional_phone,
)
from eval.stancedata.model import GenItem

FIRST_DAY = date(2024, 9, 1)
LAST_DAY = date(2025, 12, 20)
SPRING_CHANGE = date(2025, 3, 9)
FALL_CHANGE = date(2025, 11, 2)

APP_WEIGHTS = (("SMS", 30), ("WhatsApp", 25), ("Telegram", 20), ("Signal", 10), ("Instagram", 15))
APP_WEIGHTS_RU = (("SMS", 15), ("WhatsApp", 30), ("Telegram", 40), ("Signal", 5), ("Instagram", 10))


def weighted(rng: random.Random, table: tuple[tuple[str, int], ...]) -> str:
    names = [n for n, _ in table]
    weights = [w for _, w in table]
    return rng.choices(names, weights=weights, k=1)[0]


@dataclass
class Chat:
    """One chat on one phone: who is in it, which app, which clock."""

    tz: str
    app: str
    sit: str
    lang: str  # en, ru or mixed: the language of the record and most of the chatter
    owner: Account
    contacts: list[Account]
    genders: dict[str, str] = field(default_factory=dict)  # label -> m/f for Russian verbs

    @property
    def contact(self) -> Account:
        return self.contacts[0]

    def filler(
        self, rng: random.Random, neutral: bool = False, used: set[str] | None = None
    ) -> str:
        """One harmless line about the chat's own situation (one in five is small talk).

        `used` holds the lines already on screen; a line is drawn from the rest of the pool
        and added to it, so one chat never shows the same small talk twice."""
        if self.lang == "ru":
            about, small = FILLER_RU[self.sit], NEUTRAL_RU
        elif self.lang == "mixed":
            about, small = FILLER_EN[self.sit], NEUTRAL_EN + NEUTRAL_MIXED * 3
        else:
            about, small = FILLER_EN[self.sit], NEUTRAL_EN
        pool = small if neutral or rng.random() < 0.2 else about
        if used is not None:
            pool = [t for t in pool if t not in used] or pool
        base = rng.choice(pool)
        if used is not None:
            used.add(base)
        return typo(rng, casual(rng, base))

    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


def telegram_id(rng: random.Random) -> str:
    return f"{rng.choice('89')}{rng.randrange(10**6):06d}"


def _label(rng: random.Random, app: str, lang: str, taken: set[str], sit: str) -> str | None:
    for _ in range(50):
        if app == "Telegram":
            label = (
                rng.choice(TELEGRAM_HANDLES)
                if lang == "en" or rng.random() < 0.5
                else (rng.choice(CYRILLIC_NAMES)[0])
            )
        elif app == "Instagram":
            label = rng.choice(LATIN_NAMES) if rng.random() < 0.6 else None
        elif lang == "en":
            r = rng.random()
            label = (
                None
                if r < 0.18
                else rng.choice(ROLE_LABELS_BY_SIT[sit])
                if r < 0.4
                else (rng.choice(LATIN_NAMES))
            )
        else:
            label = None if rng.random() < 0.15 else rng.choice(CYRILLIC_NAMES)[0]
        if label is None or label not in taken:
            return label
    raise RuntimeError("could not pick a label")


def _identifier(rng: random.Random, app: str, taken: set[str]) -> str:
    for _ in range(50):
        if app == "Telegram":
            ident = telegram_id(rng)
        elif app == "Instagram":
            ident = rng.choice(INSTAGRAM_USERNAMES)
        else:
            ident = fictional_phone(rng, AREA_CODES)
        if ident not in taken:
            return ident
    raise RuntimeError("could not pick an identifier")


def make_chat(rng: random.Random, lang: str, sit: str, members: int = 1) -> Chat:
    """A chat between the owner and `members` other accounts, with labels by app and language."""
    record_lang = "ru" if lang in ("ru", "mixed") else "en"
    tz = weighted(rng, RU_ZONES if record_lang == "ru" else US_ZONES)
    app = weighted(rng, APP_WEIGHTS_RU if record_lang == "ru" else APP_WEIGHTS)
    taken_ids: set[str] = set()
    taken_labels: set[str] = set()
    owner = Account(app, _identifier(rng, app, taken_ids), owner=True)
    taken_ids.add(owner.identifier)
    contacts: list[Account] = []
    genders: dict[str, str] = {}
    for _ in range(members):
        ident = _identifier(rng, app, taken_ids)
        taken_ids.add(ident)
        label = _label(rng, app, record_lang, taken_labels, sit)
        if label:
            taken_labels.add(label)
            for name, gender in CYRILLIC_NAMES:
                if name == label:
                    genders[label] = gender
        contacts.append(Account(app, ident, label))
    return Chat(tz=tz, app=app, sit=sit, lang=lang, owner=owner, contacts=contacts, genders=genders)


# ------------------------------------------------------------------------------------ clocks


def random_day(rng: random.Random, first: date = FIRST_DAY, last: date = LAST_DAY) -> date:
    return first + timedelta(days=rng.randrange((last - first).days + 1))


def random_local(
    rng: random.Random, tz: str, day: date | None = None, hours: tuple[int, int] = (7, 22)
) -> datetime:
    """A UTC instant whose local clock in tz falls on `day` within `hours` (inclusive hours)."""
    day = day or random_day(rng)
    lo, hi = hours
    hh = rng.randint(lo, hi)
    mm, ss = rng.randrange(60), rng.randrange(60)
    for bump in range(4):
        try:
            return at_local(day, (hh + bump) % 24, mm, ss, tz=tz)
        except NonexistentLocalTime:
            continue
    raise RuntimeError(f"no valid local time near {day} {hh}:{mm} in {tz}")


def local(utc: datetime, tz: str) -> datetime:
    return utc.astimezone(ZoneInfo(tz))


GAP_KINDS = {
    "quick": (8, 240),  # seconds
    "normal": (60, 2400),
    "slow": (3600, 6 * 3600),
    "days": (20 * 3600, 3 * 24 * 3600),
}


def gap(rng: random.Random, kind: str | None = None) -> timedelta:
    if kind is None:
        kind = rng.choices(("quick", "normal", "slow", "days"), weights=(45, 35, 14, 6))[0]
    lo, hi = GAP_KINDS[kind]
    return timedelta(seconds=rng.randint(lo, hi))


def timeline(
    rng: random.Random,
    count: int,
    target: int,
    target_utc: datetime,
    kinds: dict[int, str] | None = None,
) -> list[datetime]:
    """UTC instants for `count` lines with line `target` at target_utc.

    kinds maps a gap index i (between line i and i+1) to a gap kind; others are mixed.
    """
    kinds = kinds or {}
    times = [target_utc] * count
    for i in range(target - 1, -1, -1):
        times[i] = times[i + 1] - gap(rng, kinds.get(i))
    for i in range(target + 1, count):
        times[i] = times[i - 1] + gap(rng, kinds.get(i - 1))
    return times


# ---------------------------------------------------------------------------------- assembly


@dataclass
class Draft:
    """What a family writer returns; `finish` turns it into a checked GenItem."""

    chat: Chat
    lines: list[tuple[Account, str]]
    target: int
    assumption: str
    quote: str
    rationale: str
    kind: AssumptionKind
    times: list[datetime]

    def record_local(self) -> datetime:
        return local(self.times[self.target], self.chat.tz)


def finish(draft: Draft, probe_id: str, family_id: str, lang: str) -> GenItem:
    msgs = [
        Msg(acct, utc, text) for (acct, text), utc in zip(draft.lines, draft.times, strict=True)
    ]
    return build_item(
        probe_id=probe_id,
        family_id=family_id,
        source=SOURCE,
        generator=GENERATOR,
        lang=lang,
        kind=draft.kind,
        assumption=draft.assumption,
        msgs=msgs,
        target=draft.target,
        quote=draft.quote,
        rationale=draft.rationale,
        tz=draft.chat.tz,
    )
