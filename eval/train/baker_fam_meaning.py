"""Baker's meaning template shown with its claim (guide rule 29): bk_meaning_said,
bk_meaning_other and the meaning third of bk_claim_open.

The claim says what some words meant. bk_meaning_said: the account that used the words (in the
record itself, giving the meaning as its own, or earlier in the chat too) plainly says they mean
exactly the claim's meaning (supports). bk_meaning_other: that account says they mean something
of another kind altogether, and the claim names it as the words' user (complicates: like a
denial, the explanation says nothing about messages it does not cover, and no claim here is
dated wholly before the record, so one record cannot show that no other message used the words
as the claim says; rule 23). All three explain in the same frames, openers and tails, none of
them a marker like "only" or "nothing else", so only the meaning and the claim's person tell
them apart; the quote is the explanation alone, without the opener or tail (rule 7).
bk_claim_open: the record uses the words and nothing shown says what they mean, or its sender
gives them another meaning while the claim names no one who used them, so one account's meaning
cannot rule out another's use (complicates). A claim names the words' user only when that
account's line carries them in brackets. No line from anyone else holds the words, no other line
shares a content word with any meaning in play, and the lines after an explanation are plain
acknowledgements, so nothing hedges or corrects it.
"""

from __future__ import annotations

import random
import re
from datetime import timedelta

from eval.train.baker_claim_meaning import meaning_claim, record_when
from eval.train.baker_claim_ru import (
    EXPLAIN_RU,
    MEANINGS_RU,
    OPENERS_RU,
    OWN_RU,
    TAILS_RU,
    USE_RU,
)
from eval.train.baker_claim_words import (
    EXPLAIN,
    MEANINGS,
    OPENERS,
    OWN,
    PLURAL,
    TAILS,
    TOPICS,
    USE,
)
from eval.train.baker_claims import calm, settle
from eval.train.baker_kit import (
    Draft,
    Setup,
    any_time,
    chatter,
    lang_of_text,
    pick_kind,
    quoted_words,
    record_text,
    setup,
)
from eval.train.baker_scene import Ev, render, thread
from eval.train.baker_text import combo, salt_of, split_ru, words


def content(text: str) -> set[str]:
    """Content words that could hint at a meaning: three letters or more (Russian: four)."""
    return {w for w in words(text) if len(w) >= (4 if re.search(r"[а-яё]", w) else 3)}


def say(template: str, p: str, m: str) -> str:
    return (
        template.replace("{p}", p).replace("{m}", m).replace("{is}", "are" if p in PLURAL else "is")
    )


def _excerpt(
    rng: random.Random,
    s: Setup,
    text: str,
    from_me: bool,
    lang: str,
    quoted: str,
    meanings: set[str],
    used_before: str = "",
) -> tuple[list[Ev], int]:
    """The record from one end of the chat, with `used_before` from the same end a little
    earlier, everyday lines before it and plain acknowledgements after it."""
    utc = any_time(rng, s.phone.zone)
    frm, to = (s.me, s.you) if from_me else (s.you, s.me)
    nb = rng.randint(0, 2) if used_before else rng.randint(1, 3)
    na = rng.randint(0, 3) if nb else rng.randint(1, 3)
    rec = Ev(utc, frm, text, to=to)
    evs, target = thread(rng, rec, chatter(rng, lang, nb, quoted), calm(rng, lang, na))
    settle(rng, evs, target, lang)
    if used_before:
        first = evs[0].utc or utc
        evs.insert(0, Ev(first - timedelta(seconds=rng.randint(60, 900)), frm, used_before, to=to))
        target += 1
    for i, e in enumerate(evs):
        if i == target:
            continue
        if e.frm != frm and quoted.casefold() in e.text.casefold():
            raise ValueError("someone else uses the words")
        if content(e.text) & meanings:
            raise ValueError("a context line touches a meaning in play")
    return evs, target


def explained(rng: random.Random, k: int, family: str, unnamed: bool = False) -> Draft:
    """The words' user says what they mean, in the same frames every way: the claim's meaning
    (bk_meaning_said, the claim naming that user or no one), another kind of thing altogether
    with the claim naming that user (bk_meaning_other), or another kind of thing with the claim
    naming no one (`unnamed`, for bk_claim_open). A frame that does not give the meaning as the
    sender's own comes after the sender's own use of the words."""
    ru, ordinal = split_ru(k)
    lang = "ru" if ru else "en"
    table = MEANINGS_RU if ru else MEANINGS
    frames, openers, tails = (EXPLAIN_RU, OPENERS_RU, TAILS_RU) if ru else (EXPLAIN, OPENERS, TAILS)
    said = family == "bk_meaning_said"
    sizes = (len(table), len(frames), 1 if said else 2)
    mi, ti, oi = combo(ordinal, sizes, salt_of(f"{family}|{lang}"))
    quoted, claim_m, chat_m, others = table[mi]
    meant = chat_m if said else others[oi]
    clause = say(frames[ti], quoted, meant)
    text = rng.choice(openers) + clause + rng.choice(tails)
    s = setup(rng, pick_kind(rng), lang=lang)
    from_me = rng.random() < 0.5
    user = s.phone.person if from_me else s.you_pid
    if family == "bk_meaning_other" and user is None:
        # The claim names the words' user, shown by the line's brackets (rule 29).
        raise ValueError("bk_meaning_other needs a bracketed user for the claim to name")
    use = ""
    if rng.random() < 0.4 or frames[ti] not in (OWN_RU if ru else OWN):
        use = say(rng.choice(USE_RU if ru else USE), quoted, "")
    in_play = content(f"{claim_m} {chat_m} {' '.join(others)}") - words(quoted)
    evs, target = _excerpt(rng, s, text, from_me, lang, quoted, in_play, use)
    rec = evs[target]
    line = render(s.scene, s.phone, rec)
    if unnamed:
        named = None
    elif said:
        named = user if user is not None and rng.random() < 0.7 else None
    else:
        named = user
    claim = meaning_claim(rng, quoted, claim_m, named, record_when(rng, rec.utc, s.phone.zone))
    if not said:
        if unnamed:
            end = ("but the claim names no one who used them, and one account's meaning cannot "
                   "show that no other account used them as the claim says, so the claim's "
                   "meaning is not settled")  # fmt: skip
        else:
            end = ("unlike the claim's meaning; but the claim gives no date before the record, "
                   "and one record cannot show that no other message used the words as the claim "
                   "says, so the claim's meaning is not settled")  # fmt: skip
        head = (f"The record comes from {line.sender}, which used the words earlier in this chat "
                f'and now says "{quoted}" means "{meant}"' if use else
                f'The record comes from {line.sender}, which says what it means by "{quoted}": '
                f'"{meant}"')  # fmt: skip
        rationale = f"{head}, {end}."
    elif use:
        rationale = (f"The record comes from {line.sender}, which used the words earlier in this "
                     f'chat and now plainly says "{quoted}" means "{meant}": the meaning the '
                     "claim gives them.")  # fmt: skip
    else:
        rationale = (f"The record comes from {line.sender}, which plainly says what it means by "
                     f'"{quoted}": "{meant}", the meaning the claim gives them.')  # fmt: skip
    notes = {"user": rec.frm, "used_before": bool(use), "clause": clause,
             "own": frames[ti] in (OWN_RU if ru else OWN), "named": named is not None}  # fmt: skip
    return Draft(family, "meaning", {"quoted_text": quoted}, s.scene, s.phone, evs, target,
                 clause, rationale, notes, claim=claim)  # fmt: skip


def meaning_said(rng: random.Random, k: int) -> Draft:
    return explained(rng, k, "bk_meaning_said")


def meaning_other(rng: random.Random, k: int) -> Draft:
    return explained(rng, k, "bk_meaning_other")


def open_meaning(rng: random.Random, j: int, family: str) -> Draft:
    """The j-th meaning item of bk_claim_open, by j % 3: 0 words a claim gives a meaning to, used
    and left unexplained; 1 a span of an everyday record that a claim reads as a code; 2 the
    words' user giving them another meaning while the claim names no one who used them."""
    if j % 3 == 2:
        return explained(rng, j // 3, family, unnamed=True)
    if j % 3 == 0:
        ru, ordinal = split_ru(j // 3)
        table, uses = (MEANINGS_RU, USE_RU) if ru else (MEANINGS, USE)
        mi, ui = combo(ordinal, (len(table), len(uses)), salt_of(f"{family}|use|{ru}"))
        quoted, claim_m, chat_m, others = table[mi]
        text = say(uses[ui], quoted, "")
        in_play = content(f"{claim_m} {chat_m} {' '.join(others)}")
    else:
        i = j // 3
        text, core = record_text(rng, i, f"{family}|meaning", vague=i % 3 == 0)
        quoted = quoted_words(rng, text, core)
        topics = [t for t in TOPICS if not words(t) & words(text)]
        if not topics:
            raise ValueError("every topic shares a word with the record")
        claim_m = rng.choice(topics)
        in_play = content(claim_m)
    lang = lang_of_text(text)
    s = setup(rng, pick_kind(rng), lang=lang)
    from_me = rng.random() < 0.5
    evs, target = _excerpt(rng, s, text, from_me, lang, quoted, in_play - words(quoted))
    rec = evs[target]
    line = render(s.scene, s.phone, rec)
    user = s.phone.person if from_me else s.you_pid
    named = user if user is not None and rng.random() < 0.6 else None
    when = record_when(rng, rec.utc, s.phone.zone)
    claim = meaning_claim(rng, quoted, claim_m, named, when, code=j % 3 == 1)
    rationale = (f'The record from {line.sender} uses "{quoted}", but nothing shown says what the '
                 "words mean, so the meaning the claim gives them is not settled.")  # fmt: skip
    return Draft(family, "meaning", {"quoted_text": quoted}, s.scene, s.phone, evs, target, quoted,
                 rationale, claim=claim)  # fmt: skip
