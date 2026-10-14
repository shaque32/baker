"""Choices the Baker-wording writers share: windows, call lengths, file names and the messages
around a call."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from eval.heldout import bk_time as bt
from eval.heldout.bk_common import SITS, ctx_texts
from eval.heldout.bk_scene import Acct, Excerpt, Phone, Scene, around, chat_app
from eval.stancedata import bakerform as bf

DATE_KINDS = ("on", "On", "through", "before", "after")
ALL_KINDS = (*DATE_KINDS, "between", "between", "about")


def pick_window(
    rng: random.Random, phone_tz: str, kinds: tuple[str, ...] = ALL_KINDS, tz: str | None = None
) -> bt.Win:
    """A window in tz (default: the phone's zone). A clock-time window across two zones is
    wide enough to hold a record an hour inside it in both."""
    tz = tz or phone_tz
    kind = rng.choice(kinds)
    day = bt.base_day(rng)
    if kind in ("on", "On"):
        return bt.on_day(day, tz, cap=kind == "On")
    if kind == "through":
        return bt.through(day, day + timedelta(days=rng.randint(2, 9)), tz)
    if kind == "before":
        return bt.before(day, tz)
    if kind == "after":
        return bt.after(day, tz)
    if kind == "between":
        width = rng.randint(3, 6) if tz == phone_tz else rng.randint(7, 9)
        h1 = rng.randint(6, 23 - width)
        return bt.between(day, h1, h1 + width, tz)
    if kind == "about":
        return bt.about(day, rng.randint(8, 21), tz)
    raise ValueError(f"unknown window kind {kind!r}")


def some_time(rng: random.Random, tz: str) -> datetime:
    """A daytime instant on some day, for items whose answer does not turn on the time."""
    for _ in range(50):
        utc = bt.local_instant(bt.base_day(rng), rng.randint(7 * 60, 22 * 60), tz)
        if utc is not None:
            return utc + timedelta(seconds=rng.randrange(60))
    raise RuntimeError("no time")


# ------------------------------------------------------------------ calls


def duration(rng: random.Random) -> int:
    lo, hi = rng.choice(((25, 120), (90, 600), (300, 1500)))
    return rng.randint(lo, hi)


def _round(x: float, step: int, up: bool) -> int:
    n = int(x // step) * step
    return n + step if up and n < x else n


def range_holding(rng: random.Random, dur: int) -> tuple[int, int]:
    """A length range with the call's length inside it, at least 10% from either end."""
    step = 5 if dur < 200 else 30
    lo = _round(dur * rng.uniform(0.35, 0.85), step, up=False)
    hi = _round(dur * rng.uniform(1.2, 2.2), step, up=True)
    if not (lo <= 0.9 * dur and hi >= 1.1 * dur):
        raise ValueError(f"bad range {lo}..{hi} for {dur}s")
    return lo, hi


def range_missing(rng: random.Random, dur: int, short: bool) -> tuple[int, int]:
    """A length range the call plainly misses: it lasted under half the minimum (short) or
    over twice the maximum."""
    if short:
        lo = _round(dur * rng.uniform(2.6, 5.0) + 10, 10, up=True)
        hi = lo + _round(lo * rng.uniform(0.5, 1.5), 10, up=True)
        ok = dur * 2 < lo
    else:
        hi = _round(dur * rng.uniform(0.2, 0.4), 10, up=False)
        lo = _round(hi * rng.uniform(0.3, 0.7), 10, up=False)
        ok = dur > 2 * hi and 0 <= lo < hi
    if not ok:
        raise ValueError(f"range {lo}..{hi} does not miss {dur}s")
    return lo, hi


def short_call(rng: random.Random) -> int:
    return rng.randint(4, 40)


def long_call(rng: random.Random) -> int:
    return rng.randint(600, 2400)


def call_phone(rng: random.Random, sc: Scene, item: int, tz: str, lang: str = "en") -> Phone:
    """A phone whose owner has a Phone account and a chat app, so calls sit among messages."""
    app = chat_app(rng, lang)
    apps = ("Phone", app) if rng.random() < 0.7 else (app, "Phone")
    return sc.phone(rng, item, tz, apps)


def call_excerpt(
    rng: random.Random,
    sc: Scene,
    ph: Phone,
    call: bf.Line,
    count: tuple[int, int] = (1, 4),
    sit: str | None = None,
    where: str = "both",
) -> Excerpt:
    """The call among messages from the phone's other chats: the owner and one or two people
    who are not party to the call."""
    sit = sit or rng.choice(SITS)
    apps = [a for a in ph.own if a.app != "Phone"]
    partners = [(me, sc.new(rng, me.app)) for me in rng.sample(apps, len(apps))][:2]
    if len(partners) == 1 and rng.random() < 0.4:
        me = partners[0][0]
        partners.append((me, sc.new(rng, me.app)))
    n = rng.randint(*count)
    texts = ctx_texts(rng, sit, "en", n)
    lines: list[tuple[Acct, str]] = []
    for text in texts:
        me, other = rng.choice(partners)
        lines.append((rng.choice((me, other)), text))
    if where == "before":
        nb = n
    elif where == "after":
        nb = 0
    else:
        nb = rng.randint(max(0, n - 3), min(3, n))
    return around(rng, sc, ph, call, lines[:nb], lines[nb:])


# ------------------------------------------------------------------ attachments


def attachment_name(
    rng: random.Random, utc: datetime, tz: str, dated: bool = True, photos: bool = False
) -> str:
    """A file name as a phone saves it; a dated name carries the send date and a clock time a
    few minutes before the send. `photos` keeps to photos and videos: no voice note or
    screenshot, whose content could hold words."""
    taken = utc.astimezone(ZoneInfo(tz)) - timedelta(seconds=rng.randint(20, 400))
    if taken.date() != utc.astimezone(ZoneInfo(tz)).date():
        dated = False
    if not dated:
        return rng.choice(("IMG_{n}.jpg", "IMG_{n}.HEIC", "VID_{n}.mov", "DSC0{n}.JPG")).format(
            n=rng.randint(1000, 9999)
        )
    forms = [
        f"IMG_{taken:%Y%m%d_%H%M%S}.jpg",
        f"VID_{taken:%Y%m%d_%H%M%S}.mp4",
        f"IMG-{taken:%Y%m%d}-WA{rng.randint(1, 60):04d}.jpg",
        f"photo_{taken:%Y-%m-%d_%H-%M-%S}.jpg",
    ]
    if not photos:
        forms += [
            f"PTT-{taken:%Y%m%d}-WA{rng.randint(1, 60):04d}.opus",
            f"Screenshot_{taken:%Y%m%d-%H%M%S}.png",
        ]
    return rng.choice(forms)
