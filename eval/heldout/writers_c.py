"""Writers for the three families guide v0.4 added: told frames, undated denials, "never told".

A report ("X told the owner that ...") is about a message, so it is read as one (guide rules
12 and 23). X's own denial, or X's own other value, leaves the report open: one record cannot
show that no other message said it (`ovr_told_frame`). Only a report whose words exclude every
such message ("X never told the owner that ...") is ruled out by one message that says it
(`con_never_told`). A past-tense denial that names no time covers the act only up to when it
was sent, so the act with no time, or dated after the message, stays open
(`ovr_undated_denial`).

Kept out, as the guide keeps them out until Arsh decides: a report of a record that a later
message corrects, a told frame at the record's own minute or about it, and a "never told"
whose time misses the record.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from core.contracts import AssumptionKind as K
from eval.heldout.frames import (
    Line,
    Setup,
    anchor_times,
    draft,
    fill,
    named_fact,
    place,
    plain_fact,
    record_time,
    reported,
    setup_chat,
)
from eval.heldout.scene import Draft, local
from eval.heldout.schedule import Slot
from eval.heldout.text import capitalize_first, date_phrase, date_through, weekday_date
from eval.heldout.writers_a import _restated


def report_clause(e, st: Setup, day: date) -> str:
    """What the sender is reported to have said, as the clause after "that": the act in the
    third person ("they took the tip jar from the banquet") or the fact itself ("7 bags were
    dropped at the Halsted site"). Never a "the sender" clause, which only a message frame can
    carry (schedule.reportable keeps those templates out). A time given only relative to the
    chat ("that day") is fixed to the record's local date `day` (rule 20)."""
    clause = reported(fill(e.vp(), st)) if e.tpl.vp else fill(e.that(), st)
    return anchor_times(clause, day)


def _opening(rng: random.Random, st: Setup, e, neutral: bool = False) -> tuple[list[Line], int]:
    """The record with its question before it when the template has one: a denial answers a
    question ("did u pocket the tip jar?"), and a bare "no" needs it on screen. `neutral`
    keeps the filler to small talk, so no line beside an undated denial gives it a time."""
    if e.tpl.has("ask"):
        core: list[Line] = [(st.receiver, fill(e.part("ask"), st)), (st.sender, e.text())]
        return place(rng, st.chat, core, 1, (0, 3), (0, 2), neutral=neutral)
    return place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=neutral)


def ovr_told_frame(slot: Slot, rng: random.Random) -> Draft:
    """The assumption reports what the sender told or wrote, in the frames supports items use,
    with no time or the record's own local date, never its minute (the guide keeps a told frame
    at the record's minute out). The record, from that sender, denies it or gives another
    value."""
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = _opening(rng, st, e)
    gaps = {target - 1: rng.choice(("quick", "normal"))} if e.tpl.has("ask") else {}
    utc = record_time(rng, st, lines)
    day = local(utc, st.chat.tz).date()
    d = date_phrase(day)
    said = report_clause(e, st, day)
    s, r = st.s, st.r
    assumption = rng.choice(
        [
            f"{s} told {r} that {said}.",
            f"{s} wrote to {r} that {said}.",
            f"On {d}, {s} told {r} that {said}.",
            f"On {d}, {s} wrote to {r} that {said}.",
        ]
    )
    quote = e.quote()
    rationale = rng.choice(
        [
            f'The assumption reports what {s} told {r}. This message from {s} says "{quote}", '
            f"which cannot be true together with the reported words, but it is one message: it "
            f"does not show whether {s} said otherwise in another message, so the report stays "
            f"open.",
            f'{s} writes "{quote}" here, against what the assumption says {s} told {r}. One '
            f"message does not show whether another message from {s} said it, so the record "
            f"leaves the report open; it neither shows the report nor rules it out.",
        ]
    )
    return draft(
        slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc, kinds=gaps
    )


def ovr_undated_denial(slot: Slot, rng: random.Random) -> Draft:
    """The record is the sender's past-tense denial, naming no time and answering no question
    that names one (schedule.undated). The assumption states the act as a fact (rule 12) with
    no time, or dated after the message was sent; the denial covers only the time before."""
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = _opening(rng, st, e, neutral=True)
    gaps = {target - 1: rng.choice(("quick", "normal"))} if e.tpl.has("ask") else {}
    utc = record_time(rng, st, lines)
    sent = local(utc, st.chat.tz).date()
    fact = named_fact(e, st)
    later = rng.random() < 0.5
    if later:
        after = sent + timedelta(days=rng.randint(1, 6))
        assumption = rng.choice(
            [
                f"On {date_phrase(after)}, {fact}.",
                f"{capitalize_first(fact)} on {date_phrase(after)}.",
                f"{capitalize_first(fact)} after {date_phrase(sent)}.",
            ]
        )
        scope = "the assumption dates the act after the message, which the denial does not reach"
    else:
        assumption = plain_fact(e, st)
        scope = "the assumption gives the act no time, so it could fall after the message"
    quote = e.quote()
    sent_on = weekday_date(sent)  # the record's own weekday (rule 24)
    if e.tpl.has("ask"):
        ask = fill(e.part("ask"), st)
        opening = f'To "{ask}", {st.s} replies "{quote}".'
    else:
        opening = f'{st.s} writes "{quote}".'
    rationale = (
        f"{opening} The denial names no time, so it covers only the time before it was sent on "
        f"{sent_on}; {scope}. Nothing in the record shows whether the act happened after it was "
        f"sent, and whether the denial is true is for the expert."
    )
    return draft(
        slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc, kinds=gaps
    )


def con_never_told(slot: Slot, rng: random.Random) -> Draft:
    """The assumption says the sender never told the other party something, or did not tell it
    within a time that holds the record (its date, its month, or a span around it); the record,
    a message from that sender in that chat, says it in plain words, as a sup_plain record
    would. One such message rules the assumption out (rules 12 and 23)."""
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 3))
    utc = record_time(rng, st, lines)
    day = local(utc, st.chat.tz).date()
    said = report_clause(e, st, day)
    s, r = st.s, st.r
    form = rng.randrange(6)
    if form == 0:
        assumption, kind = f"{s} never told {r} that {said}.", K.COMPLETENESS
    elif form == 1:
        assumption, kind = f"{s} never wrote to {r} that {said}.", K.COMPLETENESS
    elif form == 2:
        assumption, kind = f"At no point did {s} tell {r} that {said}.", K.COMPLETENESS
    elif form == 3:
        assumption, kind = f"{s} did not tell {r} on {date_phrase(day)} that {said}.", K.EVENT
    elif form == 4:
        month = f"{day.strftime('%B')} {day.year}"
        assumption = f"At no time in {month} did {s} tell {r} that {said}."
        kind = K.COMPLETENESS
    else:
        d1 = day - timedelta(days=rng.randint(0, 5))
        d2 = day + timedelta(days=rng.randint(1, 5) if d1 == day else rng.randint(0, 5))
        assumption = f"{s} did not tell {r} at any time from {date_through(d1, d2)} that {said}."
        kind = K.COMPLETENESS
    # The whole message: a part of it would not rule out a report of all of it (rule 22).
    quote = e.text()
    rationale = (
        f'This message from {s} to {r}, sent on {weekday_date(day)}, says "{quote}", which '
        f"states {_restated(said)} in plain words. The assumption says no such message was "
        f"sent in that time, and one message that says it rules the assumption out."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, kind, utc)
