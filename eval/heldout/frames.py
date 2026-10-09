"""Shared pieces of the family writers: chat setup, filler placement, assumption sentences."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime

from eval.heldout.pools import CYRILLIC_NAMES, LATIN_NAMES
from eval.heldout.registry import Entry
from eval.heldout.scene import Chat, Draft, make_chat, random_local, timeline
from eval.heldout.schedule import Slot
from eval.heldout.text import (
    account_phrase,
    capitalize_first,
    clock12,
    date_phrase,
    render,
)
from eval.stancedata.chat import Account

Line = tuple[Account, str]


@dataclass
class Setup:
    chat: Chat
    sender: Account
    receiver: Account | None  # None in a group chat
    s: str  # how the assumption names the sender
    r: str  # how it names the receiver ("the group" in a group chat)


def _pick_label(rng: random.Random, lang: str, gender: str | None) -> str:
    if lang == "ru":
        pool = [n for n, g in CYRILLIC_NAMES if not gender or g == gender]
        return rng.choice(pool)
    return rng.choice(LATIN_NAMES)


def setup_chat(
    slot: Slot,
    rng: random.Random,
    *,
    members: int = 1,
    sender: str = "random",
    person_label: bool = False,
    gender: str | None = None,
) -> Setup:
    """A chat for this item. `sender` is random, contact or owner; `gender` (m/f) binds the
    contact's Cyrillic saved name when a Russian verb form needs it; `person_label` forces a
    plain first name as the contact's label."""
    entry = slot.entry
    sit = entry.tpl.sit if entry else "site"
    g = gender or (entry.tpl.g if entry else "") or None
    who = sender if sender != "random" else rng.choice(("contact", "owner"))
    chat = make_chat(rng, slot.lang, sit, members)
    contact = chat.contacts[0]
    needs_gender = slot.record_lang == "ru" and g and who == "contact"
    if person_label or (
        needs_gender
        and (
            not contact.label
            or contact.label not in chat.genders
            or chat.genders[contact.label] != g
        )
    ):
        label = _pick_label(rng, slot.record_lang, g if needs_gender else None)
        if contact.app == "Telegram" and slot.record_lang == "en":
            label = "@" + label.lower()
        contact = Account(contact.app, contact.identifier, label)
        chat.contacts[0] = contact
        for name, gg in CYRILLIC_NAMES:
            if name == label:
                chat.genders[label] = gg
    if members > 1:
        all_members = [chat.owner] + chat.contacts
        snd = rng.choice(all_members)
        return Setup(chat, snd, None, account_phrase(rng, snd), "the group")
    snd, rcv = (contact, chat.owner) if who == "contact" else (chat.owner, contact)
    return Setup(chat, snd, rcv, account_phrase(rng, snd), account_phrase(rng, rcv))


def place(
    rng: random.Random,
    chat: Chat,
    core: list[Line],
    target: int,
    before: tuple[int, int] = (0, 3),
    after: tuple[int, int] = (0, 2),
    neutral: bool = False,
    max_lines: int = 7,
) -> tuple[list[Line], int]:
    """Surround the core lines with filler; returns all lines and the record's index."""
    members = [chat.owner] + chat.contacts
    n_before = rng.randint(*before)
    n_after = rng.randint(*after)
    while len(core) + n_before + n_after > max_lines and (n_before or n_after):
        if n_before >= n_after:
            n_before -= 1
        else:
            n_after -= 1
    if len(core) + n_before + n_after < 2:  # every item has at least one context line
        n_after = 1
    used = {text for _, text in core}  # the filler draw skips lines already on screen

    def line() -> Line:
        return rng.choice(members), chat.filler(rng, neutral, used)

    pre = [line() for _ in range(n_before)]
    post = [line() for _ in range(n_after)]
    if all(acct.owner for acct, _ in pre + core + post):  # the other party must be on screen
        contact = rng.choice(chat.contacts)
        if post:
            post[-1] = (contact, post[-1][1])
        elif pre:
            pre[0] = (contact, pre[0][1])
        else:
            post = [(contact, line()[1])]
    return pre + core + post, target + n_before


def draft(
    slot: Slot,
    rng: random.Random,
    setup: Setup,
    lines: list[Line],
    target: int,
    assumption: str,
    quote: str,
    rationale: str,
    kind,
    record_utc: datetime | None = None,
    kinds: dict[int, str] | None = None,
) -> Draft:
    chat = setup.chat
    utc = record_utc or random_local(rng, chat.tz)
    times = timeline(rng, len(lines), target, utc, kinds)
    if assumption.endswith(".."):  # "... at 11 p.m.." when a clause ends in an abbreviation
        assumption = assumption[:-1]
    return Draft(chat, lines, target, capitalize_first(assumption), quote, rationale, kind, times)


# ----------------------------------------------------------------------------- sentences


def fill(text: str, setup: Setup) -> str:
    return render(text, {"s": setup.s, "r": setup.r})


def fact_sentence(
    rng: random.Random, entry: Entry, setup: Setup, local: datetime, prefer: str | None = None
) -> tuple[str, bool]:
    """An assumption stating the entry's fact. Returns (sentence, message_centric)."""
    s, r, d = setup.s, setup.r, date_phrase(local.date())
    use = prefer or (
        "vp" if entry.tpl.vp and (not entry.tpl.that or rng.random() < 0.5) else "that"
    )
    if use == "vp":
        vp = fill(entry.vp(), setup)
        rep = reported(vp)
        frames = [
            (f"{s} told {r} that {rep}.", False),
            (f"On {d}, {s} told {r} that {rep}.", False),
            (f"{s} wrote to {r} that {rep}.", False),
            (f"The message from {s} to {r} says that the sender {vp}.", True),
        ]
    else:
        that = fill(entry.that(), setup)
        if "the sender" in that:
            frames = [
                (f"The message from {s} to {r} says that {that}.", True),
                (f"The message of {d} from {s} to {r} says that {that}.", True),
            ]
        else:
            frames = [
                (f"{s} told {r} that {that}.", False),
                (f"{s} wrote to {r} that {that}.", False),
                (f"On {d}, {s} told {r} that {that}.", False),
                (f"The message from {s} to {r} says that {that}.", True),
            ]
    return rng.choice(frames)


_AGREE = {"was": "were", "has": "have", "is": "are", "does": "do"}
_TIME_WORDS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "today",
    "tonight",
    "that day",
    "that night",
    "that morning",
    "that evening",
    "that week",
    "this week",
    "the night before",
    "yesterday",
)


def reported(vp: str) -> str:
    """'was on 4 East' -> 'they were on 4 East': the sender's act as the message reports it."""
    first, _, rest = vp.partition(" ")
    return f"they {_AGREE.get(first, first)} {rest}".rstrip()


def fact_form(rng: random.Random, entry: Entry, setup: Setup, local: datetime) -> str:
    """The fact itself, with the sender named as the phone shows it; never "the message says"."""
    d = date_phrase(local.date())
    if entry.tpl.that:
        that = fill(entry.that(), setup)
        that = re.sub(r"the sender's (\w+)", lambda m: f"the {m.group(1)} of {setup.s}", that)
        that = that.replace("the sender", setup.s)
    else:
        that = f"{setup.s} {fill(entry.vp(), setup)}"
    frames = [f"{that}, according to the chat of {d} with {setup.r}."]
    if any(w in that.lower() for w in _TIME_WORDS):
        frames.append(f"According to the chat of {d}, {that}.")
    else:
        frames += [f"On {d}, {that}.", f"On {d}, {that}."]
    return rng.choice(frames)


def bare_fact(rng: random.Random, entry: Entry, setup: Setup) -> str:
    """The fact as a clause with no speaker frame, for rationales and bare assumptions."""
    if entry.tpl.that:
        return fill(entry.that(), setup)
    return f"{setup.s} {fill(entry.vp(), setup)}"


def verbatim_sentence(
    rng: random.Random, s: str, r: str, text: str, local: datetime, with_time: bool
) -> str:
    d = date_phrase(local.date())
    if with_time:
        c = clock12(local)
        frames = [
            f'At {c} on {d}, {s} sent {r} the message "{text}".',
            f'{s} messaged {r} "{text}" at {c} on {d}.',
            f'The message "{text}" from {s} to {r} is timed {c} on {d}.',
        ]
    else:
        frames = [
            f'On {d}, {s} sent {r} the message "{text}".',
            f'{s} wrote "{text}" to {r} on {d}.',
            f'{s} sent {r} a message on {d} that read "{text}".',
            f'The message "{text}" was sent by {s} to {r} on {d}.',
        ]
    return rng.choice(frames)
