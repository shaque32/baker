"""Dates, clocks and windows for the Baker-wording items. Every name, number and chat is invented.

A window is wall-clock bounds in the zone the assumption names, with the document's own words
(`raw`). A record is plainly inside when it sits at least an hour from every edge, read in that
zone and in the phone's zone; plainly outside when it is at least a day (date windows) or two
hours (clock windows) beyond the window in both readings; on a zone edge when it is inside in
one reading and outside in the other. "At about 9 p.m." is 8:52 to 9:08, eight minutes either
side, as Baker reads a document's "about" (core/audit/assumption_filler.py); a record plainly
inside it lies within five minutes of 9.

Given an rng, the builders vary the words as documents do ("prior to", "on or after", "between
9 and 11 p.m.", "at approximately", "Sept. 3", "Monday, March 3"), every form one Baker's
window check accepts. Where careful readers could differ, the window says so and no label rests
on it: "from May 1 to May 9" may or may not hold the 9th, "between May 1 and May 9" the 1st and
the 9th, "May 1–9" the 9th and "since May 1" the 1st, so a record plainly inside is never on
those days and a zone edge never falls there; "on or about May 2" may reach some days either
side, so a record plainly inside is on May 2 and one plainly outside is three weeks away.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
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
FUZZ = timedelta(days=21)  # "on or about May 2": a record this far off is plainly outside it
CLOCK_HOURS = (*range(6, 12), *range(13, 23))  # window clock times: never noon or midnight
# Month names a document may shorten (AP style; March to July stay whole).
SHORT_MONTHS = {1: "Jan.", 2: "Feb.", 8: "Aug.", 9: "Sept.", 10: "Oct.", 11: "Nov.", 12: "Dec."}
# Other words for "at about" ("about" alone could read as what a call was about).
ABOUT_WORDS = ("at approximately", "at approximately", "at around", "around")


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


def clock(h: int, m: int = 0, style: str = "") -> str:
    """'9 p.m.', '6:30 a.m.' (never noon or midnight); style ":" writes '9:00 p.m.', "PM"
    writes '9 PM' and ":PM" '9:00 PM'."""
    suffix = ("AM" if h < 12 else "PM") if "PM" in style else ("a.m." if h < 12 else "p.m.")
    hm = f"{h % 12 or 12}:{m:02d}" if m or ":" in style else f"{h % 12 or 12}"
    return f"{hm} {suffix}"


def clock_style(rng: random.Random | None) -> str:
    if rng is None or rng.random() < 0.7:
        return ""
    return rng.choice((":", ":", "PM", "PM", ":PM"))


def weekday_name(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def say_date(rng: random.Random | None, d: date) -> str:
    """A date as a document writes it: 'March 3, 2025' most often, else 'Monday, March 3,
    2025', 'Sept. 3, 2025' or 'March 3rd, 2025'."""
    roll = 1.0 if rng is None else rng.random()
    if roll < 0.1:
        return f"{weekday_name(d)}, {long_date(d)}"
    if roll < 0.18 and d.month in SHORT_MONTHS:
        return f"{SHORT_MONTHS[d.month]} {d.day}, {d.year}"
    if roll < 0.24:
        return f"{d:%B} {ordinal(d.day)}, {d.year}"
    return long_date(d)


def month_day(d: date, short: bool = False) -> str:
    """'March 3', or 'Sept. 3' when short and the month has a short form."""
    return f"{SHORT_MONTHS[d.month] if short and d.month in SHORT_MONTHS else f'{d:%B}'} {d.day}"


@dataclass(frozen=True)
class Win:
    """A stated window: wall-clock [start, end) in tz, as the document worded it."""

    start: datetime
    end: datetime
    tz: str
    raw: str
    timed: bool = False  # clock bounds on one date ("between ...", "at about ...")
    about: datetime | None = None
    loose_first: bool = False  # a reader may leave the first day out ("between May 1 and ...")
    loose_last: bool = False  # a reader may leave the last day out ("from May 1 to May 9")
    fuzzy: bool = False  # "on or about": a reader may take in some days either side

    @property
    def tw(self) -> TimeWindow:
        return bf.window(self.start, self.end, self.tz, self.raw)

    @property
    def firm(self) -> Win:
        """The window without the days a reader may leave out."""
        return replace(self, start=self.start + DAY if self.loose_first else self.start,
                       end=self.end - DAY if self.loose_last else self.end)  # fmt: skip


def _midnight(d: date) -> datetime:
    return datetime.combine(d, time())


def _cap(raw: str, cap: bool) -> str:
    return raw[:1].upper() + raw[1:] if cap else raw


def win_on(
    d: date, tz: str, cap: bool = False, rng: random.Random | None = None, fuzzy: bool = False
) -> Win:
    raw = f"{'on or about' if fuzzy else 'on'} {say_date(rng, d)}"
    return Win(_midnight(d), _midnight(d + DAY), tz, _cap(raw, cap), fuzzy=fuzzy)


def win_through(d1: date, d2: date, tz: str, rng: random.Random | None = None) -> Win:
    """From d1 through d2, both whole days: 'from March 3 through March 9, 2025', or with an
    rng another way of saying it, some of which leave an end day to the reader."""
    short = rng is not None and rng.random() < 0.12
    a, b, y = month_day(d1, short), month_day(d2, short), d2.year
    same_month = (d1.year, d1.month) == (d2.year, d2.month)
    b_day = str(d2.day) if same_month and rng is not None and rng.random() < 0.4 else b
    roll = 1.0 if rng is None else rng.random()
    first = last = False
    if roll < 0.15:
        raw, last = f"from {a} to {b}, {y}", True
    elif roll < 0.28:
        raw, first, last = f"between {a} and {b}, {y}", True, True
    elif roll < 0.36 and same_month:
        raw, last = f"during {a}–{d2.day}, {y}", True
    elif roll < 0.44:
        raw = f"during the period from {a} through {b_day}, {y}"
    elif roll < 0.5:
        raw = f"from {a} through {b_day}, {y}, inclusive"
    else:
        raw = f"from {a} through {b_day}, {y}"
    return Win(_midnight(d1), _midnight(d2 + DAY), tz, raw, loose_first=first, loose_last=last)


def win_before(rng: random.Random, d: date, tz: str, vary: bool = False) -> Win:
    """Days before d ('before March 3, 2025'); varied, 'prior to' or 'on or before', which
    holds d itself."""
    start = _midnight(d - timedelta(days=rng.randint(150, 360)))
    roll = rng.random() if vary else 1.0
    if roll < 0.25:
        return Win(start, _midnight(d + DAY), tz, f"on or before {say_date(rng, d)}")
    lead = "prior to" if roll < 0.55 else "before"
    return Win(start, _midnight(d), tz, f"{lead} {say_date(rng if vary else None, d)}")


def win_after(rng: random.Random, d: date, tz: str, vary: bool = False) -> Win:
    """Days after d ('after March 3, 2025'); varied, 'on or after', which holds d itself, or
    'since', which may or may not."""
    roll = rng.random() if vary else 1.0
    lead = "on or after" if roll < 0.2 else "since" if roll < 0.4 else "after"
    start = _midnight(d + DAY) if lead == "after" else _midnight(d)
    raw = f"{lead} {say_date(rng if vary else None, d)}"
    end = start + timedelta(days=rng.randint(150, 360))
    return Win(start, end, tz, raw, loose_first=lead == "since")


def win_between(d: date, h1: int, h2: int, tz: str, rng: random.Random | None = None) -> Win:
    """From h1 to h2 o'clock on d: 'between 9 p.m. and 11 p.m. on March 3, 2025', or with an
    rng 'between 9 and 11 p.m. on ...', 'from 9 PM to 11 PM on ...', 'on ..., between ...'."""
    style = clock_style(rng)
    a, b, day = clock(h1, 0, style), clock(h2, 0, style), say_date(rng, d)
    shapes = [f"between {a} and {b} on {day}"]
    if rng is not None:
        bare = a.rsplit(" ", 1)[0]  # "between 9 and 11 p.m.": the first hour takes the end's
        shapes += [f"from {a} to {b} on {day}", f"on {day}, between {a} and {b}"]
        # (Baker's check reads a bare first hour only without minutes: "between 9 and 11 p.m.")
        if (h1 < 12) == (h2 < 12) and ":" not in style:
            shapes += [f"between {bare} and {b} on {day}", f"from {bare} to {b} on {day}"]
    raw = shapes[0] if rng is None or rng.random() < 0.45 else rng.choice(shapes[1:])
    return Win(datetime.combine(d, time(h1)), datetime.combine(d, time(h2)), tz, raw, timed=True)


def win_about(d: date, h: int, m: int, tz: str, rng: random.Random | None = None) -> Win:
    """'at about 9 p.m. on March 3, 2025'; with an rng 'at approximately', 'around' and the
    like, or the date first ('on March 3, 2025, at about 9 p.m.')."""
    c = datetime.combine(d, time(h, m))
    t, day = clock(h, m, clock_style(rng)), say_date(rng, d)
    word = "at about" if rng is None or rng.random() < 0.45 else rng.choice(ABOUT_WORDS)
    raw = f"{word} {t} on {day}"
    if rng is not None and rng.random() < 0.15:
        raw = f"on {day}, {word} {t}"
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
    firm = win.firm
    return firm.start < firm.end and all(
        margin(firm, utc, z) >= HOUR for z in readings(win, phone_zone)
    )


def plainly_outside(win: Win, utc: datetime, phone_zone: str) -> bool:
    need = 2 * HOUR if win.timed else FUZZ if win.fuzzy else DAY
    return all(margin(win, utc, z) <= -need for z in readings(win, phone_zone))


def inside_any(win: Win, utc: datetime, phone_zone: str) -> bool:
    """Inside in some reading; "on or about" a day reaches FUZZ either side of it."""
    reach = -FUZZ if win.fuzzy else timedelta(0)
    return any(margin(win, utc, z) >= reach for z in readings(win, phone_zone))


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
