"""Placing a record against a stated window: plainly inside, plainly outside or on a zone edge.

Each function draws a date, a window wording and a record time, and keeps the first draw whose
margins pass the checks in baker_time, so a returned pair holds by construction. A share of the
"on" windows read "on or about" (`fuzzy`), for the templates where that reads naturally; a zone
edge never falls on a day a reader may leave out (baker_time).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from eval.stancedata import bakerform as bf
from eval.train.baker_time import (
    CLOCK_HOURS,
    DAY,
    Win,
    at,
    at_wall,
    edge_side,
    offset_min,
    pick_day,
    plainly_inside,
    plainly_outside,
    wall,
    win_about,
    win_after,
    win_before,
    win_between,
    win_on,
    win_through,
)

DATE_FORMS = ("on", "on", "On", "through", "through", "before", "after")
ALL_FORMS = (*DATE_FORMS, "between", "between", "about")
EDGE_FORMS = ("on", "on", "On", "through", "before", "after", "between")


def _days(n: int) -> timedelta:
    return timedelta(days=n)


def _around(rng: random.Random, form: str, w: datetime, tz: str, fuzzy: float) -> Win | None:
    """A window of this form that holds the wall-clock reading w (in tz) well inside."""
    d = w.date()
    if form in ("on", "On"):
        return win_on(d, tz, form == "On", rng, rng.random() < fuzzy)
    if form == "through":
        d1, d2 = d - _days(rng.randint(0, 4)), d + _days(rng.randint(0, 4))
        d2 = d2 + DAY if d1 == d2 else d2
        return win_through(d1, d2, tz, rng) if d1.year == d2.year else None
    if form == "before":
        return win_before(rng, d + _days(rng.randint(1, 12)), tz, vary=True)
    if form == "after":
        return win_after(rng, d - _days(rng.randint(1, 12)), tz, vary=True)
    h1, h2 = w.hour - rng.randint(1, 3), w.hour + rng.randint(2, 4)
    return win_between(d, h1, h2, tz, rng) if {h1, h2} <= set(CLOCK_HOURS) else None


def inside(
    rng: random.Random,
    phone_zone: str,
    tz: str,
    forms: tuple[str, ...] = ALL_FORMS,
    fuzzy: float = 0.0,
) -> tuple[Win, datetime]:
    """A window in tz and a record time plainly inside it in both readings; `fuzzy` is the
    share of "on" windows that read "on or about"."""
    for _ in range(400):
        form, day = rng.choice(forms), pick_day(rng)
        if form == "about":
            if tz != phone_zone:
                continue
            win = win_about(day, rng.choice(CLOCK_HOURS), rng.choice((0, 30)), tz, rng)
            assert win.about is not None  # noqa: S101 - an "about" window has its clock time
            utc = at_wall(win.about + timedelta(seconds=rng.randint(-290, 290)), tz)
        else:
            utc = at(day, rng.randint(7, 22), rng.randrange(60), rng.randrange(60), phone_zone)
            win = _around(rng, form, wall(utc, tz), tz, fuzzy)
        if win is not None and plainly_inside(win, utc, phone_zone):
            return win, utc
    raise RuntimeError("no inside window found")


def _away(rng: random.Random, form: str, w: datetime, tz: str, fuzzy: float) -> Win | None:
    """A window of this form that the wall-clock reading w (in tz) falls well outside."""
    d, sign = w.date(), rng.choice((-1, 1))
    if form in ("on", "On"):
        if rng.random() < fuzzy:  # "on or about": three weeks off at least (baker_time.FUZZ)
            return win_on(d + sign * _days(rng.randint(22, 70)), tz, form == "On", rng, True)
        return win_on(d + sign * _days(rng.randint(2, 8)), tz, form == "On", rng)
    if form == "through":
        span, gap = _days(rng.randint(1, 5)), _days(rng.randint(2, 6))
        d1, d2 = (d - gap - span, d - gap) if sign < 0 else (d + gap, d + gap + span)
        return win_through(d1, d2, tz, rng) if d1.year == d2.year else None
    if form == "before":
        return win_before(rng, d - _days(rng.randint(1, 8)), tz, vary=True)
    if form == "after":
        return win_after(rng, d + _days(rng.randint(1, 8)), tz, vary=True)
    same_day = rng.random() < 0.5
    day = d if same_day else d + sign * _days(rng.randint(1, 6))
    if form == "about":
        h = w.hour + sign * rng.randint(3, 8) if same_day else rng.choice(CLOCK_HOURS)
        return win_about(day, h, rng.choice((0, 30)), tz, rng) if h in CLOCK_HOURS else None
    if same_day and sign < 0:
        h2 = w.hour - rng.randint(3, 5)
        h1 = h2 - rng.randint(3, 5)
    else:
        h1 = w.hour + rng.randint(3, 5) if same_day else rng.choice(CLOCK_HOURS)
        h2 = h1 + rng.randint(3, 5)
    return win_between(day, h1, h2, tz, rng) if {h1, h2} <= set(CLOCK_HOURS) else None


def outside(
    rng: random.Random,
    phone_zone: str,
    tz: str,
    forms: tuple[str, ...] = ALL_FORMS,
    fuzzy: float = 0.0,
) -> tuple[Win, datetime]:
    """A window in tz and a record time plainly outside it in both readings."""
    for _ in range(400):
        form, day = rng.choice(forms), pick_day(rng)
        utc = at(day, rng.randint(7, 22), rng.randrange(60), rng.randrange(60), phone_zone)
        win = _away(rng, form, wall(utc, tz), tz, fuzzy)
        if win is not None and plainly_outside(win, utc, phone_zone):
            return win, utc
    raise RuntimeError("no outside window found")


def _edge_window(rng: random.Random, form: str, tz: str) -> tuple[Win, tuple[datetime, ...]]:
    """A window and the edges a zone-edge record may sit at: never a day a reader may leave
    out ("from May 1 to May 9" keeps its start). Both dates of a range share a year, as in
    _around and _away ("from December 31 through January 5, 2025" leaves the start's year to a
    guess), and a clock range never ends at noon (CLOCK_HOURS)."""
    day = pick_day(rng)
    if form in ("on", "On"):
        win = win_on(day, tz, form == "On", rng)
    elif form == "through":
        k = rng.randint(1, 6)
        first, last = day, day + _days(k)
        if last.year != first.year:
            first, last = day - _days(k), day
        win = win_through(first, last, tz, rng)
    elif form == "before":
        win = win_before(rng, day, tz, vary=True)
        return win, (win.end,)
    elif form == "after":
        win = win_after(rng, day, tz, vary=True)
        return win, () if win.loose_first else (win.start,)
    else:
        h1 = rng.choice(CLOCK_HOURS[:-3])
        h2 = min(h1 + rng.randint(3, 5), CLOCK_HOURS[-1])
        win = win_between(day, h1, h2 + (h2 not in CLOCK_HOURS), tz, rng)
    starts = () if win.loose_first else (win.start,)
    return win, (*starts, *(() if win.loose_last else (win.end,)))


def edge(
    rng: random.Random, phone_zone: str, side: str, forms: tuple[str, ...] = EDGE_FORMS
) -> tuple[Win, datetime]:
    """A window in another zone and a record inside it only in the phone's zone reading
    (side 'phone') or only in the window's own zone (side 'tz')."""
    for _ in range(600):
        tz = rng.choice([z for z in bf.ZONES if z != phone_zone])
        win, edges = _edge_window(rng, rng.choice(forms), tz)
        if not edges:
            continue
        e = rng.choice(edges)
        utc_e = at_wall(e, phone_zone)
        delta = timedelta(minutes=offset_min(utc_e, tz) - offset_min(utc_e, phone_zone))
        room = int((abs(delta) / 2 - timedelta(minutes=12)).total_seconds())
        if room <= 0:
            continue
        w_p = e - delta / 2 + timedelta(seconds=rng.randint(-room, room))
        utc = at_wall(w_p.replace(microsecond=0), phone_zone)
        if edge_side(win, utc, phone_zone) == side:
            return win, utc
    raise RuntimeError("no zone edge found")
