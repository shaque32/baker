"""Chat assembly: zones, dates, message timing and the lines around the record.

A Chat is the excerpt as the phone shows it: accounts, UTC-ordered messages and the index of the
record. Writers read its local date and clock from the zone, never from UTC.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from eval.stancedata.chat import Msg, NonexistentLocalTime, at_local, local_dt, local_str
from eval.train import filler, fillers_en, fillers_ru
from eval.train.names import Party

TZS_US = ("America/New_York", "America/New_York", "America/New_York", "America/New_York",
          "America/Chicago", "America/Los_Angeles")  # fmt: skip
MOSCOW = "Europe/Moscow"
# Records fall in 2024-01-03 .. 2026-09-27; context lines sit at most two days away, so every
# line falls in 2024-01-01 .. 2026-09-30 and nothing is dated after the day the set was built.
FIRST_DAY = date(2024, 1, 3)
LAST_DAY = date(2026, 9, 27)
SPRING_DST = date(2026, 3, 8)
FALL_DST = date(2025, 11, 2)

Line = tuple[str, str]  # (who, text): "o" owner, "c" contact, "c2" second contact


def pick_tz(rng: random.Random, lang: str) -> str:
    if lang == "ru" and rng.random() < 0.55:
        return MOSCOW
    return rng.choice(TZS_US)


def pick_day(rng: random.Random) -> date:
    return FIRST_DAY + timedelta(days=rng.randrange((LAST_DAY - FIRST_DAY).days + 1))


def record_time(
    rng: random.Random, day: date, tz: str, hours: tuple[int, int] = (7, 23), fold: int = 0
) -> datetime:
    """The UTC instant of a record whose local clock falls in `hours` (inclusive) on `day`."""
    while True:
        hh = rng.randint(*hours)
        try:
            return at_local(day, hh, rng.randrange(60), rng.randrange(60), tz, fold)
        except NonexistentLocalTime:
            continue


def clock12(local: datetime) -> str:
    """'8:12 a.m.' from a local datetime."""
    h = local.hour % 12 or 12
    return f"{h}:{local.minute:02d} {'a.m.' if local.hour < 12 else 'p.m.'}"


def hour12(h: int) -> str:
    """'9 a.m.', 'noon', '10 p.m.' for a whole hour."""
    if h == 0:
        return "midnight"
    if h == 12:
        return "noon"
    return f"{h % 12} {'a.m.' if h < 12 else 'p.m.'}"


def month_year(d: date) -> str:
    return f"{d.strftime('%B')} {d.year}"


def _gap(rng: random.Random) -> timedelta:
    r = rng.random()
    if r < 0.45:
        s = rng.randint(15, 240)
    elif r < 0.75:
        s = rng.randint(240, 3600)
    elif r < 0.93:
        s = rng.randint(3600, 6 * 3600)
    else:
        s = rng.randint(6 * 3600, 2 * 86400)
    return timedelta(seconds=s)


def spread(rng: random.Random, when: datetime, n_before: int, n_after: int) -> list[datetime]:
    """UTC times for n_before lines, the record at `when`, then n_after lines."""
    before: list[datetime] = []
    t = when
    for _ in range(n_before):
        t = t - _gap(rng)
        before.append(t)
    after: list[datetime] = []
    t = when
    for _ in range(n_after):
        t = t + _gap(rng)
        after.append(t)
    return list(reversed(before)) + [when] + after


@dataclass
class Chat:
    tz: str
    app: str
    owner: Party
    contacts: list[Party]
    lang: str  # "en", "ru" or "mixed"
    msgs: list[Msg]
    target: int

    def party(self, who: str) -> Party:
        if who == "o":
            return self.owner
        return self.contacts[int(who[1:]) - 1 if len(who) > 1 else 0]

    @property
    def record(self) -> Msg:
        return self.msgs[self.target]

    @property
    def sender(self) -> Party:
        acct = self.record.account
        return next(p for p in [self.owner, *self.contacts] if p.account == acct)

    @property
    def other(self) -> Party:
        """The other side of a 1:1 chat; in a group, the owner unless the owner sent it."""
        return self.contacts[0] if self.sender.account.owner else self.owner

    @property
    def local(self) -> datetime:
        return local_dt(self.record.utc, self.tz)

    @property
    def day(self) -> date:
        return self.local.date()

    @property
    def stamp(self) -> str:
        return local_str(self.record.utc, self.tz)

    def local_of(self, i: int) -> datetime:
        return local_dt(self.msgs[i].utc, self.tz)

    def is_group(self) -> bool:
        return len(self.contacts) > 1


def fill_ends(text: str, owner: Party, contact: Party) -> str:
    """Fill the Russian ending slots {c} and {o} that filler and special lines carry."""
    if "{" not in text:
        return text
    return text.replace("{c}", contact.end).replace("{o}", owner.end)


def _words(s: str) -> set[str]:
    return set(s.lower().replace(",", " ").split())


def decorate(rng: random.Random, text: str, lang: str, p: float = 0.5) -> str:
    """At most one casual decoration on a line: a prefix or a tail, each with probability p/2.

    A tail never follows a question or a short reply ("no tbh", "nothing else fr": the line's
    last clause must have three words), and neither repeats a word of the line ("lol lol").
    """
    pres, sufs = (filler.PREFIX_RU, filler.SUFFIX_RU) if lang == "ru" else (
        filler.PREFIX_EN, filler.SUFFIX_EN)  # fmt: skip
    roll = rng.random()
    if roll < p / 2:
        # No prefix repeats a word of the line, and "so" never lands before "yeah" ("so yeah").
        starts_yes = text.startswith(("yeah", "yep", "yes"))
        pres = [x for x in pres if not _words(x) & _words(text) and not (x == "so " and starts_yes)]
        return rng.choice(pres) + text
    last_clause = re.split(r"[,;:]", re.sub(r"\{[^}]*\}", "", text))[-1]  # "{o}" is an ending
    short = len(re.findall(r"[^\W\d_]+", last_clause)) < 3
    if roll < p and not short and not text.rstrip(" )").endswith("?"):
        return text + rng.choice([x for x in sufs if not _words(x) & _words(text)])
    return text


def filler_pools(lang: str, scene: str, safe: bool) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(scene lines, generic lines) for one draw; `safe` leaves the acknowledgments out."""
    if lang == "ru":
        return fillers_ru.SCENE_RU.get(scene, ()), filler.NEUTRAL_RU + (
            () if safe else filler.ACK_RU
        )
    return fillers_en.SCENE_EN.get(scene, ()), filler.NEUTRAL_EN + (() if safe else filler.ACK_EN)


def filler_lines(rng: random.Random, lang: str, n_before: int, n_after: int, owner: Party,
                 contacts: list[Party], whos: tuple[str, ...] = ("o", "c"), *, scene: str = "",
                 safe_after: bool = False, first: str | None = None,
                 ) -> tuple[list[Line], list[Line]]:  # fmt: skip
    """Small talk around the record: n_before lines before it and n_after after it.

    Lines come from the chat's scene pool about 60% of the time and from the generic pool
    otherwise, never twice in one chat. With `safe_after`, the lines after the record carry no
    acknowledgment that could read as an answer or a confirmation (guide rule 13). A line's
    "{o}" is the ending of whoever speaks it and "{c}" that of the person spoken to. `first`
    forces the first speaker, so a non-owner line is always on screen (guide rule 11).
    """
    acks = set(filler.ACK_RU if lang == "ru" else filler.ACK_EN)
    used: set[str] = set()
    out: list[Line] = []
    who = first or rng.choice(whos)
    for i in range(n_before + n_after):
        scene_lines, generic = filler_pools(lang, scene, safe_after and i >= n_before)
        scene_lines = [t for t in scene_lines if t not in used]
        generic = [t for t in generic if t not in used]
        t = rng.choice(scene_lines if scene_lines and rng.random() < 0.6 else generic)
        used.add(t)
        text = t if t in acks else decorate(rng, t, lang)
        speaker = owner if who == "o" else contacts[int(who[1:]) - 1 if len(who) > 1 else 0]
        addressee = contacts[0] if speaker is owner else owner
        out.append((who, text.replace("{o}", speaker.end).replace("{c}", addressee.end)))
        if rng.random() < 0.7:
            who = rng.choice([w for w in whos if w != who] or whos)
    return out[:n_before], out[n_before:]


def assemble(rng: random.Random, *, tz: str, app: str, owner: Party, contacts: list[Party],
             lang: str, before: list[Line], record: Line, after: list[Line],
             when: datetime) -> Chat:  # fmt: skip
    """Build the Chat: lines before, the record at `when` (UTC), lines after."""
    chat = Chat(tz, app, owner, contacts, lang, [], len(before))
    times = spread(rng, when, len(before), len(after))
    lines = [*before, record, *after]
    chat.msgs = [Msg(chat.party(who).account, t, text.strip()) for (who, text), t in
                 zip(lines, times, strict=True)]  # fmt: skip
    return chat
