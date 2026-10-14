"""Shared pieces of the family writers: chat setup, filler placement, assumption sentences."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from eval.heldout.pools import CYRILLIC_NAMES, LATIN_NAMES
from eval.heldout.registry import Entry
from eval.heldout.scene import Chat, Draft, local, make_chat, random_local, timeline
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


def _pick_label(rng: random.Random, lang: str, gender: str | None, about: str = "") -> str:
    """A saved name for a contact, never one the item's lines talk about (`about`)."""
    if lang == "ru":
        pool = [n for n, g in CYRILLIC_NAMES if not gender or g == gender]
    else:
        pool = list(LATIN_NAMES)
    return rng.choice([n for n in pool if not names_in(n, about)] or pool)


def _entry_text(entry: Entry | None) -> str:
    """Every line an entry can put on screen: the record and its extra lines (a question, a
    setup, a reply, a correction)."""
    if entry is None:
        return ""
    return " ".join([entry.text()] + [entry.part(key) for key, _ in entry.tpl.extra])


def _unclash(rng: random.Random, chat: Chat, lang: str, about: str) -> None:
    """A contact whose saved name is a person the lines talk about ("it went to Nico" from the
    contact saved as Nico) gets another name, so the excerpt never reads as self-reference."""
    taken = {a.label for a in chat.contacts if a.label}
    for i, acct in enumerate(chat.contacts):
        if not acct.label:
            continue
        first = re.split(r"[^\w]+", acct.label.lstrip("@"))[0]
        if not names_in(first, about):
            continue
        g = chat.genders.get(acct.label)
        label = acct.label
        for _ in range(50):
            label = _pick_label(rng, lang, g, about)
            if acct.app == "Telegram" and lang == "en":
                label = "@" + label.lower()
            if label not in taken:
                break
        taken.add(label)
        chat.contacts[i] = Account(acct.app, acct.identifier, label)
        if g:
            chat.genders[label] = g


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
    about = _entry_text(entry)
    _unclash(rng, chat, slot.record_lang, about)
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
        label = _pick_label(rng, slot.record_lang, g if needs_gender else None, about)
        if contact.app == "Telegram" and slot.record_lang == "en":
            label = "@" + label.lower()
        contact = Account(contact.app, contact.identifier, label)
        chat.contacts[0] = contact
        for name, gg in CYRILLIC_NAMES:
            if name == label:
                chat.genders[label] = gg
    if members > 1:
        all_members = [chat.owner] + chat.contacts
        if slot.record_lang == "ru" and g:  # a gendered Russian verb needs a matching sender
            fits = [a for a in all_members if a.owner or chat.genders.get(a.label or "") == g]
            if not fits:
                label = _pick_label(rng, "ru", g, about)
                first = chat.contacts[0]
                chat.contacts[0] = Account(first.app, first.identifier, label)
                chat.genders[label] = g
                fits = [chat.contacts[0]]
            all_members = fits
        snd = rng.choice(all_members)
        return Setup(chat, snd, None, account_phrase(rng, snd), "the group")
    snd, rcv = (contact, chat.owner) if who == "contact" else (chat.owner, contact)
    return Setup(chat, snd, rcv, account_phrase(rng, snd), account_phrase(rng, rcv))


def names_in(label: str | None, text: str) -> bool:
    """Whether a saved name or handle names someone the text talks about."""
    if not label:
        return False
    low = text.lower()
    for token in re.split(r"[^\w]+", label.lstrip("@").lower()):
        if len(token) < 3 or token.isdigit():
            continue
        if token.isascii():
            if re.search(rf"\b{re.escape(token)}\b", low):
                return True
        else:  # a Cyrillic name declines, so its stem is what the text would carry
            stem = token[:-1] if len(token) > 3 else token
            if re.search(rf"(?<![а-яё]){re.escape(stem)}", low):
                return True
    return False


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
    core_text = " ".join(text for _, text in core)
    about = {acct for acct in chat.contacts if names_in(acct.label, core_text)}
    speakers = {acct for acct, _ in core}

    def line(who: Account, after: bool) -> Line:
        # Someone who sends a core line, or whom the core lines talk about by name, gets only
        # small talk, so no filler of theirs can sit in tension with what the record says. A
        # line after the core never laughs at or doubts it (rule 24).
        small = neutral or who in about or who in speakers
        return who, chat.filler(rng, small, used, calm=after)

    pre = [line(rng.choice(members), False) for _ in range(n_before)]
    post = [line(rng.choice(members), True) for _ in range(n_after)]
    if all(acct.owner for acct, _ in pre + core + post):  # the other party must be on screen
        contact = rng.choice(chat.contacts)
        if post:
            post[-1] = line(contact, True)
        elif pre:
            pre[0] = line(contact, False)
        else:
            post = [line(contact, True)]
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
    rec_date = local(times[target], chat.tz).date()
    days = {  # "tomorrow" or "last night" in a record is an absolute local date in the assumption
        "xdate": date_phrase(rec_date),
        "xnext": date_phrase(rec_date + timedelta(days=1)),
        "xprev": date_phrase(rec_date - timedelta(days=1)),
    }
    assumption, rationale = render(assumption, days), render(rationale, days)
    if assumption.endswith(".."):  # "... at 11 p.m.." when a clause ends in an abbreviation
        assumption = assumption[:-1]
    assumption, rationale = capitalize_first(assumption), capitalize_first(rationale)
    return Draft(chat, lines, target, assumption, quote, rationale, kind, times)


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
        ]
        if not vp.startswith("said "):
            frames.append((f"The message from {s} to {r} says that the sender {vp}.", True))
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
    """'was on 4 East' -> 'they were on 4 East': the sender's act as the message reports it.

    A verb phrase that already reports speech ('said they were on nights') keeps only the
    speech itself, so no frame ends up as 'told the owner that they said'."""
    first, _, rest = vp.partition(" ")
    if first == "said":
        return rest
    return f"they {_AGREE.get(first, first)} {rest}".rstrip()


def named_fact(entry: Entry, setup: Setup) -> str:
    """The entry's fact as a clause, with the sender named as the phone shows it."""
    if entry.tpl.that:
        that = fill(entry.that(), setup)
        if setup.s == "the owner":
            that = that.replace("the sender's ", "the owner's ")
        else:
            that = re.sub(r"the sender's (\w+)", lambda m: f"the {m.group(1)} of {setup.s}", that)
        return that.replace("the sender", setup.s)
    return f"{setup.s} {fill(entry.vp(), setup)}"


def plain_fact(entry: Entry, setup: Setup) -> str:
    """The fact itself as a sentence, with no chat or message frame (rule 12): what a
    contradicting record must rule out. Its time is the template's own ({xdate}, "on {day}"),
    never the chat's date added on top, so it claims no more time than the record speaks to."""
    return capitalize_first(named_fact(entry, setup)) + "."


def fact_form(rng: random.Random, entry: Entry, setup: Setup, local: datetime | date) -> str:
    """The fact itself, with the sender named as the phone shows it: never "the message says"
    or "according to the chat", which would claim something about the chat (rules 12 and 21).
    A fact with no time of its own carries the chat's date."""
    d = date_phrase(local.date() if isinstance(local, datetime) else local)
    that = named_fact(entry, setup)
    if "{x" in that or any(w in that.lower() for w in _TIME_WORDS):
        return capitalize_first(that) + "."
    return rng.choice([f"On {d}, {that}.", f"{capitalize_first(that)} on {d}."])


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
            f'{s} sent {r} the message "{text}" at {c} on {d}.',
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
