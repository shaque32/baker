"""Assumption frames and the family specs that attach to any record.

A Spec is what a scenario adds to a Chat for one item: the family, the assumption kind, the
assumption, the quote and the rationale. The stance is never here; it comes from the family.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date, timedelta

from core.contracts import AssumptionKind as K
from eval.stancedata.chat import fictional_phone, long_date, pretty_phone
from eval.stancedata.families import family
from eval.train import facts as fx
from eval.train.facts import Fact
from eval.train.facts import claim as fact_claim
from eval.train.names import AREA_CODES, Party, full_name, person, telegram_id, username
from eval.train.scenario import MOSCOW, Chat, clock12, decorate, hour12


@dataclass(frozen=True)
class Spec:
    family: str
    kind: K
    assumption: str
    quote: str
    rationale: str


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


# Past participles of the irregular verbs that start fact claims ("had driven", "had gotten").
PARTICIPLES = {"took": "taken", "drove": "driven", "went": "gone", "gave": "given",
               "swam": "swum", "ran": "run", "did": "done", "got": "gotten", "was": "been",
               "were": "been", "ate": "eaten", "wrote": "written", "rode": "ridden",
               "saw": "seen", "flew": "flown", "came": "come", "broke": "broken",
               "stole": "stolen", "threw": "thrown", "hid": "hidden", "fell": "fallen",
               "spoke": "spoken", "drank": "drunk", "knew": "known", "showed": "shown"}  # fmt: skip


def perfect(pred: str) -> str:
    """'paid the plumber $300' -> 'had paid the plumber $300'; 'took the bus' -> 'had taken'."""
    verb, _, rest = pred.partition(" ")
    return f"had {PARTICIPLES.get(verb, verb)} {rest}".rstrip()


# An act with its own clock time or day of the month: "landed in Chicago at noon", "took the
# 8am train", "paid the rent on the 1st" (not "the 4th floor").
ACT_CLOCK = re.compile(
    r"\bat (noon|midnight|\d{1,2})(?::(\d{2}))?(?![\w:]| [ap]\.m\.)|\b(\d{1,2})(am|pm) train\b"
)
ACT_DAY = re.compile(r"\bon the (\d{1,2})(?:st|nd|rd|th)\b(?! floor)")
AFTERNOON_ACT = re.compile(r"\b(picked the kids up|checked in)\b")
DAY_MINUTES = 24 * 60


def act_minute(pred: str, day: date) -> int:
    """The minute of `day` by which an act with its own time is done, under its earliest
    natural reading: a school pickup or a hotel check-in "at 3" is 3 p.m.; a landing "at 8"
    may be 8 a.m., and a bar closes at 2 in the small hours. An act on a later day of the month
    falls in an earlier month, after every minute of `day` (DAY_MINUTES); an act with no time
    of its own is done by any minute (-1)."""
    if m := ACT_DAY.search(pred):
        n = int(m.group(1))
        return -1 if n < day.day else 0 if n == day.day else DAY_MINUTES
    m = ACT_CLOCK.search(pred)
    if m is None:
        return -1
    if m.group(3):
        return (int(m.group(3)) % 12 + (12 if m.group(4) == "pm" else 0)) * 60
    if m.group(1) in ("noon", "midnight"):
        return 720 if m.group(1) == "noon" else 0
    h = int(m.group(1))
    if h < 12 and AFTERNOON_ACT.search(pred):
        h += 12
    return h * 60 + int(m.group(2) or 0)


def clock_of(minute: int) -> str:
    """'noon', '2 p.m.', '2:05 p.m.' for a minute of the day."""
    h, m = divmod(minute, 60)
    return hour12(h) if m == 0 else f"{h % 12 or 12}:{m:02d} {'a.m.' if h < 12 else 'p.m.'}"


def bound_time(rng: random.Random, c: Chat, after: bool = False, floor: int = -1) -> str | None:
    """A whole local hour before the record's clock ('noon', '2 p.m.'), by which a past act was
    done; with `after`, a reading later than the record's ('11 p.m.', '9:40 p.m.').

    Never the record's own minute: a bound at the very minute a message was sent reads as a
    pointer to that message (and gives the answer away). The reading is never before `floor`,
    the minute by which the act's own time has passed ("by 10 a.m., had landed at noon" makes
    no sense); None when no reading fits.
    """
    h, now, roll = c.local.hour, c.local.hour * 60 + c.local.minute, rng.random()
    last = 23 * 60 + 59
    if after:
        if roll < 0.25 and h + 2 <= 23:
            t = (h + 2) * 60
        elif roll < 0.7:
            t = min(now + 20 + int(roll * 140), last)  # 20 to 117 minutes later
        else:
            t = (h + 1) * 60 if h + 1 <= 23 else last
        return clock_of(t) if t > now and t >= floor else None
    top = h * 60 if c.local.minute else (h - 1) * 60  # the last whole hour before the record
    t = top - 60 if roll < 0.35 and top - 60 >= 6 * 60 else top
    if t < floor <= top:
        t = top
    # Never "by midnight", which could be either end of the date.
    return clock_of(t) if t >= max(floor, 60) else None


def bounded(rng: random.Random, c: Chat, subj: str, pred: str, after: bool = False,
            simple: bool = False) -> str:  # fmt: skip
    """The fact `subj pred`, bounded by a local time on the record's date.

    Trap assumptions carry such a bound some of the time, before or after the record's time
    (`after`), so a clock reading is no cue for the answer. An act whose own time falls after
    every bound ("landed at noon", sent at 10 a.m.) is bounded by a date instead: the days
    before the record's, or with `after` before the next. With `simple`, the act keeps its own
    tense ("before 2 p.m., X paid Y and took the train"), never "had ...".
    """
    t = bound_time(rng, c, after, act_minute(pred, c.day))
    if t is None:
        d = long_date(c.day + timedelta(days=1 if after else 0))
        return cap(rng.choice([f"before {d}, {subj} {pred}", f"{subj} {pred} before {d}"]))
    d = long_date(c.day)
    forms = [f"before {t} on {d}, {subj} {pred}", f"by {t} on {d}, {subj} {perfect(pred)}",
             f"{subj} {perfect(pred)} by {t} on {d}"]  # fmt: skip
    # "had had the plumber come" is grammatical but reads as a slip.
    return cap(rng.choice(forms[:1] if simple or pred.startswith("had ") else forms))


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# An act on a named weekday ("returned the drill on Monday") and a booking for one ("booked
# the uhaul for Monday", whose day may still be ahead).
ON_WEEKDAY = re.compile(rf"\bon ({'|'.join(WEEKDAYS)})\b")
FOR_WEEKDAY = re.compile(rf"\bfor ({'|'.join(WEEKDAYS)})\b")


def last_weekday(day: date, weekday: int) -> date:
    """The latest date before `day` that falls on `weekday` (0 = Monday)."""
    return day - timedelta(days=(day.weekday() - weekday - 1) % 7 + 1)


def next_weekday(day: date, weekday: int) -> date:
    """The earliest date after `day` that falls on `weekday` (0 = Monday)."""
    return day + timedelta(days=(weekday - day.weekday() - 1) % 7 + 1)


def with_date(pred: str, m: re.Match[str], d: date) -> str:
    """'returned the drill on Monday' -> 'returned the drill on Monday, May 5, 2025'."""
    rest = pred[m.end():]
    return f"{pred[:m.end()]}, {long_date(d)}{',' if rest.strip() else ''}{rest}"


def some_clock(rng: random.Random, lo: int = 8 * 60, hi: int = 21 * 60) -> str:
    """A clock reading people write: a whole hour, a quarter hour or an odd minute."""
    if rng.random() < 0.5:
        return clock_of(rng.randrange(lo, hi + 1, 60))
    if rng.random() < 0.5:
        return clock_of(rng.randrange(lo, hi + 1, 15))
    return clock_of(rng.randrange(lo, hi + 1))


def act_before(rng: random.Random, c: Chat, subj: str, pred: str, clock: float = 0.0,
               back: tuple[int, int] = (1, 6)) -> str:  # fmt: skip
    """The act `subj pred` on a date strictly before the record's.

    A record rules an act out only up to the moment it was sent (guide rule 23), so a denial
    or a negation is set against an act dated before the record's date, never bounded by the
    record's own minute. An act on a named weekday takes the latest such date before the
    record's ("returned the drill on Monday, May 5, 2025"); a booking for a weekday and an act
    on a day of the month are bounded by the record's date ("before May 7, 2025, ..."); any
    other act falls `back` days earlier, at a clock time with probability `clock`.
    """
    if m := ON_WEEKDAY.search(pred):
        return cap(f"{subj} {with_date(pred, m, last_weekday(c.day, WEEKDAYS.index(m[1])))}")
    rec = long_date(c.day)
    if FOR_WEEKDAY.search(pred) or ACT_DAY.search(pred):
        return cap(f"before {rec}, {subj} {pred}")
    d = long_date(c.day - timedelta(days=rng.randint(*back)))
    if ACT_CLOCK.search(pred) is None and rng.random() < clock:
        t = some_clock(rng)
        return cap(rng.choice([f"at {t} on {d}, {subj} {pred}", f"{subj} {pred} at {t} on {d}"]))
    return cap(rng.choice([f"on {d}, {subj} {pred}", f"{subj} {pred} on {d}",
                           f"before {rec}, {subj} {pred}", f"{subj} {pred} before {rec}"]))  # fmt: skip


def sentence(text: str) -> str:
    """An assumption as a sentence: it always ends with a period, after any closing quote."""
    text = text.rstrip()
    return text if text.endswith(".") else f"{text}."


def quoted(s: str) -> str:
    """A record's words inside a rationale, in single quotes."""
    return f"'{s}'"


def kind_of(rng: random.Random, fam: str) -> K:
    return rng.choice(family(fam).kinds)


def wrap(rng: random.Random, core: str, lang: str) -> str:
    """At most one casual decoration around the quotable core, which stays word-aligned.

    Never a laugh or smiley: on a record it would leave open whether the sender meant it
    seriously (guide rule 24), which only the joke family's records do.
    """
    return decorate(rng, core, lang, 0.5, laughs=False)


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
        forms = [f"the message from {s} to {o} says that {pp}", f"{s} {told} {pp}",
                 f"{s} wrote to {o} that {pp}"]  # fmt: skip
    else:
        forms = [f"{s} {told} {pp}", f"in a message to {o}, {s} said {pp}",
                 f"{s} wrote to {o} that {pp}", f"{s} texted {o} that {pp}"]  # fmt: skip
        if not told_only:
            forms += [f"{s} {pred}", f"{s} {pred}"]
    if date:
        d = long_date(c.day)
        forms += [f"on {d}, {s} {told} {pp}", f"{s} wrote to {o} on {d} that {pp}"]
        if rng.random() < 0.6:
            # The telling, bounded by a time after the record's: the record shows it.
            forms = [f"before {bound_time(rng, c, after=True)} on {d}, {s} {told} {pp}"]
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
    now, gap = h * 60 + m, rng.randint(5, 50)
    opts = [f"{s} sent {o} a message on {d}", f"at {clock12(loc)} on {d}, {s} sent {o} a message"]
    if now + gap <= 23 * 60 + 59:
        opts.append(f"before {clock_of(now + gap)} on {d}, {s} texted {o}")
    if now - gap >= 0:
        opts.append(f"after {clock_of(now - gap)} on {d}, {s} sent {o} a message")
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


NOT_SHOWN_THEN = ("the record does not show whether a matching message was also sent then",
                  "one record cannot show that no matching message was sent then",
                  "whether the same words were also sent then is not shown")  # fmt: skip


def spec_time_mismatch(rng: random.Random, c: Chat, pred: str, quote: str,
                       clause: bool = False) -> Spec:  # fmt: skip
    """Same words and people, another local date or clock: complicates (guide rule 23).

    The record shows when these words were sent; it cannot show that no matching message was
    sent at the time the assumption states. `clause` means pred has its own subject.
    """
    loc, s, o = c.local, c.sender.who, c.other.who
    h, m, d = loc.hour, loc.minute, long_date(c.day)
    if not clause:
        pred = f"{c.sender.pron} {pred}"
    told = "wrote in the group chat that" if c.is_group() else f"told {o} that"
    clock = rng.random() < 0.4
    gap = rng.choice(NOT_SHOWN_THEN)
    # A whole hour, or a minute 15 to 90 minutes away from the record's.
    now, k, exact = h * 60 + m, rng.randint(15, 90), rng.random() < 0.5
    later = now + k if exact else (h + 1) * 60 if m <= 49 else -1
    earlier = now - k if exact else h * 60 if m >= 10 else -1
    if clock and 0 <= later <= 23 * 60 + 59:
        a = f"after {clock_of(later)} on {d}, {s} {told} {pred}"
        why = (f"Same words and people, but sent at {clock12(loc)} on {d}, not after "
               f"{clock_of(later)}; {gap}.")  # fmt: skip
    elif clock and earlier >= 0:
        a = f"before {clock_of(earlier)} on {d}, {s} {told} {pred}"
        why = (f"Same words and people, but sent at {clock12(loc)} on {d}, not before "
               f"{clock_of(earlier)}; {gap}.")  # fmt: skip
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
        why = (f"Same words and people, but sent on {d} local time ({c.stamp}), not on {w}; "
               f"{gap}.")  # fmt: skip
    return Spec("ovr_time_mismatch", K.TIME, cap(a), quote, why)


def when_sent(rng: random.Random, c: Chat) -> str:
    """A time that fits the record's: its own minute, or a bound after it."""
    if rng.random() < 0.5:
        return f"at {clock12(c.local)} on {long_date(c.day)}"
    return f"before {bound_time(rng, c, after=True)} on {long_date(c.day)}"


def other_writer_why(shown: str, claimed: str, group: bool = False) -> str:
    """Rationale for a sender or speaker mismatch: complicates, not contradicts (rule 23)."""
    where = "In the group chat, the" if group else "The"
    return (f"{where} words came from {shown}, not {claimed}; the record does not show whether "
            f"{claimed} also wrote them.")  # fmt: skip


def spec_sender_mismatch(rng: random.Random, c: Chat) -> Spec:
    text, s = c.record.text, c.sender.who
    claimed = c.contacts[0].who if c.sender.account.owner else "the owner"
    forms = [f'{claimed} wrote "{text}" to {s}', f'the message "{text}" was sent by {claimed}',
             f'{claimed} sent {s} the message "{text}"',
             f'{claimed} texted {s}: "{text}"']  # fmt: skip
    a = rng.choice(forms)
    if rng.random() < 0.35:  # the time may fit; the sender still does not
        a = f"{when_sent(rng, c)}, {a}"
    why = other_writer_why(c.record.account.sender, claimed)
    return Spec("ovr_sender_mismatch", kind_of(rng, "ovr_sender_mismatch"), cap(a), text, why)


def spec_handle_owner(rng: random.Random, c: Chat, pred: str, quote: str,
                      intro: bool) -> Spec | None:  # fmt: skip
    """A real-person name attached to the sender's account; never to the owner's own account.

    The assumption states the fact of the named person (guide rule 12), never a report.
    """
    if c.sender.account.owner:
        return None
    full, s, after = full_name(rng, c.sender.person), c.sender.who, rng.random() < 0.5
    t = bound_time(rng, c, after, act_minute(pred, c.day))
    if t is None:  # the act's own time is later than any bound (see bounded)
        late = f"{full} {pred} before {long_date(c.day + timedelta(days=int(after)))}"
    elif pred.startswith("had "):  # no "had had"
        late = f"{full} {pred}"
    else:
        late = f"{full} {perfect(pred)} by {t} on {long_date(c.day)}"
    forms = [f"{full} {pred}", f"{full} {pred}", f"{full}, writing as {s}, {pred}", late]
    why = f"The record shows only {s}; nothing shown proves that account is {full}."
    if intro:
        why += " A self-introduction in the chat is not that proof."
    return Spec("ovr_handle_owner", kind_of(rng, "ovr_handle_owner"), cap(rng.choice(forms)), quote,
                why)  # fmt: skip


def spec_partial(rng: random.Random, c: Chat, f: Fact, v: str, quote: str,
                 money: bool) -> Spec | None:  # fmt: skip
    if not f.extra:
        return None
    extra, pred, s = rng.choice(f.extra), fact_claim(f, v, money), c.sender.who
    forms = [f"{s} {pred} and {extra}", f"{s} {pred} and also {extra}"]
    a = cap(rng.choice(forms))
    if rng.random() < 0.4:
        a = bounded(rng, c, s, f"{pred} and {extra}", after=rng.random() < 0.5, simple=True)
    # The record's own words are quoted, so a weekday they name is never read as its date.
    why = (f"The record shows only {quoted(quote)}; nothing shown establishes the rest "
           f"({quoted(extra)}).")  # fmt: skip
    return Spec("ovr_partial", K.EVENT, a, quote, why)


def spec_count(rng: random.Random, c: Chat, f: Fact, v: str, quote: str,
               money: bool) -> Spec | None:  # fmt: skip
    g = fx.general(f, rng, v, money)
    if g is None:
        return None
    g = g.replace("that week", f"in the week of {long_date(c.day)}")  # a dated span, not "that"
    why = "The record shows one instance; the other occasions the assumption asserts are not shown."
    return Spec("ovr_count", K.COMPLETENESS, cap(f"{c.sender.who} {g}"), quote, why)


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
    # A window that names other dates holds the record's date strictly inside, so no reader
    # has to decide whether "between" includes its ends.
    a, b = rng.randint(1, 6), rng.randint(1, 6)
    d1, d2 = long_date(c.day - timedelta(days=a)), long_date(c.day + timedelta(days=b))
    if rng.random() < 0.6:
        span = f"on {long_date(c.day)}" if rng.random() < 0.2 else f"between {d1} and {d2}"
        text = rng.choice([f"there was no contact between the owner and {who} {span}",
                           f"the owner and {who} did not message each other {span}",
                           f"no message passed between the owner and {who} {span}"])  # fmt: skip
        why = f"The record is a message between them at {c.stamp}, inside that window."
    else:
        first = long_date(c.day + timedelta(days=rng.randint(1, 30)))
        text = rng.choice([
            f"the owner and {who} had no contact before {first}",
            f"no message between the owner and {who} predates {first}",
            f"the owner and {who} first messaged each other on {first}",
        ])  # fmt: skip
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


TIME_EVENTS = ("landed in Denver at {t}", "left the gym at {t}", "got to the airport at {t}",
               "arrived at the restaurant at {t}", "closed the shop at {t}",
               "dropped the kids at school at {t}")  # fmt: skip


def spec_irrelevant(rng: random.Random, c: Chat, fam: str, g: Fact, same_person: bool) -> Spec:
    """An assumption the record does not bear on: a plain unrelated fact (an event, an amount, a
    place or a time), never a contact pattern or an identity link, which the excerpt itself could
    bear on."""
    kinds = [k for k in family(fam).kinds if k in (K.EVENT, K.TIME)] or [K.EVENT]
    kind = rng.choice(kinds)
    subj = c.sender.who if same_person else other_party(rng, c)[0]
    if kind == K.TIME:
        t = clock12(c.local.replace(hour=rng.randrange(24), minute=rng.randrange(60)))
        a = f"{subj} {rng.choice(TIME_EVENTS).format(t=t)} on {long_date(c.day)}"
    elif rng.random() < 0.25:
        a = bounded(rng, c, subj, fact_claim(g, rng.choice(g.values)), after=rng.random() < 0.5)
    else:
        a = f"{subj} {fact_claim(g, rng.choice(g.values))}"
    why = "The record is about a different matter and does not bear on the assumption."
    if not same_person:
        why = ("The record is about a different matter and a different account; it does not "
               "bear on the assumption.")  # fmt: skip
    return Spec(fam, kind, cap(a), c.record.text, why)
