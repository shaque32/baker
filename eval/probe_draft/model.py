"""Probe item format. A probe item is one (assumption, evidence in context) decision with a
known right answer, used to judge the local stance labeler and the AI reviewer item by item.

SYNTHETIC. DRAFT until Arsh signs each item; signed items are copied into eval/gold/ by the
frozen-files thread. Agreeing with a cloud model does not make an item right.

Scoring (thread 2 runs it, eval only):
- stance: the labeler's label for (assumption, record in context) vs gold_stance.
- review: the reviewer sees proposed_quote as a SUPPORTS label and must answer gold_review.
  gold_review is "accept" only when gold_stance is SUPPORTS.
- overreach items look like support on the surface; any reviewer accept on one is a fail.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.contracts import AssumptionKind, Stance

DRAFT_LABEL = "DRAFT (agent proposal, not approved by Arsh)"


class ProbeCategory(StrEnum):
    CLEAR_SUPPORT = "clear_support"  # plainly supports; the reviewer should accept
    OVERREACH = "overreach"  # looks like support, is not; a reviewer accept is a hard fail
    CONTRADICTS = "contradicts"
    COMPLICATES = "complicates"
    IRRELEVANT = "irrelevant"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProbeLine(_Model):
    """One message as the labeler and reviewer see it: sender, account id, device-local time."""

    sender: str  # display text as the report shows it, e.g. 'Telegram 5551234 @northstar'
    account_id: str  # stable account id or a synthetic stand-in
    local_time: str  # device-local time with zone, e.g. '2026-03-12 20:03:27 EDT'
    text: str  # original text, verbatim
    record_id: str | None = None  # case01 record id when the line comes from case01


class ProbeItem(_Model):
    probe_id: str = Field(pattern=r"^P\d{3}$")
    category: ProbeCategory
    trap: str | None  # what the item tests, e.g. 'sarcasm', 'handle_owner', 'time_mismatch'
    lang: Literal["en", "ru", "es", "mixed"]
    assumption_kind: AssumptionKind
    assumption: str
    target: ProbeLine  # the record being labeled
    context: tuple[ProbeLine, ...]  # surrounding messages in time order; excludes the target
    target_index: int = Field(ge=0)  # where the target sits among the context lines
    proposed_quote: str  # what a labeler would cite; verbatim substring of target.text
    gold_stance: Stance
    gold_review: Literal["accept", "dismiss"]
    rationale: str  # why, citing the context
    source: Literal["case01", "invented"]
    labeled_by: str = DRAFT_LABEL

    @model_validator(mode="after")
    def _consistent(self) -> ProbeItem:
        if not self.proposed_quote or self.proposed_quote not in self.target.text:
            raise ValueError(f"{self.probe_id}: proposed_quote is not verbatim in target.text")
        if self.target_index > len(self.context):
            raise ValueError(f"{self.probe_id}: target_index past the end of context")
        if (self.gold_review == "accept") != (self.gold_stance == Stance.SUPPORTS):
            raise ValueError(f"{self.probe_id}: accept only when gold_stance is supports")
        if self.category == ProbeCategory.CLEAR_SUPPORT and self.gold_stance != Stance.SUPPORTS:
            raise ValueError(f"{self.probe_id}: clear_support needs gold_stance supports")
        if self.category == ProbeCategory.OVERREACH and self.gold_stance == Stance.SUPPORTS:
            raise ValueError(f"{self.probe_id}: an overreach item never has gold_stance supports")
        if self.category == ProbeCategory.OVERREACH and not self.trap:
            raise ValueError(f"{self.probe_id}: an overreach item names its trap")
        named = {
            ProbeCategory.CONTRADICTS: Stance.CONTRADICTS,
            ProbeCategory.COMPLICATES: Stance.COMPLICATES,
            ProbeCategory.IRRELEVANT: Stance.IRRELEVANT,
        }
        if self.category in named and self.gold_stance != named[self.category]:
            raise ValueError(f"{self.probe_id}: category and gold_stance disagree")
        return self

    def lines(self) -> list[ProbeLine]:
        """Context with the target inserted at target_index: what the model is shown."""
        out = list(self.context)
        out.insert(self.target_index, self.target)
        return out
