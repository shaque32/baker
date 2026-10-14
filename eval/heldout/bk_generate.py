"""The Baker-wording items of the held-out set: one writer per family, run over the fixed plan
(bk_schedule), each item from its own random stream."""

from __future__ import annotations

from collections.abc import Callable
import random

from eval.heldout import ID_PREFIX, SEEDS
from eval.heldout import bk_fam_call as cal
from eval.heldout import bk_fam_contact as con
from eval.heldout import bk_fam_count as cnt
from eval.heldout import bk_fam_ident as ide
from eval.heldout import bk_fam_sender as snd
from eval.heldout import bk_fam_time as tim
from eval.heldout import bk_fam_unrelated as unr
from eval.heldout import bk_fam_weekday as wkd
from eval.heldout.bk_common import BK_GENERATOR, BkDraft, finish
from eval.heldout.bk_schedule import BkSlot, bk_schedule
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
    "bk_author_cue": ide.author,
    "bk_claim_unseen": con.claim,
    "bk_unrelated": unr.unrelated,
}


def bk_drafts(split: str) -> list[tuple[BkSlot, BkDraft]]:
    """Every planned slot of the split with its writer's draft, in id order."""
    out = []
    for slot in bk_schedule()[split]:
        rng = item_rng(BK_GENERATOR, SEEDS[split], slot.index)
        out.append((slot, WRITERS[slot.family](slot, rng)))
    return out


def bk_items(split: str) -> list[GenItem]:
    return [finish(d, f"{ID_PREFIX[split]}{s.index:06d}") for s, d in bk_drafts(split)]
