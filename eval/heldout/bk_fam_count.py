"""Writers for the count and no-contact families: bk_count_one, bk_no_contact_inside,
bk_other_phone and bk_outside_window. Every record is between the two named parties, both on
screen: a message in their one-to-one chat (or a file sent there), or a call between them."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import (
    CALL_FORMS,
    Call,
    Pair,
    call_scene,
    channel,
    count_params,
    extra_phone,
    merge,
    pair,
    scene_lang,
    shown_as,
    two_parties,
)
from eval.heldout.bk_common import BkDraft, pick, window_words
from eval.heldout.bk_scene import Excerpt, other_zone
from eval.heldout.bk_schedule import BkSlot

NC_KINDS = (*pk.DATE_KINDS, "between")
_OP_WORDS = {"eq": "exactly", "ge": "at least", "le": "at most"}


def _win(rng: random.Random, tz: str) -> bt.Win:
    """A window for a count or no-contact assumption, now and then in another zone."""
    if rng.random() < 0.2:
        return pk.pick_window(rng, tz, NC_KINDS, other_zone(rng, tz))
    return pk.pick_window(rng, tz, NC_KINDS)


def _message(
    rng: random.Random, s: BkSlot, pr: Pair, utc: datetime, attach: bool
) -> tuple[Excerpt, str]:
    """The record between the chat's two sides: the slot's words or a file name."""
    if attach:
        text = pk.attachment_name(rng, utc, pr.p.tz, dated=rng.random() < 0.6)
    else:
        text = s.text
    return pr.chat(rng, s, utc, text, rng.random() < 0.5), text


def _sides(pr: Pair) -> str:
    return f"{shown_as(pr.sc, pr.p, pr.me)} and {shown_as(pr.sc, pr.p, pr.other)}"


def _what(attach: bool) -> str:
    return "a file sent" if attach else "a message"


def count_one(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_count_one: one message between the named parties on the named phone, plainly inside
    the window; the chat on screen holds fewer messages than the stated count."""
    pr, parties = two_parties(rng, s)
    win = _win(rng, pr.p.tz)
    utc = bt.place_inside(rng, win, pr.p.tz)
    ex, text = _message(rng, s, pr, utc, False)
    cp = count_params(rng, len(ex.lines), s.variant)
    params = {"device_ids": [pr.p.dev], **merge(parties, channel(rng, pr.me.app, 0.25)),
              "window": win.tw(), **cp}  # fmt: skip
    goal = f"{_OP_WORDS[s.variant]} {cp['expected_count']}"
    why = pick(
        rng,
        f"The record is one message between the named parties on {pr.p.dev} at "
        f"{ex.record.local_time}, inside {window_words(win)}; one message cannot show whether "
        f"the phone holds {goal}.",
        f"This message between {_sides(pr)} falls inside {window_words(win)} and is one of "
        f"those counted, but one record cannot settle whether {pr.p.dev} holds {goal}.",
    )
    return BkDraft(s.family, "message_count", params, ex, text, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": s.variant})  # fmt: skip


def _call_parties(rng: random.Random, s: BkSlot) -> Call:
    return call_scene(rng, s, rng.choice(CALL_FORMS))


def _call_words(c: Call, local: str) -> str:
    return (f"{c.said()} at {local}, whose line carries {c.person} and whose text shows "
            f"{c.to.ident}, the number {c.acct_id} names")


def nc_inside(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_no_contact_inside: a message, file or call between the named parties, plainly inside
    the window, on a phone the assumption covers."""
    v = s.variant
    if v == "call":
        c = _call_parties(rng, s)
        win = _win(rng, c.p.tz)
        ex = c.excerpt(rng, bt.place_inside(rng, win, c.p.tz), pk.duration(rng))
        params: dict[str, object] = {**c.params(), "window": win.tw()}
        if rng.random() < 0.4:
            params["device_ids"] = [c.p.dev]
        what = _call_words(c, ex.record.local_time)
        why = (f"The record is {what}; it falls inside {window_words(win)}, so it shows contact "
               "between the two named parties in the window.")
        return BkDraft(s.family, "no_contact", params, ex, ex.record.text, why, c.p, s.lang,
                       c.sc, win, facts={"variant": v})  # fmt: skip
    if v == "msg_person" or (v == "attachment" and rng.random() < 0.5):
        if rng.random() < 0.5:
            pr = pair(rng, s)
            parties = {"person_ids": [pr.p.owner], "account_ids": [pr.p.aid(pr.other)]}
        else:
            pr = pair(rng, s, linked=True)
            parties = {"person_ids": [pr.linked], "account_ids": [pr.p.aid(pr.me)]}
    elif rng.random() < 0.5:
        pr, parties = two_parties(rng, s, "cross")
    else:
        pr = pair(rng, s, linked=True)
        parties = {"person_ids": [pr.p.owner, pr.linked]}
    win = _win(rng, pr.p.tz)
    attach = v == "attachment"
    ex, text = _message(rng, s, pr, bt.place_inside(rng, win, pr.p.tz), attach)
    params = {**merge(parties, channel(rng, pr.me.app, 0.25)), "window": win.tw()}
    if rng.random() < 0.4:
        params["device_ids"] = [pr.p.dev]
    why = pick(
        rng,
        f"The record is {_what(attach)} between {_sides(pr)} at {ex.record.local_time}, inside "
        f"{window_words(win)}, so it shows contact between the two named parties in the window.",
        f"Both named parties are on screen ({_sides(pr)}), and the record between them falls "
        f"inside {window_words(win)}: contact in the window.",
    )
    return BkDraft(s.family, "no_contact", params, ex, text, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": v})  # fmt: skip


def other_phone(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_other_phone: the assumption covers one named phone; the record, between the named
    parties and inside the window, is on another phone in the scene."""
    v = s.variant
    if v == "nc_call":
        c = _call_parties(rng, s)
        q = c.q or extra_phone(rng, c.sc)
        win = _win(rng, c.p.tz)
        ex = c.excerpt(rng, bt.place_inside(rng, win, c.p.tz), pk.duration(rng))
        params: dict[str, object] = {**c.params(), "window": win.tw(), "device_ids": [q.dev]}
        template, p, sc, quote = "no_contact", c.p, c.sc, ex.record.text
    else:
        pr, parties = two_parties(rng, s)
        q = pr.q or extra_phone(rng, pr.sc, scene_lang(s))
        win = _win(rng, pr.p.tz)
        ex, quote = _message(rng, s, pr, bt.place_inside(rng, win, pr.p.tz), v == "nc_attachment")
        params = {**parties, "window": win.tw(), "device_ids": [q.dev]}
        template, p, sc = "no_contact", pr.p, pr.sc
        if v == "count_msg":
            template = "message_count"
            params.update(count_params(rng, len(ex.lines)))
    why = pick(
        rng,
        f"The record, between the named parties inside {window_words(win)}, is on {p.dev}; the "
        f"assumption is about what {q.dev} holds, which this record does not show.",
        f"This contact between the named parties sits on {p.dev}, not on {q.dev}, the only "
        "phone the assumption covers, so it does not settle what that phone holds.",
    )
    return BkDraft(s.family, template, params, ex, quote, why, p, s.lang, sc, win,
                   facts={"variant": v, "named_device": q.dev})  # fmt: skip


def _outside_everywhere(ex: Excerpt, win: bt.Win, tz: str, calls: bool) -> bool:
    """Whether every line between the parties is outside the window in both zones."""
    lines = [ex.record] if calls else ex.lines
    return all(
        ln.utc is not None and bt.outside_by(ln.utc, win, z) > timedelta(0)
        for ln in lines
        for z in (win.tz, tz)
    )


def outside_window(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_outside_window: a message, file or call between the named parties, plainly outside
    the window in both zones, with no line between them inside it."""
    v = s.variant
    count = v.startswith("count")
    if v == "nc_call":
        c = _call_parties(rng, s)
        win = _win(rng, c.p.tz)
        ex = c.excerpt(rng, bt.place_outside(rng, win, c.p.tz), pk.duration(rng))
        params: dict[str, object] = {**c.params(), "window": win.tw()}
        p, sc, quote = c.p, c.sc, ex.record.text
    else:
        pr, parties = two_parties(rng, s)
        win = _win(rng, pr.p.tz)
        for _ in range(20):
            utc = bt.place_outside(rng, win, pr.p.tz)
            ex, quote = _message(rng, s, pr, utc, v == "count_attachment")
            if _outside_everywhere(ex, win, pr.p.tz, False):
                break
        else:
            raise RuntimeError("no excerpt wholly outside the window")
        params = {**merge(parties, channel(rng, pr.me.app, 0.2)), "window": win.tw()}
        p, sc = pr.p, pr.sc
    if count:
        params.update(device_ids=[p.dev], **count_params(rng, len(ex.lines)))
    elif rng.random() < 0.4:
        params["device_ids"] = [p.dev]
    about = "how many messages the window holds" if count else "contact inside the window"
    why = pick(
        rng,
        f"The record, between the named parties, is at {ex.record.local_time}, outside "
        f"{window_words(win)} in either zone, so it does not bear on {about}.",
        f"At {ex.record.local_time}, well clear of {window_words(win)}, the record says "
        f"nothing about {about}.",
    )
    template = "message_count" if count else "no_contact"
    return BkDraft(s.family, template, params, ex, quote, why, p, s.lang, sc, win,
                   facts={"variant": v})  # fmt: skip
