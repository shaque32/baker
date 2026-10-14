"""Training items in Baker's own wording (guide rules 25 to 29): the bk_* families.

Item j of a Baker run (0-based) fills slot j % 28 of CYCLE and is the k-th item of that slot's
family, k counting the family's earlier slots; its random stream is item_rng(GENERATOR, seed, j)
alone, so the same run is byte-identical and a shorter run is a prefix of a longer one.
bk_unrelated has two slots in the cycle and every other family one: 7000 items give 250 per
family and 500 for bk_unrelated. The meaning, role and event templates carry the claim's own
text (rule 29), and every item names its people (baker_cast.py). A writer that cannot finish a
draft (a rare clash, such as quoted words that also stand on a context line) raises, and the
item is drawn again from the same stream.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from eval.stancedata.chat import item_rng
from eval.stancedata.model import GenItem
from eval.train.baker_fam_acts import claim_open, event_is_record
from eval.train.baker_fam_contact import contact_row, contact_row_differs
from eval.train.baker_fam_count import (
    count_one,
    no_contact_inside,
    other_phone,
    outside_window,
    zone_edge,
)
from eval.train.baker_fam_days import weekday_next, weekday_open, weekday_wrong
from eval.train.baker_fam_denied import claim_denied
from eval.train.baker_fam_meaning import meaning_other, meaning_said
from eval.train.baker_fam_people import account_silent, author_cue, handles_said, identity_named
from eval.train.baker_fam_sender import party_unshown, sender_other, sender_shown
from eval.train.baker_fam_time import call_inside, call_length, time_inside, time_outside
from eval.train.baker_fam_unrelated import unrelated
from eval.train.baker_kit import Draft, finish

GENERATOR = "eval.train.baker 1.0.0"
ATTEMPTS = 40

Writer = Callable[[random.Random, int], Draft]
WRITERS: dict[str, Writer] = {
    "bk_sender_shown": sender_shown,
    "bk_sender_other": sender_other,
    "bk_party_unshown": party_unshown,
    "bk_time_inside": time_inside,
    "bk_call_inside": call_inside,
    "bk_time_outside": time_outside,
    "bk_zone_edge": zone_edge,
    "bk_call_length": call_length,
    "bk_identity_named": identity_named,
    "bk_account_silent": account_silent,
    "bk_unrelated": unrelated,
    "bk_handles_said": handles_said,
    "bk_contact_row": contact_row,
    "bk_contact_row_differs": contact_row_differs,
    "bk_count_one": count_one,
    "bk_no_contact_inside": no_contact_inside,
    "bk_other_phone": other_phone,
    "bk_outside_window": outside_window,
    "bk_weekday_next": weekday_next,
    "bk_weekday_open": weekday_open,
    "bk_weekday_wrong": weekday_wrong,
    "bk_author_cue": author_cue,
    "bk_claim_open": claim_open,
    "bk_meaning_said": meaning_said,
    "bk_meaning_other": meaning_other,
    "bk_event_is_record": event_is_record,
    "bk_claim_denied": claim_denied,
}
CYCLE: tuple[str, ...] = (*WRITERS, "bk_unrelated")  # bk_unrelated at slots 10 and 27


def slot(j: int) -> tuple[str, int]:
    """(family, k) of the j-th Baker item of a run."""
    lap, pos = divmod(j, len(CYCLE))
    family = CYCLE[pos]
    per_lap = CYCLE.count(family)
    return family, lap * per_lap + CYCLE[:pos].count(family)


def build(j: int, seed: int, probe_id: str) -> tuple[GenItem, Draft, int]:
    """The j-th Baker item, its draft and the number of draws it took beyond the first."""
    family, k = slot(j)
    rng = item_rng(GENERATOR, seed, j)
    for tries in range(ATTEMPTS):
        try:
            d = WRITERS[family](rng, k)
            return finish(d, probe_id, GENERATOR, rng), d, tries
        except (ValueError, RuntimeError):
            continue
    raise RuntimeError(f"{family} item {k}: no item in {ATTEMPTS} draws")


def generate_with_drafts(
    n_baker: int, seed: int, first_id: int
) -> list[tuple[GenItem, Draft, int]]:
    """n_baker items with ids from T<first_id>, with their drafts (for tests) and redraws."""
    return [build(j, seed, f"T{first_id + j:06d}") for j in range(n_baker)]


def generate(n_baker: int, seed: int, first_id: int) -> list[GenItem]:
    return [it for it, _, _ in generate_with_drafts(n_baker, seed, first_id)]
