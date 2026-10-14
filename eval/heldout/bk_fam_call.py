"""Writers for the call families, bk_call_inside and bk_call_length, and the call record the
time families share. A call's line shows the calling number's account; the assumption names
that side by the person id its brackets carry and the other side by its Phone account id."""

from __future__ import annotations

import random
from datetime import datetime

from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import Call, call_scene
from eval.heldout.bk_common import BkDraft, pick, shown_in, window_words
from eval.heldout.bk_scene import other_zone
from eval.heldout.bk_schedule import BkSlot


def call_item(
    s: BkSlot,
    rng: random.Random,
    c: Call,
    win: bt.Win,
    utc: datetime,
    dur: int,
    duration: tuple[int, int] | None,
    why: str,
    where: str = "both",
) -> BkDraft:
    """A record_time item about a call between the two parties c names. `why` may use
    {call} {Call} {local} {win} {dur} {person} {aid} {num} {there} {tz}."""
    ex = c.excerpt(rng, utc, dur, where=where)
    params: dict[str, object] = {**c.params(), "channels": ["call"], "window": win.tw()}
    if duration is not None:
        params["duration_s"] = list(duration)
    rec = ex.record
    said = c.said()
    why = why.format(call=said, Call=said[:1].upper() + said[1:], local=rec.local_time,
                     win=window_words(win), dur=dur, person=c.person, aid=c.acct_id,
                     num=c.to.ident, there=shown_in(utc, win.tz), tz=win.tz)  # fmt: skip
    return BkDraft(s.family, "record_time", params, ex, rec.text, why, c.p, s.lang, c.sc, win,
                   facts={"variant": s.variant, "dur": dur, "duration": duration})  # fmt: skip


def inside(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_call_inside: a call between the named parties, plainly inside the window, and inside
    the length range with a tenth to spare if one is given."""
    c = call_scene(rng, s, s.variant)
    cross_zone = rng.random() < 0.25
    tz = other_zone(rng, c.p.tz) if cross_zone else c.p.tz
    kinds = (*pk.DATE_KINDS, "between") if cross_zone else pk.ALL_KINDS
    win = pk.pick_window(rng, c.p.tz, kinds, tz)
    utc = bt.place_inside(rng, win, c.p.tz)
    dur = pk.duration(rng)
    span = pk.range_holding(rng, dur) if rng.random() < 0.5 else None
    long = f", and it lasted {dur}s, within {span[0]} to {span[1]} s" if span else ""
    there = " ({there} in {tz})" if cross_zone else ""
    why = pick(
        rng,
        "The call line carries {person}, the call text shows the other number, {num}, which "
        "{aid} names, and its local time {local}" + there + " is inside {win}" + long + ".",
        "{Call} is between the named parties: its line carries {person} and the other number "
        "is {num} ({aid}); at {local}" + there + " it falls inside {win}" + long + ".",
    )
    return call_item(s, rng, c, win, utc, dur, span, why)


def length(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_call_length: a call between the named parties inside the window whose length is
    under half the stated minimum or over twice the stated maximum."""
    short = s.variant.startswith("short")
    if s.variant.endswith("_out"):
        form = rng.choice(("out_person", "cross_out"))
    else:
        form = rng.choice(("in_linked", "cross_in"))
    c = call_scene(rng, s, form)
    win = pk.pick_window(rng, c.p.tz)
    utc = bt.place_inside(rng, win, c.p.tz)
    dur = pk.short_call(rng) if short else pk.long_call(rng)
    lo, hi = pk.range_missing(rng, dur, short)
    why = pick(
        rng,
        "{Call} at {local} is inside {win}, but it lasted {dur}s, outside "
        f"{lo} to {hi} s; one record cannot show there was no other call between them that "
        "fits.",
        "The call between the named parties falls inside {win}, yet its length, {dur}s, is "
        f"far from {lo} to {hi} s; another call that fits may exist, so the record leaves it "
        "open.",
    )
    return call_item(s, rng, c, win, utc, dur, (lo, hi), why)
