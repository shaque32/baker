"""Naming parties the way Baker's templates take them, and calls with their context.

A person id names a party only when the line it is about carries that id in brackets; an account
id names one directly. All account ids together are one party (core/audit/assumptions.py), so
"two parties" always includes a person id. A call's line shows only the calling number, so the
other side of a call is always named by its Phone account id, whose number the call text shows.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from eval.train.baker_kit import Setup, chatter
from eval.train.baker_scene import Acc, Cast, Ev, Who, around
from eval.train.baker_time import offset_min


def name_account(rng: random.Random, s: Setup, acc: Acc, p_person: float = 0.5) -> dict[str, Any]:
    """One party: the account's id (on both phones of a chat between two phone owners, at
    times), or a person id its line's brackets hold."""
    persons = s.scene.persons(acc)
    if persons and rng.random() < p_person:
        return {"person_ids": (rng.choice(persons),)}
    aids = [s.phone.aid(acc)]
    if s.other is not None and s.other.owner == s.partner and rng.random() < 0.35:
        aids.append(s.other.aid(acc))
        rng.shuffle(aids)
    return {"account_ids": tuple(aids)}


def two_parties(rng: random.Random, s: Setup) -> dict[str, Any]:
    """The owner and the partner of the record's chat as two parties, both shown."""
    owner, partner = s.phone.person, s.you_pid
    options: list[dict[str, Any]] = [{"person_ids": (owner,), "account_ids": (s.phone.aid(s.you),)}]
    if partner is not None:
        options += [{"person_ids": (owner, partner)},
                    {"person_ids": (partner,), "account_ids": (s.phone.aid(s.me),)}]  # fmt: skip
    return rng.choice(options)


def call_parties(rng: random.Random, s: Setup, call: Ev, two: bool = False) -> dict[str, Any]:
    """The calling side by a person id its brackets hold (or by its account id), the other side
    by its Phone account id. With `two`, the calling side must carry brackets."""
    if call.to is None:
        raise ValueError("a call needs its other number")
    persons = s.scene.persons(call.frm)
    to_aid = s.phone.aid(call.to)
    if persons and (two or rng.random() < 0.7):
        return {"person_ids": (rng.choice(persons),), "account_ids": (to_aid,)}
    if two:
        raise ValueError("two parties need brackets on the calling side")
    return {"account_ids": (s.phone.aid(call.frm), to_aid)}


def call_event(
    rng: random.Random, s: Setup, utc: datetime, outgoing: bool, dur: int, missed: bool = False
) -> Ev:
    """A call between the owner's number and the partner's; its text prints the time as the
    report did: in UTC mostly, sometimes in the phone's own offset."""
    frm, to = (s.me_phone, s.you_phone) if outgoing else (s.you_phone, s.me_phone)
    direction = "outgoing" if outgoing else "missed" if missed else "incoming"
    off = offset_min(utc, s.phone.zone) if rng.random() < 0.25 else 0
    return Ev(utc, frm, kind="call", to=to, direction=direction, dur=0 if missed else dur,
              offset=off)  # fmt: skip


def strangers(rng: random.Random, s: Setup, n: int, lang: str = "en") -> list[Who]:
    """People with no part in the scene's parties, for the phone's other chats."""
    cast = Cast(rng)
    for p in s.scene.phones:
        cast.taken |= {p.owner.person.name, p.owner.number, p.owner.tg, p.owner.ig}
    cast.taken |= {s.partner.person.name, s.partner.number, s.partner.tg, s.partner.ig}
    return [cast.who(lang) for _ in range(n)]


def call_context(
    rng: random.Random, s: Setup, call: Ev, lang: str, with_partner: bool = True
) -> tuple[list[Ev], int]:
    """The call among messages from the phone's chats near its time: the chat with the call's
    partner (if `with_partner`) and one or two chats with other people, all on the owner's app."""
    chats = [(s.me, s.you)] if with_partner else []
    chats += [(s.me, w.acc(s.app)) for w in strangers(rng, s, rng.randint(1, 2), lang)]
    nb, na = rng.randint(0, 3), rng.randint(0, 3)
    if nb + na == 0:
        nb = 1
    return around(rng, call, chats, chatter(rng, lang, nb), chatter(rng, lang, na))


def range_holding(rng: random.Random, dur: int) -> tuple[int, int] | None:
    """A stated length range that holds `dur` with a margin of at least 10% of each bound."""
    lo = int(dur * rng.uniform(0.35, 0.85)) // 5 * 5
    hi = -(-int(dur * rng.uniform(1.25, 2.2)) // 5) * 5
    if hi > 300:
        lo, hi = lo // 30 * 30, -(-hi // 30) * 30
    if dur >= lo * 1.1 + 3 and dur <= hi * 0.9 - 3 and lo < hi:
        return lo, hi
    return None


RANGES = ((30, 60), (45, 90), (60, 120), (60, 180), (90, 150), (90, 180), (120, 240),
          (120, 300), (180, 300), (180, 360), (240, 420), (300, 600), (360, 540), (600, 900),
          (600, 1200))  # fmt: skip


def length_outside(rng: random.Random) -> tuple[tuple[int, int], int]:
    """A stated range and a call length under half its minimum or over twice its maximum."""
    lo, hi = rng.choice(RANGES)
    if rng.random() < 0.5 and lo // 2 - 1 >= 3:
        return (lo, hi), rng.randint(3, lo // 2 - 1)
    return (lo, hi), rng.randint(2 * hi + 1, 2 * hi + 900)
