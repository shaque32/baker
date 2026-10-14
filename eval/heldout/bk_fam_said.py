"""Writers for the claim families where a record speaks to the claim itself (guide rule 29),
shown with the claim: bk_meaning_said and bk_meaning_other, where the account that used the
words says what they mean, and bk_event_is_record, where the claim's event is a message or call
and the record is that message or call."""

from __future__ import annotations

import random

from eval.heldout import bk_claimkit as ck
from eval.heldout import bk_meanings as mn
from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import call_scene, pair, shown_as
from eval.heldout.bk_common import BkDraft, pick, window_words
from eval.heldout.bk_naming import owner_sur, sur
from eval.heldout.bk_schedule import BkSlot


def meaning_explained(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_meaning_said / bk_meaning_other: the account that used the words earlier in the
    chat says they mean the claim's meaning (supports), or the plain thing they name, another
    kind of thing than the claim's meaning, which the record never mentions (complicates: the
    claim gives no date, and one record cannot show that no other message used the words as
    the claim says, rule 23)."""
    p = ck.party(rng, s, linked=s.variant == "linked")
    mine = p.mine(True)
    before = [(mine, s.usage), (not mine, rng.choice(mn.ASK))]
    if rng.random() < 0.3:
        before.insert(0, (not mine, rng.choice(("hey", "u around?", "yo", "quick q"))))
    after = [(not mine, rng.choice(mn.ACK))] if rng.random() < 0.6 else []
    ex = ck.around(rng, p, pk.some_time(rng, p.pr.p.tz), s.text, mine, before, after)
    claim = pick(
        rng,
        f'{p.actor} used "{s.words}" to mean {s.meaning}.',
        f'When {p.actor} wrote "{s.words}", {p.actor} meant {s.meaning}.',
    )
    if s.family == "bk_meaning_said":
        why = (
            f'{p.shown}, which wrote "{s.words}" earlier in the chat, says the words mean '
            f"{s.meaning}, the meaning the claim gives them."
        )
    else:
        why = pick(
            rng,
            f'{p.shown}, which used "{s.words}" earlier in the chat, says they mean {s.plain}, '
            f"not {s.meaning} as the claim has it; the claim names no date, and this one "
            "explanation cannot show the words never carried the claim's meaning in some other "
            "message, so it stays open.",
            f'Asked about "{s.words}", {p.shown} explains them as {s.plain}, a different thing '
            f"from {s.meaning}; that tells how the words were meant here, but with no date in the "
            "claim, other messages could still have used them as the claim says.",
        )
    return BkDraft(s.family, "meaning", {"quoted_text": s.words}, ex, s.quote, why, p.pr.p,
                   s.lang, p.pr.sc, claim=claim, facts={"variant": s.variant})  # fmt: skip


def _message_claim(rng: random.Random, start: str, frm: str, to: str, app: str, text: str) -> str:
    if app == "SMS" and rng.random() < 0.5:
        return f'{start}, {frm} texted {to}: "{text}"'
    return pick(
        rng,
        f'{start}, {frm} sent {to} the message "{text}".',
        f'{start}, {frm} wrote to {to} on {app}: "{text}"',
    )


def _message(s: BkSlot, rng: random.Random) -> BkDraft:
    v = s.variant
    if v == "msg_cross":
        pr = pair(rng, s, cross=True)
        q = pr.q
        assert q is not None  # noqa: S101 - a cross pair has its second phone
        frm, to = owner_sur(rng, pr.sc, q), owner_sur(rng, pr.sc, pr.p)
        params: dict[str, object] = {"person_ids": [q.owner, pr.p.owner]}
        mine = False
    elif v == "msg_acct":
        pr = pair(rng, s)
        frm, to = owner_sur(rng, pr.sc, pr.p), ck.label(pr.other)
        params = {"person_ids": [pr.p.owner], "account_ids": [pr.p.aid(pr.other)]}
        mine = True
    else:
        pr = pair(rng, s, linked=True)
        mine = v == "msg_out"
        names = [sur(pr.linked), owner_sur(rng, pr.sc, pr.p)]
        frm, to = names if not mine else names[::-1]
        params = {"person_ids": [pr.p.owner, pr.linked]}
    persons = params["person_ids"]
    if isinstance(persons, list) and len(persons) == 2 and rng.random() < 0.5:
        persons.reverse()
    win = pk.pick_window(rng, pr.p.tz)
    params["window"] = win.tw()
    utc = bt.place_inside(rng, win, pr.p.tz)
    ex = pr.chat(rng, s, utc, s.text, mine, sit=s.sit)
    claim = _message_claim(rng, ck.when(win), frm, to, pr.me.app, s.text)
    sender = shown_as(pr.sc, pr.p, pr.sender(mine))
    other = shown_as(pr.sc, pr.p, pr.sender(not mine))
    why = (
        f"The record is the message the claim describes: from {sender} to {other}, sent "
        f"{ex.record.local_time}, inside {window_words(win)}, in the words the claim quotes."
    )
    return BkDraft(s.family, "event", params, ex, s.text, why, pr.p, s.lang, pr.sc, win,
                   claim=claim, facts={"variant": v})  # fmt: skip


def _call(s: BkSlot, rng: random.Random) -> BkDraft:
    forms = ("in_linked", "cross_in") if s.variant == "call_in" else ("out_person", "cross_out")
    c = call_scene(rng, s, rng.choice(forms))
    names = {c.p.owner: owner_sur(rng, c.sc, c.p)}
    if c.q is not None:
        names[c.q.owner] = owner_sur(rng, c.sc, c.q)
    for person in c.sc.links.values():
        names[person] = sur(person)
    caller = names[c.person] if c.direction == "outgoing" or c.q else names[c.person]
    holder = c.sc.owner_phone(c.to)
    callee = names.get(holder.owner, "") if holder is not None else ""
    number = ck.dial(c.to.ident)
    if c.direction == "incoming":  # the call line's person called the record phone's user
        caller, callee = names[c.person], names[c.p.owner]
    to = f"{callee} at {number}" if callee else number
    win = pk.pick_window(rng, c.p.tz, ("on", "On", "between", "about", "through"))
    utc = bt.place_inside(rng, win, c.p.tz)
    ex = c.excerpt(rng, utc, rng.randint(30, 1500))
    claim = f"{ck.when(win)}, {caller} called {to}."
    params = {**c.params(), "window": win.tw()}
    why = (
        f"The record is {c.said()}, the call the claim describes, at {ex.record.local_time}, "
        f"inside {window_words(win)}."
    )
    return BkDraft(s.family, "event", params, ex, ex.record.text, why, c.p, s.lang, c.sc, win,
                   claim=claim, facts={"variant": s.variant})  # fmt: skip


def event_record(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_event_is_record: the claim's event is a message or call between the named parties,
    and the record is it, plainly inside the window."""
    return _call(s, rng) if s.variant.startswith("call") else _message(s, rng)
