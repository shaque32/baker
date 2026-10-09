"""Writers for the clear-support and contradicts families. Each returns a Draft."""

from __future__ import annotations

import random
import re
from datetime import date, timedelta

from core.contracts import AssumptionKind as K
from eval.heldout.data_support import STATEMENTS
from eval.heldout.frames import (
    Line,
    Setup,
    bare_fact,
    draft,
    fact_form,
    fact_sentence,
    fill,
    place,
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
from eval.heldout.registry import expand
from eval.heldout.scene import FALL_CHANGE, SPRING_CHANGE, Draft, local, random_local
from eval.heldout.schedule import Slot
from eval.heldout.text import account_phrase, clock12, clock12_hm, date_phrase, render
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
    utc = random_local(rng, st.chat.tz)
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


def sup_plain(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    core: list[Line] = [(st.sender, e.text())]
    lines, target = place(rng, st.chat, core, 0, (0, 3), (0, 3))
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    assumption, centric = fact_sentence(rng, e, st, loc)
    kind = K.MEANING if centric else K.EVENT
    quote = e.quote()
    if slot.record_lang == "ru":
        rationale = (
            f'In plain Russian, "{quote}" states that {bare_fact(rng, e, st)}; no slang '
            f"or outside fact is needed, and nothing later in the chat changes it."
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
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    assumption, _ = fact_sentence(rng, e, st, loc, prefer="that" if e.tpl.that else "vp")
    quote = e.quote()
    rationale = (
        f'The record answers the question just before it ("{q}") from {st.r}; read '
        f"together they say that {bare_fact(rng, e, st)}."
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
    dst = slot.k % 7 == 3
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
                rng.randint(5, 55),
                rng.randrange(60),
                tz=st.chat.tz,
                fold=rng.randrange(2),
            )
            c1, c2 = "1:00 a.m.", "2:00 a.m."
        loc = local(utc, st.chat.tz)
    else:
        utc = random_local(rng, st.chat.tz, hours=(2, 21))
        loc = local(utc, st.chat.tz)
        lo, hi = _window(rng, loc.hour * 60 + loc.minute)
        c1, c2 = clock12_hm(lo // 60, lo % 60), clock12_hm(hi // 60, hi % 60)
    d = date_phrase(loc.date())
    form = rng.randrange(3) if not dst else 0
    if form == 0:
        assumption = f"{st.s} messaged {st.r} between {c1} and {c2} on {d}."
    elif form == 1:
        assumption = f"Before {c2} on {d}, {st.s} sent {st.r} a message."
    else:
        assumption = f"After {c1} on {d}, {st.s} sent a message to {st.r}."
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
    reply = st.chat.filler(rng, neutral=True)
    core: list[Line] = [(st.sender, text), (st.receiver, reply)]
    lines, target = place(rng, st.chat, core, 0, (0, 3), (0, 2))
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    d = loc.date()
    x = account_phrase(rng, st.chat.contact)
    form = rng.randrange(3)
    if form == 0:
        assumption = f"{st.s} and {st.r} exchanged messages on {date_phrase(d)}."
        kind = K.COMPLETENESS
        where = f"on {date_phrase(d)}"
    elif form == 1:
        d1 = d - timedelta(days=rng.randint(0, 4))
        d2 = d + timedelta(days=rng.randint(1, 4) if d1 == d else rng.randint(0, 4))
        assumption = (
            f"The owner and {x} exchanged messages between {date_phrase(d1)} and {date_phrase(d2)}."
        )
        kind = K.TIME
        where = f"on {date_phrase(d)}, within that range"
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
        core.insert(1, (st.receiver, st.chat.filler(rng, neutral=True)))
    target_core = len(core) - 1
    lines, target = place(rng, st.chat, core, target_core, (0, 2), (0, 2))
    utc = random_local(rng, st.chat.tz)
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
    utc = random_local(rng, st.chat.tz)
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
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    vp = fill(e.vp(), st)
    d = date_phrase(loc.date())
    assumption = rng.choice(
        [
            f"{st.s} {vp}, as the chat with {st.r} shows.",
            f"The chat of {d} with {st.r} shows that {st.s} {vp}.",
            f"According to the chat of {d}, {st.s} {vp}.",
        ]
    )
    quote = e.quote()
    rationale = (
        f'Asked "{ask}", {st.s} denies it outright: "{quote}". A plain denial by the '
        f"sender cannot be true at the same time as the assumption."
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


def con_other_value(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 3))
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    assumption = fact_form(rng, e, st, loc)
    quote = e.quote()
    rec = e.rec
    if "m" in rec:
        zeros = re.search(r"\{n\}(\d*)", e.tpl.text)  # "{n}00" and "{n}40" alike
        suffix = zeros.group(1) if zeros else ""
        got, claimed = f"{rec['n']}{suffix}", f"{rec['m']}{suffix}"
    elif "place2" in rec:
        got, claimed = rec["place"], rec["place2"]
    else:
        got, claimed = e.fact["day"], e.fact["day2"]
    kind = K.COMPLETENESS if "m" in rec and rng.random() < 0.5 else K.EVENT
    rationale = (
        f'The record fixes the value ("{quote}"): {got}, stated so that {claimed} '
        f"cannot also be true."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, kind, utc)


def con_other_state(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    utc = random_local(rng, st.chat.tz, hours=(9, 21))
    loc = local(utc, st.chat.tz)
    back = rng.randint(2, 3)
    wd = (loc.date() - timedelta(days=back)).weekday()
    since = SINCE_RU[wd] if slot.record_lang == "ru" else SINCE_EN[wd]
    xs = {"xwd2": since, "xdate": date_phrase(loc.date())}
    text = render(e.text(), xs)
    quote = render(e.quote(), xs)
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 2))
    fact = render(bare_fact(rng, e, st), xs).replace("the sender", st.s)
    assumption = rng.choice([f"{fact}.", f"According to the chat, {fact}."])
    rationale = (
        f'Sent on {date_phrase(loc.date())}, the record says "{quote}", a state that '
        f"cannot hold if {fact}."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


def con_in_window(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    text = slot.entry.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 3))
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    d = loc.date()
    x = account_phrase(rng, st.chat.contact)
    form = rng.randrange(5)
    if form in (0, 1):
        d1 = d - timedelta(days=rng.randint(0, 6))
        d2 = d + timedelta(days=rng.randint(1, 6) if d1 == d else rng.randint(0, 6))
        span = f"{date_phrase(d1)} to {date_phrase(d2)}"
        assumption = (
            f"There was no contact between the owner and {x} from {span}."
            if form == 0
            else f"The owner and {x} did not message each other from {span}."
        )
        kind, why = K.COMPLETENESS, f"inside the {span} window"
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


def con_other_speaker(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng, members=rng.choice((2, 3)))
    e = slot.entry
    members = [st.chat.owner] + st.chat.contacts
    others = [m for m in members if m != st.sender]
    a = rng.choice(others)
    s_a = account_phrase(rng, a)
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (1, 3), (0, 3))
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    vp = fill(e.vp(), Setup(st.chat, a, None, s_a, "the group"))
    d = date_phrase(loc.date())
    assumption = rng.choice(
        [
            f"In the group chat, {s_a} was the one who {vp}.",
            f"{s_a} {vp} in the group chat on {d}.",
            f"The group member who {vp} was {s_a}.",
        ]
    )
    quote = e.quote()
    rationale = (
        f'The message that does this ("{quote}") came from {st.s}, not from {s_a}; '
        f"the group shows the sender on every line."
    )
    kind = rng.choice((K.IDENTITY, K.EVENT))
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, kind, utc)


# ------------------------------------------------------------------------- shared with b


def random_fact(rng: random.Random, st: Setup, loc_date: date) -> str:
    """An English fact about this chat's situation, for records that must not bear on it."""
    pool = [t for t in STATEMENTS if t.lang == "en" and t.sit == st.chat.sit]
    t = rng.choice(pool)
    e = rng.choice(expand(t))
    return fact_form(rng, e, st, loc_date)
