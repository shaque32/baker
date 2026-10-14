"""Writers for the weekday families: bk_weekday_next, bk_weekday_open and bk_weekday_wrong.
The record plans for one weekday; the window is one whole local day in the phone's zone, worded
"Thursday, May 7, 2026", and its weekday is that date's."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from eval.heldout import bk_cues as cues
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import Pair, pair
from eval.heldout.bk_common import BkDraft, pick
from eval.heldout.bk_schedule import BkSlot
from eval.stancedata.chat import long_date

# Context lines never name a day or a relative day, which could change what the plan means.
_DAY_WORDS = (*cues.DAYS_EN, "понедельник", "вторник", "сред", "четверг", "пятниц", "суббот",
              "воскресен", "tomorrow", "tmrw", "today", "tonight", "week", "завтра", "сегодня",
              "недел", "выходн")  # fmt: skip


def word(s: BkSlot) -> str:
    """The weekday words as the record writes them ("next thursday", "в четверг")."""
    mod = {"next": "next ", "this": "this "}.get(s.variant, "")
    if s.lang == "en":
        return f"{mod}{cues.DAYS_EN[s.day]}"
    return cues.DAYS_RU[mod][s.day]


def _sent(rng: random.Random, day: date, tz: str) -> datetime:
    """A time between 8 a.m. and 10 p.m. local on day."""
    for _ in range(50):
        utc = bt.local_instant(day, rng.randint(8 * 60, 22 * 60), tz)
        if utc is not None:
            return utc + timedelta(seconds=rng.randrange(60))
    raise RuntimeError("no send time")


def _on_weekday(rng: random.Random, weekday: int) -> date:
    base = bt.base_day(rng)
    return base + timedelta(days=(weekday - base.weekday()) % 7)


def _item(s: BkSlot, rng: random.Random, pr: Pair, sent: date, target: date, why: str) -> BkDraft:
    utc = _sent(rng, sent, pr.p.tz)
    win = bt.weekday_day(target, pr.p.tz)
    mine = rng.random() < 0.5
    ex = pr.chat(rng, s, utc, s.text, mine, avoid=_DAY_WORDS)
    params: dict[str, object] = {"quoted_text": s.text, "window": win.tw()}
    if rng.random() < 0.25:
        params["account_ids"] = [pr.p.aid(pr.sender(mine))]
    rec = ex.record
    why = why.format(word=word(s), raw=win.raw, local=rec.local_time, sent=long_date(sent),
                     weekday=sent.strftime("%A"))  # fmt: skip
    return BkDraft(s.family, "weekday_date", params, ex, s.text, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": s.variant, "sent": sent, "target": target})  # fmt: skip


def wk_next(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_weekday_next: a plan for a bare weekday, sent one to six days before the stated
    date, which falls on that weekday."""
    pr = pair(rng, s)
    target = _on_weekday(rng, s.day)
    sent = target - timedelta(days=rng.randint(1, 6))
    why = pick(
        rng,
        'Sent on {sent}, the record plans for "{word}"; the first such day after it is '
        '"{raw}", the date the assumption gives.',
        'The record, sent {local}, names "{word}", and the next "{word}" after that is "{raw}".',
    )
    return _item(s, rng, pr, sent, target, why)


def wk_open(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_weekday_open: the plan names the weekday it was sent on, or puts "next" or "this"
    before the weekday; the stated date is one of the dates it may mean."""
    pr = pair(rng, s)
    if s.variant == "same_day":
        sent = _on_weekday(rng, s.day)
        target = sent + timedelta(days=rng.choice((0, 7)))
        why = (
            'The record says "{word}" and was sent on a {weekday} ({local}), so it may mean '
            'that same day or the one a week later; whether it means "{raw}" is open.'
        )
    elif s.variant == "next":
        sent = bt.base_day(rng)
        upcoming = sent + timedelta(days=(s.day - sent.weekday() - 1) % 7 + 1)
        target = upcoming + timedelta(days=rng.choice((0, 7)))
        why = pick(
            rng,
            'The record says "{word}", sent {local}; "next" may mean the coming one or the one '
            'after it, so whether it means "{raw}" is open.',
            'Sent on {sent}, "{word}" can point to either of two dates a week apart, and the '
            'record does not say which; "{raw}" is only one of them.',
        )
    else:
        low, high = (s.day + 1, 6) if s.day < 6 else (0, 5)
        sent = _on_weekday(rng, rng.randint(low, high))
        target = sent + timedelta(days=(s.day - sent.weekday()) % 7)
        why = (
            'The record says "{word}", sent {local}; a weekday with "this" before it leaves '
            'open which week it means, so the record does not settle that it means "{raw}".'
        )
    return _item(s, rng, pr, sent, target, why)


def wk_wrong(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_weekday_wrong: the stated date falls on another weekday than the quoted words name,
    or the plan was sent after the stated date had passed."""
    pr = pair(rng, s)
    if s.variant == "other_day":
        wd = rng.choice([d for d in range(7) if d != s.day])
        target = _on_weekday(rng, wd)
        sent = target - timedelta(days=rng.randint(1, 6))
        why = pick(
            rng,
            'The quoted words name "{word}", and the stated date "{raw}" falls on another '
            "weekday, so the words cannot mean that date.",
            'The record plans for "{word}", while "{raw}" is a different weekday; the quoted '
            "words rule that date out.",
        )
    else:
        target = _on_weekday(rng, s.day)
        sent = target + timedelta(days=rng.randint(1, 6))
        why = pick(
            rng,
            'The record plans for "{word}" and was sent on {sent}, after "{raw}" had passed, so '
            "the plan cannot mean that date.",
            'Sent {local}, the plan for "{word}" looks ahead, and "{raw}" was already past, so '
            "the words cannot mean it.",
        )
    return _item(s, rng, pr, sent, target, why)
