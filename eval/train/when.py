"""When a record was sent, as the message-level assumptions word it. Every name, number and chat
is invented.

The supports families and the time trap take their time phrases from the same shapes: a date
(some of the time with its weekday), a part of the day, a bound ("before 9:40 p.m.", "by",
"no later than", "sometime after"), the record's own minute, "about" a minute, or a range of
clock times or dates. `fit_when` gives a phrase that holds the record's local time; `miss_when`
one that plainly misses it, by at least 15 minutes for a bound, 20 for a minute, an hour for
"about" or a part of the day, 30 minutes beyond a range, and a day for a date. So neither the
shape nor its place in the sentence tells the answer; only whether the time fits does. `span`
gives the windows the contact families state around the record (and, for sup_contact, around
the reply that makes it an exchange).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from eval.stancedata.chat import long_date
from eval.train.scenario import MOSCOW, Chat, clock12, hour12

PARTS = ((5, 12, "morning"), (12, 17, "afternoon"), (17, 21, "evening"), (21, 24, "night"))
LAST = 23 * 60 + 59


def clock_of(minute: int) -> str:
    """'noon', '2 p.m.', '2:05 p.m.' for a minute of the day."""
    h, m = divmod(minute, 60)
    return hour12(h) if m == 0 else f"{h % 12 or 12}:{m:02d} {'a.m.' if h < 12 else 'p.m.'}"


def part_of_day(hour: int) -> str | None:
    """The part of the day an hour falls in; None in the small hours, where "the night of"
    could name either date."""
    return next((p for lo, hi, p in PARTS if lo <= hour < hi), None)


def clear_part(minute: int, margin: int = 30) -> str | None:
    """The part of the day a minute falls in, at least `margin` minutes from its edges."""
    return next((p for lo, hi, p in PARTS if lo * 60 + margin <= minute <= hi * 60 - margin), None)


# The widest everyday reading of a part of the day, in minutes, for a time that plainly misses
# a record: "3 in the morning" and "11 in the evening" are both said, and part_phrase calls
# 9:30 to 11:30 p.m. "late in the evening", so the evening runs to midnight. "The night of May
# 2" can mean its small hours or its evening ("Friday night at 6" is said too); it misses only
# the daytime between them.
WIDE_PARTS = (
    ("morning", 0, 12 * 60),
    ("afternoon", 12 * 60, 17 * 60),
    ("evening", 17 * 60, LAST + 1),
)
NIGHT_GAP = (6 * 60, 18 * 60)


def far_parts(minute: int, gap: int = 120) -> list[str]:
    """The parts of the day that plainly miss the minute: at least `gap` minutes from the
    part's widest reading (WIDE_PARTS), and "night" for a daytime minute at least `gap` from
    both ends of NIGHT_GAP."""
    out = [p for p, lo, hi in WIDE_PARTS if minute <= lo - gap or minute >= hi + gap]
    if NIGHT_GAP[0] + gap <= minute <= NIGHT_GAP[1] - gap:
        out.append("night")
    return out


def now_of(c: Chat) -> int:
    return c.local.hour * 60 + c.local.minute


def say_day(rng: random.Random, d: date, weekday: float = 0.07) -> str:
    """A local date as an assumption names it: 'May 2, 2025', some of the time with its own
    weekday ('Friday, May 2, 2025')."""
    return f"{d:%A}, {long_date(d)}" if rng.random() < weekday else long_date(d)


def part_phrase(rng: random.Random, part: str, d: str) -> str:
    if part == "night":
        return rng.choice([f"on the night of {d}", f"late in the evening on {d}"])
    forms = [f"on the {part} of {d}", f"in the {part} on {d}", f"during the {part} of {d}"]
    return rng.choice(forms)


def bound_time(rng: random.Random, c: Chat, after: bool = False, floor: int = -1) -> str | None:
    """A whole local hour before the record's clock ('noon', '2 p.m.'), by which a past act was
    done; with `after`, a reading later than the record's ('11 p.m.', '9:40 p.m.').

    Never the record's own minute: a bound at the very minute a message was sent reads as a
    pointer to that message (and gives the answer away). The reading is never before `floor`,
    the minute by which the act's own time has passed ("by 10 a.m., had landed at noon" makes
    no sense); None when no reading fits.
    """
    h, now, roll = c.local.hour, now_of(c), rng.random()
    if after:
        if roll < 0.25 and h + 2 <= 23:
            t = (h + 2) * 60
        elif roll < 0.7:
            t = min(now + 20 + int(roll * 140), LAST)  # 20 to 117 minutes later
        else:
            t = (h + 1) * 60 if h + 1 <= 23 else LAST
        return clock_of(t) if t > now and t >= floor else None
    top = h * 60 if c.local.minute else (h - 1) * 60  # the last whole hour before the record
    t = top - 60 if roll < 0.35 and top - 60 >= 6 * 60 else top
    if t < floor <= top:
        t = top
    # Never "by midnight", which could be either end of the date.
    return clock_of(t) if t >= max(floor, 60) else None


ABOUT = ("at about", "around", "at around", "at approximately")


def _about(rng: random.Random, t: int, d: str) -> str:
    return f"{rng.choice(ABOUT)} {clock_of(t)} on {d}"


def _range(rng: random.Random, lo: int, hi: int, d: str) -> str:
    if rng.random() < 0.5:
        return f"between {clock_of(lo)} and {clock_of(hi)} on {d}"
    return f"from {clock_of(lo)} to {clock_of(hi)} on {d}"


def _round(minute: int, step: int, up: bool) -> int:
    return -(-minute // step) * step if up else minute // step * step


def clock_around(rng: random.Random, lo: int, hi: int, d: str) -> str | None:
    """A range of clock times on d that holds the minutes lo to hi at least ten minutes inside
    its ends, which fall on a whole or a half hour; None if it would touch midnight."""
    step = rng.choice((30, 60))
    a = _round(lo - rng.randint(10, 120), step, up=False)
    b = _round(hi + rng.randint(10, 120), step, up=True)
    if a < 60 or b > 23 * 60 + 30 or b - a > 8 * 60:
        return None
    return _range(rng, a, b, d)


def fit_clock(rng: random.Random, c: Chat, d: str) -> str | None:
    """A clock phrase on the record's date that holds its local minute."""
    now, shape = now_of(c), rng.choice(("later", "later", "earlier", "earlier", "at", "about",
                                        "range"))  # fmt: skip
    if shape == "at":
        return f"at {clock12(c.local)} on {d}"
    if shape == "about":  # within two and a half minutes of the record's
        t = _round(now + 2, 5, up=False)
        return _about(rng, t, d) if 5 <= t <= 23 * 60 + 55 else None
    if shape == "range":
        return clock_around(rng, now, now, d)
    if shape == "later":
        if (t := bound_time(rng, c, after=True)) is None:
            return None
        lead = rng.choice(("before", "before", "before", "by", "by", "no later than",
                           "sometime before"))  # fmt: skip
        return f"{lead} {t} on {d}"
    if (t := bound_time(rng, c)) is None:
        return None
    lead = rng.choice(("after", "after", "after", "no earlier than", "sometime after"))
    return f"{lead} {t} on {d}"


def act_clock(rng: random.Random, minute: int, d: str, closed: bool = False) -> str:
    """A clock phrase on d for an act at about `minute`, where the record's own time decides
    nothing (an unrelated event, or an act dated before the record's date): the minute, about
    it or a range around it, in the shapes fit_clock gives the supports items; unless `closed`,
    also the part of the day it falls in or an open bound ("sometime after 9 p.m."). A closed
    phrase names a clock and ends on d, so an act a denial rules out stays before the denial."""
    roll = rng.random()
    if roll < 0.15 and 5 <= (t := _round(minute, 5, up=False)) <= 23 * 60 + 55:
        return _about(rng, t, d)
    if roll < 0.3 and (t := clock_around(rng, minute, minute, d)):
        return t
    if roll < 0.45 and not closed and (p := clear_part(minute)):
        return part_phrase(rng, p, d)
    if roll < 0.55 and not closed:
        h = minute // 60
        if rng.random() < 0.5 and h >= 1:
            lead = rng.choice(("after", "sometime after", "no earlier than"))
            return f"{lead} {hour12(h)} on {d}"
        if h + 1 <= 23:
            return f"{rng.choice(('before', 'no later than'))} {hour12(h + 1)} on {d}"
    return f"at {clock_of(minute)} on {d}"


def date_bound(rng: random.Random, day: date, fits: bool) -> tuple[str, str]:
    """A bound of dates that holds the local date `day` ('before May 9, 2025', 'on or after
    May 1, 2025') or, without `fits`, plainly leaves it out ('prior to May 2, 2025' for a
    record of May 2), and the same bound with no weekday, for a rationale (rule 24).
    Contradicts items bound an act by a date ("before May 2, 2025, X paid"), so supports and
    trap items bound the sending the same way."""
    upper, inclusive = rng.random() < 0.55, rng.random() < 0.3
    k = rng.randint(1 if inclusive != fits else 0, 9)
    if upper:
        lead = "on or before" if inclusive else prior_word(rng)
        bound = day + timedelta(days=k) if fits else day - timedelta(days=k)
    else:
        lead = "on or after" if inclusive else "after"
        bound = day - timedelta(days=k) if fits else day + timedelta(days=k)
    return f"{lead} {say_day(rng, bound)}", f"{lead} {long_date(bound)}"


def prior_word(rng: random.Random) -> str:
    """'before', or some of the time 'prior to', for a date bound."""
    return "prior to" if rng.random() < 0.25 else "before"


def fit_when(rng: random.Random, c: Chat, date: float = 0.62, clock: float = 0.2,
             part: float = 0.07, bound: float = 0.05) -> str | None:  # fmt: skip
    """When the record was sent, as a supports or message-level assumption may say it.

    With probability `date` the phrase names the record's local date: plainly ("on May 2,
    2025"), by a part of the day well inside it, by a bound of dates that holds it (with
    probability `bound`), or (with probability `clock`) by a clock phrase that holds the
    record's minute (fit_clock). None leaves the time out. A date on a message makes no cue for
    any answer: trap and contradicts assumptions carry dates as often, and the time trap's
    misses (miss_when) take the same shapes.
    """
    roll, d = rng.random(), say_day(rng, c.day)
    if roll >= date:
        return None
    if roll < clock:
        if t := fit_clock(rng, c, d):
            return t
    elif roll < clock + part:
        if p := clear_part(now_of(c)):
            return part_phrase(rng, p, d)
    elif roll < clock + part + bound:
        return date_bound(rng, c.day, fits=True)[0]
    return f"on {d}"


def telling_when(rng: random.Random, c: Chat, date: float = 0.62,
                 clock: float = 0.2) -> str | None:  # fmt: skip
    """When the record was sent, for an assumption that reports it (see fit_when)."""
    return fit_when(rng, c, date, clock)


def when_sent(rng: random.Random, c: Chat) -> str | None:
    """A time that fits the record's, for a sender or speaker trap: its own minute some of the
    time, or a fit_when phrase (None for no time). Supports items use the same shapes."""
    if rng.random() < 0.15:
        return f"at {clock12(c.local)} on {say_day(rng, c.day)}"
    return fit_when(rng, c, date=0.6, clock=0.25)


def _other_day(rng: random.Random, c: Chat) -> date:
    """A local date other than the record's: some of the time its UTC date, which a reader who
    skips the zone would take for it."""
    h = c.local.hour
    if c.tz == MOSCOW and h <= 2 and rng.random() < 0.7:
        return c.day - timedelta(days=1)  # the UTC date
    if c.tz != MOSCOW and h >= 20 and rng.random() < 0.7:
        return c.day + timedelta(days=1)  # the UTC date
    return c.day + timedelta(days=rng.choice((-3, -2, -1, 1, 2, 3)))


def miss_clock(rng: random.Random, c: Chat) -> str | None:
    """A clock phrase with {d} for the record's date that plainly misses the record's minute."""
    now, h, m = now_of(c), c.local.hour, c.local.minute
    shape = rng.choice(("after", "after", "before", "before", "at", "about", "range", "part"))
    k, exact = rng.randint(15, 90), rng.random() < 0.5
    if shape == "after":
        t = now + k if exact else (h + 1) * 60 if m <= 45 else -1
        lead = rng.choice(("after", "after", "no earlier than", "sometime after"))
        return f"{lead} {clock_of(t)} on {{d}}" if now < t <= LAST else None
    if shape == "before":
        t = now - k if exact else h * 60 if m >= 15 else -1
        lead = rng.choice(("before", "before", "by", "no later than", "sometime before"))
        return f"{lead} {clock_of(t)} on {{d}}" if 60 <= t < now else None
    if shape == "at":
        t = now + rng.choice((-1, 1)) * rng.randint(20, 240)
        return f"at {clock_of(t)} on {{d}}" if 60 <= t <= LAST else None
    if shape == "about":
        t = _round(now + rng.choice((-1, 1)) * rng.randint(65, 300), 5, up=False)
        return f"{rng.choice(ABOUT)} {clock_of(t)} on {{d}}" if 60 <= t <= 23 * 60 + 55 else None
    if shape == "range":
        width = rng.choice((60, 120, 180))
        if rng.random() < 0.5:
            b = _round(now - rng.randint(30, 240), 30, up=False)
            a = b - width
        else:
            a = _round(now + rng.randint(30, 240), 30, up=True)
            b = a + width
        if a < 60 or b > 23 * 60 + 30:
            return None
        return _range(rng, a, b, "{d}")
    parts = far_parts(now)
    return part_phrase(rng, rng.choice(parts), "{d}") if parts else None


def miss_when(rng: random.Random, c: Chat) -> tuple[str, str]:
    """A time phrase that plainly misses the record's local time, and the rationale's account
    of the miss: a clock phrase or part of the day on the record's date (50%), a bound of dates
    that leaves it out (10%) or another date, in the shapes fit_when holds a record with (a
    range of dates only in the contact windows, which both sides of an answer state)."""
    loc, d = c.local, long_date(c.day)
    roll = rng.random()
    if roll < 0.5:
        if t := miss_clock(rng, c):
            phrase = t.replace("{d}", say_day(rng, c.day))
            stated = t.replace("{d}", d)
            return phrase, f"sent at {clock12(loc)} on {d}, outside the time stated ('{stated}')"
    elif roll < 0.6:
        phrase, plain = date_bound(rng, c.day, fits=False)
        return phrase, f"sent on {d} local time ({c.stamp}), not {plain}"
    w = _other_day(rng, c)
    return f"on {say_day(rng, w)}", f"sent on {d} local time ({c.stamp}), not on {long_date(w)}"


def later_time(rng: random.Random, c: Chat) -> str | None:
    """A clock reading later on the record's date, as '9 p.m. on May 2, 2025'."""
    t = bound_time(rng, c, after=True)
    return f"{t} on {say_day(rng, c.day)}" if t else None


def span(rng: random.Random, c: Chat, lo: int, hi: int, clock: float = 0.3) -> str:
    """A window that holds the minutes lo to hi of the record's date: a date, a pair of dates,
    a range "from ... through ..." (never "between" two dates, whose ends a reader must guess),
    a month, an open end, a part of the day or a range of clock times."""
    d = say_day(rng, c.day)
    if rng.random() < clock:
        shape = rng.choice(("range", "range", "after", "before", "part"))
        if shape == "range" and (t := clock_around(rng, lo, hi, d)):
            return t
        a = _round(lo - rng.randint(10, 150), rng.choice((30, 60)), up=False)
        b = _round(hi + rng.randint(10, 150), rng.choice((30, 60)), up=True)
        if shape == "after" and a >= 60:
            return f"after {clock_of(a)} on {d}"
        if shape == "before" and b <= 23 * 60 + 30:
            return f"before {clock_of(b)} on {d}"
        if shape == "part" and (p := clear_part(lo)) and clear_part(hi) == p:
            return part_phrase(rng, p, d)
    roll, day = rng.random(), c.day
    if roll < 0.32:
        return f"on {d}"
    if roll < 0.56:
        a, b = rng.randint(0, 6), rng.randint(0, 6)
        b += a == b == 0
        lo_d, hi_d = day - timedelta(days=a), day + timedelta(days=b)
        return f"from {long_date(lo_d)} through {long_date(hi_d)}"
    if roll < 0.66:
        near = day + timedelta(days=rng.choice((-1, 1)))
        first, second = sorted((day, near))
        return f"on {long_date(first)} or {long_date(second)}"
    if roll < 0.78:
        return f"{rng.choice(('in', 'in', 'during'))} {day:%B %Y}"
    if roll < 0.89:
        if rng.random() < 0.5:
            return f"before {long_date(day + timedelta(days=rng.randint(1, 20)))}"
        return f"on or before {long_date(day + timedelta(days=rng.randint(0, 20)))}"
    if rng.random() < 0.5:
        return f"after {long_date(day - timedelta(days=rng.randint(1, 20)))}"
    return f"on or after {long_date(day - timedelta(days=rng.randint(0, 20)))}"
