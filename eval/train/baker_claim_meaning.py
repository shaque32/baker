"""Meaning claims as a government document states them (guide rule 29): what some words meant,
as used by a named person or in the messages at large, sometimes at the record's date.

People appear as {{person id}} and {{person id|last}}, as in baker_claims.py. Everyday sentences
a claim reads as code take frames that say so outright.
"""

from __future__ import annotations

import random
from datetime import datetime

from eval.stancedata.chat import long_date
from eval.train.baker_claims import full, last, upfirst
from eval.train.baker_time import wall

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
