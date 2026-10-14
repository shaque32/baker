"""Writers for the weekday families: bk_weekday_next, bk_weekday_open, bk_weekday_wrong and
bk_weekday_after. The record plans for one weekday; the window is one whole local day in the
phone's zone, worded "Thursday, May 7, 2026", and its weekday is that date's."""

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


def _sent(rng: random.Random, day: date, tz: str, last: int = 22 * 60) -> datetime:
    """A time between 8 a.m. and the minute `last` (10 p.m.) local on day."""
    for _ in range(50):
        utc = bt.local_instant(day, rng.randint(8 * 60, last), tz)
        if utc is not None:
            return utc + timedelta(seconds=rng.randrange(60))
    raise RuntimeError("no send time")


def _on_weekday(rng: random.Random, weekday: int) -> date:
    base = bt.base_day(rng)
    return base + timedelta(days=(weekday - base.weekday()) % 7)


def _item(
    s: BkSlot, rng: random.Random, pr: Pair, sent: date, target: date, why: str, last: int = 22 * 60
) -> BkDraft:
    utc = _sent(rng, sent, pr.p.tz, last)
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
    before the weekday; the stated date is one of the dates it may mean. A plan for the send
    day's own weekday is sent before 10 a.m., so a time it names ("at 7") can still be that
    day's."""
    pr = pair(rng, s)
    last = 22 * 60
    if s.variant == "same_day":
        last = 9 * 60 + 59
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
        # Never a later day of the same Monday-to-Saturday week, where "this" is plain: a day
        # already past that week, or a Sunday on either side.
        low, high = (s.day + 1, 6) if s.day < 6 else (0, 5)
        sent = _on_weekday(rng, rng.randint(low, high))
        target = sent + timedelta(days=(s.day - sent.weekday()) % 7)
        if 6 in (s.day, sent.weekday()):
            why = (
                'The record says "{word}", sent {local}; whether that week\'s day is still ahead '
                "depends on which day a week starts on, and for some people it had passed, so "
                '"this" does not plainly point to "{raw}".'
            )
        else:
            why = (
                'The record says "{word}", sent {local}, after that week\'s day had passed, so '
                '"this" does not plainly point to "{raw}", and the record leaves the date open.'
            )
    return _item(s, rng, pr, sent, target, why, last)


def wk_wrong(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_weekday_wrong: the stated date falls on another weekday than the quoted words name."""
    pr = pair(rng, s)
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
    return _item(s, rng, pr, sent, target, why)


def wk_after(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_weekday_after: a plan for the stated date's weekday, sent one to six days after that
    date: this record means a later date, and the same words sent before the date could mean
    it (rule 23)."""
    pr = pair(rng, s)
    target = _on_weekday(rng, s.day)
    sent = target + timedelta(days=rng.randint(1, 6))
    why = pick(
        rng,
        'The record plans for "{word}" but was sent on {sent}, after "{raw}" had passed, so '
        "this message means a later date; the same words sent before that date could mean it, "
        "and one record cannot show that no such message exists.",
        'Sent {local}, the plan for "{word}" looks ahead past "{raw}", so this record does not '
        "mean that date; another message with the same words, sent earlier, could, and nothing "
        "here shows there was none.",
    )
    return _item(s, rng, pr, sent, target, why)
