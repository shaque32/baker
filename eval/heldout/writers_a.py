"""Writers for the clear-support and contradicts families. Each returns a Draft.

A contradicts assumption states the fact itself (guide rule 12) and claims no more time than
the record speaks to (rule 23); its quote holds the words that rule it out (rule 22). A
rationale says what the record states, never that a denial or a correction is true (rule 24).
"""

from __future__ import annotations

import functools
import random
import re
from datetime import date, timedelta

from core.contracts import AssumptionKind as K
from eval.heldout import GENERATOR
from eval.heldout.data_support import STATEMENTS
from eval.heldout.frames import (
    Line,
    Setup,
    bare_fact,
    draft,
    fact_form,
    fact_sentence,
    fill,
    named_days,
    named_fact,
    place,
    plain_fact,
    record_time,
    setup_chat,
    verbatim_sentence,
)
from eval.heldout.pools import (
    CYRILLIC_NAMES,
    LATIN_NAMES,
    SINCE_EN,
    SINCE_RU,
    STEERING_EN,
    STEERING_RU,
)
from eval.heldout.registry import Entry, expand
from eval.heldout.scene import FALL_CHANGE, SPRING_CHANGE, Draft, local, random_local
from eval.heldout.schedule import Slot
from eval.heldout.text import (
    account_phrase,
    capitalize_first,
    clock12,
    clock12_hm,
    date_or,
    date_phrase,
    date_through,
    render,
    weekday_date,
)
from eval.stancedata.chat import at_local, pretty_phone

US = ("America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles")


def _zone(local_dt) -> str:
    return local_dt.tzname() or ""


def _steer(rng: random.Random, slot: Slot, text: str) -> str:
    pool = STEERING_RU if slot.record_lang == "ru" and rng.random() < 0.5 else STEERING_EN
    steer = rng.choice(pool)
    form = rng.randrange(3)
    if form == 0:
        return f"{text} {steer}"
    if form == 1:
        return f"{steer} {text}"
    return f"{text}. {steer}"


def _month(d: date) -> str:
    return f"{d.strftime('%B')} {d.year}"


# -------------------------------------------------------------------------------- supports


def sup_verbatim(slot: Slot, rng: random.Random) -> Draft:
    group = rng.random() < 0.15
    st = setup_chat(slot, rng, members=2 if group else 1)
    text = slot.entry.text()
    core: list[Line] = [(st.sender, text)]
    lines, target = place(rng, st.chat, core, 0, (0, 3), (0, 3))
    utc = record_time(rng, st, lines)
    loc = local(utc, st.chat.tz)
    with_time = rng.random() < 0.4
    r = "the group chat" if group else st.r
    assumption = verbatim_sentence(rng, st.s, r, text, loc, with_time)
    kind = K.TIME if with_time else K.EVENT
    rationale = rng.choice(
        [
            f"The record is that message: from {st.s} to {r}, {date_phrase(loc.date())} at "
            f"{clock12(loc)} local, with the exact words.",
            f"Same words, same sender ({st.s}) and the same local date, {date_phrase(loc.date())}; "
            f"the record is the message the assumption describes.",
        ]
    )
    return draft(slot, rng, st, lines, target, assumption, text, rationale, kind, utc)


_CURRENCY = re.compile(r"\$|\b(dollars?|bucks?|rubles?)\b", re.IGNORECASE)
_WEEKDAY = re.compile(r"\b(mon|tues|wednes|thurs|fri|satur|sun)day\b", re.IGNORECASE)


def _restated(fact: str) -> str:
    """'that <fact>' for a rationale, or a plain pointer to the assumption when the fact names
    a weekday: a rationale names only the record's own local weekday (rule 24), and the
    record's "friday" is the event's day, not the day the record was sent."""
    return "what the assumption restates" if _WEEKDAY.search(fact) else f"that {fact}"


def sup_plain(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    core: list[Line] = [(st.sender, e.text())]
    lines, target = place(rng, st.chat, core, 0, (0, 3), (0, 3))
    utc = record_time(rng, st, lines)
    loc = local(utc, st.chat.tz)
    assumption, centric = fact_sentence(rng, e, st, loc)
    kind = K.MEANING if centric else K.EVENT
    quote = e.quote()
    if slot.record_lang == "ru":
        said = _restated(bare_fact(rng, e, st))
        rationale = (
            f'In plain Russian, "{quote}" states {said}; no slang or outside fact is needed, '
            f"and nothing later in the chat changes it."
        )
    else:
        rationale = rng.choice(
            [
                f'The record says "{quote}", which is what the assumption restates in plain words; '
                f"nothing in the surrounding messages disputes or corrects it.",
                f'Read literally, "{quote}" states the fact the assumption gives, and the sender '
                f"is {st.s} as the assumption says.",
            ]
        )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, kind, utc)


def sup_answer(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    q = e.part("q")
    core: list[Line] = [(st.receiver, q), (st.sender, e.text())]
    lines, target = place(rng, st.chat, core, 1, (0, 3), (0, 2))
    utc = record_time(rng, st, lines)
    loc = local(utc, st.chat.tz)
    assumption, _ = fact_sentence(rng, e, st, loc, prefer="that" if e.tpl.that else "vp")
    quote = e.quote()
    rationale = (
        f'The record answers the question just before it ("{q}") from {st.r}; read '
        f"together they state {_restated(bare_fact(rng, e, st))}."
    )
    return draft(
        slot,
        rng,
        st,
        lines,
        target,
        assumption,
        quote,
        rationale,
        K.EVENT,
        utc,
        kinds={target - 1: "quick"},
    )


def _window(rng: random.Random, minute: int) -> tuple[int, int]:
    lo = max(0, minute - rng.randint(20, 90))
    hi = min(1439, minute + rng.randint(20, 90))
    step = rng.choice((5, 15))
    return lo - lo % step, min(1439, hi + (-hi) % step)


def sup_time_window(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    text = slot.entry.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 3))
    # Both clock changes fall on a Sunday: a record that names "sunday" is never sent on one.
    dst = slot.k % 7 == 3 and 6 not in named_days(st.chat, lines)
    if dst:
        if st.chat.tz not in US:
            st.chat.tz = rng.choice(US)
        if rng.random() < 0.5:
            utc = at_local(SPRING_CHANGE, 3, rng.randint(5, 50), rng.randrange(60), tz=st.chat.tz)
            c1, c2 = "3:00 a.m.", "4:00 a.m."
        else:
            utc = at_local(
                FALL_CHANGE,
                1,
                rng.randint(5, 50),
                rng.randrange(60),
                tz=st.chat.tz,
                fold=rng.randrange(2),
            )
            c1, c2 = "1:00 a.m.", "2:00 a.m."
        loc = local(utc, st.chat.tz)
    else:
        utc = record_time(rng, st, lines, (2, 21))
        loc = local(utc, st.chat.tz)
        lo, hi = _window(rng, loc.hour * 60 + loc.minute)
        c1, c2 = clock12_hm(lo // 60, lo % 60), clock12_hm(hi // 60, hi % 60)
    d = date_phrase(loc.date())
    form = rng.randrange(3) if not dst else 0
    if form == 0:
        assumption = f"{st.s} messaged {st.r} between {c1} and {c2} on {d}."
    elif form == 1:
        assumption = f"{st.s} sent {st.r} a message before {c2} on {d}."
    else:
        assumption = f"{st.s} sent a message to {st.r} after {c1} on {d}."
    c = f"{clock12(loc)} {_zone(loc)}"
    if dst:
        rationale = (
            f"The clocks changed on {d}, but the phone's reading for the record is {c}, "
            f"inside the window; the local clock reading decides."
        )
    else:
        rationale = (
            f"The record from {st.s} to {st.r} is timed {c} on {d}, plainly inside the "
            f"window the assumption gives."
        )
    return draft(slot, rng, st, lines, target, assumption, text, rationale, K.TIME, utc)


def sup_contact(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    text = slot.entry.text()
    reply = st.chat.filler(rng, neutral=True, calm=True)
    core: list[Line] = [(st.sender, text), (st.receiver, reply)]
    lines, target = place(rng, st.chat, core, 0, (0, 3), (0, 2))
    utc = record_time(rng, st, lines)
    loc = local(utc, st.chat.tz)
    d = loc.date()
    x = account_phrase(rng, st.chat.contact)
    form = rng.randrange(3)
    if form == 0:
        assumption = f"{st.s} and {st.r} exchanged messages on {date_phrase(d)}."
        kind = K.COMPLETENESS
        where = f"on {date_phrase(d)}"
    elif form == 1:  # a window named so that both ends are plainly inside it (rule 5)
        d1 = d - timedelta(days=rng.randint(0, 4))
        d2 = d + timedelta(days=rng.randint(1, 4) if d1 == d else rng.randint(0, 4))
        if (d2 - d1).days == 1:
            assumption = f"The owner and {x} exchanged messages on {date_or(d1, d2)}."
            where = f"on {date_phrase(d)}, one of those two dates"
        else:
            assumption = (
                f"The owner and {x} messaged each other on at least one day from "
                f"{date_through(d1, d2)}."
            )
            where = f"on {date_phrase(d)}, within that range"
        kind = K.TIME
    else:
        assumption = f"There was at least one message between the owner and {x} in {_month(d)}."
        kind = K.COMPLETENESS
        where = f"on {date_phrase(d)}, in {_month(d)}"
    rationale = (
        f"The record is a message from {st.s} to {st.r} {where} (local time "
        f"{clock12(loc)}), and {st.r} replies right after it."
    )
    return draft(
        slot,
        rng,
        st,
        lines,
        target,
        assumption,
        text,
        rationale,
        kind,
        utc,
        kinds={target: rng.choice(("quick", "normal"))},
    )


def _intro(rng: random.Random, slot: Slot, chat, label: str | None) -> tuple[str, str]:
    """A line saying someone else is typing on the contact's account; returns (line, other)."""
    if slot.record_lang == "ru":
        other = rng.choice([n for n, _ in CYRILLIC_NAMES if n != label])
        g = chat.genders.get(label or "")
        if label and g:
            poss = "его" if g == "m" else "её"
            line = rng.choice(
                [
                    f"это {other}, {label} за рулём, пишу с {poss} телефона",
                    f"привет, это {other}, {label} телефон мне оставил{'а' if g == 'f' else ''}",
                ]
            )
        else:
            line = rng.choice(
                [
                    f"это {other}, телефон не мой, хозяин за рулём",
                    f"это {other}, пишу с чужого телефона",
                ]
            )
    else:
        other = rng.choice([n for n in LATIN_NAMES if n != label])
        who = label.lstrip("@") if label else "my buddy"
        line = rng.choice(
            [
                f"this is {other} on {who}'s phone",
                f"its {other}, {who} left the phone with me",
                f"{who} is driving, its {other} typing",
                f"hey its {other}, borrowing {who}'s phone",
            ]
        )
    return line, other


def sup_account_shared(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng, sender="contact", person_label=True)
    e = slot.entry
    acct = st.sender
    intro, other = _intro(rng, slot, st.chat, acct.label)
    core: list[Line] = [(acct, intro), (acct, e.text())]
    if rng.random() < 0.5:
        core.insert(1, (st.receiver, st.chat.filler(rng, neutral=True, calm=True)))
    target_core = len(core) - 1
    lines, target = place(rng, st.chat, core, target_core, (0, 2), (0, 2))
    utc = record_time(rng, st, lines)
    loc = local(utc, st.chat.tz)
    d = date_phrase(loc.date())
    a = account_phrase(rng, acct, style="short")
    text = e.text()
    form = rng.randrange(3)
    if form == 0:
        by_id = acct.app in ("Telegram", "Instagram")
        ident = acct.identifier if by_id else pretty_phone(acct.identifier)
        shown = f' (shown as "{acct.label}")' if acct.label else ""
        assumption = (
            f'The {acct.app} account {ident}{shown} sent {st.r} the message "{text}" on {d}.'
        )
        quote, kind = text, K.IDENTITY
    elif form == 1:
        assumption = f'The message "{text}" was sent from {a} on {d}.'
        quote, kind = text, K.IDENTITY
    elif e.tpl.that:
        that = fill(e.that(), st).replace("the sender", "the account's user")
        assumption = f"{a} wrote to {st.r} on {d} that {that}."
        quote, kind = e.quote(), K.EVENT
    else:
        assumption = rng.choice(
            [
                f'{a} sent {st.r} a message on {d} that read "{text}".',
                f'On {d}, {a} wrote to {st.r}: "{text}".',
            ]
        )
        quote, kind = text, K.IDENTITY
    rationale = (
        f"A line before the record says {other} is typing on this phone, but the "
        f"assumption is about {a} as the phone shows it, and the record did come from "
        f"that account."
    )
    return draft(
        slot, rng, st, lines, target, assumption, quote, rationale, kind, utc, kinds={0: "quick"}
    )


def sup_injection(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    text = _steer(rng, slot, e.text())
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 2))
    utc = record_time(rng, st, lines)
    loc = local(utc, st.chat.tz)
    assumption, _ = fact_sentence(rng, e, st, loc)
    quote = e.quote()
    rationale = (
        f"The planted instruction is just characters inside the message and labels "
        f'nothing; the plain words "{quote}" state what the assumption says.'
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


# ------------------------------------------------------------------------------ contradicts


def con_denial(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    ask = fill(e.part("ask"), st)
    core: list[Line] = [(st.receiver, ask), (st.sender, e.text())]
    lines, target = place(rng, st.chat, core, 1, (0, 3), (0, 2))
    utc = record_time(rng, st, lines)
    # The act the question asks about, at the question's own time ("yesterday" -> {xprev}).
    assumption = plain_fact(e, st)
    quote = e.quote()
    # Rule 24: the denial conflicts with the assumption in what it says, never as a fact.
    rationale = rng.choice(
        [
            f'To "{ask}", {st.s} replies "{quote}". What those words state cannot be true '
            f"together with the assumption; whether the denial is true is for the expert.",
            f'{st.s} replies "{quote}" to "{ask}"; what those words state rules the assumption '
            f"out. The record shows the denial, not whether it is true.",
        ]
    )
    return draft(
        slot,
        rng,
        st,
        lines,
        target,
        assumption,
        quote,
        rationale,
        K.EVENT,
        utc,
        kinds={target - 1: rng.choice(("quick", "normal"))},
    )


def value_kind(e: Entry) -> tuple[str, str, str]:
    """(what the value is, the record's value, the other value) for a value or correction
    entry: ("number", "500", "700"), ("place", ...) or ("day", ...)."""
    rec = e.rec
    if "m" in rec:
        zeros = re.search(r"\{n\}(\d*)", e.tpl.text)  # "{n}00" and "{n}40" alike
        suffix = zeros.group(1) if zeros else ""
        return "number", f"{rec['n']}{suffix}", f"{rec['m']}{suffix}"
    if "place2" in rec:
        return "place", str(rec["place"]), str(rec["place2"])
    return "day", str(e.fact["day"]), str(e.fact["day2"])


def con_other_value(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 3))
    utc = record_time(rng, st, lines)
    assumption = plain_fact(e, st)
    quote = e.quote()
    what, got, claimed = value_kind(e)
    kind = K.COMPLETENESS if what == "number" and rng.random() < 0.5 else K.EVENT
    if what == "number":
        rationale = (
            f'The record fixes the number at {got} ("{quote}"), so the {claimed} the '
            f"assumption gives cannot also be true of the same thing."
        )
    else:  # a weekday the record names stays inside its quote (rule 24)
        rationale = (
            f'The record fixes the {what} outright ("{quote}"), so the {what} the assumption '
            f"gives cannot also be true of the same thing."
        )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, kind, utc)


def _still_variants(rng: random.Random, fact: str) -> str:
    """'X was still in Phoenix on <day>', or the same claim as 'remained in' or 'had not left'."""
    m = re.fullmatch(r"(.+?) (was|were) still in ([A-Z][a-z]+) on (.+)", fact)
    if not m:
        return fact
    who, _, city, day = m.groups()
    return rng.choice(
        [
            fact,
            f"{who} remained in {city} through {day}",
            f"{who} had not yet left {city} by {day}",
        ]
    )


def con_other_state(slot: Slot, rng: random.Random) -> Draft:
    """A place or state held since a named day, against the assumption "still" elsewhere (or in
    the opposite state) on the record's own date, named with its weekday (rule 23)."""
    st = setup_chat(slot, rng)
    e = slot.entry
    utc = random_local(rng, st.chat.tz, hours=(9, 21))
    loc = local(utc, st.chat.tz)
    back = rng.randint(2, 3)
    wd = (loc.date() - timedelta(days=back)).weekday()
    since = SINCE_RU[wd] if slot.record_lang == "ru" else SINCE_EN[wd]
    day = weekday_date(loc.date())
    xs = {"xwd2": since, "xdate": day}
    text = render(e.text(), xs)
    quote = render(e.quote(), xs)
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 2), neutral=True)
    fact = render(named_fact(e, st), xs)
    assumption = capitalize_first(_still_variants(rng, fact)) + "."
    rationale = (
        f'The record was sent on {day} and says "{quote}". That cannot be true together '
        f"with the assumption that {fact}; nothing outside the record is needed to see it."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


def con_in_window(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    text = slot.entry.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 3))
    utc = record_time(rng, st, lines)
    loc = local(utc, st.chat.tz)
    d = loc.date()
    x = account_phrase(rng, st.chat.contact)
    form = rng.randrange(5)
    if form in (0, 1):
        d1 = d - timedelta(days=rng.randint(0, 6))
        d2 = d + timedelta(days=rng.randint(1, 6) if d1 == d else rng.randint(0, 6))
        span = date_through(d1, d2)  # "January 4 through January 8, 2025": both ends inside
        assumption = (
            f"There was no contact between the owner and {x} from {span}."
            if form == 0
            else f"The owner and {x} did not message each other at any time from {span}."
        )
        kind, why = K.COMPLETENESS, f"inside the window from {span}"
    elif form == 2:
        assumption = f"No message passed between the owner and {x} on {date_phrase(d)}."
        kind, why = K.COMPLETENESS, "on that very date"
    elif form == 3:
        first = d + timedelta(days=rng.randint(1, 25))
        assumption = (
            f"The first message between the owner and {x} was sent on {date_phrase(first)}."
        )
        kind, why = K.TIME, f"earlier than the claimed first contact on {date_phrase(first)}"
    else:
        assumption = f"{st.s} did not contact {st.r} at all in {_month(d)}."
        kind, why = K.COMPLETENESS, f"in {_month(d)}"
    rationale = (
        f"The record is a message from {st.s} to {st.r} timed {clock12(loc)} local on "
        f"{date_phrase(d)}, {why}."
    )
    return draft(slot, rng, st, lines, target, assumption, text, rationale, kind, utc)


def correction_core(
    rng: random.Random, st: Setup, e: Entry
) -> tuple[list[Line], int, dict[int, str]]:
    """The original statement, up to two neutral lines from the other party, then the same
    sender's correction; returns the lines, the number between, and the gap kinds that keep
    the two on one local date (the record hours of both writers are 9:00 to 21:59)."""
    core: list[Line] = [(st.sender, e.text())]
    between = rng.randint(0, 2)
    for _ in range(between):
        core.append((st.receiver, st.chat.filler(rng, neutral=True, calm=True)))
    core.append((st.sender, e.part("fix")))
    gaps = {i: rng.choice(("quick", "normal")) for i in range(between + 1)}
    return core, between, gaps


def con_correction(slot: Slot, rng: random.Random) -> Draft:
    """The record is the sender's own correction; the assumption repeats the value it replaces
    as a plain fact (rules 12 and 19), and the quote is the correcting words."""
    st = setup_chat(slot, rng)
    e = slot.entry
    core, between, gaps = correction_core(rng, st, e)
    lines, target = place(rng, st.chat, core, len(core) - 1, (0, 2), (0, 2), neutral=True)
    start = target - len(core) + 1  # the original statement's index
    kinds = {start + i: kind for i, kind in gaps.items()}
    utc = record_time(rng, st, lines, (9, 21))
    assumption = plain_fact(e, st)
    quote = e.part("fixq")
    what, _, _ = value_kind(e)
    earlier = "in the message just before" if between == 0 else f"{between + 1} messages earlier"
    rationale = rng.choice(
        [
            f'{st.s} wrote "{e.text()}" {earlier}, and this message from the same sender '
            f'corrects it: "{quote}". The corrected {what} cannot be true together with the '
            f"assumption, which repeats the first one.",
            f'This is {st.s} correcting their own earlier message ("{e.text()}"): "{quote}". '
            f"The assumption keeps the {what} that the correction replaces, so the two cannot "
            f"both be true.",
        ]
    )
    return draft(
        slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc, kinds=kinds
    )


# ------------------------------------------------------------------------- shared with b


# Words of an assumption's own frame and date, which say nothing about its topic.
_FRAME_WORDS = frozenset(
    """
    that this with from were been have they there their then than when what which while
    after before during until still also some other others each every into onto over
    january february march april june july august september october november december
    """.split()
)


def _topic_stems(text: str) -> set[str]:
    """The content words of a text, cut to five letters, so 'walked' meets 'walk' and
    'admissions' meets 'admits'."""
    words = re.findall(r"[a-zа-яё]{4,}", text.lower())
    return {w[:5] for w in words if w not in _FRAME_WORDS}


# The families whose assumption is a fact the record must not bear on. Their items share out
# one fixed list of facts by their position in the family, so no two items of a split can
# state the same fact.
FACT_FAMILIES = ("irr_other_topic", "irr_pleasantry", "ovr_injection_unrelated")
FACT_SHARE = 50  # more than any of those families has items in one split


@functools.cache
def _fact_entries() -> tuple[Entry, ...]:
    """Every English statement entry naming no currency, one per distinct fact, in a fixed
    shuffled order."""
    out: list[Entry] = []
    seen: set[str] = set()
    for t in STATEMENTS:
        if t.lang != "en" or _CURRENCY.search(t.vp + " " + t.that):
            continue
        for e in expand(t):
            key = e.that() if t.that else e.vp()
            if key not in seen:
                seen.add(key)
                out.append(e)
    random.Random(f"{GENERATOR}|facts").shuffle(out)  # noqa: S311 - a fixed table
    return tuple(out)


def random_fact(
    rng: random.Random, slot: Slot, st: Setup, loc_date: date, lines: list[Line]
) -> str:
    """An English fact for records that must not bear on it (rule 21): drawn from another
    situation than the chat's, whose filler is on screen, and sharing no content word, name or
    weekday with any line shown or any saved name. It names no currency, since no record on
    screen shows one (rule 15). Each item draws only from its own share of the facts."""
    if slot.k >= FACT_SHARE:
        raise ValueError(f"{slot.family} has more than {FACT_SHARE} items in a split")
    shown = " ".join(text for _, text in lines)
    shown += " " + " ".join(a.label or "" for a in st.chat.contacts)
    taken = _topic_stems(shown)
    start = FACT_FAMILIES.index(slot.family) * FACT_SHARE + slot.k
    share = list(_fact_entries()[start :: len(FACT_FAMILIES) * FACT_SHARE])
    rng.shuffle(share)
    for e in share:
        if e.tpl.sit == st.chat.sit:
            continue
        fact = fact_form(rng, e, st, loc_date)
        if not _topic_stems(fact.replace(st.s, " ")) & taken:
            return fact
    raise RuntimeError(f"no unrelated fact in its share for the lines {shown!r}")
