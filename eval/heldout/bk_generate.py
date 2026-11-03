"""The Baker-wording items of the held-out set: one writer per family, run over the fixed plan
(bk_schedule) and the wording each slot claimed (bk_wording), each item from its own random
stream."""

from __future__ import annotations

import random
from collections.abc import Callable

from eval.heldout import ID_PREFIX, SEEDS
from eval.heldout import bk_fam_call as cal
from eval.heldout import bk_fam_claim as clm
from eval.heldout import bk_fam_contact as con
from eval.heldout import bk_fam_count as cnt
from eval.heldout import bk_fam_ident as ide
from eval.heldout import bk_fam_said as said
from eval.heldout import bk_fam_sender as snd
from eval.heldout import bk_fam_time as tim
from eval.heldout import bk_fam_unrelated as unr
from eval.heldout import bk_fam_weekday as wkd
from eval.heldout.bk_common import BK_GENERATOR, BkDraft, finish
from eval.heldout.bk_naming import name_people, readable
from eval.heldout.bk_schedule import BkSlot
from eval.heldout.bk_wording import bk_schedule
from eval.stancedata.chat import item_rng
from eval.stancedata.model import GenItem

Writer = Callable[[BkSlot, random.Random], BkDraft]

WRITERS: dict[str, Writer] = {
    "bk_sender_shown": snd.shown,
    "bk_sender_other": snd.other,
    "bk_party_unshown": snd.unshown,
    "bk_time_inside": tim.inside,
    "bk_call_inside": cal.inside,
    "bk_time_outside": tim.outside,
    "bk_zone_edge": tim.edge,
    "bk_call_length": cal.length,
    "bk_identity_named": ide.identity,
    "bk_account_silent": ide.silent,
    "bk_handles_said": ide.handles,
    "bk_contact_row": con.row,
    "bk_contact_row_differs": con.row_differs,
    "bk_count_one": cnt.count_one,
    "bk_no_contact_inside": cnt.nc_inside,
    "bk_other_phone": cnt.other_phone,
    "bk_outside_window": cnt.outside_window,
    "bk_weekday_next": wkd.wk_next,
    "bk_weekday_open": wkd.wk_open,
    "bk_weekday_wrong": wkd.wk_wrong,
    "bk_weekday_after": wkd.wk_after,
    "bk_author_cue": ide.author,
    "bk_claim_open": clm.claim_open,
    "bk_meaning_said": said.meaning_explained,
    "bk_meaning_other": said.meaning_explained,
    "bk_event_is_record": said.event_record,
    "bk_claim_denied": clm.claim_denied,
    "bk_unrelated": unr.unrelated,
}


# Each item's random stream is keyed by its place in this block, counted on from the plain
# item count of eval.heldout 1.3.0 (1,150 test, 575 dev), never by its id: plain families
# added later (1.4.0 added three) move the ids but leave these items as they were.
STREAM_BASE = {"test": 1150, "dev": 575}


def bk_drafts(split: str) -> list[tuple[BkSlot, BkDraft, dict[str, str]]]:
    """Every planned slot of the split with its writer's draft and the names its people read
    by, in id order; the draft's rationale already reads by those names."""
    out = []
    planned = bk_schedule()[split]
    first = planned[0].index if planned else 1
    for slot in planned:
        stream = STREAM_BASE[split] + 1 + (slot.index - first)
        rng = item_rng(BK_GENERATOR, SEEDS[split], stream)
        draft = WRITERS[slot.family](slot, rng)
        names = name_people(rng, slot, draft)
        draft.rationale = readable(draft.rationale, names)
        out.append((slot, draft, names))
    return out


def bk_items(split: str) -> list[GenItem]:
    return [finish(d, f"{ID_PREFIX[split]}{s.index:06d}", n) for s, d, n in bk_drafts(split)]
