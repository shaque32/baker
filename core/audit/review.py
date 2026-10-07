"""EvidenceReviewer: a second local-model pass over one verified supporting item.

The prompt is human-owned (core/audit/prompts/reviewer.md). Rules this module enforces:
- It reviews only verified SUPPORTS items still OPEN. Anything else is a caller bug and raises:
  dismissing a contradicting item, or overwriting a human decision, would be unsafe.
- The reviewer sees the assumption, the verified quote and the context. It never sees the
  labeler's rationale; the prompt is built from those three inputs only.
- It returns AI_ACCEPTED or DISMISSED, never ACCEPTED or CONFIRMED. An AI acceptance shows
  as "AI-reviewed"; a human decision always overrides it.
- It fails closed: a model error, malformed output or an empty reason is a dismissal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from core.audit._llm_json import (
    PROMPTS_DIR,
    BadModelOutput,
    JsonModel,
    call_model,
    fill_prompt,
    load_prompt,
    model_run_id,
    prompt_version,
    required_placeholders,
)
from core.contracts import Assumption, EvidenceItem, EvidenceStatus, Stance

PROMPT_FILE = "reviewer.md"
PLACEHOLDERS = frozenset({"assumption", "quote", "context"})
REVIEWER_ID = "ai_reviewer"
MAX_REASON_CHARS = 1000

REVIEW_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["accept", "dismiss"]},
        "reason": {"type": "string", "minLength": 1, "maxLength": MAX_REASON_CHARS},
    },
    "required": ["decision", "reason"],
    "additionalProperties": False,
}


class NotReviewableError(ValueError):
    """The item is not a verified, open, supporting item. Nothing was reviewed."""


class _ReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "dismiss"]
    reason: StrictStr = Field(min_length=1, max_length=MAX_REASON_CHARS)


@dataclass(frozen=True)
class ReviewOutcome:
    """One review, kept or failed. `error` is set when the dismissal came from failing closed
    rather than from the model deciding to dismiss. Maps onto the v0.2 ReviewDecision."""

    evidence_id: str
    status: EvidenceStatus  # AI_ACCEPTED or DISMISSED only
    reason: str
    reviewer: str
    model_run_id: str | None
    prompt_version: str
    raw_output: str | None
    error: str | None


def check_reviewable(item: EvidenceItem) -> None:
    if item.stance != Stance.SUPPORTS:
        raise NotReviewableError(f"{item.id}: reviewer only reviews supports, got {item.stance}")
    if item.status != EvidenceStatus.OPEN:
        raise NotReviewableError(f"{item.id}: status is {item.status}, not open")
    if item.quote_verified is not True or not item.quote.strip():
        raise NotReviewableError(f"{item.id}: quote is not verified")


class LocalEvidenceReviewer:
    """Implements core.contracts.EvidenceReviewer on a local JsonModel."""

    def __init__(
        self,
        model: JsonModel,
        *,
        template: str | None = None,
        prompts_dir: Path = PROMPTS_DIR,
    ) -> None:
        self.model = model
        self.template = template if template is not None else load_prompt(PROMPT_FILE, prompts_dir)
        missing = PLACEHOLDERS - required_placeholders(self.template)
        if missing:
            raise ValueError(f"reviewer prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)

    def build_prompt(self, assumption: Assumption, item: EvidenceItem, context: str) -> str:
        # item.rationale is deliberately not an input: the reviewer judges the quote cold.
        return fill_prompt(
            self.template,
            {"assumption": assumption.text, "quote": item.quote, "context": context},
        )

    def review_with_reason(
        self, assumption: Assumption, item: EvidenceItem, context: str
    ) -> ReviewOutcome:
        check_reviewable(item)
        if item.assumption_id != assumption.id:
            raise NotReviewableError(f"{item.id} belongs to {item.assumption_id}")
        run_id = model_run_id(self.model)
        raw: str | None = None
        try:
            if run_id is None:
                raise BadModelOutput("model has no run id", None)
            prompt = self.build_prompt(assumption, item, context)
            raw, obj = call_model(self.model, prompt, REVIEW_SCHEMA)
            try:
                out = _ReviewOut.model_validate(obj)
            except ValidationError as e:
                raise BadModelOutput(f"wrong shape: {e.errors(include_url=False)}", raw) from None
            if not out.reason.strip():
                raise BadModelOutput("empty reason", raw)
        except BadModelOutput as e:
            return ReviewOutcome(
                evidence_id=item.id,
                status=EvidenceStatus.DISMISSED,
                reason=f"Dismissed because the reviewer output was unusable ({e.reason}).",
                reviewer=REVIEWER_ID,
                model_run_id=run_id,
                prompt_version=self.prompt_version,
                raw_output=raw or e.raw,
                error=e.reason,
            )
        accepted = out.decision == "accept"
        status = EvidenceStatus.AI_ACCEPTED if accepted else EvidenceStatus.DISMISSED
        return ReviewOutcome(
            evidence_id=item.id,
            status=status,
            reason=out.reason.strip(),
            reviewer=REVIEWER_ID,
            model_run_id=run_id,
            prompt_version=self.prompt_version,
            raw_output=raw,
            error=None,
        )

    def review(self, assumption: Assumption, item: EvidenceItem, context: str) -> EvidenceStatus:
        return self.review_with_reason(assumption, item, context).status
