"""The fixed plan of the Baker-wording items: family, variant, language and claimed wording.

Both splits put these items after the plain ones, ids continuing. The test split has the
composition below and the dev split half of it. Each slot claims its wording from the walk
(bk_walk) in schedule order, test split first, so no record text repeats in the held-out set
and the two splits share none.
"""

from __future__ import annotations

import functools
from collections import Counter
from dataclasses import dataclass

from eval.heldout import bk_cues as cues
from eval.heldout.bk_walk import Walk
from eval.heldout.schedule import counts as plain_counts

BK_COMPOSITION: dict[str, int] = {
    "bk_sender_shown": 24,
    "bk_sender_other": 24,
    "bk_party_unshown": 24,
    "bk_time_inside": 24,
    "bk_call_inside": 24,
    "bk_time_outside": 24,
    "bk_zone_edge": 24,
    "bk_call_length": 24,
    "bk_identity_named": 24,
    "bk_account_silent": 24,
    "bk_handles_said": 24,
    "bk_contact_row": 24,
    "bk_contact_row_differs": 24,
    "bk_count_one": 24,
    "bk_no_contact_inside": 24,
    "bk_other_phone": 24,
    "bk_outside_window": 24,
    "bk_weekday_next": 24,
    "bk_weekday_open": 24,
    "bk_weekday_wrong": 24,
    "bk_author_cue": 24,
    "bk_claim_unseen": 24,
    "bk_unrelated": 48,
}

# Variants cycle within a family; every cycle length divides 12, so the dev split keeps the
# test split's shape.
VARIANTS: dict[str, tuple[str, ...]] = {
    "bk_sender_shown": ("acct_third", "acct_owner", "owner_person", "linked", "cross", "acct_both"),
    "bk_sender_other": ("named_owner", "named_third", "named_linked", "named_cross"),
    "bk_party_unshown": ("sender", "sender_named", "time_msg", "time_call", "nc_msg", "count_msg"),
    "bk_time_inside": ("anyone", "acct", "owner_person", "linked", "about", "cross_zone"),
    "bk_call_inside": ("out_person", "in_acct", "in_linked", "cross"),
    "bk_time_outside": ("msg_acct", "msg_anyone", "msg_person", "msg_linked", "call_person",
                        "call_acct"),
    "bk_zone_edge": ("msg_phone", "msg_named", "call_phone", "call_named", "nc_phone",
                     "nc_named"),
    "bk_call_length": ("short_out", "long_out", "short_in", "long_in"),
    "bk_identity_named": ("intro", "answer"),
    "bk_account_silent": ("identity", "authorship"),
    "bk_handles_said": ("self", "any_same_app", "any_other_app"),
    "bk_contact_row": ("row",),
    "bk_contact_row_differs": ("other_number", "other_name"),
    "bk_count_one": ("eq", "ge", "le"),
    "bk_no_contact_inside": ("msg_person", "msg_two_persons", "call", "attachment"),
    "bk_other_phone": ("nc_msg", "nc_call", "count_msg", "nc_attachment"),
    "bk_outside_window": ("nc_msg", "count_msg", "nc_call", "count_attachment"),
    "bk_weekday_next": ("plan",),
    "bk_weekday_open": ("same_day", "next", "this"),
    "bk_weekday_wrong": ("other_day", "after_date"),
    "bk_author_cue": ("slug_third", "owner_self"),
    "bk_claim_unseen": ("meaning", "role", "event"),
    "bk_unrelated": ("sender_same", "sender_att", "time_msg", "time_call3", "count_third",
                     "nc_call3", "same_acct", "contact_other", "weekday_msg", "meaning_call",
                     "ident_other", "role_event_row"),
}  # fmt: skip

_NO_TEXT = {"time_call", "call_person", "call_acct", "call_phone", "call_named", "call",
            "nc_call", "attachment", "nc_attachment", "count_attachment"}  # fmt: skip
_UNRELATED: dict[str, tuple[str, ...]] = {
    "sender_same": ("say", "q"),
    "sender_att": ("q",),
    "time_msg": ("say", "q"),
    "time_call3": (),
    "count_third": ("say",),
    "nc_call3": (),
    "same_acct": ("say", "handles"),
    "contact_other": ("contact",),
    "weekday_msg": ("say", "wkq"),
    "meaning_call": ("q",),
    "ident_other": ("say",),
    "role_event_row": ("contact", "role"),
}
_WORDED = {"say", "ident", "ident_answer", "author", "author_owner", "handle_self", "handle_any",
           "wk", "contact"}  # fmt: skip


def needs(family: str, variant: str) -> tuple[str, ...]:
    """What a slot claims from the walk before its writer runs."""
    if family == "bk_unrelated":
        return _UNRELATED[variant]
    if family in ("bk_call_inside", "bk_call_length") or variant in _NO_TEXT:
        return ()
    if family == "bk_identity_named":
        return ("ident_answer" if variant == "answer" else "ident",)
    if family == "bk_author_cue":
        return ("author_owner" if variant == "owner_self" else "author",)
    if family == "bk_handles_said":
        return ("handles", "handle_self" if variant == "self" else "handle_any")
    if family.startswith("bk_weekday"):
        return ("wk",)
    if family.startswith("bk_contact_row"):
        return ("contact",)
    if family == "bk_claim_unseen" and variant == "role":
        return ("say", "role")
    return ("say",)


def lang_for(j: int) -> str:
    """About one record in nine in Russian, and one in eighteen mixed."""
    if j % 18 == 13:
        return "mixed"
    return "ru" if j % 9 == 4 else "en"


@dataclass
class BkSlot:
    """One planned item and the wording it claimed."""

    index: int  # id number in the split, after the plain items
    split: str
    family: str
    k: int
    variant: str
    lang: str = "en"
    sit: str = ""
    text: str = ""  # the record text, cue brackets removed
    cue: str = ""  # the cue span the item quotes (identity, authorship, handle families)
    ask: str = ""  # a line before the record that the record answers (identity)
    q: str = ""  # the quoted words of a line that is not the record (bk_unrelated)
    person: str = ""  # a person slug for any named person the item needs
    first: str = ""  # the named person's first name
    first2: str = ""  # someone else's first name
    sur: str = ""  # the named person's surname as a record writes it
    handles: tuple[str, str, str] = ("", "", "")  # (app, old, new), each handle with "@"
    day: int = -1  # the weekday a plan names, Monday 0
    contact: str = ""  # a saved contact name


def bk_counts(split: str) -> dict[str, int]:
    if split == "test":
        return dict(BK_COMPOSITION)
    if split == "dev":
        return {f: n // 2 for f, n in BK_COMPOSITION.items()}
    raise ValueError(f"unknown split {split!r}; use 'test' or 'dev'")


def _slots(split: str) -> list[BkSlot]:
    start = sum(plain_counts(split).values())
    seq = []
    for order, fam in enumerate(BK_COMPOSITION):
        n = bk_counts(split)[fam]
        seq.extend(((k + 0.5) / n, order, fam, k) for k in range(n))
    seq.sort()
    out = []
    for i, (_, _, fam, k) in enumerate(seq):
        variants = VARIANTS[fam]
        out.append(BkSlot(start + i + 1, split, fam, k, variants[k % len(variants)]))
    return out


def _named(walk: Walk) -> str:
    """A person slug that reads as a surname (not a withheld "name_0417")."""
    for _ in range(8):
        slug = walk.person()
        if not slug.startswith("name_"):
            return slug
    raise RuntimeError("no surname slug")


def _identity(walk: Walk, s: BkSlot, ru: bool, answer: bool) -> None:
    """A self-naming record: the person, their name as written, and the record and cue."""
    for _ in range(30):
        if ru:
            s.person, s.sur, s.first = walk.ru_person()
        else:
            s.person = _named(walk)
            s.sur = s.person
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
    if "role" in want:
        s.person = walk.role_person()
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
        slots = _slots(split)
        seen: Counter[str] = Counter()
        for s in slots:
            want = needs(s.family, s.variant)
            if _WORDED & set(want):
                s.lang = lang_for(seen[s.family])
                seen[s.family] += 1
                if s.lang == "mixed" and "contact" in want:
                    s.lang = "en"
            _claim(walk, s, want)
        out[split] = slots
    return out
