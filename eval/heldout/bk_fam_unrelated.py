"""The writer for bk_unrelated: an assumption in any Baker template and a record that holds
none of its quoted words and does not involve its named parties on the matter: another message
from the same account, a file, a call or message with a third party, an unrelated contact row."""

from __future__ import annotations

import random

from eval.heldout import bk_cues as cues
from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import call_scene, pair, shown_as
from eval.heldout.bk_common import BkDraft, pick
from eval.heldout.bk_fam_contact import contact_phone, other_name
from eval.heldout.bk_scene import Acct, Excerpt, Phone, Scene
from eval.heldout.bk_schedule import BkSlot
from eval.stancedata import bakerform as bf

_NC_KINDS = (*pk.DATE_KINDS, "between")


def _plan_day(text: str) -> int:
    """The weekday a weekday plan names (Monday 0)."""
    low = text.lower()
    for d, name in enumerate(cues.DAYS_EN):
        if name in low:
            return d
    for d, form in enumerate(cues.DAYS_RU[""]):
        if form in low:
            return d
    raise ValueError(f"no weekday in {text!r}")


def _draft(
    s: BkSlot,
    template: str,
    params: dict[str, object],
    ex: Excerpt,
    why: str,
    ph: Phone,
    sc: Scene,
    win: bt.Win | None = None,
) -> BkDraft:
    return BkDraft(s.family, template, params, ex, ex.record.text, why, ph, s.lang, sc, win,
                   facts={"variant": s.variant})  # fmt: skip


def unrelated(s: BkSlot, rng: random.Random) -> BkDraft:
    v = s.variant
    if v in ("time_call3", "nc_call3", "meaning_call"):
        return _call(s, rng)
    if v in ("contact_other", "role_event_row"):
        return _row(s, rng)
    # handles live on Telegram or Instagram; a chat elsewhere comes from neither handle
    pr = pair(rng, s, app=rng.choice(("SMS", "Signal", "WhatsApp")) if v == "same_acct" else None)
    mine = rng.random() < 0.5
    utc = pk.some_time(rng, pr.p.tz)
    text = s.text
    if v == "sender_att":
        text = pk.attachment_name(rng, utc, pr.p.tz, dated=rng.random() < 0.5, photos=True)
    ex = pr.chat(rng, s, utc, text, mine, avoid=(s.q,))
    sender = pr.sender(mine)
    who = shown_as(pr.sc, pr.p, sender)
    if v in ("sender_same", "sender_att"):
        params: dict[str, object] = {"quoted_text": s.q, "account_ids": [pr.p.aid(sender)]}
        what = "a file" if v == "sender_att" else "another message"
        why = pick(
            rng,
            f"The record is {what} from the same account, {who}; it holds none of the quoted "
            "words and does not bear on who sent them.",
            f"Nothing in the record matches the quoted words: it is {what} from {who}, which "
            "says nothing about the message the assumption is about.",
        )
        return _draft(s, "sender", params, ex, why, pr.p, pr.sc)
    if v == "time_msg":
        win = pk.pick_window(rng, pr.p.tz, _NC_KINDS)
        params = {"quoted_text": s.q, "window": win.tw()}
        why = (
            "The record holds none of the quoted words, so its time says nothing about when "
            "the quoted message was sent."
        )
        return _draft(s, "record_time", params, ex, why, pr.p, pr.sc, win)
    if v == "count_third":
        y = pr.sc.new(rng, pr.me.app)
        win = pk.pick_window(rng, pr.p.tz, _NC_KINDS)
        params = {"device_ids": [pr.p.dev], "person_ids": [pr.p.owner],
                  "account_ids": [pr.p.aid(y)], "window": win.tw(),
                  "expected_count": rng.choice((2, 4, 7, 12)), "count_op": "ge"}  # fmt: skip
        why = (
            f"The record is between the owner and {shown_as(pr.sc, pr.p, pr.other)}, not "
            f"{y.ident}, so it is not one of the messages the assumption counts."
        )
        return _draft(s, "message_count", params, ex, why, pr.p, pr.sc, win)
    if v == "same_acct":
        app, old, new = s.handles
        params = {"channels": [app], "handles": [old, new]}
        why = (
            "The record mentions neither handle, so it does not bear on whether they are one "
            "account."
        )
        return _draft(s, "same_account", params, ex, why, pr.p, pr.sc)
    if v == "weekday_msg":
        day = _plan_day(s.q)
        target = bt.base_day(rng)
        target = target.fromordinal(target.toordinal() + (day - target.weekday()) % 7)
        win = bt.weekday_day(target, pr.p.tz)
        params = {"quoted_text": s.q, "window": win.tw()}
        why = (
            "The record holds none of the quoted words, so it does not bear on which date "
            "they mean."
        )
        return _draft(s, "weekday_date", params, ex, why, pr.p, pr.sc, win)
    # ident_other: the named account is not on screen; the record comes from someone else
    named = pr.sc.new(rng, pr.me.app)
    params = {"person_ids": [bf.named_person(s.person)], "account_ids": [pr.p.aid(named)]}
    why = (
        f"The record comes from {who}, not the named account, and says nothing about who "
        "holds that account."
    )
    return _draft(s, "person_identity", params, ex, why, pr.p, pr.sc)


def _call(s: BkSlot, rng: random.Random) -> BkDraft:
    """A call record: with a third party (time and no-contact forms) or any call (meaning)."""
    v = s.variant
    c = call_scene(rng, s, rng.choice(("out_person", "in_linked")))
    third = c.to if c.direction == "outgoing" else c.frm
    win = pk.pick_window(rng, c.p.tz, _NC_KINDS)
    utc = bt.place_inside(rng, win, c.p.tz)
    ex = c.excerpt(rng, utc, pk.duration(rng))
    said = c.said()
    if v == "meaning_call":
        params: dict[str, object] = {"quoted_text": s.q}
        why = (
            f"The record is {said}; it holds none of the quoted words and does not bear on "
            "what they mean."
        )
        return _draft(s, "meaning", params, ex, why, c.p, c.sc)
    y = c.sc.new(rng, "Phone")
    params = {"person_ids": [c.p.owner], "account_ids": [c.p.aid(y)], "window": win.tw()}
    why = (
        f"The record is {said}; its other side is {third.ident}, not {y.ident}, so it is "
        "not a call between the named parties."
    )
    if v == "time_call3":
        params["channels"] = ["call"]
        return _draft(s, "record_time", params, ex, why, c.p, c.sc, win)
    why = why.replace("not a call", "not contact")
    return _draft(s, "no_contact", params, ex, why, c.p, c.sc, win)


def _row(s: BkSlot, rng: random.Random) -> BkDraft:
    """A contact row that holds neither the name nor the number the assumption gives, or that
    sits beside a role or event assumption it has no bracketed person for."""
    ru = s.lang == "ru"
    sc, p = contact_phone(rng, "ru" if ru else "en")
    rec = sc.contact(p, s.contact, sc.number(rng))
    ex = Excerpt([rec], 0)
    if s.variant == "contact_other":
        name, number = other_name(rng, s.contact, ru, share_one=False), sc.number(rng)
        params: dict[str, object] = {"device_ids": [p.dev], "quoted_text": name,
                                     "account_ids": [p.aid(Acct("Phone", number))]}  # fmt: skip
        why = (
            f'The row "{rec.text}" holds neither the name "{name}" nor the number {number}, '
            "so it does not bear on that entry."
        )
        return _draft(s, "contact_entry", params, ex, why, p, sc)
    person = bf.named_person(s.person)
    if (s.k // 12) % 2 == 0:
        params = {"person_ids": [person]}
        template = "role"
    else:
        win = pk.pick_window(rng, p.tz, _NC_KINDS)
        params = {"person_ids": [person], "window": win.tw()}
        template = "event"
    why = (
        f"The record is a contact row; it neither comes from nor goes to an account "
        f"bracketed with {person}."
    )
    return _draft(s, template, params, ex, why, p, sc)
