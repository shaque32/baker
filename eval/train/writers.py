"""Assumption frames and the family specs that attach to any record.

A Spec is what a scenario adds to a Chat for one item: the family, the assumption kind, the
assumption, the quote and the rationale. The stance is never here; it comes from the family.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import timedelta

from core.contracts import AssumptionKind as K
from eval.stancedata.chat import fictional_phone, long_date, pretty_phone
from eval.stancedata.families import family
from eval.train import filler
from eval.train.facts import Fact
from eval.train.facts import claim as fact_claim
from eval.train.facts import shown as fact_shown
from eval.train.names import AREA_CODES, Party, full_name, person, telegram_id, username
from eval.train.scenario import MOSCOW, Chat, clock12, hour12, month_year


@dataclass(frozen=True)
class Spec:
    family: str
    kind: K
    assumption: str
    quote: str
    rationale: str


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def kind_of(rng: random.Random, fam: str) -> K:
    return rng.choice(family(fam).kinds)


DONE_WORDS = {"done", "finally", "всё", "наконец"}


def wrap(rng: random.Random, core: str, lang: str, done_ok: bool = True) -> str:
    """Casual prefix and suffix around the quotable core; both keep the core word-aligned.

    Neither repeats a word next to it ("ok so so did u", "lol lol", "done. ... . done"). With
    done_ok False (plans, conditions, questions, denials) neither can suggest completion.
    """

    def words(s: str) -> set[str]:
        return set(re.findall(r"\w+", s.lower()))

    def ok(s: str) -> bool:
        return done_ok or not words(s) & DONE_WORDS

    core_words = re.findall(r"\w+", core.lower())
    head, tail = set(core_words[:1]), set(core_words[-1:])
    pres = filler.PREFIX_RU if lang == "ru" else filler.PREFIX_EN
    pre = rng.choice([p for p in pres if ok(p) and not words(p) & head])
    sufs = filler.SUFFIX_RU if lang == "ru" else filler.SUFFIX_EN
    suf = rng.choice([s for s in sufs if ok(s) and not words(s) & (words(pre) | tail)])
    return f"{pre}{core}{suf}"


def frame(rng: random.Random, c: Chat, pred: str, *, date: bool = False, meaning: bool = False,
          told_only: bool = False, bare: bool = False) -> str:  # fmt: skip
    """'{S} told {O} that {pron} {pred}' in one of several frames; a date attaches to the telling.

    told_only keeps the frames that report the saying (for plans, hedges and reports, where
    the bare event frame would claim more than the record says). With `bare`, the predicate
    carries its own subject ("Lina said she ...") and no pronoun is put before it.
    """
    s, o = c.sender.who, c.other.who
    pp = pred if bare else f"{c.sender.pron} {pred}"
    told = "wrote in the group chat that" if c.is_group() else f"told {o} that"
    if meaning:
        forms = [f"the message from {s} to {o} says that {pp}",
                 f"read plainly, the message from {s} states that {pp}"]  # fmt: skip
    else:
        forms = [f"{s} {told} {pp}", f"in a message to {o}, {s} said {pp}",
                 f"{s} wrote to {o} that {pp}", f"{s} texted {o} that {pp}"]  # fmt: skip
        if not told_only:
            forms += [f"{s} {pred}", f"{s} {pred}"]
    if date:
        d = long_date(c.day)
        forms += [f"on {d}, {s} {told} {pp}", f"{s} wrote to {o} on {d} that {pp}"]
    return cap(rng.choice(forms))


def spec_plain(rng: random.Random, c: Chat, pred: str, quote: str, why: str,
               told_only: bool = False, bare: bool = False) -> Spec:  # fmt: skip
    kind = kind_of(rng, "sup_plain")
    date = rng.random() < 0.3
    # A supports assumption always reports what the message communicates (guide rule 14);
    # told_only additionally skips the "the message says that" frames for plans and reports.
    text = frame(rng, c, pred, date=date, meaning=kind == K.MEANING and not told_only,
                 told_only=True, bare=bare)  # fmt: skip
    return Spec("sup_plain", kind, text, quote, why)


def spec_verbatim(rng: random.Random, c: Chat) -> Spec:
    s, o, text, d = c.sender.who, c.other.who, c.record.text, long_date(c.day)
    forms = [(f'{s} sent {o} the message "{text}" on {d}', K.TIME),
             (f'on {d}, {s} wrote "{text}" to {o}', K.TIME),
             (f'{s} texted {o} "{text}"', K.EVENT), (f'{s} wrote "{text}" to {o} on {d}', K.TIME),
             (f'the message "{text}" was sent by {s} to {o}', K.EVENT)]  # fmt: skip
    a, kind = rng.choice(forms)
    why = f"The record is that message, from {c.record.account.sender} at {c.stamp}."
    return Spec("sup_verbatim", kind, cap(a), text, why)


def spec_time_window(rng: random.Random, c: Chat) -> Spec:
    loc, s, o, d = c.local, c.sender.who, c.other.who, long_date(c.day)
    h, m = loc.hour, loc.minute
    opts = [f"{s} sent {o} a message on {d}"]
    if m <= 49 and h + 1 <= 23:
        opts.append(f"before {hour12(h + 1)} on {d}, {s} texted {o}")
    if m >= 10:
        opts.append(f"after {hour12(h)} on {d}, {s} sent {o} a message")
    if 10 <= m <= 49 and h + 2 <= 23:
        opts.append(f"between {hour12(h)} and {hour12(h + 2)} on {d}, {s} messaged {o}")
    parts = {range(6, 11): "morning", range(13, 17): "afternoon", range(18, 21): "evening",
             range(22, 24): "night"}  # fmt: skip
    for r, part in parts.items():
        if h in r:
            opts.append(f"{s} messaged {o} on the {part} of {d}")
    why = f"The record's local time is {c.stamp}, inside the window the assumption states."
    return Spec("sup_time_window", K.TIME, cap(rng.choice(opts)), c.record.text, why)


def spec_time_mismatch(rng: random.Random, c: Chat, pred: str, quote: str,
                       clause: bool = False) -> Spec:  # fmt: skip
    """Same words and people, wrong local date or clock. `clause` means pred has its own subject."""
    loc, s, o = c.local, c.sender.who, c.other.who
    h, m, d = loc.hour, loc.minute, long_date(c.day)
    if not clause:
        pred = f"{c.sender.pron} {pred}"
    told = "wrote in the group chat that" if c.is_group() else f"told {o} that"
    clock = rng.random() < 0.4
    if clock and m <= 49 and h + 1 <= 23:
        a = f"after {hour12(h + 1)} on {d}, {s} {told} {pred}"
        why = f"The record's local clock reads {clock12(loc)}, before {hour12(h + 1)}."
    elif clock and m >= 10:
        a = f"before {hour12(h)} on {d}, {s} {told} {pred}"
        why = f"The record's local clock reads {clock12(loc)}, after {hour12(h)}."
    else:
        if c.tz == MOSCOW and h <= 2:
            wrong = c.day - timedelta(days=1)  # the UTC date
        elif c.tz != MOSCOW and h >= 20:
            wrong = c.day + timedelta(days=1)  # the UTC date
        else:
            wrong = c.day + timedelta(days=rng.choice((-3, -2, -1, 1, 2, 3)))
        w = long_date(wrong)
        a = rng.choice([f"on {w}, {s} {told} {pred}", f"{s} wrote to {o} on {w} that {pred}",
                        f"{s} {told} {pred}, in a message sent on {w}"])  # fmt: skip
        why = f"The record's local time is {c.stamp}: {d}, not {w}."
    return Spec("ovr_time_mismatch", K.TIME, cap(a), quote, why)


def spec_sender_mismatch(rng: random.Random, c: Chat) -> Spec:
    text, s = c.record.text, c.sender.who
    claimed = c.contacts[0].who if c.sender.account.owner else "the owner"
    forms = [f'{claimed} wrote "{text}" to {s}', f'the message "{text}" was sent by {claimed}',
             f'{claimed} sent {s} the message "{text}"',
             f'{claimed} texted {s}: "{text}"']  # fmt: skip
    why = f"The sender line shows {c.record.account.sender}, not {claimed}."
    return Spec("ovr_sender_mismatch", kind_of(rng, "ovr_sender_mismatch"), cap(rng.choice(forms)),
                text, why)  # fmt: skip


def spec_handle_owner(rng: random.Random, c: Chat, pred: str, quote: str,
                      intro: bool) -> Spec | None:  # fmt: skip
    """A real-person name attached to the sender's account; never to the owner's own account."""
    if c.sender.account.owner:
        return None
    full, s, o, p = full_name(rng, c.sender.person), c.sender.who, c.other.who, c.sender.person.pron
    forms = [f"{full} told {o} that {p} {pred}", f"{full} {pred}",
             f"{full}, writing as {s}, told {o} that {p} {pred}",
             f"{full} wrote to {o} that {p} {pred}"]  # fmt: skip
    why = f"The record shows only {s}; nothing shown proves that account is {full}."
    if intro:
        why += " A self-introduction in the chat is not that proof."
    return Spec("ovr_handle_owner", kind_of(rng, "ovr_handle_owner"), cap(rng.choice(forms)), quote,
                why)  # fmt: skip


def spec_partial(rng: random.Random, c: Chat, f: Fact, v: str, quote: str) -> Spec | None:
    if not f.extra:
        return None
    extra, pred, s, o, p = (
        rng.choice(f.extra),
        fact_claim(f, v),
        c.sender.who,
        c.other.who,
        c.sender.pron,
    )
    forms = [f"{s} {pred} and {extra}", f"{s} told {o} that {p} {pred} and {extra}"]
    why = f"The record shows only that {p} {pred}; nothing shown establishes that {p} {extra}."
    return Spec("ovr_partial", K.EVENT, cap(rng.choice(forms)), quote, why)


def spec_count(rng: random.Random, c: Chat, f: Fact, v: str, quote: str) -> Spec | None:
    if not f.general:
        return None
    g = rng.choice(f.general).replace("{v}", fact_shown(f, v))
    s, o, p = c.sender.who, c.other.who, c.sender.pron
    forms = [f"{s} {g}", f"{s} told {o} that {p} {g}"]
    why = "The record shows one instance; the other occasions the assumption asserts are not shown."
    return Spec("ovr_count", K.COMPLETENESS, cap(rng.choice(forms)), quote, why)


def spec_contact(rng: random.Random, c: Chat) -> Spec | None:
    other = c.other
    replied = any(m.account == other.account and c.local_of(i).date() == c.day
                  for i, m in enumerate(c.msgs) if i != c.target)  # fmt: skip
    if not replied or c.is_group():
        return None
    who, d = c.contacts[0].who, long_date(c.day)
    d1 = long_date(c.day - timedelta(days=rng.randint(0, 5)))
    d2 = long_date(c.day + timedelta(days=rng.randint(0, 5)))
    forms = [f"the owner and {who} exchanged messages on {d}",
             f"the owner and {who} were in contact on {d}",
             f"between {d1} and {d2}, the owner and {who} exchanged messages"]  # fmt: skip
    why = (f"The record is a message between them at {c.stamp}, and the other side also "
           "writes the same day.")  # fmt: skip
    return Spec(
        "sup_contact", kind_of(rng, "sup_contact"), cap(rng.choice(forms)), c.record.text, why
    )


def spec_in_window(rng: random.Random, c: Chat) -> Spec:
    who = c.contacts[0].who
    a, b = rng.randint(0, 6), rng.randint(0, 6)
    d1, d2 = long_date(c.day - timedelta(days=a)), long_date(c.day + timedelta(days=b))
    if rng.random() < 0.6:
        span = f"on {d1}" if a == b == 0 else f"between {d1} and {d2}"
        text = f"there was no contact between the owner and {who} {span}"
        why = f"The record is a message between them at {c.stamp}, inside that window."
    else:
        first = long_date(c.day + timedelta(days=rng.randint(1, 30)))
        text = f"the first message between the owner and {who} was sent on {first}"
        why = f"The record is a message between them at {c.stamp}, earlier than that date."
    return Spec("con_in_window", kind_of(rng, "con_in_window"), cap(text), c.record.text, why)


def other_party(rng: random.Random, c: Chat) -> tuple[str, Party | None]:
    """An account that is not in the chat, named as a phone would show it."""
    lang = "ru" if c.lang == "ru" else "en"
    names = {p.person.name for p in [c.owner, *c.contacts]}
    p = person(rng, lang)
    while p.name in names:
        p = person(rng, lang)
    roll = rng.random()
    if roll < 0.5:
        return f"the contact saved as {p.name}", p
    if roll < 0.7:
        return f"Telegram user {telegram_id(rng)}", None
    if roll < 0.85:
        return pretty_phone(fictional_phone(rng, AREA_CODES)), None
    return f"the Instagram account {username(rng, p)}", None


TIME_EVENTS = ("landed in Denver at {t}", "called the owner at {t}", "left the gym at {t}",
               "arrived at the restaurant at {t}", "got to the airport at {t}")  # fmt: skip
ABSENT_WORDS = ("groceries", "party favors", "candy", "paperwork", "vitamins", "the blue ones")


def spec_irrelevant(rng: random.Random, c: Chat, fam: str, g: Fact, same_person: bool) -> Spec:
    """An assumption the record does not bear on, in any assumption kind."""
    kind = kind_of(rng, fam)
    if same_person:
        subj, pron = c.sender.who, c.sender.pron
    else:
        subj, p = other_party(rng, c)
        pron = p.pron if p else "they"
    v = rng.choice(g.values)
    if kind == K.EVENT:
        a = rng.choice(
            [f"{subj} {fact_claim(g, v)}", f"{subj} told the owner that {pron} {fact_claim(g, v)}"]
        )
    elif kind == K.IDENTITY:
        a = f"{subj} belongs to {full_name(rng, person(rng, 'ru' if c.lang == 'ru' else 'en'))}"
    elif kind == K.TIME:
        t = clock12(c.local.replace(hour=rng.randrange(24), minute=rng.randrange(60)))
        a = f"{subj} {rng.choice(TIME_EVENTS).format(t=t)} on {long_date(c.day)}"
    elif kind == K.MEANING:
        w = rng.choice([x for x in ABSENT_WORDS if x not in c.record.text.lower()])
        a = f"by '{w}' in the chat, {subj} meant drugs"
    else:
        a = f"the owner and {subj} exchanged messages every day in {month_year(c.day)}"
    why = "The record is about a different matter and does not bear on the assumption."
    if not same_person:
        why = ("The record is about a different matter and a different account; it does not "
               "bear on the assumption.")  # fmt: skip
    return Spec(fam, kind, cap(a), c.record.text, why)
