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
from eval.train.names import AREA_CODES, Party, full_name, person, telegram_id, username
from eval.train.scenario import MOSCOW, Chat, clock12, decorate, hour12
from eval.train.topics import topic_stems


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
    record's own minute. An act on a named weekday or on a day of the month takes the latest
    such date before the record's ("returned the drill on Monday, May 5, 2025", "paid the rent
    on May 3, 2025"); a booking for a weekday is made before the record's date, for the
    weekday's next date ("before May 7, 2025, ... booked the uhaul for Monday, May 12, 2025");
    any other act falls `back` days earlier, at a clock time with probability `clock`.
    """
    rec = long_date(c.day)
    if FOR_WEEKDAY.search(pred):
        return cap(f"before {rec}, {subj} {pin(c, pred)}")
    if pinned := pin(c, pred):
        return cap(f"{subj} {pinned}")
    d = long_date(c.day - timedelta(days=rng.randint(*back)))
    if ACT_CLOCK.search(pred) is None and rng.random() < clock:
        t = some_clock(rng)
        return cap(rng.choice([f"at {t} on {d}, {subj} {pred}", f"{subj} {pred} at {t} on {d}"]))
    forms = [f"on {d}, {subj} {pred}", f"{subj} {pred} on {d}", f"before {rec}, {subj} {pred}",
             f"{subj} {pred} before {rec}"]  # fmt: skip
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


PARTS = ((5, 12, "morning"), (12, 17, "afternoon"), (17, 21, "evening"), (21, 24, "night"))


def part_of_day(hour: int) -> str | None:
    """The part of the day an hour falls in; None in the small hours, where "the night of"
    could name either date."""
    return next((p for lo, hi, p in PARTS if lo <= hour < hi), None)


def telling_when(rng: random.Random, c: Chat, date: float = 0.62,
                 clock: float = 0.2) -> str | None:  # fmt: skip
    """When the record was sent, as a supports or message-level assumption may say it.

    With probability `date` the phrase names the record's local date: plainly ("on May 2,
    2025"), by the part of the day, or (with probability `clock`) as a bound after or before
    the record's clock, never its own minute (see bound_time). None leaves the time out. A
    date on a message makes no cue for any answer: trap and contradicts assumptions carry dates
    as often.
    """
    roll, d = rng.random(), long_date(c.day)
    if roll >= date:
        return None
    if roll < clock:
        if rng.random() < 0.55 and (t := bound_time(rng, c, after=True)):
            return f"before {t} on {d}"
        if t := bound_time(rng, c):
            return f"after {t} on {d}"
    elif roll < clock + 0.07 and (part := part_of_day(c.local.hour)):
        return f"on the {part} of {d}"
    return f"on {d}"


def frame(rng: random.Random, c: Chat, pred: str, *, when: str | None = None,
          meaning: bool = False, bare: bool = False) -> str:  # fmt: skip
    """'{S} wrote that they {pred}' in one of several frames that report the message (guide
    rule 14); `when` (see telling_when) dates the telling, never the act.

    In a chat that shows one non-owner account the message went to the owner; a group chat
    frame names the group and never a recipient (rule 11). With `bare`, the predicate carries
    its own subject ("Lina said they ...") and no pronoun is put before it.
    """
    s, o = c.sender.who, c.other.who
    pp = pred if bare else f"{c.sender.pron} {pred}"
    if meaning and rng.random() < 0.3:
        # The date belongs to the sending: "the message X sent on May 2, 2025 says that ...".
        to = " to the group" if c.is_group() else ""
        sent = f"the message {s} sent{to} {when}" if when else f"the message from {s}{to}"
        return cap(f"{sent} says that {pp}")
    if c.is_group():
        forms = [f"{s} wrote in the group chat that {pp}", f"{s} told the group that {pp}"]
    else:
        forms = [
            f"{s} wrote that {pp}",
            f"{s} wrote that {pp}",
            f"{s} wrote that {pp}",
            f"{s} texted that {pp}",
            f"{s} said {pp}",
        ]
        if not c.sender.account.owner:  # "told the owner"; a contact's saved name runs long
            forms.append(f"{s} told {o} that {pp}")
    a = rng.choice(forms)
    return cap(f"{when}, {a}" if when else a)


def spec_plain(rng: random.Random, c: Chat, pred: str, quote: str, why: str,
               told_only: bool = False, bare: bool = False) -> Spec:  # fmt: skip
    """A supports assumption that reports what the message communicates (guide rule 14);
    told_only skips the "the message says that" frames for plans and reports."""
    kind = kind_of(rng, "sup_plain")
    text = frame(rng, c, pred, when=telling_when(rng, c, date=0.7, clock=0.15), bare=bare,
                 meaning=kind == K.MEANING and not told_only)  # fmt: skip
    return Spec("sup_plain", kind, text, quote, why)


def spec_verbatim(rng: random.Random, c: Chat) -> Spec:
    s, o, text = c.sender.who, c.other.who, c.record.text
    when = telling_when(rng, c, date=0.7)
    if c.is_group():
        forms = [f'{s} wrote "{text}" in the group chat', f'{s} sent "{text}" to the group']
    else:
        forms = [f'{s} sent {o} the message "{text}"', f'{s} wrote "{text}" to {o}',
                 f'{s} texted {o} "{text}"', f'the message "{text}" was sent by {s} to {o}',
                 f'{s} sent the message "{text}"']  # fmt: skip
    a = rng.choice(forms)
    why = f"The record is that message, from {c.record.account.sender} at {c.stamp}."
    return Spec("sup_verbatim", K.TIME if when else K.EVENT, cap(f"{when}, {a}" if when else a),
                text, why)  # fmt: skip


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
    if part := part_of_day(h):
        opts.append(f"{s} messaged {o} on the {part} of {d}")
    why = f"The record's local time is {c.stamp}, inside the window the assumption states."
    return Spec("sup_time_window", K.TIME, cap(rng.choice(opts)), c.record.text, why)


NOT_SHOWN_THEN = ("the record does not show whether a matching message was also sent then",
                  "one record cannot show that no matching message was sent then",
                  "whether the same words were also sent then is not shown")  # fmt: skip


def spec_time_mismatch(rng: random.Random, c: Chat, pred: str, clause: bool = False) -> Spec:
    """Same words and people, another local date or clock: complicates (guide rule 23).

    The record shows when these words were sent; it cannot show that no matching message was
    sent at the time the assumption states. The answer rests on the record's time, so the
    quote is the record in full (rule 22). `clause` means pred has its own subject.
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
    elif clock and earlier >= 60:
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
    return Spec("ovr_time_mismatch", K.TIME, cap(a), c.record.text, why)


def when_sent(rng: random.Random, c: Chat) -> str | None:
    """A time that fits the record's: its own minute, which picks out the message, or a
    telling_when phrase (None for no time)."""
    if rng.random() < 0.3:
        return f"at {clock12(c.local)} on {long_date(c.day)}"
    return telling_when(rng, c, date=0.55, clock=0.25)


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
    if when := when_sent(rng, c):  # the time may fit; the sender still does not
        a = f"{when}, {a}"
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
    nxt = long_date(c.day + timedelta(days=1))
    t = bound_time(rng, c, after=True, floor=act_minute(pred, c.day))
    if t is None or FOR_WEEKDAY.search(pred) or ACT_DAY.search(pred) or rng.random() < 0.4:
        return cap(f"before {nxt}, {subj} {pred}")
    d = long_date(c.day)
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
    d = long_date(c.day + timedelta(days=k if ahead else -k))
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
    other = c.other
    replied = any(m.account == other.account and c.local_of(i).date() == c.day
                  for i, m in enumerate(c.msgs) if i != c.target)  # fmt: skip
    if not replied or c.is_group():
        return None
    who, d = c.contacts[0].who, long_date(c.day)
    d1 = long_date(c.day - timedelta(days=rng.randint(0, 5)))
    d2 = long_date(c.day + timedelta(days=rng.randint(0, 5)))
    # "From ... through ..." includes both ends: no reader has to decide what "between" covers.
    forms = [f"the owner and {who} exchanged messages on {d}",
             f"the owner and {who} were in contact on {d}",
             f"from {d1} through {d2}, the owner and {who} exchanged messages"]  # fmt: skip
    why = (f"The record is a message between them at {c.stamp}, and the other side also "
           "writes the same day.")  # fmt: skip
    return Spec(
        "sup_contact", kind_of(rng, "sup_contact"), cap(rng.choice(forms)), c.record.text, why
    )


def _no_contact(rng: random.Random, who: str, span: str) -> str:
    return rng.choice([f"there was no contact between the owner and {who} {span}",
                       f"the owner and {who} did not message each other {span}",
                       f"no message passed between the owner and {who} {span}"])  # fmt: skip


def spec_in_window(rng: random.Random, c: Chat) -> Spec:
    """No contact in a window that holds the record, or a first contact after it.

    Windows of dates say "from ... through ..." or "on ... or ...", so no reader has to decide
    whether "between" includes its ends (and no window ends at the record's own minute).
    """
    who, d, roll = c.contacts[0].who, long_date(c.day), rng.random()
    lo, hi = bound_time(rng, c), bound_time(rng, c, after=True)
    inside = f"The record is a message between them at {c.stamp}, inside that window."
    if roll < 0.3 and lo and hi:
        span = rng.choice([f"from {lo} to {hi} on {d}", f"after {lo} on {d}"])
        text, why = _no_contact(rng, who, span), inside
    elif roll < 0.4 and hi:
        text = rng.choice(
            [
                f"the owner and {who} had no contact before {hi} on {d}",
                f"the owner and {who} first messaged each other after {hi} on {d}",
            ]
        )
        why = f"The record is a message between them at {c.stamp}, earlier than that time."
    elif roll < 0.75:
        a, b = rng.randint(1, 6), rng.randint(1, 6)
        d1, d2 = long_date(c.day - timedelta(days=a)), long_date(c.day + timedelta(days=b))
        k = rng.choice((-1, 1))
        near = long_date(c.day + timedelta(days=k))
        pair = f"on {near} or {d}" if k < 0 else f"on {d} or {near}"
        span = rng.choice([f"on {d}", f"from {d1} through {d2}", pair])
        text, why = _no_contact(rng, who, span), inside
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
    """The topic stems of every line of the chat and of every name it shows."""
    out: set[str] = set()
    for m in c.msgs:
        out |= topic_stems(m.text)
    for p in [c.owner, *c.contacts]:
        out |= topic_stems(p.who)
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
        d, part = long_date(c.day + timedelta(days=rng.randint(-3, 3))), rng.choice(parts)
        if rng.random() < 0.45:
            lo, hi = HOURS[part]
            t = clock_of(rng.randrange(lo * 60, hi * 60 + 60, rng.choice((1, 5, 15, 60))))
            a = cap(f"{subj} {event} at {t} on {d}")
        else:
            a = cap(f"{subj} {event} on the {part} of {d}")
    else:
        claims = [w for g in pool for w, topics in own_claims(g) if not topics & seen]
        if not claims:  # never on the current pools; a plain unrelated event instead
            claims = ["went for a run"]
        pred, roll = rng.choice(claims), rng.random()
        d = long_date(c.day + timedelta(days=rng.randint(-4, 2)))
        if not FOR_WEEKDAY.search(pred) and (pinned := pin(c, pred)):
            a = cap(f"{subj} {pinned}")  # "on Monday" or "on the 3rd" gets its own date
        elif FOR_WEEKDAY.search(pred) or ACT_CLOCK.search(pred):
            # The act keeps its own time ("ordered 4 kegs for Saturday"): no bound, and a date
            # before it never reads as the act's.
            a = cap(f"on {d}, {subj} {pred}") if roll < 0.5 else cap(f"{subj} {pred}")
        elif roll < 0.12:
            a = bounded(rng, c, subj, pred, after=rng.random() < 0.5)
        elif roll < 0.5:
            a = _on(rng, subj, pred, d)
        else:
            a = cap(f"{subj} {pred}")
    why = "The record is about a different matter and does not bear on the assumption."
    if not same_person:
        why = ("The record is about a different matter and a different account; it does not "
               "bear on the assumption.")  # fmt: skip
    return Spec(fam, kind, a, c.record.text, why)
