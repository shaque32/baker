"""Families on Baker's weekday template: a plan that names a weekday, against a stated date.

The window is the stated date's whole local day in the phone's zone ("Thursday, May 7, 2026"),
and the record is sent between 8 a.m. and 10 p.m. on the phone's clock. bk_weekday_next: a bare
weekday, sent one to six days before a date with that weekday, or "this" before a weekday that
is a later day of the same Monday-to-Saturday week as the send day (supports). bk_weekday_open:
the weekday the record was sent on (sent before 10 a.m., so no time of day it names has passed),
"next" before a weekday, or "this" before a weekday that is not a later day of that week,
against one of the dates it can mean: for "this", the coming such day, never the one a week
after it (complicates). bk_weekday_wrong: another weekday (contradicts). bk_weekday_after: the
date's weekday, sent after the date has passed: this record means a later date, but the same
words sent before the date could mean it, and one record cannot show that no such message
exists (complicates, rule 23).
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from eval.stancedata.chat import long_date
from eval.train.baker_days import (
    DAYS_EN,
    NA_RU,
    NEXT_RU,
    NEXT_THIS,
    OPEN_RU,
    PLANS,
    PLANS_RU,
    SHORT_EN,
    THIS_RU,
    V_RU,
)
from eval.train.baker_kit import Draft, chat, lang_of_text, pick_kind, quoted_words, setup
from eval.train.baker_text import combo, fill, salt_of, split_ru
from eval.train.baker_time import WEEKDAYS, at, pick_day, weekday_name, win_day


def _derived(prefix: str) -> tuple[str, ...]:
    """PLANS with "next" or "this" before the weekday, and NEXT_THIS lines with that word."""
    own = [t for t in NEXT_THIS if f"{prefix} {{wd}}" in t]
    made = [t.replace("on {wd}", "{wd}").replace("{wd}", f"{prefix} {{wd}}") for t in PLANS]
    return tuple(dict.fromkeys(own + made))


POOLS = {
    ("en", ""): PLANS,
    ("en", "next"): _derived("next"),
    ("en", "this"): _derived("this"),
    ("ru", ""): PLANS_RU,
    ("ru", "next"): OPEN_RU,
    ("ru", "this"): OPEN_RU,
}


def full(d: date) -> str:
    """'Monday, May 4, 2026'."""
    return f"{weekday_name(d)}, {long_date(d)}"


def _plan(rng: random.Random, k: int, family: str, prefix: str = "") -> tuple[str, str, str, int]:
    """(text, quotable span, the weekday words, weekday 0-6) of the k-th plan of a family and
    prefix; no two share a pool line and weekday. One in ten is Russian."""
    ru, ordinal = split_ru(k)
    lang = "ru" if ru else "en"
    pool = POOLS[(lang, prefix)]
    t, wd = combo(ordinal, (len(pool), 7), salt_of(f"{family}|{lang}|{prefix}"))
    if ru:
        v = {"": V_RU, "next": NEXT_RU, "this": THIS_RU}[prefix][wd]
        word = NA_RU[wd] if "{na}" in pool[t] else v
        text, core = fill(rng, pool[t].replace("{v}", v).replace("{na}", NA_RU[wd]))
        return text, core, word, wd
    day = DAYS_EN[wd]
    if wd in SHORT_EN and rng.random() < 0.2:
        day = SHORT_EN[wd]
    elif rng.random() < 0.15:
        day = day.capitalize()
    word = f"{prefix} {day}" if prefix else day
    text, core = fill(rng, pool[t].replace(f"{prefix} {{wd}}" if prefix else "{wd}", word))
    return text, core, word, wd


def later_this_week(sent_wd: int, wd: int) -> bool:
    """Whether weekday wd is a later day than weekday sent_wd in the same Monday-to-Saturday
    week (Monday 0), so that "this <weekday>" sent then plainly means the next such day."""
    return sent_wd < wd <= 5


def _day_with(rng: random.Random, wd: int, same: bool) -> date:
    """A day whose weekday is wd (same) or is not wd."""
    d = pick_day(rng)
    if same:
        return d + timedelta(days=(wd - d.weekday()) % 7)
    return d if d.weekday() != wd else d + timedelta(days=rng.randint(1, 6))


def _draft(
    rng: random.Random,
    family: str,
    text: str,
    core: str,
    sent: date,
    target: date,
    last_hour: int = 21,
) -> Draft:
    """The plan as a message sent on `sent` between 8 a.m. and last_hour:59, against the whole
    local day `target`."""
    lang = lang_of_text(text)
    s = setup(rng, pick_kind(rng), lang=lang)
    utc = at(sent, rng.randint(8, last_hour), rng.randrange(60), rng.randrange(60), s.phone.zone)
    quoted = quoted_words(rng, text, core)
    evs, idx = chat(rng, s, text, utc, rng.random() < 0.5, lang, avoid=quoted)
    win = win_day(target, s.phone.zone)
    params: dict[str, Any] = {"quoted_text": quoted, "window": win.tw}
    notes = {"sent": sent, "date": target, "utc": utc}
    return Draft(family, "weekday_date", params, s.scene, s.phone, evs, idx, quoted, "", notes)


def weekday_next(rng: random.Random, k: int) -> Draft:
    """Three in four: a bare weekday. One in four: "this" before a weekday that is a later day
    of the same Monday-to-Saturday week, Tuesday to Saturday."""
    family = "bk_weekday_next"
    prefix = "this" if k % 4 == 3 else ""
    text, core, word, wd = _plan(rng, k, family, prefix)
    if prefix and not 1 <= wd <= 5:
        prefix = ""
        text, core, word, wd = _plan(rng, k, family)
    if prefix:
        target = _day_with(rng, wd, same=True)
        sent = target - timedelta(days=rng.randint(1, wd))
    else:
        sent = _day_with(rng, wd, same=False)
        target = sent + timedelta(days=(wd - sent.weekday()) % 7)
    gap = (target - sent).days
    d = _draft(rng, family, text, core, sent, target)
    days = f"{gap} day{'s' if gap > 1 else ''}"
    if prefix:
        d.rationale = (f"The record was sent on {full(sent)}, {days} before {full(target)}, a "
                       f"later day of the same week; \"{word}\" names that date.")  # fmt: skip
    else:
        d.rationale = (f"The record was sent on {full(sent)}, {days} before {full(target)}; "
                       f"\"{word}\" names that date's weekday.")  # fmt: skip
    d.notes["prefix"] = prefix
    return d


def weekday_open(rng: random.Random, k: int) -> Draft:
    """k % 3: 0 the weekday it was sent on, 1 "next", 2 "this" before a weekday that is not a
    later day of the send day's Monday-to-Saturday week (one already past that week, or a
    Sunday on either side, where weeks that start on Sunday and on Monday disagree); the stated
    date is the first such day on or after the send date, or, except after "this", the one a
    week later. A plan for the send day's own weekday is sent before 10 a.m., so a time of day
    it names ("monday morning", "after lunch") can still be that day's."""
    family = "bk_weekday_open"
    prefix = ("", "next", "this")[k % 3]
    text, core, word, wd = _plan(rng, k, family, prefix)
    if prefix == "this":
        # A day after the weekday, Monday to Saturday; for Saturday and Sunday, a Sunday on
        # either side instead.
        days = list(range(wd + 1, 6)) or [x for x in range(7) if x != wd and (x > wd or wd == 6)]
        assert not any(later_this_week(x, wd) for x in days)  # noqa: S101 - by construction
        sent = _day_with(rng, rng.choice(days), same=True)
    else:
        sent = _day_with(rng, wd, same=not prefix)
    first = sent + timedelta(days=(wd - sent.weekday()) % 7)
    later = first + timedelta(days=7)
    # "This" names a day of the send day's own week, the one already past or the coming one,
    # never the one a week after that; "next" and the send day's weekday can mean either.
    target = first if prefix == "this" else rng.choice((first, later))
    past = first - timedelta(days=7)
    d = _draft(rng, family, text, core, sent, target, last_hour=21 if prefix else 9)
    if prefix == "this" and 6 in (wd, sent.weekday()):
        d.rationale = (f"Weeks start on different days for different people, so \"{word}\", "
                       f"sent on {full(sent)}, could mean {full(past)} or {full(first)}; which "
                       "date it means is open.")  # fmt: skip
    elif prefix == "this":
        d.rationale = (f"Sent on {full(sent)}, \"{word}\" names a day of that week already past, "
                       f"{full(past)}, or the coming one, {full(first)}; which date it means is "
                       "open.")  # fmt: skip
    elif prefix:
        d.rationale = (f"Sent on {full(sent)}, \"{word}\" could mean {full(first)} or "
                       f"{full(later)}, so which date it means is open.")  # fmt: skip
    else:
        d.rationale = (f"The record was sent on {full(sent)}, the weekday it names, so \"{word}\" "
                       f"could mean that day or {full(later)}.")  # fmt: skip
    d.notes["prefix"] = prefix
    return d


def weekday_wrong(rng: random.Random, k: int) -> Draft:
    """The words name another weekday than the stated date's, sent one to six days before it."""
    family = "bk_weekday_wrong"
    text, core, word, wd = _plan(rng, k, family)
    target = _day_with(rng, wd, same=False)
    sent = target - timedelta(days=rng.randint(1, 6))
    if sent.weekday() == wd:
        sent -= timedelta(days=1) if (target - sent).days < 6 else timedelta(days=-1)
    d = _draft(rng, family, text, core, sent, target)
    d.rationale = (f"\"{word}\" names a {WEEKDAYS[wd]}, not "
                   f"{full(target)}, the date the assumption states.")  # fmt: skip
    return d


def weekday_after(rng: random.Random, k: int) -> Draft:
    """The date's own weekday, sent two to six days after the date (rule 23)."""
    family = "bk_weekday_after"
    text, core, word, wd = _plan(rng, k, family)
    target = _day_with(rng, wd, same=True)
    sent = target + timedelta(days=rng.randint(2, 6))
    d = _draft(rng, family, text, core, sent, target)
    d.rationale = (f"The record was sent on {full(sent)}, after {full(target)} had passed, so its "
                   f"plan for \"{word}\" means a later date; the same words sent before "
                   f"{full(target)} could mean that date, and one record cannot show that no such "
                   "message exists.")  # fmt: skip
    return d
