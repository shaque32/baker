"""Each planned Baker-wording item claims its wording from the walk (bk_walk): a record line,
a cue, a weekday plan, a contact, meaning words, an act or a role, and the names they carry.
Slots claim in schedule order, test split first, so the same command always gives each item
the same wording.
"""

from __future__ import annotations

import functools
from collections import Counter

from eval.heldout import bk_cues as cues
from eval.heldout.bk_schedule import ACT_FORMS, WORDED, BkSlot, lang_for, needs, slots
from eval.heldout.bk_walk import Walk


def _named(walk: Walk) -> str:
    """A person slug that reads as a surname (not a withheld "name_0417")."""
    for _ in range(8):
        slug = walk.person()
        if not slug.startswith("name_"):
            return slug
    raise RuntimeError("no surname slug")


def _fit_first(walk: Walk, s: BkSlot) -> None:
    """A first name that is no part of the surname ("Rook Rookwood" reads as one name)."""
    sur = s.person.split("_")[0]
    while s.first and (s.first.lower() in sur or sur in s.first.lower()):
        s.first = walk.first(avoid=s.first)
    if s.first2 == s.first:
        s.first2 = walk.first(avoid=s.first)


def _identity(walk: Walk, s: BkSlot, ru: bool, answer: bool) -> None:
    """A self-naming record: the person, their name as written, and the record and cue."""
    for _ in range(30):
        if ru:
            s.person, s.sur, s.first = walk.ru_person()
        else:
            s.person = _named(walk)
            s.sur = s.person
            _fit_first(walk, s)
        names = {"first": s.first.lower(), "First": s.first, "sur": s.sur.lower(),
                 "Sur": s.sur[:1].upper() + s.sur[1:]}  # fmt: skip
        try:
            if not answer:
                table = cues.ID_RU if ru else cues.ID_EN
                s.text, s.cue = walk.marked(table, f"id|{ru}", **names)
                return
            pairs = cues.ID_ANSWER_RU if ru else cues.ID_ANSWER_EN
            ask, rec = pairs[walk._next(f"ida|{ru}", len(pairs))]
            s.text, s.cue = walk.marked((rec,), f"idr|{ru}", **names)
            s.ask = cues.fill(ask, **names)
            return
        except RuntimeError:
            continue
    raise RuntimeError("no unused identity record")


def _author(walk: Walk, s: BkSlot, ru: bool, named: bool) -> None:
    """A record with a cue about who is typing; `named` cues name the assumption's person."""
    for _ in range(30):
        first2 = walk.ru_first() if ru else s.first2.lower()
        if ru:
            table = cues.AUTHOR_RU
        else:
            table = cues.AUTHOR_EN if named else cues.AUTHOR_OWNER_EN
        if named and not ru:
            s.person = _named(walk)
            _fit_first(walk, s)
            first2 = s.first2.lower()
        sur = s.person
        try:
            s.text, s.cue = walk.marked(table, f"au|{ru}|{named}", first2=first2, sur=sur,
                                        Sur=sur.capitalize(), First=s.first)  # fmt: skip
            s.first2 = first2
            return
        except RuntimeError:
            s.first2 = walk.first(avoid=s.first)
    raise RuntimeError("no unused authorship record")


def _claim(walk: Walk, s: BkSlot, want: tuple[str, ...]) -> None:
    ru = s.lang in ("ru", "mixed")
    s.person = walk.person()
    s.first, s.first2 = walk.first(), ""
    s.first2 = walk.first(avoid=s.first)
    _fit_first(walk, s)
    if "handles" in want:
        s.handles = walk.handle_pair()
    old, new = (h.lstrip("@") for h in s.handles[1:])
    if "say" in want:
        s.sit, s.text = walk.say_line(s.lang)
    if "q" in want:
        _, s.q = walk.say_line(s.lang if "say" in want else "en", no_money=True)
    if "wkq" in want:
        _, s.q, _ = walk.weekday(s.lang, "")
    if "wk" in want:
        mod = {"next": "next ", "this": "this "}.get(s.variant, "")
        s.sit, s.text, s.day = walk.weekday(s.lang, mod)
    if "contact" in want:
        s.contact = walk.contact("ru" if ru else "en")
    if "ident" in want or "ident_answer" in want:
        _identity(walk, s, ru, "ident_answer" in want)
    if "author" in want or "author_owner" in want:
        _author(walk, s, ru, "author" in want)
    if {"meaning", "meaning_open", "meaning_bare"} & set(want):
        form = {"bk_meaning_said": "said", "bk_meaning_other": "other"}.get(s.family, "bare")
        if "meaning_open" in want:
            form = "open" if s.variant == "meaning" else "open_q"
        s.sit, s.words, s.meaning, s.plain, s.usage, text = walk.meaning(s.lang, form)
        s.text = text or s.text
    if {"act", "role", "claim_bare"} & set(want):
        kind = "role" if "role" in want else "act"
        if "claim_bare" in want:
            kind = "role" if (s.k // 12) % 2 == 0 else "act"
        s.person2 = walk.person()
        forms = ACT_FORMS.get(s.variant, ("deny",) if s.family == "bk_claim_denied" else ("",))
        form = forms[walk._next(f"form|{s.family}|{s.variant}", len(forms))]
        s.sit, s.act, s.vals, text = walk.act(kind, form, s.person2)
        s.vals["kind"], s.vals["form"] = kind, form
        s.text = text or s.text
    if "handle_self" in want or "handle_any" in want:
        kind = "self" if "handle_self" in want else "any"
        table = getattr(cues, f"HANDLE_{kind.upper()}_{'RU' if ru else 'EN'}")
        s.text, s.cue = walk.marked(table, f"hd|{kind}|{ru}", old=old, new=new)


@functools.lru_cache(maxsize=1)
def bk_schedule() -> dict[str, list[BkSlot]]:
    """Both splits with their wording claimed, test first; a fixed table."""
    walk = Walk()
    out: dict[str, list[BkSlot]] = {}
    for split in ("test", "dev"):
        planned = slots(split)
        seen: Counter[str] = Counter()
        for s in planned:
            want = needs(s.family, s.variant)
            if WORDED & set(want):
                s.lang = lang_for(seen[s.family])
                seen[s.family] += 1
                if s.lang == "mixed" and "contact" in want:
                    s.lang = "en"
            _claim(walk, s, want)
        out[split] = planned
    return out
