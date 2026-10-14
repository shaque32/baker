"""Writers for the identity families: bk_identity_named, bk_account_silent, bk_handles_said
and bk_author_cue. Their accounts are third parties no expert has linked to anyone, or (for an
authorship cue on the owner's own account) the stipulated owner's."""

from __future__ import annotations

import random

from eval.heldout import bk_pick as pk
from eval.heldout.bk_build import any_sit, pair, shown_as
from eval.heldout.bk_common import BkDraft, chat_excerpt, ctx_texts, own_apps, pick
from eval.heldout.bk_scene import Acct, Scene, chat, items, zone
from eval.heldout.bk_schedule import BkSlot
from eval.stancedata import bakerform as bf


def identity(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_identity_named: the record, from the named account, gives the person's name, or
    answers to it when the owner asks."""
    pr = pair(rng, s)
    utc = pk.some_time(rng, pr.p.tz)
    sit = any_sit(rng, s)
    if s.variant == "answer":
        n_before, n_after = rng.randint(0, 1), rng.randint(0, 2)
        texts = ctx_texts(rng, sit, s.lang, n_before + n_after, avoid=(s.text, s.ask))
        before = [(False, t) for t in texts[:n_before]] + [(True, s.ask)]
        after = [(i % 2 == 1, t) for i, t in enumerate(texts[n_before:])]
        ex = chat(rng, pr.sc, pr.p, pr.me, pr.other, utc, s.text, False, before, after)
    else:
        ex = pr.chat(rng, s, utc, s.text, False, sit=sit)
    who = shown_as(pr.sc, pr.p, pr.other)
    person = bf.named_person(s.person)
    params = {"person_ids": [person], "account_ids": [pr.p.aid(pr.other)]}
    if s.variant == "answer":
        why = (f'The owner asks "{s.ask}" and {who} answers "{s.cue}"; answering to a name in a '
               "chat does not show who holds the account.")
    else:
        why = pick(
            rng,
            f'The record from {who} gives the name: "{s.cue}"; a name typed in a chat is not '
            "proof of who holds the account.",
            f'{who} introduces itself with "{s.cue}", but a self-introduction does not show who '
            f"holds the account, and no line carries {person} in brackets.",
        )
    return BkDraft(s.family, "person_identity", params, ex, s.cue, why, pr.p, s.lang, pr.sc,
                   facts={"variant": s.variant})  # fmt: skip


def silent(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_account_silent: an ordinary update from the named account, saying nothing about who
    holds it or who typed it."""
    pr = pair(rng, s)
    ex = pr.chat(rng, s, pk.some_time(rng, pr.p.tz), s.text, False)
    who = shown_as(pr.sc, pr.p, pr.other)
    params = {"person_ids": [bf.named_person(s.person)], "account_ids": [pr.p.aid(pr.other)]}
    if s.variant == "identity":
        template = "person_identity"
        why = pick(
            rng,
            f"The record from {who} is an ordinary update; it says nothing about who holds "
            "the account.",
            f"Nothing in this update from {who} names or describes the person behind the "
            "account, so it does not bear on whose account it is.",
        )
    else:
        template = "authorship"
        why = pick(
            rng,
            f"The record from {who} is an ordinary update; it says nothing about who typed "
            "it.",
            f"This update from {who} carries no cue about who was typing, so it does not "
            "bear on who wrote what the account sent.",
        )
    return BkDraft(s.family, template, params, ex, s.text, why, pr.p, s.lang, pr.sc,
                   facts={"variant": s.variant})  # fmt: skip


def handles(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_handles_said: a message, from the account itself or anyone else, says the two
    handles are one account or that one became the other."""
    app, old, new = s.handles
    sc = Scene()
    sc.taken |= {old.lstrip("@"), new.lstrip("@")}
    v = s.variant
    chat_on = app
    if v == "any_other_app":
        chat_on = rng.choice(("SMS", "Signal", "WhatsApp", "Telegram", "Instagram"))
        while chat_on == app:
            chat_on = rng.choice(("SMS", "Signal", "WhatsApp", "Telegram"))
    p = sc.phone(rng, items(rng, 1)[0], zone(rng), own_apps(rng, chat_on))
    me = p.mine(chat_on)
    if v == "self" and app == "Instagram":
        them = Acct("Instagram", new.lstrip("@"))  # an Instagram account's id is its username
    else:
        them = sc.new(rng, chat_on)
    mine = v != "self" and rng.random() < 0.3
    utc = pk.some_time(rng, p.tz)
    ex = chat_excerpt(rng, sc, p, me, them, utc, s.text, mine, any_sit(rng, s), s.lang)
    hs = [old, new] if rng.random() < 0.8 else [new, old]
    params = {"channels": [app], "handles": hs}
    who = "The account itself" if v == "self" else ("The owner" if mine else "Another account")
    why = pick(
        rng,
        f'{who} says "{s.cue}"; a message shows what was said about the handles, not the '
        "platform's own record that they are one account.",
        f'The record says "{s.cue}", which bears on the handles, but a chat message cannot '
        "show the platform's records of the rename.",
    )
    return BkDraft(s.family, "same_account", params, ex, s.cue, why, p, s.lang, sc,
                   facts={"variant": v})  # fmt: skip


def author(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_author_cue: the record, from the named account, carries a cue about who is typing."""
    pr = pair(rng, s)
    own = s.variant == "owner_self"
    ex = pr.chat(rng, s, pk.some_time(rng, pr.p.tz), s.text, own)
    a = pr.sender(own)
    person = pr.p.owner if own else bf.named_person(s.person)
    params = {"person_ids": [person], "account_ids": [pr.p.aid(a)]}
    why = pick(
        rng,
        f'The record carries a cue about who is typing ("{s.cue}"); one record cannot show who '
        "typed what the account sent.",
        f'"{s.cue}" points to someone other than the usual user, so who wrote what '
        f"{a.app} {a.ident} sent is left open.",
    )
    return BkDraft(s.family, "authorship", params, ex, s.cue, why, pr.p, s.lang, pr.sc,
                   facts={"variant": s.variant})  # fmt: skip
