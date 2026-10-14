"""Writers for the time families of messages and calls: bk_time_inside, bk_time_outside and
bk_zone_edge."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta

from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import CALL_FORMS, Pair, call_scene, channel, merge, owner_style, pair
from eval.heldout.bk_common import BkDraft, clause, pick, shown_in, window_words
from eval.heldout.bk_fam_call import call_item
from eval.heldout.bk_scene import Excerpt, other_zone
from eval.heldout.bk_schedule import BkSlot

_STYLE = {"anyone": "none", "acct": "acct", "owner_person": "owner", "linked": "linked",
          "msg_acct": "acct", "msg_anyone": "none", "msg_person": "owner",
          "msg_linked": "linked"}  # fmt: skip


def _party(rng: random.Random, pr: Pair, style: str) -> tuple[dict[str, list[str]], bool, str]:
    """(params naming the sender, whether the owner sent the record, how a rationale names
    the sender) for a sender style: none, acct, owner or linked."""
    if style == "owner":
        who = f"the owner's account, whose line carries {pr.p.owner}"
        return {"person_ids": [pr.p.owner]}, True, who
    if style == "linked":
        who = f"{pr.other.app} {pr.other.ident}, whose line carries {pr.linked}"
        return {"person_ids": [pr.linked]}, False, who
    mine = rng.random() < 0.4
    a = pr.sender(mine)
    if style == "acct":
        return {"account_ids": [pr.p.aid(a)]}, mine, f"{a.app} {a.ident}, the named account"
    return {}, mine, ""


def _message(
    s: BkSlot,
    rng: random.Random,
    style: str,
    win_of: Callable[[Pair], bt.Win],
    place: Callable[[random.Random, bt.Win, str], datetime],
) -> tuple[Pair, bt.Win, Excerpt, str, dict[str, object], str]:
    pr = pair(rng, s, linked=style == "linked")
    win = win_of(pr)
    utc = place(rng, win, pr.p.tz)
    party, mine, who = _party(rng, pr, style)
    ex = pr.chat(rng, s, utc, s.text, mine)
    q = clause(rng, s.text)
    params = {"quoted_text": q, "window": win.tw(), **merge(party, channel(rng, pr.me.app, 0.2))}
    return pr, win, ex, q, params, who


def inside(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_time_inside: the quoted words, from the named sender if one is named, at a local
    time plainly inside the window in the named zone (and on the phone's clock)."""
    v = s.variant
    style = _STYLE.get(v) or rng.choice(("none", "acct", "acct", "owner"))

    def win_of(pr: Pair) -> bt.Win:
        if v == "about":
            return pk.pick_window(rng, pr.p.tz, ("about",))
        tz = other_zone(rng, pr.p.tz) if v == "cross_zone" else pr.p.tz
        return pk.pick_window(rng, pr.p.tz, (*pk.DATE_KINDS, "between"), tz)

    pr, win, ex, q, params, who = _message(s, rng, style, win_of, bt.place_inside)
    rec = ex.record
    by = f" from {who}" if who else ""
    if v == "about":
        why = (
            f"The record holds the quoted words{by}, sent at {rec.local_time}, within "
            f"minutes of the time {window_words(win)} gives."
        )
    elif win.tz != pr.p.tz:
        why = (
            f"The record holds the quoted words{by}; its local time {rec.local_time} is "
            f"{shown_in(rec.utc, win.tz)} in {win.tz}, inside {window_words(win)} on "
            "either clock."
        )
    else:
        why = pick(
            rng,
            f"The record holds the quoted words{by}, and its local time {rec.local_time} is "
            f"inside {window_words(win)}.",
            f"Sent at {rec.local_time}, the record falls inside {window_words(win)} and holds "
            f"the quoted words{by}.",
        )
    return BkDraft(s.family, "record_time", params, ex, q, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": v})  # fmt: skip


def _any_window(rng: random.Random, phone_tz: str) -> bt.Win:
    """Any window kind; now and then in another zone (never "at about" there)."""
    if rng.random() < 0.2:
        return pk.pick_window(rng, phone_tz, (*pk.DATE_KINDS, "between"),
                              other_zone(rng, phone_tz))  # fmt: skip
    return pk.pick_window(rng, phone_tz)


def outside(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_time_outside: the named message, or a call between the named parties, plainly
    outside the window in both zones."""
    v = s.variant
    if v.startswith("call"):
        c = call_scene(rng, s, "out_person" if v == "call_person" else "in_linked")
        win = _any_window(rng, c.p.tz)
        utc = bt.place_outside(rng, win, c.p.tz)
        why = pick(
            rng,
            "{Call} has local time {local}, outside {win}; one record cannot show there was "
            "no call between them inside it.",
            "The call between the named parties is at {local}, well outside {win}; another "
            "call inside the window may exist, so the record leaves it open.",
        )
        return call_item(s, rng, c, win, utc, pk.duration(rng), None, why)
    style = _STYLE[v]
    pr, win, ex, q, params, who = _message(
        s, rng, style, lambda pr: _any_window(rng, pr.p.tz), bt.place_outside
    )
    rec = ex.record
    by = f" from {who}" if who else ""
    why = pick(
        rng,
        f"The record holds the quoted words{by}, but its local time {rec.local_time} is "
        f"outside {window_words(win)}; one record cannot show the same words were not also "
        "sent inside it.",
        f"Sent at {rec.local_time}, the record is outside {window_words(win)}; the same words "
        "may have been sent again inside the window, so the record leaves it open.",
    )
    return BkDraft(s.family, "record_time", params, ex, q, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": v})  # fmt: skip


# ------------------------------------------------------------------ bk_zone_edge

_EDGE_KINDS = ("on", "On", "through", "between")


def _near_end(utc: datetime, win: bt.Win) -> bool:
    start, end = bt.wall_utc(win.start, win.tz), bt.wall_utc(win.end, win.tz)
    return abs(utc - end) < abs(utc - start)


def _edge_words(want: str, local: str, there: str, win: bt.Win) -> str:
    if want == "phone":
        return (
            f'On the phone\'s clock the record is at {local}, inside the words "{win.raw}"; '
            f"read in {win.tz}, the window's zone, the same moment is {there}, outside "
            "them, so the answer turns on the zone."
        )
    return (
        f"Read in {win.tz}, the window's zone, the record's moment is {there}, inside "
        f'"{win.raw}"; on the phone\'s own clock it is {local}, outside those words, so the '
        "answer depends on the zone."
    )


def edge(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_zone_edge: the window is in another zone than the phone's, and the record is inside
    it in one zone and outside it in the other, by ten minutes or more."""
    v = s.variant
    want = "phone" if v.endswith("_phone") else "named"
    if v.startswith("call"):
        c = call_scene(rng, s, rng.choice(CALL_FORMS))
        win = pk.pick_window(rng, c.p.tz, _EDGE_KINDS, other_zone(rng, c.p.tz))
        utc = bt.place_flip(rng, win, c.p.tz, want)
        why = _edge_words(want, "{local}", "{there}", win).replace("the record", "the call")
        return call_item(s, rng, c, win, utc, pk.duration(rng), None, why)
    pr = pair(rng, s, linked=rng.random() < 0.25)
    win = pk.pick_window(rng, pr.p.tz, _EDGE_KINDS, other_zone(rng, pr.p.tz))
    utc = bt.place_flip(rng, win, pr.p.tz, want)
    mine = rng.random() < 0.5
    where = "after" if _near_end(utc, win) else "before"
    if v.startswith("msg"):
        ex = pr.chat(rng, s, utc, s.text, mine)
        q = clause(rng, s.text)
        sender = pr.sender(mine)
        party = {"account_ids": [pr.p.aid(sender)]} if rng.random() < 0.5 else {}
        params: dict[str, object] = {"quoted_text": q, "window": win.tw(), **party}
        template, quote = "record_time", q
    else:
        ex = pr.chat(rng, s, utc, s.text, mine, where=where)
        for ln in ex.lines:
            if ln is not ex.record and ln.utc is not None:
                both = min(bt.inside_by(ln.utc, win, z) for z in (win.tz, pr.p.tz))
                if both >= timedelta(0):
                    raise RuntimeError("a context line falls inside the window in both zones")
        them = {"person_ids": [pr.linked]} if pr.linked else {"account_ids": [pr.p.aid(pr.other)]}
        if "account_ids" in them:
            mine_part: dict[str, list[str]] = {"person_ids": [pr.p.owner]}
        else:
            mine_part = owner_style(rng, pr)
        params = {**merge(them, mine_part), "window": win.tw()}
        if rng.random() < 0.4:
            params["device_ids"] = [pr.p.dev]
        template, quote = "no_contact", s.text
    rec = ex.record
    why = _edge_words(want, rec.local_time, shown_in(utc, win.tz), win)
    return BkDraft(s.family, template, params, ex, quote, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": v, "want": want})  # fmt: skip
