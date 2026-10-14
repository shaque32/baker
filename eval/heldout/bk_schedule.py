"""The fixed plan of the Baker-wording items: family, variant, language and claimed wording.

Both splits put these items after the plain ones, ids continuing. The test split has the
composition below and the dev split half of it. Each slot then claims its wording from the
walk in schedule order, test split first (bk_wording), so no record text repeats in the
held-out set and the two splits share none.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    "bk_claim_open": 24,
    "bk_meaning_said": 24,
    "bk_meaning_other": 24,
    "bk_event_is_record": 24,
    "bk_claim_denied": 24,
    "bk_unrelated": 48,
}

# Variants cycle within a family; every cycle length divides 12, so the dev split keeps the
# test split's shape.
VARIANTS: dict[str, tuple[str, ...]] = {
    "bk_sender_shown": ("acct_third", "acct_owner", "owner_person", "linked", "cross", "acct_both"),
    "bk_sender_other": ("named_owner", "named_third", "named_linked", "named_cross"),
    "bk_party_unshown": ("sender", "sender_named", "time_msg", "time_call", "nc_msg", "count_msg"),
    "bk_time_inside": ("anyone", "acct", "owner_person", "linked", "about", "cross_zone"),
    "bk_call_inside": ("out_person", "in_linked", "cross_out", "cross_in"),
    "bk_time_outside": ("msg_acct", "msg_anyone", "msg_person", "msg_linked", "call_person",
                        "call_linked"),
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
    "bk_claim_open": ("meaning", "role_from", "event_from", "meaning_q", "role_to", "event_to"),
    "bk_meaning_said": ("linked", "owner"),
    "bk_meaning_other": ("linked", "owner"),
    "bk_event_is_record": ("msg_in", "msg_out", "call_in", "msg_cross", "msg_acct", "call_out"),
    "bk_claim_denied": ("event_linked", "event_owner", "role_linked", "role_owner"),
    "bk_unrelated": ("sender_same", "sender_att", "time_msg", "time_call3", "count_third",
                     "nc_call3", "same_acct", "contact_other", "weekday_msg", "meaning_call",
                     "ident_other", "role_event_row"),
}  # fmt: skip

_NO_TEXT = {"time_call", "call_person", "call_linked", "call_phone", "call_named", "call",
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
    "meaning_call": ("meaning_bare",),
    "ident_other": ("say",),
    "role_event_row": ("contact", "claim_bare"),
}
WORDED = {"say", "ident", "ident_answer", "author", "author_owner", "handle_self", "handle_any",
           "wk", "contact", "meaning_open"}  # fmt: skip
# The record lines each claim variant writes (bk_acts): "" leaves the record to the writer.
ACT_FORMS = {"role_from": ("from",), "role_to": ("to",), "event_from": ("plan", "did"),
              "event_to": ("ask", "tell")}  # fmt: skip


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
    if family == "bk_claim_open":
        if variant.startswith("meaning"):
            return ("meaning_open",)
        return ("role",) if variant.startswith("role") else ("act",)
    if family in ("bk_meaning_said", "bk_meaning_other"):
        return ("meaning",)
    if family == "bk_event_is_record":
        return () if variant.startswith("call") else ("say",)
    if family == "bk_claim_denied":
        return ("role",) if variant.startswith("role") else ("act",)
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
    person2: str = ""  # another person a claim names (person:<slug>), never on any line
    words: str = ""  # the quoted words of a meaning claim
    meaning: str = ""  # the meaning the claim gives them
    plain: str = ""  # the plain thing they name in the chat
    usage: str = ""  # a line that uses the words
    act: str = ""  # the act or role a claim states (bk_acts key)
    vals: dict[str, str] = field(default_factory=dict)  # its slot values (z, spot, thing, hh)


def bk_counts(split: str) -> dict[str, int]:
    if split == "test":
        return dict(BK_COMPOSITION)
    if split == "dev":
        return {f: n // 2 for f, n in BK_COMPOSITION.items()}
    raise ValueError(f"unknown split {split!r}; use 'test' or 'dev'")


def slots(split: str) -> list[BkSlot]:
    """The split's planned items in id order, before they claim their wording."""
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
