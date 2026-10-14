"""Windows as a document words them, and where a record falls against them, in both zones.

A window is wall-clock bounds in the zone the assumption names. Every test here reads the
window in that zone and, when the phone keeps another zone, in the phone's zone too:
"plainly inside" is at least an hour from every edge in both (an "at about" window: within ten
minutes of its time, same zone only), "plainly outside" at least a day (dates) or two hours
(clock times) beyond every edge in both, and a zone flip is inside in one zone and outside in
the other by ten minutes or more. Words that allow a second reading ("after May 6" may start
on May 6 or on May 7) keep every reading, and a record must pass under all of them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.contracts import TimeWindow
from eval.stancedata import bakerform as bf
from eval.stancedata.chat import NonexistentLocalTime, at_local, long_date

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
FLIP_MARGIN = timedelta(minutes=10)
FAR_PAST = datetime(2020, 1, 1)
FAR_FUTURE = datetime(2030, 1, 1)
FIRST_DAY = date(2024, 1, 10)
LAST_DAY = date(2026, 8, 25)
# Sundays the US clocks changed; a DST week is the Sunday and the six days after it.
DST_SUNDAYS = (date(2024, 3, 10), date(2024, 11, 3), date(2025, 3, 9), date(2025, 11, 2),
               date(2026, 3, 8))  # fmt: skip


@dataclass(frozen=True)
class Win:
    kind: str  # on, On, through, before, after, between, about, weekday
    start: datetime  # wall clock, inclusive
    end: datetime  # wall clock, exclusive
    tz: str
    raw: str
    readings: tuple[tuple[datetime, datetime], ...]  # every reading of the words
    nominal: datetime | None = None  # the clock time of an "at about" window

    @property
    def timed(self) -> bool:
        return self.kind in ("between", "about")

    def tw(self) -> TimeWindow:
        return bf.window(self.start, self.end, self.tz, self.raw)

    def first_day(self) -> date:
        return self.start.date()

    def last_day(self) -> date:
        return (self.end - timedelta(microseconds=1)).date()


def wall_utc(wall: datetime, tz: str) -> datetime:
    return wall.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC)


def clock(hour: int) -> str:
    """'9 p.m.', '10 a.m.', 'noon'."""
    if hour == 12:
        return "noon"
    return f"{hour % 12 or 12} {'a.m.' if hour < 12 else 'p.m.'}"


def _at(day: date, minutes: int) -> datetime:
    return datetime.combine(day, time()) + timedelta(minutes=minutes)


def on_day(day: date, tz: str, cap: bool = False) -> Win:
    start = _at(day, 0)
    raw = ("On " if cap else "on ") + long_date(day)
    return Win("On" if cap else "on", start, start + DAY, tz, raw, ((start, start + DAY),))


def weekday_day(day: date, tz: str) -> Win:
    start = _at(day, 0)
    raw = f"{day.strftime('%A')}, {long_date(day)}"
    return Win("weekday", start, start + DAY, tz, raw, ((start, start + DAY),))


def through(first: date, last: date, tz: str) -> Win:
    if first.year != last.year:
        head = long_date(first)
    else:
        head = f"{first.strftime('%B')} {first.day}"
    start, end = _at(first, 0), _at(last, 0) + DAY
    raw = f"from {head} through {long_date(last)}"
    return Win("through", start, end, tz, raw, ((start, end),))


def before(day: date, tz: str) -> Win:
    end = _at(day, 0)
    raw = f"before {long_date(day)}"
    return Win("before", FAR_PAST, end, tz, raw, ((FAR_PAST, end), (FAR_PAST, end + DAY)))


def after(day: date, tz: str) -> Win:
    start = _at(day, 0) + DAY
    raw = f"after {long_date(day)}"
    return Win("after", start, FAR_FUTURE, tz, raw,
               ((start, FAR_FUTURE), (start - DAY, FAR_FUTURE)))  # fmt: skip


def between(day: date, h1: int, h2: int, tz: str) -> Win:
    if not 5 <= h1 < h2 <= 23:
        raise ValueError(f"bad hours {h1}..{h2}")
    start, end = _at(day, h1 * 60), _at(day, h2 * 60)
    raw = f"between {clock(h1)} and {clock(h2)} on {long_date(day)}"
    return Win("between", start, end, tz, raw, ((start, end),))


def about(day: date, hour: int, tz: str) -> Win:
    nominal = _at(day, hour * 60)
    start, end = nominal - timedelta(minutes=30), nominal + timedelta(minutes=30)
    raw = f"at about {clock(hour)} on {long_date(day)}"
    return Win("about", start, end, tz, raw, ((start, end),), nominal)


# ------------------------------------------------------------------ where an instant falls


def inside_by(utc: datetime, win: Win, tz: str) -> timedelta:
    """How far inside every reading of the window, read in tz, the instant is (< 0: outside)."""
    return min(min(utc - wall_utc(s, tz), wall_utc(e, tz) - utc) for s, e in win.readings)


def outside_by(utc: datetime, win: Win, tz: str) -> timedelta:
    """How far outside every reading of the window, read in tz, the instant is (< 0: inside)."""
    return min(max(wall_utc(s, tz) - utc, utc - wall_utc(e, tz)) for s, e in win.readings)


def plainly_inside(utc: datetime, win: Win, phone_tz: str) -> bool:
    if win.kind == "about":
        near = abs(utc - wall_utc(win.nominal, win.tz)) <= timedelta(minutes=10)  # type: ignore[arg-type]
        return win.tz == phone_tz and near
    return all(inside_by(utc, win, z) >= HOUR for z in {win.tz, phone_tz})


def plainly_outside(utc: datetime, win: Win, phone_tz: str) -> bool:
    need = 2 * HOUR if win.timed else DAY
    return all(outside_by(utc, win, z) >= need for z in {win.tz, phone_tz})


def flip(utc: datetime, win: Win, phone_tz: str) -> str | None:
    """'named' if the instant is inside only in the zone the assumption names, 'phone' if only
    on the phone's clock, None if the zones agree or it sits within ten minutes of an edge."""
    if win.tz == phone_tz or len(win.readings) != 1:
        return None
    named, phone = inside_by(utc, win, win.tz), inside_by(utc, win, phone_tz)
    if named >= FLIP_MARGIN and -phone >= FLIP_MARGIN:
        return "named"
    if phone >= FLIP_MARGIN and -named >= FLIP_MARGIN:
        return "phone"
    return None


# ------------------------------------------------------------------ choosing days and times


def base_day(rng: random.Random, dst_share: float = 0.2) -> date:
    """A day from 2024 to 2026; about one in five falls in a week the clocks changed."""
    if rng.random() < dst_share:
        return rng.choice(DST_SUNDAYS) + timedelta(days=rng.randrange(7))
    return FIRST_DAY + timedelta(days=rng.randrange((LAST_DAY - FIRST_DAY).days + 1))


def local_instant(day: date, minutes: int, tz: str) -> datetime | None:
    """The UTC instant the clock in tz read `minutes` after midnight on day, or None for a
    clock time the spring change skipped."""
    hh, mm = divmod(minutes, 60)
    try:
        return at_local(day, hh, mm, 0, tz=tz)
    except NonexistentLocalTime:
        return None


def _jitter(rng: random.Random, utc: datetime) -> datetime:
    return utc + timedelta(seconds=rng.randrange(60))


def _inside_candidate(rng: random.Random, win: Win) -> datetime | None:
    if win.kind == "about":
        base = wall_utc(win.nominal, win.tz)  # type: ignore[arg-type]
        return base + timedelta(seconds=rng.randint(-540, 540))
    if win.kind == "between":
        lo, hi = win.start.hour * 60 + 60, win.end.hour * 60 - 60
        return local_instant(win.start.date(), rng.randint(lo, hi), win.tz)
    if win.kind == "before":
        day = win.end.date() - timedelta(days=rng.randrange(2, 30))
    elif win.kind == "after":
        day = win.start.date() + timedelta(days=rng.randrange(1, 30))
    else:
        span = (win.last_day() - win.first_day()).days + 1
        day = win.first_day() + timedelta(days=rng.randrange(span))
    return local_instant(day, rng.randint(7 * 60, 21 * 60), win.tz)


def place_inside(rng: random.Random, win: Win, phone_tz: str) -> datetime:
    for _ in range(400):
        utc = _inside_candidate(rng, win)
        if utc is not None:
            utc = _jitter(rng, utc) if win.kind != "about" else utc
            if plainly_inside(utc, win, phone_tz):
                return utc
    raise RuntimeError(f"no plainly inside time for {win.raw!r} ({win.tz}, phone {phone_tz})")


def _outside_candidate(rng: random.Random, win: Win, phone_tz: str) -> datetime | None:
    minutes = rng.randint(7 * 60, 21 * 60)
    if win.timed:
        day = win.start.date() + timedelta(days=rng.choice((-2, -1, 0, 0, 0, 1, 2)))
        return local_instant(day, minutes, phone_tz)
    if win.kind == "before":
        day = win.end.date() + timedelta(days=rng.randrange(3, 20))
    elif win.kind == "after":
        day = win.start.date() - timedelta(days=rng.randrange(4, 20))
    elif rng.random() < 0.5:
        day = win.first_day() - timedelta(days=rng.randrange(2, 12))
    else:
        day = win.last_day() + timedelta(days=rng.randrange(2, 12))
    return local_instant(day, minutes, phone_tz)


def place_outside(rng: random.Random, win: Win, phone_tz: str) -> datetime:
    for _ in range(400):
        utc = _outside_candidate(rng, win, phone_tz)
        if utc is not None:
            utc = _jitter(rng, utc)
            if plainly_outside(utc, win, phone_tz):
                return utc
    raise RuntimeError(f"no plainly outside time for {win.raw!r} ({win.tz}, phone {phone_tz})")


def place_flip(rng: random.Random, win: Win, phone_tz: str, want: str) -> datetime:
    """An instant inside the window only in the named zone (want='named') or only on the
    phone's clock (want='phone')."""
    spans = []
    for wall in win.readings[0]:
        a, b = sorted((wall_utc(wall, win.tz), wall_utc(wall, phone_tz)))
        if b - a >= 3 * FLIP_MARGIN:
            spans.append((a, b))
    for _ in range(200):
        a, b = rng.choice(spans)
        lo, hi = int(FLIP_MARGIN.total_seconds()) + 60, int((b - a - FLIP_MARGIN).total_seconds())
        utc = a + timedelta(seconds=rng.randint(lo, hi - 60))
        if flip(utc, win, phone_tz) == want:
            return utc
    raise RuntimeError(f"no {want} flip for {win.raw!r} ({win.tz}, phone {phone_tz})")


def report_offset(rng: random.Random, utc: datetime, tz: str, share: float = 0.25) -> int:
    """The offset a report printed a call's time in: usually UTC, sometimes the phone's own."""
    if rng.random() >= share:
        return 0
    off = utc.astimezone(ZoneInfo(tz)).utcoffset()
    return int(off.total_seconds() // 60) if off else 0
