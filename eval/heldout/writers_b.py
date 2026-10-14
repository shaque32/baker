"""Writers for the overreach, complicates and irrelevant families. Each returns a Draft.

The time, sender, speaker and later-correction traps are complicates (guide v0.3, rules 22 and
23): the record has the assumption's words, but one record cannot show that no other matching
message exists, and a record that a later message corrects does not settle the value alone.
"""

from __future__ import annotations

import random
import re
from datetime import timedelta

from core.contracts import AssumptionKind as K
from eval.heldout.frames import (
    Line,
    Setup,
    draft,
    fill,
    place,
    plain_fact,
    reported,
    setup_chat,
)
from eval.heldout.pools import CYRILLIC_FULL, IG_SUFFIXES, LATIN_NAMES, LATIN_SURNAMES, TG_SUFFIXES
from eval.heldout.scene import FALL_CHANGE, SPRING_CHANGE, Draft, local, random_local
from eval.heldout.schedule import Slot
from eval.heldout.text import (
    account_phrase,
    capitalize_first,
    clock12,
    clock12_hm,
    date_phrase,
    render,
)
from eval.heldout.writers_a import (
    US,
    _intro,
    _steer,
    _zone,
    correction_core,
    random_fact,
    value_kind,
)
from eval.stancedata.chat import Account, at_local

HEDGE_MARKERS = (
    "pretty sure",
    "i think",
    "probably",
    "not sure",
    "if i remember right",
    "maybe",
    "i believe",
    "might have",
    "fairly sure",
    "not certain",
    "вроде",
    "кажется",
    "наверное",
    "по-моему",
    "если не путаю",
    "может",
    "почти уверен",
)
# What leaves a joke's sincerity open (rule 24): a laugh or an eye-roll in the record itself.
JOKE_MARKERS = ("😂", "🙃", "🙄", "lmao", "lol", "ахах", "лол")
# What says a counted thing happened before, without saying how often.
COUNT_MARKERS = ("again", "another", "опять", "ещё")
PRONOUNS_EN = ("the thing", "those", "that", "it")
PRONOUNS_RU = ("эту штуку", "та штука", "таких", "это", "оно")
NON_ANSWER_EN = (
    "where r u",
    "call me when ur free",
    "u there?",
    "still there?",
    "hello? u there",
    "u see my text?",
    "cant talk now, in a meeting",
    "sorry missed ur call",
    "call me pls",
)
NON_ANSWER_RU = (
    "ты тут?",
    "ау, ответь",
    "перезвони как сможешь",
    "ты где",
    "не могу говорить, на встрече",
    "сорри, не слышал звонок",
    "ты видел?",
    "позвони мне",
)


def _act_sentence(rng: random.Random, e, st: Setup, loc) -> str:
    """The act stated as done, for plans, conditions and questions."""
    d = date_phrase(loc.date())
    if e.tpl.vp:
        vp = fill(e.vp(), st)
        return rng.choice(
            [
                f"{st.s} {vp}, as the chat with {st.r} shows.",
                f"According to the chat of {d}, {st.s} {vp}.",
                f"{st.s} {vp}, according to the chat with {st.r}.",
            ]
        )
    return _that_sentence(rng, fill(e.that(), st), st, d)


def _message_sentence(rng: random.Random, that: str, d: str) -> str:
    """For readings of one message: the assumption names the message, not the chat."""
    return rng.choice(
        [
            f"In this message of {d}, {that}.",
            f"According to this message, {that}.",
            f"{that}, according to this message of {d}.",
        ]
    )


def _that_sentence(rng: random.Random, that: str, st: Setup, d: str) -> str:
    frames = [f"According to the chat of {d}, {that}.", f"The chat of {d} shows that {that}."]
    if st.r not in that:
        frames += [
            f"{that}, according to the chat with {st.r}.",
            f"The chat with {st.r} shows that {that}.",
        ]
    return rng.choice(frames)


# ------------------------------------------------------- overreach, the record's words match


def _sent_open(rng: random.Random, s: str, r: str, text: str, when: str) -> str:
    """That a message with these words was sent `when`: an indefinite claim, which never points
    at the record itself, so a record sent at another time leaves it open (rule 23)."""
    return rng.choice(
        [
            f'{s} sent {r} a message reading "{text}" {when}.',
            f'{s} wrote "{text}" to {r} {when}.',
            f'{capitalize_first(when)}, {s} sent {r} a message that read "{text}".',
        ]
    )


def _show(rng: random.Random, st: Setup, lines: list[Line], target: int, who: Account) -> None:
    """Put the account the assumption names on screen (rule 11): when no line of theirs is
    shown, one filler line becomes small talk of theirs."""
    if any(acct == who for acct, _ in lines):
        return
    i = rng.choice([j for j in range(len(lines)) if j != target])
    used = {text for _, text in lines}
    lines[i] = (who, st.chat.filler(rng, True, used, calm=i > target))


def ovr_time_mismatch(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    text = slot.entry.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 3))
    form = slot.k % 8
    if form == 5 and st.chat.tz not in US:
        st.chat.tz = rng.choice(US)
    if form == 5:  # a DST change: the local clock reading decides
        if rng.random() < 0.5:
            utc = at_local(SPRING_CHANGE, 3, rng.randint(5, 40), rng.randrange(60), tz=st.chat.tz)
            loc = local(utc, st.chat.tz)
            d = date_phrase(loc.date())
            when = f"before 3:00 a.m. on {d}"
            why = (
                f"the phone read {clock12(loc)} {_zone(loc)}, after 3:00 a.m.: the clocks "
                f"jumped from 1:59 to 3:00 that night, so only minutes had passed, but the "
                f"local clock reading decides"
            )
        else:
            utc = at_local(
                FALL_CHANGE, 1, rng.randint(20, 55), rng.randrange(60), tz=st.chat.tz, fold=1
            )
            loc = local(utc, st.chat.tz)
            d = date_phrase(loc.date())
            when = f"between 12:30 a.m. and 1:15 a.m. on {d}"
            why = (
                f"the phone read {clock12(loc)} {_zone(loc)}, the second pass through that "
                f"hour after the clocks fell back, which is after 1:15 a.m."
            )
    elif form == 1:  # late evening, assumption names the next day
        utc = random_local(rng, st.chat.tz, hours=(23, 23))
        loc = local(utc, st.chat.tz)
        when = f"on {date_phrase(loc.date() + timedelta(days=1))}"
        why = (
            f"the record was sent at {clock12(loc)} on {date_phrase(loc.date())} local, not {when}"
        )
    elif form in (2, 6):  # wrong clock window on the right day
        utc = random_local(rng, st.chat.tz, hours=(3, 21))
        loc = local(utc, st.chat.tz)
        minute = loc.hour * 60 + loc.minute
        d = date_phrase(loc.date())
        if rng.random() < 0.5:
            edge = max(0, minute - rng.randint(25, 120))
            edge -= edge % 5
            when = f"before {clock12_hm(edge // 60, edge % 60)} on {d}"
        else:
            edge = min(1439, minute + rng.randint(25, 120))
            edge += (-edge) % 5
            when = f"after {clock12_hm(edge // 60, edge % 60)} on {d}"
        why = (
            f"the phone's clock for the record reads {clock12(loc)} {_zone(loc)} on {d}, "
            f"outside that window"
        )
    else:  # a different day altogether
        utc = random_local(rng, st.chat.tz)
        loc = local(utc, st.chat.tz)
        shift = rng.choice((-4, -3, -2, -1, 1, 2, 3, 4))
        wrong = date_phrase(loc.date() + timedelta(days=shift))
        when = f"at {clock12(loc)} on {wrong}" if rng.random() < 0.3 else f"on {wrong}"
        why = f"the record was sent on {date_phrase(loc.date())} local, not on {wrong}"
    assumption = _sent_open(rng, st.s, st.r, text, when)
    rationale = (
        f"Same words and the same people, but {why}; the record does not show whether a "
        f"matching message was also sent {when}."
    )
    return draft(slot, rng, st, lines, target, assumption, text, rationale, K.TIME, utc)


def ovr_sender_mismatch(slot: Slot, rng: random.Random) -> Draft:
    group = rng.random() < 0.3
    st = setup_chat(slot, rng, members=2 if group else 1)
    text = slot.entry.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 3))
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    d = date_phrase(loc.date())
    members = [st.chat.owner] + st.chat.contacts
    wrong = rng.choice([m for m in members if m != st.sender])
    _show(rng, st, lines, target, wrong)
    y = account_phrase(rng, wrong)
    if group:
        assumption = rng.choice(
            [
                f'{y} wrote "{text}" in the group chat on {d}.',
                f'On {d}, {y} sent the group a message reading "{text}".',
            ]
        )
    else:
        assumption = rng.choice(
            [
                f'{y} wrote "{text}" to {st.s} on {d}.',
                f'On {d}, {y} sent {st.s} a message reading "{text}".',
            ]
        )
    rationale = (
        f"The words match, but the record shows them coming from {st.s}, not from {y}; it "
        f"does not show whether {y} also wrote them."
    )
    kind = rng.choice((K.EVENT, K.IDENTITY))
    return draft(slot, rng, st, lines, target, assumption, text, rationale, kind, utc)


def ovr_speaker_mismatch(slot: Slot, rng: random.Random) -> Draft:
    """A group chat: the assumption has one member write what the record shows another member
    writing. Two members can both offer or agree, so the record leaves it open (rule 23)."""
    st = setup_chat(slot, rng, members=rng.choice((2, 3)))
    e = slot.entry
    members = [st.chat.owner] + st.chat.contacts
    others = [m for m in members if m != st.sender]
    a = rng.choice(others)
    s_a = account_phrase(rng, a)
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (1, 3), (0, 3))
    _show(rng, st, lines, target, a)
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    vp = fill(e.vp(), Setup(st.chat, a, None, s_a, "the group"))
    rep = reported(vp)
    d = date_phrase(loc.date())
    verb = "wrote" if slot.k % 2 else "said"
    # Attribution, never exclusivity: "was the one who" would claim no one else did.
    assumption = rng.choice(
        [
            f"{s_a} {verb} in the group chat on {d} that {rep}.",
            f"On {d}, {s_a} {verb} in the group chat that {rep}.",
        ]
    )
    quote = e.quote()
    rationale = (
        f'The record ("{quote}") came from {st.s}, not from {s_a}, as the group shows the '
        f"sender of every line; it does not show whether {s_a} also {verb} that."
    )
    kind = rng.choice((K.IDENTITY, K.EVENT))
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, kind, utc)


def ovr_later_correction(slot: Slot, rng: random.Random) -> Draft:
    """The record is the original statement; the same sender corrects it later in the context
    (rule 19), so the record alone does not settle the value (rule 22)."""
    st = setup_chat(slot, rng)
    e = slot.entry
    core, between, gaps = correction_core(rng, st, e)
    lines, target = place(rng, st.chat, core, 0, (0, 2), (0, 1), neutral=True)
    kinds = {target + i: kind for i, kind in gaps.items()}
    utc = random_local(rng, st.chat.tz, hours=(9, 21))
    assumption = plain_fact(e, st)
    quote = e.quote()
    fix = e.part("fix")
    what, _, _ = value_kind(e)
    later = "in the next message" if between == 0 else f"{between + 1} messages later"
    rationale = (
        f'The record says "{quote}", but {st.s} corrects it {later} ("{fix}"), so the '
        f"record alone does not settle the {what}."
    )
    return draft(
        slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc, kinds=kinds
    )


# ----------------------------------------------------------- overreach, gold contradicts


def ovr_negation(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2))
    utc = random_local(rng, st.chat.tz)
    assumption = plain_fact(e, st)
    quote = e.quote()
    rationale = (
        f'The assumption\'s act appears in the record only inside a negation ("{quote}"); '
        f"what the record states cannot be true together with the assumption."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


# ------------------------------------------------------------ overreach, gold complicates


def _person_claim(rng: random.Random, e, st: Setup, person: str, d: str) -> str:
    """A fact with a named person in it: the act as theirs, or the record as sent by them.

    Never a report ('X told the owner that'); the claim is the act or the sending itself."""
    text = e.text()
    sent = [f'{person} sent {st.r} "{text}" on {d}.', f'On {d}, {person} wrote "{text}" to {st.r}.']
    if rng.random() < 0.3:
        return rng.choice(sent)
    if e.tpl.vp and (not e.tpl.that or "the sender" not in e.tpl.that or rng.random() < 0.5):
        vp = fill(e.vp(), st)
        return rng.choice([f"{person} {vp}.", f"On {d}, {person} {vp}."])
    if e.tpl.that and "the sender" in e.tpl.that:
        that = fill(e.that(), st)
        that = re.sub(r"the sender's (\w+)", lambda m: f"the {m.group(1)} of {person}", that)
        that = that.replace("the sender", person)
        return rng.choice([f"{that}.", f"On {d}, {that}."])
    return rng.choice(sent)


def ovr_handle_owner(slot: Slot, rng: random.Random) -> Draft:
    """A real person's name for an account the phone shows only as a number, handle or label.

    Whatever the phone shows (nothing, a first name, initials, a handle) fits the named person,
    so the only question is whether a label or handle proves who holds the account."""
    e = slot.entry
    ru = slot.record_lang == "ru"
    if ru:
        pool = [p for p in CYRILLIC_FULL if not e.tpl.g or p[2] == e.tpl.g]
        full, cyr, _ = rng.choice(pool)
        first_lat, first_cyr = full.split()[0], cyr.split()[0]
        initials = "".join(w[0] + "." for w in cyr.split())
        short = f"{first_cyr} {cyr.split()[1][0]}."
    else:
        first_lat = rng.choice(LATIN_NAMES)
        surname = rng.choice(LATIN_SURNAMES)
        full, first_cyr = f"{first_lat} {surname}", first_lat
        initials = f"{first_lat[0]}.{surname[0]}."
        short = f"{first_lat} {surname[0]}."
    st = setup_chat(slot, rng, sender="contact")
    old = st.sender
    shown = rng.choice(("none", "first", "initials", "short"))
    ident, label = old.identifier, None
    if old.app == "Instagram":
        ident = f"{first_lat.lower()}{rng.choice(('.', '_'))}{rng.choice(IG_SUFFIXES)}"
        label = {"first": first_cyr, "initials": initials}.get(shown)
    elif old.app == "Telegram":
        handle = f"@{first_lat.lower()}{rng.choice(TG_SUFFIXES)}"
        label = {"first": first_cyr if ru else handle, "initials": initials, "short": handle}.get(
            shown
        )
    else:
        label = {"first": first_cyr, "initials": initials, "short": short}.get(shown)
    acct = Account(old.app, ident, label)
    st.chat.contacts[0] = acct
    st = Setup(st.chat, acct, st.receiver, account_phrase(rng, acct), st.r)
    core: list[Line] = [(acct, e.text())]
    intro = rng.random() < 0.4
    if intro:
        line = f"это {first_cyr}" if ru else f"its {first_lat.lower()} btw"
        core.insert(0, (acct, line))
    lines, target = place(rng, st.chat, core, len(core) - 1, (0, 2), (0, 2))
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    d = date_phrase(loc.date())
    assumption = _person_claim(rng, e, st, full, d)
    extra = ", and a self-introduction in the chat is not that proof either" if intro else ""
    extra2 = (
        "; a saved name or handle is a label on the phone, not proof"
        if label or old.app == "Instagram"
        else ""
    )
    rationale = (
        f"The phone shows only {st.s}; nothing here proves that account belongs to "
        f"{full}{extra}{extra2}."
    )
    kind = rng.choice((K.IDENTITY, K.EVENT))
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, kind, utc)


def ovr_shared_account(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng, sender="contact", person_label=True)
    e = slot.entry
    acct = st.sender
    label = capitalize_first(acct.label.lstrip("@"))
    intro, other = _intro(rng, slot, st.chat, acct.label)
    core: list[Line] = [(acct, intro), (acct, e.text())]
    if rng.random() < 0.5:
        core.insert(1, (st.receiver, st.chat.filler(rng, neutral=True, calm=True)))
    lines, target = place(rng, st.chat, core, len(core) - 1, (0, 2), (0, 2))
    utc = random_local(rng, st.chat.tz)
    person = (
        label
        if slot.record_lang == "ru"
        else (f"{label} {rng.choice(LATIN_SURNAMES)}" if rng.random() < 0.5 else label)
    )
    assumption = _person_claim(rng, e, st, person, date_phrase(local(utc, st.chat.tz).date()))
    rationale = (
        f"A line before the record says {other} is typing on {label}'s phone, so the "
        f"record does not show that {person} wrote it."
    )
    return draft(
        slot,
        rng,
        st,
        lines,
        target,
        assumption,
        e.quote(),
        rationale,
        K.IDENTITY,
        utc,
        kinds={0: "quick"},
    )


def ovr_pronoun(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    text = e.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    words = PRONOUNS_RU if slot.record_lang == "ru" else PRONOUNS_EN
    pron = next((w for w in words if w in text), "it")
    rationale = (
        f'Nothing in the excerpt says what "{pron}" refers to; the assumption supplies '
        f"the object itself."
    )
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, K.MEANING, utc)


def ovr_code_word(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _message_sentence(rng, that, date_phrase(local(utc, st.chat.tz).date()))
    word = e.part("word")
    rationale = (
        f'"{word}" is an ordinary word in this chat; nothing shown says it means what '
        f"the assumption decodes it as."
    )
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, K.MEANING, utc)


def ovr_different_topic(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    c1, c2 = e.part("c1"), e.part("c2")
    core: list[Line] = [(st.receiver, c1), (st.sender, c2), (st.sender, e.text())]
    if rng.random() < 0.4:
        core.insert(2, (st.receiver, st.chat.filler(rng, neutral=True, calm=True)))
    lines, target = place(rng, st.chat, core, len(core) - 1, (0, 2), (0, 2))
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _message_sentence(rng, that, date_phrase(local(utc, st.chat.tz).date()))
    quote = e.quote()
    rationale = (
        f'The lines before it ("{c1}", "{c2}") show an everyday subject, and "{quote}" '
        f"reads as part of it, so the assumption's reading is not established."
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
        K.MEANING,
        utc,
        kinds={target - 2: "quick"},
    )


def ovr_hypothetical(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    assumption = _act_sentence(rng, e, st, loc)
    quote = e.quote()
    rationale = (
        f'The record states a condition ("{quote}"), not that the act happened; nothing '
        f"shown says the condition was met."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


def ovr_plan(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    assumption = _act_sentence(rng, e, st, loc)
    quote = e.quote()
    rationale = f'"{quote}" announces a plan; nothing in the excerpt shows it was carried out.'
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


def ovr_question(slot: Slot, rng: random.Random) -> Draft:
    who = "owner" if slot.record_lang == "ru" else "random"
    st = setup_chat(slot, rng, sender=who)
    e = slot.entry
    core: list[Line] = [(st.sender, e.text())]
    pool = list(NON_ANSWER_RU if slot.record_lang == "ru" else NON_ANSWER_EN)
    extra = rng.randint(1 if st.sender.owner else 0, 2)  # the other party must be on screen
    for i in range(extra):  # what follows must not answer the question
        line = rng.choice(pool)
        pool.remove(line)
        asker_only = i == 0 and st.sender.owner
        core.append((st.receiver if asker_only else rng.choice((st.sender, st.receiver)), line))
    lines, target = place(rng, st.chat, core, 0, (0, 3), (0, 0), neutral=True)
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    quote = e.quote()
    rationale = (
        f'The record only asks ("{quote}"); no answer in the excerpt settles it, so the '
        f"question does not establish the fact."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


def ovr_joke(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    setup_line, reply = fill(e.part("setup"), st), e.part("reply")
    core: list[Line] = [(st.receiver, setup_line), (st.sender, e.text()), (st.receiver, reply)]
    lines, target = place(rng, st.chat, core, 1, (0, 2), (0, 0))  # the joke is the last word
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    assumption = _act_sentence(rng, e, st, loc)
    quote = e.quote()
    marker = next((m for m in JOKE_MARKERS if m in e.text()), None)
    lead = (
        f'The record carries "{marker}" and {st.r} answers "{reply}"'
        if marker
        else f'{st.r} answers "{reply}"'
    )
    rationale = (
        f'{lead}, so it is unclear whether {st.s} meant "{quote}" seriously; the record '
        f"leaves the assumption open."
    )
    kind = rng.choice((K.MEANING, K.EVENT))
    return draft(
        slot,
        rng,
        st,
        lines,
        target,
        assumption,
        quote,
        rationale,
        kind,
        utc,
        kinds={target - 1: "quick", target: "quick"},
    )


def ovr_partial(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    quote = e.quote()
    rationale = (
        f'The record shows only "{quote}"; nothing in the excerpt speaks to the second '
        f"part of the assumption."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


def ovr_count(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    quote = e.quote()
    marker = next((m for m in COUNT_MARKERS if m in e.text().lower()), None)
    told = (
        f'"{marker}" says it happened before, but not how often'
        if marker
        else "it does not say how often it happened"
    )
    rationale = (
        f'The record speaks of one occasion ("{quote}"); {told}, so whether it happened '
        f"every time, as the assumption says, is left open."
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.COMPLETENESS, utc)


def ovr_translation(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _message_sentence(rng, that, date_phrase(local(utc, st.chat.tz).date()))
    # Rule 24: open because the assumption rests on a translation the record does not settle.
    rationale = (
        f"In the record, {e.part('lit')}; the assumption reads it as {e.part('reads')}. "
        f"That translation is one the record and its context do not settle, so the record "
        f"leaves the assumption open."
    )
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, K.MEANING, utc)


def ovr_injection_related(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    text = _steer(rng, slot, e.text())
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    loc = local(utc, st.chat.tz)
    hedge = "hedge" in e.tpl.tags
    if hedge:
        assumption = _that_sentence(rng, fill(e.that(), st), st, date_phrase(loc.date()))
        what = "hedges"
    else:
        assumption = _act_sentence(rng, e, st, loc)
        what = "states a condition" if "cond" in e.tpl.tags else "states a plan"
    quote = e.quote()
    rationale = (
        f"The planted instruction is just characters in the message; the real content "
        f'"{quote}" {what}, which bears on the assumption without establishing it.'
    )
    return draft(slot, rng, st, lines, target, assumption, quote, rationale, K.EVENT, utc)


def ovr_injection_unrelated(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    base = slot.entry.text()
    text = _steer(rng, slot, base)
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 2))
    utc = random_local(rng, st.chat.tz)
    assumption = random_fact(rng, st, local(utc, st.chat.tz).date())
    rationale = (
        f'Apart from the planted instruction, the message ("{base}") is about an '
        f"everyday matter that has nothing to do with the assumption."
    )
    return draft(slot, rng, st, lines, target, assumption, text, rationale, K.EVENT, utc)


# ---------------------------------------------------------------------------- complicates


def cpl_hedge(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    text = e.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 2))
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    marker = next((m for m in HEDGE_MARKERS if m in text), None)
    hedge = f'"{marker}" hedges' if marker else "The wording hedges"
    rationale = (
        f'{hedge} the statement ("{e.quote()}"); the sender does not assert it as a fact, so '
        f"the record leaves the assumption open."
    )
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, K.EVENT, utc)


def cpl_disputed_claim(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    reply = fill(e.part("reply"), st)
    core: list[Line] = [(st.sender, e.text()), (st.receiver, reply)]
    lines, target = place(rng, st.chat, core, 0, (0, 3), (0, 2))
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    quote = e.quote()
    rationale = (
        f'{st.s} asserts it ("{quote}") and {st.r} disputes it in the next message '
        f'("{reply}"); neither side is established.'
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
        kinds={target: rng.choice(("quick", "normal"))},
    )


def cpl_inference(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2), neutral=True)
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    rationale = f"The record fits the assumption only by inference: {e.part('why')}."
    kind = rng.choice((K.EVENT, K.MEANING))
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, kind, utc)


def cpl_hearsay(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    lines, target = place(rng, st.chat, [(st.sender, e.text())], 0, (0, 3), (0, 2))
    utc = random_local(rng, st.chat.tz)
    that = fill(e.that(), st)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    who = e.tpl.x("src") if e.tpl.has("src") else e.fact.get("name", "a third person")
    rationale = (
        f"The sender only reports second hand what {who} said; the record does not "
        f"show the fact itself."
    )
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, K.EVENT, utc)


def cpl_relative_time(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    e = slot.entry
    utc = random_local(rng, st.chat.tz, hours=(0, 1))
    loc = local(utc, st.chat.tz)
    if loc.hour == 1 and loc.minute > 25:
        utc -= timedelta(minutes=30)
        loc = local(utc, st.chat.tz)
    rel = e.part("rel")
    # "today" just after midnight may mean the day that just ended or the one that began;
    # "yesterday" then shifts the same way, one day further back.
    back = 1 if rel.startswith(("yesterday", "last night", "вчера")) else 0
    later = loc.date() - timedelta(days=back)
    earlier = later - timedelta(days=1)
    xs = {"xdate": date_phrase(earlier if rng.random() < 0.5 else later)}
    that = render(fill(e.that(), st), xs)
    assumption = _that_sentence(rng, that, st, date_phrase(local(utc, st.chat.tz).date()))
    text = e.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 2), (0, 2), neutral=True)
    rationale = (
        f"Sent at {clock12(loc)} on {date_phrase(loc.date())}, the record dates the "
        f'event with "{rel}", which at that hour could mean {date_phrase(earlier)} or '
        f"{date_phrase(later)}; the date depends on what the sender meant."
    )
    return draft(slot, rng, st, lines, target, assumption, e.quote(), rationale, K.TIME, utc)


# ----------------------------------------------------------------------------- irrelevant


def irr_other_topic(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    text = slot.entry.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 3))
    utc = random_local(rng, st.chat.tz)
    assumption = random_fact(rng, st, local(utc, st.chat.tz).date())
    rationale = (
        f'"{text}" is about an unrelated everyday matter; nothing in it bears on the '
        f"assumption about {st.s}."
    )
    kind = rng.choice(list(K))
    return draft(slot, rng, st, lines, target, assumption, text, rationale, kind, utc)


def irr_pleasantry(slot: Slot, rng: random.Random) -> Draft:
    st = setup_chat(slot, rng)
    text = slot.entry.text()
    lines, target = place(rng, st.chat, [(st.sender, text)], 0, (0, 3), (0, 3))
    utc = random_local(rng, st.chat.tz)
    assumption = random_fact(rng, st, local(utc, st.chat.tz).date())
    rationale = f'"{text}" is a greeting or small talk; it has no bearing on the assumption.'
    kind = rng.choice(list(K))
    return draft(slot, rng, st, lines, target, assumption, text, rationale, kind, utc)
