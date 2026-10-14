"""Baker's role and event templates shown with their claim (guide rule 29): bk_claim_open (all
three templates) and bk_event_is_record.

A role or an act stated as a fact is never shown by a message (rule 14). bk_claim_open: a record
from or to an account bracketed with a named person, plainly inside the window if the claim has
one, bears on the act or role without being it or ruling it out (complicates); its meaning third
comes from baker_fam_meaning. bk_event_is_record: the claim's event is a message or a call, and
the record is that very message or call between the named parties, plainly inside the window,
the message saying what the claim says it said, word for word or (a code) value for value
(supports). A named party is the record's own line (its account or the person its brackets
carry) or the other end of the chat or call; when the other end carries brackets, the claim
names that person.
"""

from __future__ import annotations

import random
from typing import Any

from eval.stancedata import bakerform as bf
from eval.train.baker_claim_words import EVENTS, ROLES, TOPICS
from eval.train.baker_claims import (
    CODE_TEXTS,
    CODES,
    STREETS,
    act_claim,
    call_claim,
    code_claim,
    fresh_slug,
    meaning_claim,
    message_claim,
    steady_chat,
)
from eval.train.baker_fam_meaning import content, open_meaning
from eval.train.baker_fam_time import other_zone, when
from eval.train.baker_kit import (
    Draft,
    Setup,
    any_time,
    chat,
    lang_of_text,
    pick_kind,
    record_text,
    setup,
)
from eval.train.baker_parties import call_context, call_event
from eval.train.baker_place import inside
from eval.train.baker_scene import Acc, render
from eval.train.baker_text import combo, fill, salt_of

TELL = ("", "ok ", "update: ", "so ", "btw ", "heads up, ")
ASK = ("", "hey ", "quick q, ", "yo ", "so ", "ok ")
ACT_FORMS = {"role": ("through", "through", "before"),
             "event": ("on", "On", "through", "between", "about")}  # fmt: skip


def shown(s: Setup, acc: Acc) -> str:
    """An account's sender text on the record's phone, brackets included."""
    return bf.sender_line(acc.app, acc.ident, owner=acc in s.phone.own,
                          persons=s.scene.persons(acc))  # fmt: skip


def claim_open(rng: random.Random, k: int) -> Draft:
    """k % 3: 0 meaning, 1 role, 2 event."""
    family = "bk_claim_open"
    template = ("meaning", "role", "event")[k % 3]
    if template == "meaning":
        return open_meaning(rng, k // 3, family)
    return open_act(rng, k // 3, template, family)


def open_act(rng: random.Random, j: int, template: str, family: str) -> Draft:
    """A line that bears on the act or role, from or to the account of the person it names."""
    acts = ROLES if template == "role" else EVENTS
    pairs = [(a, b) for a, act in enumerate(acts) for b in range(len(act.bearing))]
    pi, xi = combo(j, (len(pairs), len(TELL)), salt_of(f"{family}|{template}"))
    act = acts[pairs[pi][0]]
    line = act.bearing[pairs[pi][1]]
    to_p = line.startswith(">")
    text = fill(rng, (ASK if to_p else TELL)[xi] + line.lstrip(">"))[0]
    s = setup(rng, pick_kind(rng, (4, 3, 3)))
    p_owner = s.you_pid is None or rng.random() < 0.6
    p, p_acc = (s.phone.person, s.me) if p_owner else (s.you_pid, s.you)
    other, other_acc = (s.you_pid, s.you) if p_owner else (s.phone.person, s.me)
    q = other if other is not None and rng.random() < 0.6 else fresh_slug(rng, {p, other or ""})
    win = None
    if rng.random() < 0.7:
        tz = other_zone(rng, s.phone.zone) if rng.random() < 0.2 else s.phone.zone
        win, utc = inside(rng, s.phone.zone, tz, ACT_FORMS[template])
    else:
        utc = any_time(rng, s.phone.zone)
    evs, target = chat(rng, s, text, utc, p_owner != to_p, "en")
    rec = evs[target]
    params: dict[str, Any] = {"person_ids": (p,)}
    if template == "event":
        opts: list[dict[str, Any]] = [{"person_ids": (p,)}, {"person_ids": (p, q)}]
        if other is None or q == other:  # the other end's account stands for the claim's person
            opts.append({"person_ids": (p,), "account_ids": (s.phone.aid(other_acc),)})
        params = rng.choice(opts)
    at = ""
    if win is not None:
        params["window"] = win.tw
        at = when(render(s.scene, s.phone, rec).local_time, win, utc, s.phone.zone)
        at = f', sent {at}, plainly inside "{win.raw}" ({win.tz})'
    claim = act_claim(rng, template, p, act.claim, q, rng.choice(STREETS),
                      win.raw if win else None)  # fmt: skip
    way = "comes from" if rec.frm == p_acc else "goes to"
    rationale = (f"The record {way} {shown(s, p_acc)}{at}. It bears on the {template} the claim "
                 "states without showing it or ruling it out.")  # fmt: skip
    return Draft(family, template, params, s.scene, s.phone, evs, target, text, rationale,
                 {"named_acc": p_acc}, claim=claim)  # fmt: skip


def _code(k: int) -> str:
    c = 1000 + (k * 7919 + 4111) % 9000
    return str(c + 1 if c in (1190, 4471) else c)


def event_is_record(rng: random.Random, k: int) -> Draft:
    """k % 4: 3 a call; 1 a message giving a code, which the claim names in its own words; 0 and
    2 a message the claim quotes word for word."""
    family = "bk_event_is_record"
    if k % 4 == 3:
        return _call(rng, family)
    what = code = ""
    if k % 4 == 1:
        said, what = CODES[(k // 4) % len(CODES)]
        code = _code(k)
        text = rng.choice(CODE_TEXTS).format(k=said, c=code)
    else:
        text, _ = record_text(rng, k, family)
    lang = lang_of_text(text)
    s = setup(rng, pick_kind(rng, (4, 3, 3)), lang=lang)
    from_me = s.you_pid is None or rng.random() < 0.55
    p = s.phone.person if from_me else s.you_pid
    other = s.you_pid if from_me else s.phone.person
    tz = other_zone(rng, s.phone.zone) if rng.random() < 0.2 else s.phone.zone
    win, utc = inside(rng, s.phone.zone, tz, ("on", "On", "between", "about"))
    evs, target = steady_chat(rng, s, text, utc, from_me, lang, avoid=text)
    rec = evs[target]
    if rec.to is None:
        raise ValueError("a message needs its chat partner")
    if other is not None and rng.random() < 0.5:
        params: dict[str, Any] = {"person_ids": (p, other)}
    else:
        params = {"person_ids": (p,), "account_ids": (s.phone.aid(rec.to),)}
    params["window"] = win.tw
    q = other if other is not None else fresh_slug(rng, {p})
    if what:
        claim = code_claim(rng, p, q, rec.frm.app, what, code, win.raw)
    else:
        claim = message_claim(rng, p, q, rec.frm.app, text, win.raw)
    line = render(s.scene, s.phone, rec)
    at = when(line.local_time, win, utc, s.phone.zone)
    same = f"giving the {what}, {code}" if what else "word for word"
    rationale = (f"The record from {line.sender} to {shown(s, rec.to)}, sent {at}, plainly inside "
                 f'"{win.raw}" ({win.tz}), is the message the claim states, {same}.')  # fmt: skip
    return Draft(family, "event", params, s.scene, s.phone, evs, target, text, rationale,
                 {"utc": utc}, claim=claim)  # fmt: skip


def _call(rng: random.Random, family: str) -> Draft:
    """The claim says one named person called the other; the record is that call, from the
    caller's number, at least 20 seconds long."""
    s = setup(rng, pick_kind(rng, (4, 3, 3)))
    p_owner = s.you_pid is None or rng.random() < 0.55
    p = s.phone.person if p_owner else s.you_pid
    other = s.you_pid if p_owner else s.phone.person
    win, utc = inside(rng, s.phone.zone, s.phone.zone, ("about", "about", "on", "On", "between"))
    call = call_event(rng, s, utc, p_owner, rng.randint(20, 1500))
    lang = "ru" if rng.random() < 0.1 else "en"
    evs, target = call_context(rng, s, call, lang, with_partner=rng.random() < 0.5)
    if call.to is None:
        raise ValueError("a call needs its other number")
    params = {"person_ids": (p,), "account_ids": (s.phone.aid(call.to),), "window": win.tw}
    q = other if other is not None else fresh_slug(rng, {p})
    line = render(s.scene, s.phone, call)
    rationale = (f"The record is a call from {line.sender} to Phone {call.to.ident} at "
                 f'{line.local_time}, plainly inside "{win.raw}" ({win.tz}): the call the claim '
                 "states.")  # fmt: skip
    return Draft(family, "event", params, s.scene, s.phone, evs, target, line.text, rationale,
                 {"utc": utc}, claim=call_claim(rng, p, q, win.raw))  # fmt: skip


def claim_apart(
    rng: random.Random, template: str, params: dict[str, Any], seen: set[str], taken: set[str]
) -> str:
    """A claim for a bk_unrelated item: a meaning, role or act that shares no content word with
    the excerpt (`seen`), about the person the assumption names or someone no line shows."""
    if template == "meaning":
        who = None if rng.random() < 0.5 else fresh_slug(rng, taken)
        topics = [t for t in TOPICS if not content(t) & seen]
        if not topics:
            raise ValueError("every topic shares a word with the excerpt")
        return meaning_claim(rng, params["quoted_text"], rng.choice(topics), who, None, code=True)
    acts = ROLES if template == "role" else EVENTS
    act = rng.choice([a for a in acts if not content(a.claim) & seen] or list(acts))
    q = fresh_slug(rng, taken | set(params["person_ids"]))
    raw = params["window"].raw if "window" in params else None
    return act_claim(rng, template, params["person_ids"][0], act.claim, q, rng.choice(STREETS), raw)
