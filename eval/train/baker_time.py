"""Dates, clocks and windows for the Baker-wording items. Every name, number and chat is invented.

A window is wall-clock bounds in the zone the assumption names, with the document's own words
(`raw`). A record is plainly inside when it sits at least an hour from every edge, read in that
zone and in the phone's zone; plainly outside when it is at least a day (date windows) or two
hours (clock windows) beyond the window in both readings; on a zone edge when it is inside in
one reading and outside in the other. "At about 9 p.m." is 8:52 to 9:08, eight minutes either
side, as Baker reads a document's "about" (core/audit/assumption_filler.py); a record plainly
inside it lies within five minutes of 9.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.contracts import TimeWindow
from eval.stancedata import bakerform as bf
from eval.stancedata.chat import NonexistentLocalTime, at_local, long_date

# Records fall in this range; windows and context lines stay inside 2024-01-01 .. 2026-09-30.
FIRST_DAY = date(2024, 1, 22)
LAST_DAY = date(2026, 9, 12)
# Days the US clocks change (2 a.m. local); scenes near them show both EST and EDT.
DST_DAYS = (date(2024, 3, 10), date(2024, 11, 3), date(2025, 3, 9), date(2025, 11, 2),
            date(2026, 3, 8))  # fmt: skip
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
EDGE = timedelta(minutes=10)  # a zone-edge record is this far from the edge in both readings
ABOUT_HALF = timedelta(minutes=8)  # "at about 9 p.m." is 8:52 to 9:08, as Baker reads it
ABOUT = timedelta(minutes=5)  # a record plainly inside it is this close to 9
CLOCK_HOURS = (*range(6, 12), *range(13, 23))  # window clock times: never noon or midnight


def pick_day(rng: random.Random) -> date:
    if rng.random() < 0.18:
        return rng.choice(DST_DAYS) + timedelta(days=rng.randint(-3, 3))
    return FIRST_DAY + timedelta(days=rng.randrange((LAST_DAY - FIRST_DAY).days + 1))


def at(day: date, hh: int, mm: int, ss: int, tz: str) -> datetime:
    """The UTC instant of a wall-clock reading; one the spring change skips moves an hour on."""
    try:
        return at_local(day, hh, mm, ss, tz)
    except NonexistentLocalTime:
        return at_local(day, hh + 1, mm, ss, tz)


def at_wall(w: datetime, tz: str) -> datetime:
    return at(w.date(), w.hour, w.minute, w.second, tz)


def wall(utc: datetime, tz: str) -> datetime:
    """The phone's clock reading in tz, without its zone."""
    return utc.astimezone(ZoneInfo(tz)).replace(tzinfo=None)


def offset_min(utc: datetime, tz: str) -> int:
    off = utc.astimezone(ZoneInfo(tz)).utcoffset()
    return int(off.total_seconds() // 60) if off is not None else 0


def clock(h: int, m: int = 0) -> str:
    """'9 p.m.', '6:30 a.m.' (never noon or midnight)."""
    suffix = "a.m." if h < 12 else "p.m."
    return f"{h % 12 or 12}:{m:02d} {suffix}" if m else f"{h % 12 or 12} {suffix}"


def weekday_name(d: date) -> str:
    return WEEKDAYS[d.weekday()]


@dataclass(frozen=True)
class Win:
    """A stated window: wall-clock [start, end) in tz, as the document worded it."""

    start: datetime
    end: datetime
    tz: str
    raw: str
    timed: bool = False  # clock bounds on one date ("between ...", "at about ...")
    about: datetime | None = None

    @property
    def tw(self) -> TimeWindow:
        return bf.window(self.start, self.end, self.tz, self.raw)


def _midnight(d: date) -> datetime:
    return datetime.combine(d, time())


def win_on(d: date, tz: str, cap: bool = False) -> Win:
    return Win(_midnight(d), _midnight(d + DAY), tz, f"{'On' if cap else 'on'} {long_date(d)}")


def win_through(d1: date, d2: date, tz: str) -> Win:
    raw = f"from {d1:%B} {d1.day} through {d2:%B} {d2.day}, {d2.year}"
    return Win(_midnight(d1), _midnight(d2 + DAY), tz, raw)


def win_before(rng: random.Random, d: date, tz: str) -> Win:
    start = _midnight(d - timedelta(days=rng.randint(150, 360)))
    return Win(start, _midnight(d), tz, f"before {long_date(d)}")


def win_after(rng: random.Random, d: date, tz: str) -> Win:
    start = _midnight(d + DAY)
    return Win(start, start + timedelta(days=rng.randint(150, 360)), tz, f"after {long_date(d)}")


def win_between(d: date, h1: int, h2: int, tz: str) -> Win:
    raw = f"between {clock(h1)} and {clock(h2)} on {long_date(d)}"
    return Win(datetime.combine(d, time(h1)), datetime.combine(d, time(h2)), tz, raw, timed=True)


def win_about(d: date, h: int, m: int, tz: str) -> Win:
    c = datetime.combine(d, time(h, m))
    raw = f"at about {clock(h, m)} on {long_date(d)}"
    return Win(c - ABOUT_HALF, c + ABOUT_HALF, tz, raw, True, c)


def win_day(d: date, tz: str) -> Win:
    """The weekday template's window: one whole local day, named with its weekday."""
    return Win(_midnight(d), _midnight(d + DAY), tz, f"{weekday_name(d)}, {long_date(d)}")


# ---------------------------------------------------------------- where a record falls


def margin(win: Win, utc: datetime, zone: str) -> timedelta:
    """How far inside (positive) or outside (negative) the window the instant is when its
    wall-clock bounds are read in `zone`: the smaller of the clock and the elapsed distance.
    Zero where the two disagree (the repeated hour of a fall change)."""
    w, z = wall(utc, zone), ZoneInfo(zone)
    s_utc = win.start.replace(tzinfo=z).astimezone(UTC)
    e_utc = win.end.replace(tzinfo=z).astimezone(UTC)
    in_wall, in_el = win.start <= w < win.end, s_utc <= utc < e_utc
    if in_wall != in_el:
        return timedelta(0)
    if in_wall:
        return min(w - win.start, win.end - w, utc - s_utc, e_utc - utc)
    near_wall = win.start - w if w < win.start else w - win.end
    near_el = s_utc - utc if utc < s_utc else utc - e_utc
    return -min(near_wall, near_el)


def readings(win: Win, phone_zone: str) -> tuple[str, ...]:
    return (win.tz,) if win.tz == phone_zone else (win.tz, phone_zone)


def plainly_inside(win: Win, utc: datetime, phone_zone: str) -> bool:
    if win.about is not None:
        return all(abs(wall(utc, z) - win.about) <= ABOUT for z in readings(win, phone_zone))
    return all(margin(win, utc, z) >= HOUR for z in readings(win, phone_zone))


def plainly_outside(win: Win, utc: datetime, phone_zone: str) -> bool:
    need = 2 * HOUR if win.timed else DAY
    return all(margin(win, utc, z) <= -need for z in readings(win, phone_zone))


def inside_any(win: Win, utc: datetime, phone_zone: str) -> bool:
    return any(margin(win, utc, z) >= timedelta(0) for z in readings(win, phone_zone))


def inside_both(win: Win, utc: datetime, phone_zone: str) -> bool:
    return all(margin(win, utc, z) > timedelta(0) for z in readings(win, phone_zone))


def edge_side(win: Win, utc: datetime, phone_zone: str) -> str | None:
    """'phone' if the record is inside only in the phone's zone, 'tz' if only in the window's."""
    if win.tz == phone_zone:
        return None
    a, p = margin(win, utc, win.tz), margin(win, utc, phone_zone)
    if p >= EDGE and a <= -EDGE:
        return "phone"
    if a >= EDGE and p <= -EDGE:
        return "tz"
    return None
