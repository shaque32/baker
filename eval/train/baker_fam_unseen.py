"""bk_claim_unseen: Baker's meaning, role and event templates point to a claim the stance step
is not shown (guide rule 29), so a record that holds the quoted words, or comes from or goes to
an account bracketed with a named person (inside the window, if one is given), is complicates.
"""

from __future__ import annotations

import random
from typing import Any

from eval.stancedata import bakerform as bf
from eval.train.baker_kit import (
    Draft,
    Setup,
    any_time,
    chat,
    lang_of_text,
    pick_kind,
    quoted_words,
    record_text,
    setup,
)
from eval.train.baker_place import inside
from eval.train.baker_scene import Acc, render

FAMILY = "bk_claim_unseen"


def shown(s: Setup, acc: Acc) -> str:
    """An account's sender text on the record's phone, brackets included."""
    return bf.sender_line(acc.app, acc.ident, owner=acc in s.phone.own,
                          persons=s.scene.persons(acc))  # fmt: skip


def _text(rng: random.Random, k: int) -> tuple[str, str]:
    """Every sixth item quotes a vague phrase; the rest take everyday records, one stream for
    the family, so no record text repeats."""
    if k % 6 == 0:
        return record_text(rng, k // 6, FAMILY + "|vague", vague=True)
    return record_text(rng, k - (k + 5) // 6, FAMILY)


def claim_unseen(rng: random.Random, k: int) -> Draft:
    """k % 3: 0 meaning (the record holds the quoted words), 1 role, 2 event (the record comes
    from or goes to an account bracketed with a person the assumption names)."""
    template = ("meaning", "role", "event")[k % 3]
    text, core = _text(rng, k)
    lang = lang_of_text(text)
    s = setup(
        rng, pick_kind(rng, (2, 4, 4)) if template != "meaning" else pick_kind(rng), lang=lang
    )
    win = None
    if template == "event" and rng.random() < 0.5:
        win, utc = inside(rng, s.phone.zone, s.phone.zone)
    else:
        utc = any_time(rng, s.phone.zone)
    from_me = rng.random() < 0.5
    quoted = quoted_words(rng, text, core) if template == "meaning" else ""
    evs, target = chat(rng, s, text, utc, from_me, lang, avoid=quoted)
    rec = evs[target]
    line = render(s.scene, s.phone, rec)
    if template == "meaning":
        params: dict[str, Any] = {"quoted_text": quoted}
        rationale = ("The record holds the quoted words, but nothing shown says what the claim "
                     "states they mean.")  # fmt: skip
        return Draft(FAMILY, template, params, s.scene, s.phone, evs, target, quoted, rationale)
    if rec.to is None:
        raise ValueError("a message needs its chat partner")
    ends = {s.phone.person: s.me}
    if s.you_pid is not None:
        ends[s.you_pid] = s.you
    named = rng.sample(sorted(ends), rng.choice((1, 1, 2)) if len(ends) > 1 else 1)
    params = {"person_ids": tuple(named)}
    if len(named) == 2:
        rationale = (f"The record is between {shown(s, rec.frm)} and {shown(s, rec.to)}, "
                     "bracketed with the named persons")  # fmt: skip
    else:
        way = "comes from" if ends[named[0]] == rec.frm else "goes to"
        rationale = f"The record {way} {shown(s, ends[named[0]])}, bracketed with {named[0]}"
    if win is not None:
        params["window"] = win.tw
        rationale += f', inside "{win.raw}" ({win.tz}) at {line.local_time}'
    what = "role" if template == "role" else "event"
    rationale += f", but nothing shown says what {what} the claim states."
    return Draft(FAMILY, template, params, s.scene, s.phone, evs, target, line.text, rationale)
