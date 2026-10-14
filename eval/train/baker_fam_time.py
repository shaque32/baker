"""Families on Baker's time template: a message or a call against a stated window.

The answer rests on the record's time (and sender), so the quote is the record's full text
(guide rule 22); the assumption's quoted words are all of it or a span of it.

bk_time_inside and bk_call_inside are supports (plainly inside, the named sender or parties
shown); bk_time_outside (plainly outside), bk_call_length (inside, wrong length) and bk_zone_edge
(inside in one zone reading only) are complicates.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from eval.stancedata import bakerform as bf
from eval.stancedata.chat import local_str
from eval.train.baker_kit import (
    Draft,
    Setup,
    chat,
    lang_of_text,
    pick_kind,
    quoted_words,
    record_text,
    setup,
)
from eval.train.baker_parties import (
    call_context,
    call_event,
    call_parties,
    length_outside,
    name_account,
    range_holding,
)
from eval.train.baker_place import edge, inside, outside
from eval.train.baker_scene import render
from eval.train.baker_time import Win, wall

T = "record_time"


def other_zone(rng: random.Random, zone: str) -> str:
    return rng.choice([z for z in bf.ZONES if z != zone])


def when(local_time: str, win: Win, utc: datetime, zone: str) -> str:
    """'2026-05-02 21:10:44 CDT', with the reading in the window's zone when it differs."""
    if win.tz == zone:
        return local_time
    return f"{local_time} ({local_str(utc, win.tz)} in {win.tz})"


def _message(
    rng: random.Random, k: int, family: str, place: str, side: str = ""
) -> tuple[Draft, Win]:
    """A quoted message with an optional named sender, placed against a window."""
    text, core = record_text(rng, k, family)
    lang = lang_of_text(text)
    s = setup(rng, pick_kind(rng), lang=lang)
    tz = other_zone(rng, s.phone.zone) if place == "edge" or rng.random() < 0.2 else s.phone.zone
    if place == "inside":
        win, utc = inside(rng, s.phone.zone, tz)
    elif place == "outside":
        win, utc = outside(rng, s.phone.zone, tz)
    else:
        win, utc = edge(rng, s.phone.zone, side)
    quoted = quoted_words(rng, text, core)
    evs, target = chat(rng, s, text, utc, rng.random() < 0.5, lang, avoid=quoted)
    rec = evs[target]
    params: dict[str, Any] = {"quoted_text": quoted, "window": win.tw}
    line = render(s.scene, s.phone, rec)
    who = ""
    if rng.random() < 0.6:
        params |= name_account(rng, s, rec.frm)
        who = f" from {line.sender}"
    at = when(line.local_time, win, utc, s.phone.zone)
    d = Draft(family, T, params, s.scene, s.phone, evs, target, text, "", {"utc": utc})
    d.rationale = f"The record holding the quoted words{who} was sent {at}"
    return d, win


def _call(
    rng: random.Random, place: str, family: str, side: str = "", wrong_length: bool = False
) -> tuple[Draft, Win, Setup]:
    """A call between the named parties, placed against a window."""
    s = setup(rng, pick_kind(rng, (3, 3, 4)))
    tz = other_zone(rng, s.phone.zone) if place == "edge" or rng.random() < 0.15 else s.phone.zone
    if place == "inside":
        win, utc = inside(rng, s.phone.zone, tz)
    elif place == "outside":
        win, utc = outside(rng, s.phone.zone, tz)
    else:
        win, utc = edge(rng, s.phone.zone, side)
    stated: tuple[int, int] | None = None
    if wrong_length:
        stated, dur = length_outside(rng)
    else:
        dur = rng.randint(20, 1500)
        stated = range_holding(rng, dur) if rng.random() < 0.5 else None
    call = call_event(rng, s, utc, rng.random() < 0.55, dur)
    lang = "ru" if rng.random() < 0.1 else "en"
    evs, target = call_context(rng, s, call, lang, with_partner=rng.random() < 0.5)
    params = call_parties(rng, s, call) | {"channels": ("call",), "window": win.tw}
    if stated is not None:
        params["duration_s"] = stated
    line = render(s.scene, s.phone, call)
    d = Draft(family, T, params, s.scene, s.phone, evs, target, line.text, "", {"utc": utc})
    lasted = f", lasting {dur}s" + (f" against the stated {stated[0]} to {stated[1]} s"
                                    if stated else "")  # fmt: skip
    at = when(line.local_time, win, utc, s.phone.zone)
    d.rationale = f"The call line shows {line.sender}; the call between the named parties{lasted}"
    d.rationale += f", is at {at}"
    return d, win, s


def time_inside(rng: random.Random, k: int) -> Draft:
    d, win = _message(rng, k, "bk_time_inside", "inside")
    d.rationale += f', plainly inside "{win.raw}" ({win.tz}).'
    return d


def call_inside(rng: random.Random, k: int) -> Draft:
    d, win, _ = _call(rng, "inside", "bk_call_inside")
    d.rationale += f', plainly inside "{win.raw}" ({win.tz}).'
    return d


def time_outside(rng: random.Random, k: int) -> Draft:
    if rng.random() < 0.6:
        d, win = _message(rng, k, "bk_time_outside", "outside")
        d.rationale += (f", plainly outside \"{win.raw}\" ({win.tz}); one record cannot show "
                        "that no matching message was sent inside it.")  # fmt: skip
        return d
    d, win, _ = _call(rng, "outside", "bk_time_outside")
    d.rationale += (f", plainly outside \"{win.raw}\" ({win.tz}); one record cannot show that "
                    "no call between them happened inside it.")  # fmt: skip
    return d


def call_length(rng: random.Random, k: int) -> Draft:
    d, win, _ = _call(rng, "inside", "bk_call_length", wrong_length=True)
    d.rationale += (f", inside \"{win.raw}\" ({win.tz}), but its length is outside the stated "
                    "range; one record cannot show there was no other call.")  # fmt: skip
    return d


def edge_words(win: Win, utc: datetime, zone: str) -> str:
    """Which reading holds the record: 'inside "<raw>" read in <zone A> but outside it in <B>'."""
    inside_tz = wall(utc, win.tz)
    holds = win.start <= inside_tz < win.end
    yes, no = (win.tz, zone) if holds else (zone, win.tz)
    return (f"inside \"{win.raw}\" read in {yes} but outside it in {no}, so the answer "
            "depends on the time zone.")  # fmt: skip
