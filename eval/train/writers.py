"""Assumption frames and the family specs that attach to any record.

A Spec is what a scenario adds to a Chat for one item: the family, the assumption kind, the
assumption, the quote and the rationale. The stance is never here; it comes from the family.
"""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache

from core.contracts import AssumptionKind as K
from eval.stancedata.chat import fictional_phone, long_date, pretty_phone
from eval.stancedata.families import family
from eval.train import facts as fx
from eval.train.facts import Fact
from eval.train.facts import claim as fact_claim
from eval.train.frames import contact, contact_by, first_contact, none_before, report, sent, words
from eval.train.names import AREA_CODES, Party, full_name, person, telegram_id, username
from eval.train.scenario import Chat, clock12, decorate
from eval.train.topics import topic_stems
from eval.train.when import (
    act_clock,
    bound_time,
    clock_of,
    date_bound,
    fit_when,
    later_time,
    miss_when,
    part_phrase,
    prior_word,
    say_day,
    span,
    telling_when,
    when_sent,
)


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
        d = f"{prior_word(rng)} {day_of(rng, c.day + timedelta(days=1 if after else 0), pred)}"
        return cap(rng.choice([f"{d}, {subj} {pred}", f"{subj} {pred} {d}"]))
    d = day_of(rng, c.day, pred)
    forms = [f"before {t} on {d}, {subj} {pred}", f"by {t} on {d}, {subj} {perfect(pred)}",
             f"{subj} {perfect(pred)} by {t} on {d}"]  # fmt: skip
    # "had had the plumber come" is grammatical but reads as a slip.
    return cap(rng.choice(forms[:1] if simple or pred.startswith("had ") else forms))


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# An act on a named weekday ("returned the drill on Monday") and a booking for one ("booked
# the uhaul for Monday", whose day may still be ahead).
ON_WEEKDAY = re.compile(rf"\bon ({'|'.join(WEEKDAYS)})\b")
FOR_WEEKDAY = re.compile(rf"\bfor ({'|'.join(WEEKDAYS)})\b")
WEEKDAY_WORD = re.compile(rf"\b({'|'.join(WEEKDAYS)})\b", re.I)


def day_of(rng: random.Random, d: date, pred: str) -> str:
    """A date for the act `pred` (when.say_day), without a weekday when the act names its own
    ("booked the uhaul for Saturday"): two weekdays would muddle which day is meant."""
    return long_date(d) if WEEKDAY_WORD.search(pred) else say_day(rng, d)


def last_weekday(day: date, weekday: int) -> date:
    """The latest date before `day` that falls on `weekday` (0 = Monday)."""
    return day - timedelta(days=(day.weekday() - weekday - 1) % 7 + 1)


def next_weekday(day: date, weekday: int) -> date:
    """The earliest date after `day` that falls on `weekday` (0 = Monday)."""
    return day + timedelta(days=(weekday - day.weekday() - 1) % 7 + 1)


def with_date(pred: str, m: re.Match[str], d: date) -> str:
    """'returned the drill on Monday' -> 'returned the drill on Monday, May 5, 2025'."""
    rest = pred[m.end() :]
    return f"{pred[: m.end()]}, {long_date(d)}{',' if rest.strip() else ''}{rest}"


def month_day(day: date, n: int, ahead: bool = False) -> date:
    """The latest date before `day` that is the n-th of its month; with `ahead`, the earliest
    after it."""
    step = 1 if ahead else -1
    d = day + timedelta(days=step)
    while d.day != n:
        d += timedelta(days=step)
    return d


def pin(c: Chat, pred: str, ahead: bool = False) -> str | None:
    """`pred` with the weekday or the day of the month it names as a date, so the act has one
    natural date (guide rule 24): an act on a weekday or on the n-th takes the latest such
    date before the record's, or for a plan (`ahead`) the earliest after it ('returned the
    drill on Monday, May 5, 2025', 'paid the rent on May 3, 2025'); a booking for a weekday
    takes the earliest such date after the record's. None if `pred` names neither."""
    if m := ON_WEEKDAY.search(pred):
        near = next_weekday if ahead else last_weekday
        return with_date(pred, m, near(c.day, WEEKDAYS.index(m[1])))
    if m := FOR_WEEKDAY.search(pred):
        return with_date(pred, m, next_weekday(c.day, WEEKDAYS.index(m[1])))
    if m := ACT_DAY.search(pred):
        d = month_day(c.day, int(m[1]), ahead)
        return f"{pred[: m.start()]}on {long_date(d)}{pred[m.end() :]}"
    return None


def some_minute(rng: random.Random, lo: int = 8 * 60, hi: int = 21 * 60) -> int:
    """A minute of the day people write: a whole hour, a quarter hour or an odd minute."""
    if rng.random() < 0.5:
        return rng.randrange(lo, hi + 1, 60)
    if rng.random() < 0.5:
        return rng.randrange(lo, hi + 1, 15)
    return rng.randrange(lo, hi + 1)


def some_clock(rng: random.Random, lo: int = 8 * 60, hi: int = 21 * 60) -> str:
    """A clock reading people write (see some_minute)."""
    return clock_of(some_minute(rng, lo, hi))


def act_before(rng: random.Random, c: Chat, subj: str, pred: str, clock: float = 0.0,
               back: tuple[int, int] = (1, 6)) -> str:  # fmt: skip
    """The act `subj pred` on a date strictly before the record's.

    A record rules an act out only up to the moment it was sent (guide rule 23), so a denial
    or a negation is set against an act dated before the record's date, never bounded by the
    record's own minute. An act on a named weekday or on a day of the month takes the latest
    such date before the record's ("returned the drill on Monday, May 5, 2025", "paid the rent
    on May 3, 2025"); a booking for a weekday is made before the record's date, for the
    weekday's next date ("before May 7, 2025, ... booked the uhaul for Monday, May 12, 2025");
    any other act falls `back` days earlier, at a clock time with probability `clock`.
    """
    rec = f"{prior_word(rng)} {day_of(rng, c.day, pred)}"
    if FOR_WEEKDAY.search(pred):
        return cap(f"{rec}, {subj} {pin(c, pred)}")
    if pinned := pin(c, pred):
        return cap(f"{subj} {pinned}")
    d = day_of(rng, c.day - timedelta(days=rng.randint(*back)), pred)
    if ACT_CLOCK.search(pred) is None and rng.random() < clock:
        # A closed time on the earlier date: at a minute, about it, a range or a part of the
        # day, never an open bound that could run past the record.
        t = act_clock(rng, some_minute(rng), d, closed=True)
        return cap(rng.choice([f"{t}, {subj} {pred}", f"{subj} {pred} {t}"]))
    forms = [f"on {d}, {subj} {pred}", f"{subj} {pred} on {d}", f"{rec}, {subj} {pred}",
             f"{subj} {pred} {rec}"]  # fmt: skip
    return cap(rng.choice(forms))


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


def frame(rng: random.Random, c: Chat, pred: str, *, when: str | None = None,
          meaning: bool = False, bare: bool = False, who: str | None = None,
          answer: bool = False) -> str:  # fmt: skip
    """'{S} wrote that they {pred}' in one of the frames that report the message (guide rule
    14, frames.report); `when` (see when.py) dates the telling, never the act.

    In a chat that shows one non-owner account the message went to the owner; a group chat
    frame names the group and never a recipient (rule 11). With `bare`, the predicate carries
    its own subject ("Lina said they ...") and no pronoun is put before it. `who` names
    another sender than the record's (the speaker trap); `answer` adds the frames for a reply
    to a question.
    """
    pp = pred if bare else f"{c.sender.pron} {pred}"
    s = c.sender.who if who is None else who
    return cap(report(rng, s, c.other.who, pp, group=c.is_group(), when=when, meaning=meaning,
                      answer=answer))  # fmt: skip


def spec_plain(rng: random.Random, c: Chat, pred: str, quote: str, why: str,
               told_only: bool = False, bare: bool = False) -> Spec:  # fmt: skip
    """A supports assumption that reports what the message communicates (guide rule 14);
    told_only skips the "the message says that" frames for plans and reports."""
    kind = kind_of(rng, "sup_plain")
    text = frame(rng, c, pred, when=telling_when(rng, c, date=0.65, clock=0.12), bare=bare,
                 meaning=kind == K.MEANING and not told_only)  # fmt: skip
    return Spec("sup_plain", kind, text, quote, why)


def spec_verbatim(rng: random.Random, c: Chat) -> Spec:
    when = telling_when(rng, c, date=0.7)
    a = words(rng, c.sender.who, c.other.who, c.record.text, group=c.is_group(), when=when)
    why = f"The record is that message, from {c.record.account.sender} at {c.stamp}."
    return Spec("sup_verbatim", K.TIME if when else K.EVENT, cap(a), c.record.text, why)


def spec_time_window(rng: random.Random, c: Chat) -> Spec:
    """That the record's sender messaged the other side within a window that plainly holds
    the record's local time, in the shapes the time trap's windows take (when.fit_when)."""
    when = fit_when(rng, c, date=1.0, clock=0.65, part=0.1) or f"on {long_date(c.day)}"
    a = sent(rng, c.sender.who, c.other.who, when, group=c.is_group())
    why = f"The record's local time is {c.stamp}, inside the window the assumption states."
    return Spec("sup_time_window", K.TIME, cap(a), c.record.text, why)


NOT_SHOWN_THEN = ("the record does not show whether a matching message was also sent then",
                  "one record cannot show that no matching message was sent then",
                  "whether the same words were also sent then is not shown")  # fmt: skip


def spec_time_mismatch(rng: random.Random, c: Chat, pred: str, clause: bool = False,
                       answer: bool = False) -> Spec:  # fmt: skip
    """Same words and people, another local date or clock: complicates (guide rule 23).

    The record shows when these words were sent; it cannot show that no matching message was
    sent at the time the assumption states. The answer rests on the record's time, so the
    quote is the record in full (rule 22). `clause` means pred has its own subject. The
    assumption reports the message in the frames the supports items use (frames.py), or gives
    its exact words; the time phrase plainly misses the record's (when.miss_when).
    """
    when, miss = miss_when(rng, c)
    if rng.random() < 0.25:
        a = words(rng, c.sender.who, c.other.who, c.record.text, group=c.is_group(), when=when)
    else:
        a = frame(rng, c, pred, when=when, bare=clause, answer=answer)
    why = f"Same words and people, but {miss}; {rng.choice(NOT_SHOWN_THEN)}."
    return Spec("ovr_time_mismatch", K.TIME, cap(a), c.record.text, why)


def other_writer_why(shown: str, claimed: str, group: bool = False) -> str:
    """Rationale for a sender or speaker mismatch: complicates, not contradicts (rule 23)."""
    where = "In the group chat, the" if group else "The"
    return (f"{where} words came from {shown}, not {claimed}; the record does not show whether "
            f"{claimed} also wrote them.")  # fmt: skip


def spec_sender_mismatch(rng: random.Random, c: Chat) -> Spec:
    """The record's words, said to come from the other side of the chat."""
    text, s = c.record.text, c.sender.who
    claimed = c.contacts[0].who if c.sender.account.owner else "the owner"
    # The time may fit; the sender still does not.
    a = words(rng, claimed, s, text, when=when_sent(rng, c))
    why = other_writer_why(c.record.account.sender, claimed)
    return Spec("ovr_sender_mismatch", kind_of(rng, "ovr_sender_mismatch"), cap(a), text, why)


# Words that end an act which takes no date after it ("paid the deposit too on May 2").
NO_TAIL = re.compile(r"\b(too|alone|first|after|front|again|day|time|week)$")


def _on(rng: random.Random, subj: str, pred: str, d: str) -> str:
    """'On {d}, {subj} {pred}' or '{subj} {pred} on {d}'."""
    if " and " in pred or NO_TAIL.search(pred) or rng.random() < 0.5:
        return cap(f"on {d}, {subj} {pred}")
    return cap(f"{subj} {pred} on {d}")


def done_by(rng: random.Random, c: Chat, subj: str, pred: str, p: float = 0.65,
            simple: bool = False) -> str:  # fmt: skip
    """The act `subj pred` as the record states it, dated (with probability p) only by what
    the record shows: done by a clock reading after the record's or before the next date.

    For a trap whose open point is something else (who the account is, an added detail, a
    later correction), the date never adds a second unshown fact.
    """
    if rng.random() >= p:
        return cap(f"{subj} {pred}")
    if m := ON_WEEKDAY.search(pred):
        return cap(f"{subj} {with_date(pred, m, last_weekday(c.day, WEEKDAYS.index(m[1])))}")
    nxt = day_of(rng, c.day + timedelta(days=1), pred)
    t = bound_time(rng, c, after=True, floor=act_minute(pred, c.day))
    if t is None or FOR_WEEKDAY.search(pred) or ACT_DAY.search(pred) or rng.random() < 0.4:
        return cap(f"{prior_word(rng)} {nxt}, {subj} {pred}")
    d = day_of(rng, c.day, pred)
    forms = [f"before {t} on {d}, {subj} {pred}", f"by {t} on {d}, {subj} {perfect(pred)}"]
    return cap(rng.choice(forms[:1] if simple or pred.startswith("had ") else forms))


def dated_act(rng: random.Random, c: Chat, subj: str, pred: str, *, ahead: bool = False,
              p: float = 0.7, clock: float = 0.25, simple: bool = False) -> str:  # fmt: skip
    """The act `subj pred` for a trap whose record does not show the act done, dated with
    probability p: on the record's date or up to four days before it, or for a plan or a
    condition (`ahead`) on it or up to four days after; some of the time (`clock`) bounded by
    a clock reading (see bounded) instead. An act on a named weekday or a day of the month
    takes its nearest date on the same side of the record (see pin). Any such date leaves the
    answer as the trap's.
    """
    if not FOR_WEEKDAY.search(pred) and (pinned := pin(c, pred, ahead)):
        return cap(f"{subj} {pinned}")
    if rng.random() >= p:
        return cap(f"{subj} {pred}")
    k = rng.randint(0, 4)
    d = day_of(rng, c.day + timedelta(days=k if ahead else -k), pred)
    if FOR_WEEKDAY.search(pred) or ACT_CLOCK.search(pred):
        return cap(f"on {d}, {subj} {pred}")  # the act keeps its own day or time
    if rng.random() < clock:
        if not ahead:
            return bounded(rng, c, subj, pred, after=rng.random() < 0.5, simple=simple)
        t = some_clock(rng)
        if simple or pred.startswith("had "):
            return cap(f"before {t} on {d}, {subj} {pred}")
        return cap(rng.choice([f"by {t} on {d}, {subj} {perfect(pred)}",
                               f"before {t} on {d}, {subj} {pred}"]))  # fmt: skip
    return _on(rng, subj, pred, d)


def spec_handle_owner(rng: random.Random, c: Chat, pred: str, quote: str,
                      intro: bool) -> Spec | None:  # fmt: skip
    """A real-person name attached to the sender's account; never to the owner's own account.

    The assumption states the fact of the named person (guide rule 12), never a report, dated
    only as far as the record shows it (see done_by).
    """
    if c.sender.account.owner:
        return None
    full, s = full_name(rng, c.sender.person), c.sender.who
    if rng.random() < 0.2:
        a = cap(f"{full}, writing as {s}, {pred}")
    else:
        a = done_by(rng, c, full, pred, p=0.75)
    why = f"The record shows only {s}; nothing shown proves that account is {full}."
    if intro:
        why += " A self-introduction in the chat is not that proof."
    return Spec("ovr_handle_owner", kind_of(rng, "ovr_handle_owner"), a, quote, why)


def spec_partial(rng: random.Random, c: Chat, f: Fact, v: str, quote: str,
                 money: bool) -> Spec | None:  # fmt: skip
    if not f.extra:
        return None
    extra, pred, s = rng.choice(f.extra), fact_claim(f, v, money), c.sender.who
    also = "" if extra.endswith(" too") else rng.choice(("", "also "))
    a = done_by(rng, c, s, f"{pred} and {also}{extra}", p=0.7, simple=True)
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
    """The owner and the other side were in contact in a window that holds the record and a
    reply from the other side the same day, so the two did exchange messages there. Said with
    the verbs and windows con_in_window says the opposite with (frames.contact, when.span)."""
    if c.is_group():
        return None
    other = c.other
    replies = [i for i, m in enumerate(c.msgs) if i != c.target and m.account == other.account
               and c.local_of(i).date() == c.day]  # fmt: skip
    if not replies:
        return None
    reply = min(replies, key=lambda i: abs(c.local_of(i) - c.local))
    now, back = c.local.hour * 60 + c.local.minute, c.local_of(reply)
    lo, hi = sorted((now, back.hour * 60 + back.minute))
    who = c.contacts[0].who
    if rng.random() < 0.12:
        a = contact_by(rng, who, long_date(c.day + timedelta(days=rng.randint(1, 20))))
    else:
        a = contact(rng, who, span(rng, c, lo, hi, clock=0.6), yes=True)
    why = (f"The record is a message between them at {c.stamp}, and the other side also writes "
           f"in that chat at {clock12(back)} the same day, inside the window.")  # fmt: skip
    return Spec("sup_contact", kind_of(rng, "sup_contact"), cap(a), c.record.text, why)


def spec_in_window(rng: random.Random, c: Chat) -> Spec:
    """No contact in a window that holds the record, or a first contact after it, in the
    words and windows sup_contact uses the other way (frames.contact, when.span). The window
    also holds the other side's nearest message that day when there is one, as sup_contact's
    does; only then may the denial use the verbs that need both sides ("did not exchange
    messages"), and likewise before a first contact."""
    who, roll = c.contacts[0].who, rng.random()
    now = c.local.hour * 60 + c.local.minute
    theirs = [i for i, m in enumerate(c.msgs) if i != c.target and m.account == c.other.account]
    replies = [i for i in theirs if c.local_of(i).date() == c.day]
    earlier = any(c.local_of(i) <= c.local for i in theirs)  # both sides wrote by the record
    if roll < 0.7:
        lo = hi = now
        why = f"The record is a message between them at {c.stamp}, inside that window."
        if replies:
            back = c.local_of(min(replies, key=lambda i: abs(c.local_of(i) - c.local)))
            lo, hi = sorted((now, back.hour * 60 + back.minute))
            why = (f"The record is a message between them at {c.stamp}, inside that window, and "
                   f"the other side also writes in it at {clock12(back)}.")  # fmt: skip
        text = contact(rng, who, span(rng, c, lo, hi, clock=0.6), yes=False,
                       two_way=bool(replies))  # fmt: skip
    elif roll < 0.8 and (t := later_time(rng, c)):
        if rng.random() < 0.5:
            text = first_contact(rng, who, f"after {t}", two_way=earlier)
        else:
            text = none_before(rng, who, t, two_way=earlier)
        why = f"The record is a message between them at {c.stamp}, earlier than that time."
    else:
        first = say_day(rng, c.day + timedelta(days=rng.randint(1, 30)))
        if rng.random() < 0.5:
            text = first_contact(rng, who, f"on {first}", two_way=earlier)
        else:
            text = none_before(rng, who, first, two_way=earlier)
        why = f"The record is a message between them at {c.stamp}, earlier than that date."
    return Spec("con_in_window", kind_of(rng, "con_in_window"), cap(text), c.record.text, why)


def other_party(rng: random.Random, c: Chat) -> tuple[str, Party | None]:
    """An account that is not in the chat, named as a phone would show it; its name is no
    chat member's and appears in no line ("лёша меня кинул" never sits beside an assumption
    about "the contact saved as Лёша")."""
    lang = "ru" if c.lang == "ru" else "en"
    names = {p.person.name for p in [c.owner, *c.contacts]}
    said = " ".join(m.text.lower() for m in c.msgs)
    p = person(rng, lang)
    while p.name in names or p.name.lower()[:4] in said:
        p = person(rng, lang)
    roll = rng.random()
    if roll < 0.5:
        return f"the contact saved as {p.name}", p
    if roll < 0.7:
        return f"Telegram user {telegram_id(rng)}", None
    if roll < 0.85:
        return pretty_phone(fictional_phone(rng, AREA_CODES)), None
    return f"the Instagram account {username(rng, p)}", None


# Unrelated events at a time of day, for irrelevant items. None needs a referent the chat
# would have to show: places anyone can name, or the subject's own ("their").
# Each with the parts of the day it fits: nobody drops kids at school in the evening.
ANY = ("morning", "afternoon", "evening")
TIME_EVENTS = (("landed in Denver on a flight from Atlanta", ANY),
               ("left the gym on Fifth Street", ANY), ("got to the airport in Newark", ANY),
               ("got to work late", ("morning",)), ("left work early", ("afternoon",)),
               ("got home from the grocery store", ANY),
               ("picked their kids up from school", ("afternoon",)),
               ("dropped their kids at school", ("morning",)),
               ("closed their shop early", ("afternoon", "evening")),
               ("checked out of a hotel in Albany", ("morning",)),
               ("boarded a bus to Newark", ANY), ("got gas off Route 9", ANY),
               ("walked their dog for an hour", ANY),
               ("went for a run in the park", ("morning", "evening")))  # fmt: skip
HOURS = {"morning": (6, 11), "afternoon": (12, 16), "evening": (17, 21)}
# Places anyone can name without an antecedent, and things a subject owns or uses: an
# irrelevant assumption says "their rent" where a fact claim says "the rent".
PLACES = ("gym", "airport", "dentist", "doctor", "vet", "ATM", "bank", "train", "bus", "school",
          "police", "hospital", "store", "pharmacy", "DMV")  # fmt: skip
OWNED = ("kids", "car", "truck", "van", "rent", "lease", "landlord", "laptop", "phone", "TV",
         "keys", "key", "apartment", "house", "dog", "sink", "roof", "AC", "plumber",
         "electrician", "mechanic", "trainer", "tutor", "sitter", "accountant", "super",
         "garage", "yard", "deposit", "paycheck", "timesheet", "printer", "router",
         "windshield", "couch", "plates", "passport", "utilities", "loan", "brother", "sister",
         "drill", "hair", "lashes", "nails", "braids", "watch", "bike", "mom", "dad",
         "babysitter", "cousin", "storage unit", "phone bill", "car insurance",
         "gym membership")  # fmt: skip
_OWNED = re.compile(rf"\bthe (?=(?:{'|'.join(OWNED)})\b)")
# What one rents or books is not one's own: "rented a truck", never "rented their truck".
_HIRED = re.compile(r"\b(rented|booked) the (?=(?:truck|van|car)\b)")
# "the gym" needs no referent; "the train tickets" does (the place word is not the head).
_ENDS = "to|at|on|in|for|with|and|by|from|before|after|every|too|again|until|the|a"
_UNANCHORED = re.compile(rf"\bthe (?!(?:{'|'.join(PLACES)})(?:$|[,.]| (?:{_ENDS})\b))")


def own_words(claim: str) -> str | None:
    """A fact claim worded for an irrelevant item, whose record and context show none of its
    referents (guide rule 21): "the rent" becomes "their rent"; None if a referent would stay
    unanchored ("the venue", "the 65 inch TV")."""
    out = _OWNED.sub("their ", _HIRED.sub(r"\1 a ", claim))
    return None if _UNANCHORED.search(out) else out


def chat_topics(c: Chat) -> set[str]:
    """The topic stems of every line of the chat and of every name it shows: how an assumption
    names each party, and the saved name and handle its lines print ("garage_x", the owner's
    own included)."""
    out: set[str] = set()
    for m in c.msgs:
        out |= topic_stems(m.text)
    for p in [c.owner, *c.contacts]:
        out |= topic_stems(f"{p.who} {p.account.label or ''} {p.account.identifier}")
    return out


@cache
def own_claims(g: Fact) -> tuple[tuple[str, frozenset[str]], ...]:
    """The fact's claims, one per value, worded for an irrelevant item (see own_words), each
    with its topic stems."""
    out = []
    for v in g.values:
        if w := own_words(fact_claim(g, v)):
            out.append((w, frozenset(topic_stems(w))))
    return tuple(out)


def spec_irrelevant(rng: random.Random, c: Chat, fam: str, pool: Sequence[Fact],
                    same_person: bool) -> Spec:  # fmt: skip
    """An assumption the record does not bear on: a plain unrelated fact (an event, an amount, a
    place or a time), never a contact pattern or an identity link, which the excerpt itself could
    bear on (guide rule 21). Its words share no topic with any line of the chat or any name the
    chat shows, and it names nothing whose referent the chat would have to show."""
    kind = K.TIME if K.TIME in family(fam).kinds and rng.random() < 0.35 else K.EVENT
    subj = c.sender.who if same_person else other_party(rng, c)[0]
    seen = chat_topics(c)
    if kind == K.TIME:
        events = [e for e in TIME_EVENTS if not topic_stems(e[0]) & seen]
        event, parts = rng.choice(events or list(TIME_EVENTS))
        d, part = say_day(rng, c.day + timedelta(days=rng.randint(-3, 3))), rng.choice(parts)
        if rng.random() < 0.45:
            lo, hi = HOURS[part]
            t = act_clock(rng, rng.randrange(lo * 60, hi * 60 + 60, rng.choice((1, 5, 15, 60))), d)
        else:
            t = part_phrase(rng, part, d)
        a = cap(f"{subj} {event} {t}" if rng.random() < 0.75 else f"{t}, {subj} {event}")
    else:
        claims = [w for g in pool for w, topics in own_claims(g) if not topics & seen]
        if not claims:  # never on the current pools; a plain unrelated event instead
            claims = ["went for a run"]
        pred, roll = rng.choice(claims), rng.random()
        d = day_of(rng, c.day + timedelta(days=rng.randint(-4, 2)), pred)
        if not FOR_WEEKDAY.search(pred) and (pinned := pin(c, pred)):
            a = cap(f"{subj} {pinned}")  # "on Monday" or "on the 3rd" gets its own date
        elif FOR_WEEKDAY.search(pred) or ACT_CLOCK.search(pred):
            # The act keeps its own time ("ordered 4 kegs for Saturday"): no bound, and a date
            # before it never reads as the act's.
            a = cap(f"on {d}, {subj} {pred}") if roll < 0.5 else cap(f"{subj} {pred}")
        elif roll < 0.12:
            a = bounded(rng, c, subj, pred, after=rng.random() < 0.5)
        elif roll < 0.2 and not WEEKDAY_WORD.search(pred):
            t = date_bound(rng, c.day + timedelta(days=rng.randint(-4, 2)), rng.random() < 0.5)[0]
            a = cap(f"{t}, {subj} {pred}" if rng.random() < 0.6 else f"{subj} {pred} {t}")
        elif roll < 0.45:  # with the time events, about as many dated as in other families
            a = _on(rng, subj, pred, d)
        else:
            a = cap(f"{subj} {pred}")
    why = "The record is about a different matter and does not bear on the assumption."
    if not same_person:
        why = ("The record is about a different matter and a different account; it does not "
               "bear on the assumption.")  # fmt: skip
    return Spec(fam, kind, a, c.record.text, why)
