"""bk_claim_denied: a person a role or event claim names rules it out, in their own words, for
the claim's whole time (guide rules 23 and 29; contradicts).

The record comes from an account bracketed with that person (the record phone's user, or a
partner an expert linked or stipulated) and is sent one to ten days after the window ends. It
denies the act or role for any time ("i never drove for kapoor, ever"), or, from the phone's
user, whose zone is the window's, says they did not see the other person at all on the claim's
day or stretch of days, which rules out an act that needs both of them in one place. The other
person is named by surname or full name, or is the chat partner ("u") when that partner's lines
carry them. Plain acknowledgements follow, so nothing hedges, corrects or reopens the time.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from eval.train.baker_cast import FIRSTS_EN, cap
from eval.train.baker_claim_words import CITIES, DAY_DENIALS, EVENTS, ROLES, SPAN_DENIALS
from eval.train.baker_claims import STREETS, act_claim, chat_day, chat_span, fresh_slug, steady_chat
from eval.train.baker_kit import Draft, pick_kind, setup, surname_of
from eval.train.baker_scene import render
from eval.train.baker_text import combo, salt_of
from eval.train.baker_time import (
    CLOCK_HOURS,
    Win,
    at,
    pick_day,
    wall,
    win_about,
    win_before,
    win_between,
    win_on,
    win_through,
)

FAMILY = "bk_claim_denied"
PREFIX = ("", "look, ", "for the record, ", "no, ", "to be clear, ", "listen, ", "again, ",
          "let me be clear, ")  # fmt: skip
LAST = date(2026, 9, 30)


def _space(template: str) -> list[tuple[int, str, str]]:
    """(act, kind, denial): an act's own denials for any time; for events, also denials of a
    day or a stretch of days, which fit any act that needs both people in one place."""
    acts = ROLES if template == "role" else EVENTS
    out = [(a, "never", t) for a, act in enumerate(acts) for t in act.never]
    if template == "event":
        out += [(-1, "day", t) for t in DAY_DENIALS] + [(-1, "span", t) for t in SPAN_DENIALS]
    return out


SPACE = {t: _space(t) for t in ("role", "event")}
TOGETHER = [a for a, act in enumerate(EVENTS) if act.together]


def _window(rng: random.Random, template: str, kind: str, zone: str) -> Win:
    for _ in range(100):
        d = pick_day(rng)
        if template == "role":
            end = d + timedelta(days=rng.randint(14, 120))
            ok = end.year == d.year and rng.random() < 0.7
            return win_through(d, end, zone) if ok else win_before(rng, d, zone)
        if kind == "span" or (kind == "never" and rng.random() < 0.25):
            end = d + timedelta(days=rng.randint(1, 8))
            if end.year == d.year:
                return win_through(d, end, zone)
            continue
        form = rng.choice(("on", "On", "between", "about"))
        if form == "between":
            h1 = rng.choice(CLOCK_HOURS[:-2])
            h2 = rng.choice([h for h in CLOCK_HOURS if h1 + 2 <= h <= h1 + 5])
            return win_between(d, h1, h2, zone)
        if form == "about":
            return win_about(d, rng.choice(CLOCK_HOURS), rng.choice((0, 30)), zone)
        return win_on(d, zone, form == "On")
    raise RuntimeError("no window found")


def claim_denied(rng: random.Random, k: int) -> Draft:
    template = ("role", "event")[k % 2]
    space = SPACE[template]
    ei, xi = combo(k // 2, (len(space), len(PREFIX)), salt_of(f"{FAMILY}|{template}"))
    a, kind, line = space[ei]
    a = a if a >= 0 else rng.choice(TOGETHER)
    act = (ROLES if template == "role" else EVENTS)[a]
    s = setup(rng, pick_kind(rng, (3, 4, 3)))
    owner_speaks = kind != "never" or s.you_pid is None or rng.random() < 0.6
    p, p_acc = (s.phone.person, s.me) if owner_speaks else (s.you_pid, s.you)
    listener, l_acc = (s.you_pid, s.you) if owner_speaks else (s.phone.person, s.me)
    you = listener is not None and rng.random() < 0.4
    q = listener if you and listener is not None else fresh_slug(rng, {p, listener or ""})
    names: dict[str, str] = {}
    if you:
        line = line.replace("{q}s ", "ur ").replace("{q}", "u")
    elif rng.random() < 0.3:  # the full name, as the document gives it
        chat_names = {ph.owner.person.name for ph in s.scene.phones} | {s.partner.person.name}
        first = rng.choice([f for f in FIRSTS_EN if f not in chat_names])
        names[q] = f"{first} {cap(surname_of(q))}"
        line = line.replace("{q}", f"{first.lower()} {surname_of(q)}")
    else:
        line = line.replace("{q}", surname_of(q))
    win = _window(rng, template, kind, s.phone.zone)
    last_day = (win.end - timedelta(microseconds=1)).date()
    sent = last_day + timedelta(days=rng.randint(1, 10))
    if sent > LAST:
        raise ValueError("the record would fall after the data's last day")
    utc = at(sent, rng.randint(8, 22), rng.randrange(60), rng.randrange(60), s.phone.zone)
    sent = wall(utc, s.phone.zone).date()
    line = line.replace("{dc}", chat_day(rng, win.start.date(), sent))
    line = line.replace("{span}", chat_span(rng, win.start.date(), last_day))
    text = PREFIX[xi] + line.replace("{city}", rng.choice(CITIES))
    from_me = p_acc == s.me
    evs, target = steady_chat(rng, s, text, utc, from_me, "en")
    rec = evs[target]
    params: dict[str, Any] = {"person_ids": (p,)}
    if template == "event":
        opts: list[dict[str, Any]] = [{"person_ids": (p,)}, {"person_ids": (p, q)}]
        if you:
            opts.append({"person_ids": (p,), "account_ids": (s.phone.aid(l_acc),)})
        params = rng.choice(opts)
    params["window"] = win.tw
    claim = act_claim(rng, template, p, act.claim, q, rng.choice(STREETS), win.raw)
    rendered = render(s.scene, s.phone, rec)
    says = {
        "never": f"denies the {template} the claim states outright, for any time",
        "day": f"rules out being with {q} at any point on the day the claim names",
        "span": f"rules out being with {q} on any day of the stretch the claim names",
    }[kind]
    rationale = (f"In the record from {rendered.sender}, sent {rendered.local_time}, after "
                 f'"{win.raw}" ({win.tz}) ended, {p} {says}; that covers the claim\'s whole '
                 "time.")  # fmt: skip
    d = Draft(FAMILY, template, params, s.scene, s.phone, evs, target, text, rationale,
              {"kind": kind, "speaker": p, "end": win.end}, claim=claim)  # fmt: skip
    d.names.update(names)
    return d
