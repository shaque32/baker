"""Sentence banks for the message-level families. Every name, number and chat is invented.

The supports families and the families that differ from them only in who sent a message, when
it was sent, or whether any message passed at all draw on the same banks: the same verbs, the
same sentence shapes and the same places for a time phrase (see when.py). A trained model
then has only the facts to go on: whether the sender, the time or the window fits the record.

Each bank holds functions, not format strings, because a record's text may hold braces.
"""

from __future__ import annotations

import random
from collections.abc import Callable

# ---------------------------------------------------------------- what a message said

Report = tuple[Callable[[str, str, str], str], Callable[[str, str, str, str], str] | None, float]

# Frames that report what a message says (guide rule 14), as (s, o, p) -> text with no time,
# (s, o, p, w) -> text with the time phrase w inside (or None), and a weight: the short frames
# come up most, so a report runs no longer than it did (the length of an assumption is no cue
# for its answer). s sent the message, o is the other side of a one-to-one chat, p is the
# clause ("they paid the plumber $300").
ONE_TO_ONE: tuple[Report, ...] = (
    (lambda s, o, p: f"{s} wrote that {p}", lambda s, o, p, w: f"{s} wrote {w} that {p}", 6),
    (lambda s, o, p: f"{s} texted that {p}", lambda s, o, p, w: f"{s} texted {w} that {p}", 2),
    (lambda s, o, p: f"{s} said {p}", lambda s, o, p, w: f"{s} said {w} that {p}", 2),
    (lambda s, o, p: f"{s} said in a message that {p}",
     lambda s, o, p, w: f"{s} said in a message sent {w} that {p}", 0.6),
    (lambda s, o, p: f"{s} told {o} that {p}", lambda s, o, p, w: f"{s} told {o} {w} that {p}",
     0.7),
    (lambda s, o, p: f"{s} wrote to {o} that {p}",
     lambda s, o, p, w: f"{s} wrote to {o} {w} that {p}", 0.25),
    (lambda s, o, p: f"{s} texted {o} that {p}",
     lambda s, o, p, w: f"{s} texted {o} {w} that {p}", 0.2),
    (lambda s, o, p: f"{s} messaged {o} that {p}",
     lambda s, o, p, w: f"{s} messaged {o} {w} that {p}", 0.2),
    (lambda s, o, p: f"{s} let {o} know that {p}", None, 0.2),
    (lambda s, o, p: f"{s} said in a text to {o} that {p}",
     lambda s, o, p, w: f"{s} said in a text to {o} {w} that {p}", 0.1),
    (lambda s, o, p: f"in a message to {o}, {s} said {p}",
     lambda s, o, p, w: f"in a message to {o} {w}, {s} said {p}", 0.1),
    (lambda s, o, p: f"{s} sent {o} a message saying {p}",
     lambda s, o, p, w: f"{s} sent {o} a message {w} saying {p}", 0.1),
    (lambda s, o, p: f"{s} mentioned to {o} that {p}", None, 0.1),
)  # fmt: skip
NO_RECIPIENT = 4  # the first four one-to-one frames name no recipient
GROUP: tuple[Report, ...] = (
    (lambda s, o, p: f"{s} wrote in the group chat that {p}",
     lambda s, o, p, w: f"{s} wrote in the group chat {w} that {p}", 3),
    (lambda s, o, p: f"{s} told the group that {p}",
     lambda s, o, p, w: f"{s} told the group {w} that {p}", 2),
    (lambda s, o, p: f"{s} said in the group chat that {p}",
     lambda s, o, p, w: f"{s} said in the group chat {w} that {p}", 1),
    (lambda s, o, p: f"in the group chat, {s} said {p}", None, 1),
    (lambda s, o, p: f"{s} posted in the group chat that {p}", None, 1),
    (lambda s, o, p: f"{s} wrote to the group that {p}",
     lambda s, o, p, w: f"{s} wrote to the group {w} that {p}", 1),
    (lambda s, o, p: f"{s} let the group know that {p}", None, 0.5),
)  # fmt: skip
# An answer to a question just before it (sup_answer, and the traps beside it). No "confirmed":
# an answer such as "55 so far" says a number, not that it is settled.
ANSWER: tuple[Report, ...] = (
    (lambda s, o, p: f"answering {o}, {s} said {p}", None, 2),
    (lambda s, o, p: f"{s} replied to {o} that {p}",
     lambda s, o, p, w: f"{s} replied to {o} {w} that {p}", 2),
    (lambda s, o, p: f"in reply to {o}, {s} said {p}", None, 1),
)  # fmt: skip


def report(rng: random.Random, s: str, o: str, p: str, *, group: bool = False,
           when: str | None = None, meaning: bool = False,
           answer: bool = False) -> str:  # fmt: skip
    """'{s} wrote that {p}' in one of the frames above; a time phrase (when.py) opens the
    sentence, sits inside the frame, or closes it as "in a message sent ...", never after the
    clause alone, where it would date the act rather than the telling. With `meaning`, some of
    the time the message itself is the subject ("the message X sent on May 2, 2025 says that
    ..."). A group chat frame names the group and never a recipient (rule 11)."""
    if meaning and rng.random() < 0.3:
        return says(rng, s, o, p, group=group, when=when)
    bank = GROUP if group else ONE_TO_ONE + (ANSWER if answer else ())
    # A contact's label runs long, so a report seldom names it as the recipient (a supports
    # item would run longer than the rest); the owner, as "the owner", is named as often as
    # the frames' weights say.
    weights = [w if o == "the owner" or i < NO_RECIPIENT else w / 8
               for i, (*_, w) in enumerate(bank)]  # fmt: skip
    plain, mid, _ = rng.choices(bank, weights)[0]
    if when is None:
        return plain(s, o, p)
    roll = rng.random()
    if roll < 0.05:
        return f"{plain(s, o, p)}, in a message sent {when}"
    if roll < 0.27 and mid is not None:
        return mid(s, o, p, when)
    return f"{when}, {plain(s, o, p)}"


def says(rng: random.Random, s: str, o: str, p: str, *, group: bool = False,
         when: str | None = None) -> str:  # fmt: skip
    """The message as the subject: 'the message X sent on May 2, 2025 says that ...'."""
    to = " to the group" if group else ""
    if when is not None:
        forms = [f"the message {s} sent{to} {when} says that {p}",
                 f"a message {s} sent{to} {when} says {p}"]  # fmt: skip
        if not group:
            forms.append(f"the text {s} sent {o} {when} says that {p}")
        return rng.choice(forms)
    forms = [f"the message from {s}{to} says that {p}", f"a message from {s}{to} says {p}"]
    if not group:
        forms.append(f"the text {s} sent {o} says that {p}")
    return rng.choice(forms)


# ---------------------------------------------------------------- the words themselves

Words = tuple[Callable[[str, str, str], str], float]

# A message's exact words, as (b, t, x) -> text, b sent the words x to t, with a weight: the
# short shapes come up most.
WORDS_ONE_TO_ONE: tuple[Words, ...] = (
    (lambda b, t, x: f'{b} sent {t} the message "{x}"', 2),
    (lambda b, t, x: f'{b} wrote "{x}" to {t}', 2),
    (lambda b, t, x: f'{b} texted {t} "{x}"', 2),
    (lambda b, t, x: f'{b} texted {t}: "{x}"', 1),
    (lambda b, t, x: f'the message "{x}" was sent by {b} to {t}', 0.6),
    (lambda b, t, x: f'the message "{x}" was sent by {b}', 1),
    (lambda b, t, x: f'{b} sent the message "{x}"', 1.5),
    (lambda b, t, x: f'{b} messaged {t}: "{x}"', 1),
    (lambda b, t, x: f'{b} wrote to {t}: "{x}"', 1),
    (lambda b, t, x: f'{b} sent {t} a text saying "{x}"', 0.4),
    (lambda b, t, x: f'{t} got the message "{x}" from {b}', 0.4),
    (lambda b, t, x: f'the text "{x}" came from {b}', 0.8),
    (lambda b, t, x: f'{b} was the one who sent {t} "{x}"', 0.4),
    (lambda b, t, x: f'in a message to {t}, {b} wrote "{x}"', 0.4),
    (lambda b, t, x: f'the words "{x}" were sent by {b} to {t}', 0.4),
)
WORDS_GROUP: tuple[Words, ...] = (
    (lambda b, t, x: f'{b} wrote "{x}" in the group chat', 2),
    (lambda b, t, x: f'{b} sent "{x}" to the group', 2),
    (lambda b, t, x: f'in the group chat, {b} wrote "{x}"', 1),
    (lambda b, t, x: f'{b} posted "{x}" in the group chat', 1),
    (lambda b, t, x: f'the message "{x}" in the group chat came from {b}', 0.5),
    (lambda b, t, x: f'{b} was the one who wrote "{x}" in the group chat', 0.4),
    (lambda b, t, x: f'the words "{x}" were sent to the group by {b}', 0.4),
)


def words(rng: random.Random, b: str, t: str, x: str, *, group: bool = False,
          when: str | None = None) -> str:  # fmt: skip
    """'{b} sent {t} the message "{x}"' in one of the shapes above, with the time phrase (if
    any) before it or after it: after the closing quote it can only date the sending."""
    bank = WORDS_GROUP if group else WORDS_ONE_TO_ONE
    a = rng.choices(bank, [w for _, w in bank])[0][0](b, t, x)
    if when is None:
        return a
    return f"{when}, {a}" if rng.random() < 0.6 else f"{a} {when}"


# ---------------------------------------------------------------- a message, no words

Sent = Callable[[str, str, str], str]

# That a message was sent at a time, as (s, o, w) -> text (sup_time_window).
SENT_ONE_TO_ONE: tuple[Sent, ...] = (
    lambda s, o, w: f"{s} sent {o} a message {w}",
    lambda s, o, w: f"{w}, {s} sent {o} a message",
    lambda s, o, w: f"{w}, {s} texted {o}",
    lambda s, o, w: f"{s} messaged {o} {w}",
    lambda s, o, w: f"{s} wrote to {o} {w}",
    lambda s, o, w: f"{s} texted {o} {w}",
    lambda s, o, w: f"a message from {s} to {o} was sent {w}",
    lambda s, o, w: f"{s} sent a message to {o} {w}",
    lambda s, o, w: f"{w}, {o} got a message from {s}",
    lambda s, o, w: f"{w}, {s} messaged {o}",
)
SENT_GROUP: tuple[Sent, ...] = (
    lambda s, o, w: f"{s} wrote in the group chat {w}",
    lambda s, o, w: f"{w}, {s} posted in the group chat",
    lambda s, o, w: f"{s} sent a message to the group {w}",
    lambda s, o, w: f"{w}, {s} wrote to the group",
)


def sent(rng: random.Random, s: str, o: str, w: str, *, group: bool = False) -> str:
    bank = SENT_GROUP if group else SENT_ONE_TO_ONE
    # The first three shapes are the short ones and come up most.
    return (rng.choice(bank[:3]) if rng.random() < 0.6 else rng.choice(bank))(s, o, w)


# ---------------------------------------------------------------- contact in a window

# What passed between the owner and an account, said both ways with the same verbs: run 4
# read "messaged each other" as a sign of contradicts because only con_in_window used it. The
# verbs that need both sides to have written ("exchanged", "each other", "traded",
# "communicated") deny contact only over a window that holds a message from each side: one
# message alone leaves "did not exchange messages" open. ONE_WAY_NO and the one-way shapes
# below need only one.
CONTACT_YES = ("exchanged messages", "were in contact", "messaged each other", "texted each other",
               "were in touch", "communicated", "traded messages", "had contact",
               "wrote to each other")  # fmt: skip
CONTACT_NO = ("did not exchange messages", "were not in contact", "did not message each other",
              "did not text each other", "were not in touch", "did not communicate",
              "did not trade messages", "had no contact", "never messaged each other",
              "never exchanged messages", "were out of contact", "were out of touch",
              "never wrote to each other")  # fmt: skip
ONE_WAY_NO = ("were not in contact", "were not in touch", "had no contact", "were out of contact",
              "were out of touch")  # fmt: skip


def contact(rng: random.Random, who: str, window: str, yes: bool, two_way: bool = True) -> str:
    """That the owner and `who` were (yes) or were not in contact in the window (when.span).
    `two_way`: the window holds a message from each side, so a denial may use the verbs that
    need both."""
    v = rng.choice(CONTACT_YES if yes else CONTACT_NO if two_way else ONE_WAY_NO)
    shapes = [f"the owner and {who} {v} {window}", f"{window}, the owner and {who} {v}",
              f"{who} and the owner {v} {window}"]  # fmt: skip
    if yes:
        more = [f"there was contact between the owner and {who} {window}",
                f"messages passed between the owner and {who} {window}",
                f"the owner was in contact with {who} {window}",
                f"the owner exchanged messages with {who} {window}",
                f"{who} was in touch with the owner {window}"]  # fmt: skip
    else:
        more = [f"there was no contact between the owner and {who} {window}",
                f"no message passed between the owner and {who} {window}",
                f"the owner was not in contact with {who} {window}",
                f"neither the owner nor {who} messaged the other {window}"]  # fmt: skip
        if two_way:
            more += [f"no messages were exchanged between the owner and {who} {window}",
                     f"the owner did not exchange any messages with {who} {window}"]  # fmt: skip
    return rng.choice(shapes) if rng.random() < 0.6 else rng.choice(more)


def contact_by(rng: random.Random, who: str, d: str) -> str:
    """That the owner and `who` had been in contact by a later date."""
    return rng.choice([f"the owner and {who} had been in contact by {d}",
                       f"by {d}, the owner and {who} had exchanged messages",
                       f"the owner and {who} were in contact before {d}"])  # fmt: skip


def first_contact(rng: random.Random, who: str, t: str, two_way: bool = True) -> str:
    """That the owner and `who` were first in contact at `t` ("on June 5, 2025", "after 9
    p.m. on May 2, 2025"); `two_way` as in contact(), for the messages before `t`."""
    forms = [f"the owner and {who} were first in contact {t}",
             f"the first contact between the owner and {who} came {t}",
             f"the first message between the owner and {who} was sent {t}",
             f"contact between the owner and {who} began {t}"]  # fmt: skip
    if two_way:
        forms += [f"the owner and {who} first messaged each other {t}",
                  f"the owner and {who} first exchanged messages {t}",
                  f"the owner and {who} first texted each other {t}",
                  f"the owner and {who} began messaging each other {t}"]  # fmt: skip
    return rng.choice(forms)


def none_before(rng: random.Random, who: str, t: str, two_way: bool = True) -> str:
    """That the owner and `who` had no contact before `t` ("June 5, 2025", "9 p.m. on May 2,
    2025"); `two_way` as in contact(), for the messages before `t`."""
    forms = [f"the owner and {who} had no contact before {t}",
             f"the owner and {who} had never been in contact before {t}",
             f"no message between the owner and {who} predates {t}",
             f"until {t}, the owner and {who} had never been in contact",
             f"every message between the owner and {who} came after {t}"]  # fmt: skip
    if two_way:
        forms.append(f"the owner and {who} had not exchanged any messages before {t}")
    return rng.choice(forms)
