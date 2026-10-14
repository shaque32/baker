"""Writers for the sender families: bk_sender_shown, bk_sender_other and bk_party_unshown."""

from __future__ import annotations

import random
from datetime import timedelta

from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import (
    Pair,
    acct_ids,
    channel,
    count_params,
    merge,
    owner_style,
    pair,
    scene_lang,
    shown_as,
)
from eval.heldout.bk_common import BkDraft, clause, pick, window_words
from eval.heldout.bk_scene import Excerpt, Scene, items, zone
from eval.heldout.bk_schedule import BkSlot
from eval.stancedata import bakerform as bf

_NAME_LINES = ("thx {sur}", "ok {sur}, noted", "got it {sur}", "{sur} ur a lifesaver",
               "cheers {sur}", "perfect, ty {sur}", "nice one {sur}")  # fmt: skip


def shown(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_sender_shown: the record holds the quoted words, and its line shows the named
    sender, by account id or by the person id in its brackets."""
    v = s.variant
    pr = pair(rng, s, cross=v in ("cross", "acct_both"), linked=v == "linked")
    mine = v in ("acct_owner", "owner_person")
    sender = pr.sender(mine)
    ex = pr.chat(rng, s, pk.some_time(rng, pr.p.tz), s.text, mine)
    line = ex.record
    q = clause(rng, s.text)
    if v.startswith("acct"):
        ids = acct_ids(pr, sender, rng, both=v == "acct_both")
        party = {"account_ids": ids}
        if len(ids) == 2:
            why = (
                f"Both ids name one account, {sender.app} {sender.ident}, as the two phones "
                "list it, and the record's line shows it sending the quoted words."
            )
        else:
            why = pick(
                rng,
                f"The record holds the quoted words, and its sender line, {line.sender}, is the "
                "account the assumption names.",
                f"Its line shows {sender.app} {sender.ident} as the sender; {ids[0]} is that "
                "account on this phone, and the record holds the quoted words.",
            )
    else:
        if v == "owner_person":
            person = pr.p.owner
        elif v == "linked":
            person = pr.linked
        else:
            person = pr.q.owner if pr.q else ""
        party = {"person_ids": [person]}
        why = pick(
            rng,
            f"The record holds the quoted words, and its sender line carries {person} in "
            "brackets, a link Baker holds as confirmed.",
            f"Its line, {line.sender}, carries {person}, so the named person is shown as the "
            "sender of the quoted words.",
        )
    params = {"quoted_text": q, **merge(party, channel(rng, sender.app))}
    return BkDraft(s.family, "sender", params, ex, q, why, pr.p, s.lang, pr.sc,
                   facts={"variant": v})  # fmt: skip


def other(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_sender_other: the record holds the quoted words, but its line shows a different
    account or person than the one named, who is on screen too."""
    v = s.variant
    pr = pair(rng, s, cross=v == "named_cross", linked=v == "named_linked")
    if v == "named_owner":
        mine, named = False, pr.p.owner
    elif v == "named_third":
        mine, named = True, pr.p.aid(pr.other)
    elif v == "named_linked":
        mine, named = True, pr.linked
    else:
        mine = rng.random() < 0.5
        named = pr.q.owner if mine and pr.q else pr.p.owner
    party = {"account_ids": [named]} if named.startswith("acct:") else {"person_ids": [named]}
    ex = pr.chat(rng, s, pk.some_time(rng, pr.p.tz), s.text, mine)
    line = ex.record
    q = clause(rng, s.text)
    why = pick(
        rng,
        f"The record holds the quoted words, but its line shows {line.sender}, not {named}; one "
        "record cannot show that the named sender never sent the same words.",
        f"Here the quoted words come from {line.sender}, while the assumption names {named}; "
        "both may have sent them, so the record leaves the assumption open.",
    )
    params = {"quoted_text": q, **merge(party, channel(rng, pr.me.app))}
    return BkDraft(s.family, "sender", params, ex, q, why, pr.p, s.lang, pr.sc,
                   facts={"variant": v})  # fmt: skip


# ------------------------------------------------------------------ bk_party_unshown


def _name_line(rng: random.Random, pr: Pair, s: BkSlot, ex: Excerpt) -> None:
    """A line after the record in which the owner calls the sender by the person's surname."""
    text = rng.choice(_NAME_LINES).format(sur=s.person)
    t = ex.lines[-1].utc
    if t is None:
        raise ValueError("a chat line needs its time")
    ex.lines.append(pr.sc.msg(pr.p, pr.me, t + timedelta(seconds=rng.randint(40, 900)), text))


def window(rng: random.Random, tz: str) -> bt.Win:
    return pk.pick_window(rng, tz, (*pk.DATE_KINDS, "between"))


def unshown(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_party_unshown: the assumption names person:<slug>, which no line carries; the record
    otherwise fits (its words, its time, contact between the shown party and some account)."""
    v = s.variant
    slug = bf.named_person(s.person)
    if v == "time_call":
        return _unshown_call(s, rng, slug)
    pr = pair(rng, s)
    them = shown_as(pr.sc, pr.p, pr.other)
    win = None if v.startswith("sender") else window(rng, pr.p.tz)
    utc = bt.place_inside(rng, win, pr.p.tz) if win else pk.some_time(rng, pr.p.tz)
    mine = False if v in ("sender", "sender_named", "time_msg") else rng.random() < 0.5
    named = v == "sender_named" and not s.person.startswith("name_") and s.lang != "ru"
    ex = pr.chat(rng, s, utc, s.text, mine, where="before" if named else "both")
    if named:
        _name_line(rng, pr, s, ex)
    params: dict[str, object]
    if v in ("sender", "sender_named", "time_msg"):
        quote = clause(rng, s.text)
        params = {"quoted_text": quote, "person_ids": [slug]}
        template = "sender" if win is None else "record_time"
        if win is not None:
            params["window"] = win.tw()
        if named:
            why = (
                f'The owner calls the sender "{s.person}", but no line carries {slug} in '
                f"brackets; a name used in a chat does not show who holds {them}."
            )
        else:
            why = pick(
                rng,
                f"No line in the excerpt carries {slug} in brackets; the record's sender shows "
                f"only as {them}, and nothing shown ties that account to the person.",
                f"The record holds the quoted words, but its sender is shown only as {them}; "
                f"{slug} appears in no bracket, so who sent it stays open.",
            )
    else:
        quote = s.text
        params = merge({"person_ids": [slug]}, owner_style(rng, pr), channel(rng, pr.me.app))
        params["window"] = win.tw() if win else None
        if v == "nc_msg":
            template = "no_contact"
            if rng.random() < 0.5:
                params["device_ids"] = [pr.p.dev]
        else:
            template = "message_count"
            params.update(device_ids=[pr.p.dev], **count_params(rng, len(ex.lines)))
        why = pick(
            rng,
            f"The record is between the owner and {them}, but no line carries {slug} in "
            "brackets, so the excerpt does not show whether that account is the person's.",
            f"{slug} appears in no bracket; the record shows contact between the owner and "
            f"{them} inside {window_words(win) if win else 'the window'}, not with an account "
            "confirmed as the named person's.",
        )
    return BkDraft(s.family, template, params, ex, quote, why, pr.p, s.lang, pr.sc, win,
                   facts={"variant": v})  # fmt: skip


def _unshown_call(s: BkSlot, rng: random.Random, slug: str) -> BkDraft:
    sc = Scene()
    p = pk.call_phone(rng, sc, items(rng, 1)[0], zone(rng), scene_lang(s))
    mine, them = p.mine("Phone"), sc.new(rng, "Phone")
    out = rng.random() < 0.5
    frm, to = (mine, them) if out else (them, mine)
    win = window(rng, p.tz)
    utc = bt.place_inside(rng, win, p.tz)
    off = bt.report_offset(rng, utc, p.tz)
    rec = sc.call(p, utc, "outgoing" if out else "incoming", frm, to, pk.duration(rng), off)
    ex = pk.call_excerpt(rng, sc, p, rec)
    params = {"person_ids": [slug], "account_ids": [p.aid(mine)], "channels": ["call"],
              "window": win.tw()}  # fmt: skip
    why = pick(
        rng,
        f"The call is between the owner's number and {them.ident}, and no line carries {slug} "
        "in brackets, so the excerpt does not show who holds that number.",
        f"{slug} appears in no bracket; the call shows only the number {them.ident} on the "
        "other side, which nothing shown ties to the named person.",
    )
    return BkDraft(s.family, "record_time", params, ex, rec.text, why, p, s.lang, sc, win,
                   facts={"variant": s.variant})  # fmt: skip
