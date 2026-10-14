"""Families on Baker's no-contact and count templates, and the zone edge.

The record is a message, an attachment or a call between the two named parties (both shown):
plainly inside the window (bk_no_contact_inside contradicts; bk_count_one complicates, since one
message cannot settle a count), on a phone the assumption does not name (bk_other_phone), plainly
outside (bk_outside_window, irrelevant), or inside in one zone reading only (bk_zone_edge).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from eval.train.baker_fam_time import _call, _message, edge_words, other_zone, when
from eval.train.baker_kit import (
    Draft,
    Setup,
    chat,
    lang_of_text,
    pick_kind,
    record_text,
    setup,
    with_other_phone,
)
from eval.train.baker_parties import call_context, call_event, call_parties, two_parties
from eval.train.baker_place import edge, inside, outside
from eval.train.baker_scene import Ev, render
from eval.train.baker_text import salt_of, spread
from eval.train.baker_time import Win, inside_any, inside_both, wall

KIND_WORD = {"msg": "a message", "att": "an attachment", "call": "a call"}


def file_name(rng: random.Random, k: int, family: str, local: datetime, dated: bool) -> str:
    """An attachment's file name: camera-style with the capture time, or a numbered photo."""
    if not dated:
        n = 1000 + spread(k, 9000, salt_of(family + "|file"))[0]
        return f"IMG_{n}.{rng.choice(('HEIC', 'JPG', 'MOV', 'PNG'))}"
    shot = local - timedelta(seconds=rng.randint(5, 900))
    form = rng.choice(("IMG_{:%Y%m%d_%H%M%S}.jpg", "VID_{:%Y%m%d_%H%M%S}.mp4",
                       "Screenshot_{:%Y%m%d-%H%M%S}.png", "PXL_{:%Y%m%d_%H%M%S}.jpg"))  # fmt: skip
    return form.format(shot)


def _record(
    rng: random.Random, k: int, family: str, s: Setup, utc: datetime, kind: str, near_end: bool
) -> tuple[list[Ev], int]:
    """The record between the chat's two ends at utc, in its context. A message or attachment
    on a zone edge keeps its chat lines on the far side of the edge."""
    lang = "en"
    if kind == "call":
        outgoing = s.you_pid is None or rng.random() < 0.5
        call = call_event(rng, s, utc, outgoing, rng.randint(20, 1500))
        return call_context(rng, s, call, "ru" if rng.random() < 0.1 else "en", False)
    if kind == "att":
        text = file_name(rng, k, family, wall(utc, s.phone.zone), dated=False)
    else:
        text, _ = record_text(rng, k, family)
        lang = lang_of_text(text)
    nb = na = None
    if family == "bk_zone_edge":
        nb, na = (0, rng.randint(1, 3)) if near_end else (rng.randint(1, 3), 0)
    return chat(rng, s, text, utc, rng.random() < 0.5, lang, 600, nb, na, kind=kind)


def _between_lines(evs: list[Ev], s: Setup) -> list[Ev]:
    """The lines whose two ends are the chat's owner and its partner, on any of their accounts."""
    a = s.scene.holders(s.phone.person)
    b = frozenset({s.you, s.you_phone}) | (s.scene.holders(s.you_pid) if s.you_pid else set())
    return [e for e in evs if e.between(a, frozenset(b))]


def _contact(
    rng: random.Random, k: int, family: str, place: str, template: str, side: str = ""
) -> tuple[Draft, Win, Ev, Setup]:
    """A record between the named parties against a window; params name both parties."""
    kinds = ("msg", "msg", "msg", "att") if template == "message_count" else (
        "msg", "msg", "att", "call", "call")  # fmt: skip
    kind = rng.choice(kinds)
    s = setup(rng, pick_kind(rng, (4, 3, 3)))
    if family == "bk_other_phone":
        s = with_other_phone(rng, s)
    tz = other_zone(rng, s.phone.zone) if rng.random() < 0.2 else s.phone.zone
    if place == "inside":
        win, utc = inside(rng, s.phone.zone, tz)
    elif place == "outside":
        win, utc = outside(rng, s.phone.zone, tz)
    else:
        win, utc = edge(rng, s.phone.zone, side)
    w = wall(utc, win.tz)
    near_end = abs(w - win.end) < abs(w - win.start)
    evs, target = _record(rng, k, family, s, utc, kind, near_end)
    rec = evs[target]
    if rec.kind == "call":
        params: dict[str, Any] = call_parties(rng, s, rec, two=True)
    else:
        params = two_parties(rng, s)
    params["window"] = win.tw
    if rng.random() < 0.3:
        params["channels"] = ("call",) if rec.kind == "call" else (s.app,)
    for e in _between_lines(evs, s):  # no other line between the parties changes the answer
        if e is rec or place == "inside" or e.utc is None:
            continue
        test = inside_any if place == "outside" else inside_both
        if test(win, e.utc, s.phone.zone):
            raise ValueError("a context line between the parties is inside the window")
    line = render(s.scene, s.phone, rec)
    at = when(line.local_time, win, utc, s.phone.zone)
    d = Draft(family, template, params, s.scene, s.phone, evs, target, line.text, "",
              {"utc": utc})  # fmt: skip
    d.rationale = f"The record is {KIND_WORD[rec.kind]} between the named parties at {at}"
    return d, win, rec, s


def _count(rng: random.Random, d: Draft, win: Win, s: Setup, device: str) -> None:
    """Count parameters whose number the excerpt cannot reach: more than every line it shows
    inside the window, whoever sent them."""
    shown = sum(1 for e in d.evs if e.utc is not None and inside_any(win, e.utc, s.phone.zone))
    d.params |= {"device_ids": (device,), "count_op": rng.choice(("eq", "ge", "le")),
                 "expected_count": rng.randint(max(2, shown + 1), max(8, shown + 40))}  # fmt: skip


def _devices(rng: random.Random, s: Setup) -> tuple[str, ...]:
    pick = rng.random()
    if pick < 0.5:
        return ()
    if pick < 0.8 or s.other is None:
        return (s.phone.dev,)
    return tuple(sorted((s.phone.dev, s.other.dev)))


def no_contact_inside(rng: random.Random, k: int) -> Draft:
    d, win, rec, s = _contact(rng, k, "bk_no_contact_inside", "inside", "no_contact")
    if devices := _devices(rng, s):
        d.params["device_ids"] = devices
    d.rationale += (f", plainly inside \"{win.raw}\" ({win.tz}), on {s.phone.dev}, a phone the "
                    "assumption covers.")  # fmt: skip
    return d


def count_one(rng: random.Random, k: int) -> Draft:
    d, win, rec, s = _contact(rng, k, "bk_count_one", "inside", "message_count")
    _count(rng, d, win, s, s.phone.dev)
    d.rationale += (f", inside \"{win.raw}\" ({win.tz}) on {s.phone.dev}: one of the counted "
                    "messages, which cannot settle how many the phone holds.")  # fmt: skip
    return d


def other_phone(rng: random.Random, k: int) -> Draft:
    template = ("no_contact", "message_count")[k % 2]
    d, win, rec, s = _contact(rng, k, "bk_other_phone", "inside", template)
    if s.other is None:
        raise ValueError("bk_other_phone needs a second phone")
    if template == "message_count":
        _count(rng, d, win, s, s.other.dev)
    else:
        d.params["device_ids"] = (s.other.dev,)
    d.rationale += (f", inside \"{win.raw}\" ({win.tz}), but it is on {s.phone.dev}: it shows "
                    f"the contact, not what {s.other.dev} holds.")  # fmt: skip
    return d


def outside_window(rng: random.Random, k: int) -> Draft:
    template = ("no_contact", "message_count")[k % 2]
    d, win, rec, s = _contact(rng, k, "bk_outside_window", "outside", template)
    if template == "message_count":
        _count(rng, d, win, s, s.phone.dev)
    elif devices := _devices(rng, s):
        d.params["device_ids"] = devices
    d.rationale += f', plainly outside "{win.raw}" ({win.tz}), so it does not bear on it.'
    return d


def zone_edge(rng: random.Random, k: int) -> Draft:
    side = ("phone", "tz")[(k // 2) % 2]
    if k % 2 == 0:
        if rng.random() < 0.6:
            d, win = _message(rng, k, "bk_zone_edge", "edge", side)
        else:
            d, win, _ = _call(rng, "edge", "bk_zone_edge", side)
        zone = d.phone.zone
    else:
        d, win, rec, s = _contact(rng, k, "bk_zone_edge", "edge", "no_contact", side)
        if devices := _devices(rng, s):
            d.params["device_ids"] = devices
        zone = s.phone.zone
    d.rationale += ", " + edge_words(win, d.notes["utc"], zone)
    d.notes["side"] = side
    return d
