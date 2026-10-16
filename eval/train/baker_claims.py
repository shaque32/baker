"""Role, event, message and call claims as a government document states them (guide rule 29),
and the chat around a record they rest on.

A claim is one or two formal, third-person, past-tense sentences. People appear as {{person id}}
(the full name) on first mention and {{person id|last}} (the surname) after it;
baker_cast.fill_claim writes in the names the item's cast gives them. A claim's time is its
window's own words, so the claim and the assumption's window always agree. Each builder picks
among several frames, so the wording varies; none uses a word the tool never says. Meaning
claims are in baker_claim_meaning.py.
"""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta

from eval.stancedata import bakerform as bf
from eval.train.baker_cues import SURNAMES
from eval.train.baker_kit import Setup, chatter
from eval.train.baker_scene import Acc, Ev, thread

STREETS = ("Dekalb Avenue", "Halsey Street", "Bergen Street", "Meserole Avenue", "Grand Street",
           "Dean Street", "Lorimer Street", "Kent Avenue", "Hart Street", "Atlantic Avenue",
           "Classon Avenue", "Bedford Avenue", "Flushing Avenue", "Graham Avenue", "Hicks Street",
           "Henry Street", "Clinton Street", "Court Street", "Montague Street", "Lafayette Avenue",
           "Gates Avenue", "Fulton Street", "Franklin Avenue", "Johnson Avenue", "Ainslie Street",
           "Driggs Avenue", "Leonard Street", "Manhattan Avenue", "Morgan Avenue", "Ellery Street",
           "Bushwick Avenue", "Irving Avenue", "Knickerbocker Avenue")  # fmt: skip
# (how a chat names a code, how a claim names it)
CODES = (("lockbox code", "lockbox code"), ("alarm code", "alarm code"),
         ("door code for the side entrance", "door code for the side entrance"),
         ("code to the storage unit", "code to the storage unit"),
         ("locker combo", "locker combination"), ("garage code", "garage code"),
         ("keypad code for the office", "keypad code for the office"))  # fmt: skip
CODE_TEXTS = ("{k} is {c}", "{k}: {c}", "the {k} is {c}", "{k} {c}")
# Plain acknowledgements: lines after a statement that neither hedge nor correct it.
CALM = {
    "en": ("ok", "k", "ok thx", "got it", "sounds good", "np", "👍", "yep", "cool", "will do",
           "kk", "perfect", "ty", "no worries", "ok cool", "alright", "copy that", "ok noted",
           "makes sense", "ty ty", "ok good", "all good"),
    "ru": ("ок", "понял", "поняла", "спасибо", "ага", "хорошо", "ладно", "норм", "окей", "принято",
           "ясно", "спс", "договорились", "ну ок", "👍"),
}  # fmt: skip


def full(pid: str) -> str:
    return "{{" + pid + "}}"


def last(pid: str) -> str:
    return "{{" + pid + "|last}}"


def upfirst(s: str) -> str:
    return s[:1].upper() + s[1:]


def timed(rng: random.Random, frames: tuple[str, ...] | list[str], raw: str) -> str:
    """A frame that writes the window's own words exactly as they are: at the sentence's start
    ({T}) when they begin with a capital ("On May 2, 2026"), inside it ({t}) otherwise."""
    return rng.choice([f for f in frames if f.startswith("{T}") == raw[:1].isupper()])


SELF = {"en": ("ok", "k", "👍", "kk"), "ru": ("ок", "ага", "👍")}  # the record's own sender


def calm(rng: random.Random, lang: str, n: int) -> list[str]:
    return [rng.choice(CALM[lang]) for _ in range(n)]


def settle(rng: random.Random, evs: list[Ev], target: int, lang: str) -> None:
    """After the record its own sender only says "ok" or the like, never a second thought."""
    frm, last = evs[target].frm, ""
    for i in range(target + 1, len(evs)):
        e = evs[i]
        if e.frm == frm:
            last = rng.choice([x for x in SELF[lang] if x != last])  # no "kk" twice running
            evs[i] = Ev(e.utc, e.frm, last, to=e.to)


def steady_chat(
    rng: random.Random,
    s: Setup,
    text: str,
    utc: datetime,
    from_me: bool,
    lang: str,
    avoid: str = "",
    lead: str = "",
) -> tuple[list[Ev], int]:
    """The record in its own chat: everyday lines before it, plain acknowledgements after;
    `lead`, if given, is the other end's line just before the record (a question it answers)."""
    frm, to = (s.me, s.you) if from_me else (s.you, s.me)
    rec = Ev(utc, frm, text, to=to)
    before = chatter(rng, lang, rng.randint(1, 3), avoid)
    evs, target = thread(rng, rec, before, calm(rng, lang, rng.randint(0, 3)))
    settle(rng, evs, target, lang)
    if lead:
        evs.insert(target, Ev(utc - timedelta(seconds=rng.randint(5, 20)), to, lead, to=frm))
        target += 1
        while target > 3:  # at most three lines before the record
            evs.pop(0)
            target -= 1
    return evs, target


def fresh_slug(rng: random.Random, taken: set[str]) -> str:
    """A person the document names by an invented surname, none of `taken`."""
    for _ in range(100):
        pid = bf.named_person(rng.choice(SURNAMES))
        if pid not in taken:
            return pid
    raise RuntimeError("no free surname")


# ---------------------------------------------------------------- claims


def number_text(ident: str) -> str:
    """A US number as a document writes it: '+13475550132' is '(347) 555-0132'."""
    d = ident[-10:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}"


def reach(name: str, acc: Acc | None) -> str:
    """A person a message or call claim names, with the account it gives for them, as a document
    writes it: "Dara Ahern at (347) 555-0132", "Finn Guzman, Telegram user 4063495,"."""
    if acc is None:
        return name
    if acc.app in ("Telegram", "Instagram"):
        return f"{name}, {acc.app} user {acc.ident},"
    return f"{name} at {number_text(acc.ident)}"


def uses(q: str, acc: Acc) -> str:
    """The sentence a role or event claim adds to give the account it ties to q."""
    if acc.app in ("Telegram", "Instagram"):
        return f"{last(q)} used the {acc.app} account {acc.ident}."
    return f"{last(q)} used the number {number_text(acc.ident)}."


def tidy(text: str, raw: str = "") -> str:
    """An appositive's closing comma gives way to the punctuation after it, and a window that
    ends a sentence on "p.m." takes no second full stop."""
    return re.sub(r",([.:;])", r"\1", stop(text, raw))


def stop(text: str, raw: str) -> str:
    """'... between 10 a.m. and 5 p.m.' ends its sentence with its own full stop."""
    return text.replace(f"{raw}.", raw) if raw.endswith(".") else text


def _did(act: str, q: str, street: str) -> str:
    """An act with its other person in by name: the full name first, the surname after."""
    out, n = act.replace("{Street}", street), 0
    while "{Q}" in out:
        out = out.replace("{Q}", full(q) if n == 0 else last(q), 1)
        n += 1
    return out


def act_claim(
    rng: random.Random,
    template: str,
    p: str,
    act: str,
    q: str,
    street: str,
    raw: str | None,
    q_acc: Acc | None = None,
) -> str:
    """A role or event claim: p did `act` (with q), within the window's own words if given;
    `q_acc` is an account the claim gives for q, in a sentence of its own."""
    did, P, Pl = _did(act, q, street), full(p), last(p)
    if raw is None:
        out = rng.choice(("{P} {did}.", "It was {P} who {did}.")).format(P=P, did=did)
    else:
        frames = ["{T}, {P} {did}.", "{P} {did} {t}."]
        frames.append("{P} {did}. {Pl} did so {t}." if template == "role" else
                      "{P} {did}. This took place {t}.")  # fmt: skip
        if raw.startswith(("from", "before", "after")):
            frames.append("During the period {t}, {P} {did}.")
        out = stop(timed(rng, frames, raw).format(P=P, Pl=Pl, did=did, T=raw, t=raw), raw)
    return f"{out} {uses(q, q_acc)}" if q_acc else out


# {Q} is the other person, with the account the claim gives for them when it gives one.
MESSAGE_FRAMES = (
    '{T}, {P} sent a message to {Q} that read "{x}".', '{T}, {P} messaged {Q}: "{x}".',
    '{P} wrote to {Q} {t}: "{x}".', 'In a message to {Q} sent {t}, {P} wrote "{x}".',
    '{T}, {P} sent a message to {Q} reading "{x}".',
    '{P} sent a message to {Q} {t}. The message read "{x}".',
)  # fmt: skip
APP_FRAMES = {
    "SMS": ('{T}, {P} texted {Q}: "{x}".', '{T}, {P} sent a text message to {Q} that read "{x}".'),
    "WhatsApp": ('{T}, {P} sent a WhatsApp message to {Q} that read "{x}".',),
    "Telegram": ('{T}, {P} sent a Telegram message to {Q} that read "{x}".',),
    "Signal": ('{T}, {P} sent a Signal message to {Q} reading "{x}".',),
    "Instagram": ('{T}, {P} sent a direct message on Instagram to {Q} that read "{x}".',),
}
CODE_FRAMES = ("{T}, {P} sent the {k}, {c}, to {Q}.",
               "{P} gave the {k}, {c}, to {Q} in a message sent {t}.",
               "{T}, {P} sent a message with the {k}, {c}, to {Q}.")  # fmt: skip
CALL_FRAMES = ("{T}, {P} called {Q}.", "{P} placed a call to {Q} {t}.", "{T}, {P} phoned {Q}.",
               "{P} called {Q} {t}.", "{P} made a phone call to {Q} {t}.")  # fmt: skip


def message_claim(
    rng: random.Random, p: str, q: str, app: str, text: str, raw: str, q_acc: Acc | None = None
) -> str:
    """p sent q (at `q_acc`, if the claim gives it) a message reading `text`, word for word,
    within the window."""
    frames = MESSAGE_FRAMES + APP_FRAMES.get(app, ())
    Q = reach(full(q), q_acc)
    return tidy(timed(rng, frames, raw).format(P=full(p), Q=Q, x=text, T=raw, t=raw), raw)


def code_claim(
    rng: random.Random,
    p: str,
    q: str,
    app: str,
    what: str,
    code: str,
    raw: str,
    q_acc: Acc | None = None,
) -> str:
    """p sent q the code `what` is, in other words than the message's own."""
    frames = CODE_FRAMES + (("{T}, {P} texted the {k}, {c}, to {Q}.",) if app == "SMS" else ())
    Q = reach(full(q), q_acc)
    return tidy(timed(rng, frames, raw).format(P=full(p), Q=Q, k=what, c=code, T=raw, t=raw), raw)


def call_claim(rng: random.Random, p: str, q: str, raw: str, q_acc: Acc | None = None) -> str:
    """p called q (at `q_acc`, if the claim gives it) within the window."""
    Q = reach(full(q), q_acc)
    return tidy(timed(rng, CALL_FRAMES, raw).format(P=full(p), Q=Q, T=raw, t=raw), raw)
