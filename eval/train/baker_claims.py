"""Claims as a government document states them (guide rule 29), and dates as a chat writes them.

A claim is one or two formal, third-person, past-tense sentences. People appear as {{person id}}
(the full name) on first mention and {{person id|last}} (the surname) after it;
baker_cast.fill_claim writes in the names the item's cast gives them. A claim's time is its
window's own words, so the claim and the assumption's window always agree. Each builder picks
among several frames, so the wording varies; none uses a word the tool never says.
"""

from __future__ import annotations

import random
from datetime import date, datetime

from eval.stancedata import bakerform as bf
from eval.stancedata.chat import long_date
from eval.train.baker_cues import SURNAMES
from eval.train.baker_kit import Setup, chatter
from eval.train.baker_scene import Ev, thread
from eval.train.baker_time import wall

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
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december")  # fmt: skip


def full(pid: str) -> str:
    return "{{" + pid + "}}"


def last(pid: str) -> str:
    return "{{" + pid + "|last}}"


def upfirst(s: str) -> str:
    return s[:1].upper() + s[1:]


def lowfirst(s: str) -> str:
    return s[:1].lower() + s[1:]


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
) -> tuple[list[Ev], int]:
    """The record in its own chat: everyday lines before it, plain acknowledgements after."""
    frm, to = (s.me, s.you) if from_me else (s.you, s.me)
    rec = Ev(utc, frm, text, to=to)
    before = chatter(rng, lang, rng.randint(1, 3), avoid)
    evs, target = thread(rng, rec, before, calm(rng, lang, rng.randint(0, 3)))
    settle(rng, evs, target, lang)
    return evs, target


def fresh_slug(rng: random.Random, taken: set[str]) -> str:
    """A person the document names by an invented surname, none of `taken`."""
    for _ in range(100):
        pid = bf.named_person(rng.choice(SURNAMES))
        if pid not in taken:
            return pid
    raise RuntimeError("no free surname")


# ---------------------------------------------------------------- claims


def _did(act: str, q: str, street: str) -> str:
    """An act with its other person in by name: the full name first, the surname after."""
    out, n = act.replace("{Street}", street), 0
    while "{Q}" in out:
        out = out.replace("{Q}", full(q) if n == 0 else last(q), 1)
        n += 1
    return out


def act_claim(
    rng: random.Random, template: str, p: str, act: str, q: str, street: str, raw: str | None
) -> str:
    """A role or event claim: p did `act` (with q), within the window's own words if given."""
    did, P, Pl = _did(act, q, street), full(p), last(p)
    if raw is None:
        frames = ["{P} {did}.", "It was {P} who {did}."]
    else:
        frames = ["{T}, {P} {did}.", "{P} {did} {t}."]
        frames.append("{P} {did}. {Pl} did so {t}." if template == "role" else
                      "{P} {did}. This took place {t}.")  # fmt: skip
        if raw.startswith(("from", "before", "after")):
            frames.append("During the period {t}, {P} {did}.")
    t = lowfirst(raw or "")
    return rng.choice(frames).format(P=P, Pl=Pl, did=did, T=upfirst(t), t=t)


MESSAGE_FRAMES = (
    '{T}, {P} sent {Q} a message that read "{x}".', '{T}, {P} messaged {Q}: "{x}".',
    '{P} wrote to {Q} {t}: "{x}".', 'In a message to {Q} sent {t}, {P} wrote "{x}".',
    '{T}, {P} sent a message to {Q} reading "{x}".',
    '{P} sent {Q} a message {t}. The message read "{x}".',
)  # fmt: skip
APP_FRAMES = {
    "SMS": ('{T}, {P} texted {Q}: "{x}".', '{T}, {P} sent {Q} a text message that read "{x}".'),
    "WhatsApp": ('{T}, {P} sent {Q} a WhatsApp message that read "{x}".',),
    "Telegram": ('{T}, {P} wrote to {Q} on Telegram: "{x}".',),
    "Signal": ('{T}, {P} sent {Q} a Signal message reading "{x}".',),
    "Instagram": ('{T}, {P} sent {Q} a direct message on Instagram that read "{x}".',),
}
CODE_FRAMES = ("{T}, {P} sent {Q} the {k}, {c}.",
               "{P} gave {Q} the {k}, {c}, in a message sent {t}.",
               "{T}, {P} sent {Q} a message with the {k}, {c}.")  # fmt: skip
CALL_FRAMES = ("{T}, {P} called {Q}.", "{P} placed a call to {Q} {t}.", "{T}, {P} phoned {Q}.",
               "{P} called {Q} {t}.", "{P} made a phone call to {Q} {t}.")  # fmt: skip


def message_claim(rng: random.Random, p: str, q: str, app: str, text: str, raw: str) -> str:
    """p sent q a message reading `text`, word for word, within the window."""
    frames = MESSAGE_FRAMES + APP_FRAMES.get(app, ())
    t = lowfirst(raw)
    return rng.choice(frames).format(P=full(p), Q=full(q), x=text, T=upfirst(t), t=t)


def code_claim(rng: random.Random, p: str, q: str, app: str, what: str, code: str, raw: str) -> str:
    """p sent q the code `what` is, in other words than the message's own."""
    frames = CODE_FRAMES + (("{T}, {P} texted {Q} the {k}, {c}.",) if app == "SMS" else ())
    t = lowfirst(raw)
    return rng.choice(frames).format(P=full(p), Q=full(q), k=what, c=code, T=upfirst(t), t=t)


def call_claim(rng: random.Random, p: str, q: str, raw: str) -> str:
    """p called q within the window."""
    t = lowfirst(raw)
    return rng.choice(CALL_FRAMES).format(P=full(p), Q=full(q), T=upfirst(t), t=t)


MEANING_P = ('{P} used "{w}" to refer to {m}.', '{P} used the words "{w}" as a code for {m}.',
             'When {P} wrote "{w}", {Pl} meant {m}.', 'In {P}\'s messages, "{w}" referred to {m}.',
             '{P} referred to {m} as "{w}".', 'As {P} used it, "{w}" meant {m}.')  # fmt: skip
MEANING_P_WHEN = ('In messages sent {when}, {P} used "{w}" to refer to {m}.',
                  '{P} used the words "{w}" {when} as a code for {m}.',
                  'When {P} wrote "{w}" {when}, {Pl} meant {m}.',
                  '{When}, {P} referred to {m} as "{w}".')  # fmt: skip
MEANING = (
    'In the messages, "{w}" referred to {m}.',
    'The phrase "{w}" was used to mean {m}.',
    'The words "{w}" were a coded reference to {m}.',
    'The term "{w}" in the messages meant {m}.',
    'The messages used "{w}" to mean {m}.',
)
MEANING_WHEN = ('In messages sent {when}, "{w}" referred to {m}.',
                'The phrase "{w}", as used {when}, meant {m}.',
                '{When}, the words "{w}" were used to mean {m}.')  # fmt: skip


# For whole everyday sentences a claim reads as code: the frames say so outright.
CODE_P = ('{P} used the words "{w}" as a code for {m}.',
          'The words "{w}" in {P}\'s message were a coded reference to {m}.',
          'When {P} wrote "{w}", the words were a coded reference to {m}.')  # fmt: skip
CODE_P_WHEN = ('In a message sent {when}, {P} used the words "{w}" as a code for {m}.',
               '{When}, {P} wrote "{w}" as a coded reference to {m}.')  # fmt: skip
CODE = (
    'The words "{w}" were a coded reference to {m}.',
    'The phrase "{w}" was a coded reference to {m}.',
    'The message used "{w}" as code for {m}.',
)
CODE_WHEN = ('In a message sent {when}, the words "{w}" were a coded reference to {m}.',
             '{When}, the phrase "{w}" was used as a code for {m}.')  # fmt: skip


def meaning_claim(
    rng: random.Random,
    words: str,
    meaning: str,
    p: str | None,
    when: str | None,
    code: bool = False,
) -> str:
    """The words meant `meaning`, as used by p (a person the words' account is bracketed with)
    or by no one named, at the record's time if `when` is given; `code` for everyday sentences
    the claim reads as code."""
    table = {
        (False, False): (MEANING, MEANING_WHEN), (False, True): (MEANING_P, MEANING_P_WHEN),
        (True, False): (CODE, CODE_WHEN), (True, True): (CODE_P, CODE_P_WHEN),
    }[(code, p is not None)]  # fmt: skip
    frames = table[1] if when else table[0]
    return rng.choice(frames).format(P=full(p or ""), Pl=last(p or ""), w=words, m=meaning,
                                     when=when or "", When=upfirst(when or ""))  # fmt: skip


def record_when(rng: random.Random, utc: datetime, zone: str) -> str | None:
    """The record's date as a claim writes it, when every US zone reads the same day or month:
    "on May 2, 2026", "in May 2026", or nothing."""
    w, r = wall(utc, zone), rng.random()
    if r < 0.45:
        return None
    if r < 0.75 and 9 <= w.hour <= 20:
        return f"on {long_date(w.date())}"
    return f"in {w:%B} {w.year}" if 3 <= w.day <= 26 else None


# ---------------------------------------------------------------- dates in a chat


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def chat_day(rng: random.Random, d: date, sent: date) -> str:
    """'may 2nd', 'may 2', '5/2', or 'the 2nd' when sent in the same month."""
    opts = [f"{MONTHS[d.month - 1]} {ordinal(d.day)}", f"{MONTHS[d.month - 1]} {d.day}",
            f"{d.month}/{d.day}"]  # fmt: skip
    if (d.year, d.month) == (sent.year, sent.month):
        opts.append(f"the {ordinal(d.day)}")
    return rng.choice(opts)


def chat_span(rng: random.Random, d1: date, d2: date) -> str:
    """'from may 1st through the 9th', 'from april 28th through may 3rd'."""
    a = f"{MONTHS[d1.month - 1]} {ordinal(d1.day)}"
    if d1.month == d2.month:
        b = rng.choice((f"the {ordinal(d2.day)}", f"{MONTHS[d2.month - 1]} {ordinal(d2.day)}"))
    else:
        b = f"{MONTHS[d2.month - 1]} {ordinal(d2.day)}"
    return f"from {a} through {b}"
