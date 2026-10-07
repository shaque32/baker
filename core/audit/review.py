"""EvidenceReviewer: a second local-model pass over one verified supporting item.

The prompt is human-owned (core/audit/prompts/reviewer.md). Rules this module enforces:
- It reviews only verified SUPPORTS items that are open and have never been reviewed.
  Anything else is a caller bug and raises: dismissing a contradicting item, or overwriting
  (or re-doing after an undo) a human decision, would be unsafe.
- The reviewer sees the assumption, the verified quote and the context. It never sees the
  labeler's rationale; the prompt is built from those three inputs only.
- It returns a ReviewDecision with status AI_ACCEPTED or DISMISSED, never ACCEPTED or
  CONFIRMED. An AI acceptance shows as "AI-reviewed"; a human decision always overrides it.
- It fails closed: a model error, malformed output, an empty reason or an empty context is a
  DISMISSED decision whose reason says why.
- It never accepts a quote that needs a human reader (any letter outside the Latin script).
  Such an item is refused and stays open for an expert, so a machine reading of Russian never
  raises a claim to "supported" on its own.

Every model call, kept or failed, is recorded as a ModelCall (see `recorder.calls`).
`insert_review` and `review_count` store and read decisions in `evidence_reviews`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from core.audit._llm_json import (
    PROMPTS_DIR,
    BadModelOutput,
    CallRecorder,
    JsonModel,
    fill_prompt,
    load_prompt,
    model_run_id,
    prompt_version,
    required_placeholders,
    run_json_call,
    utc_now,
)
from core.audit.translation import needs_human_reader
from core.contracts import (
    Assumption,
    EvidenceItem,
    EvidenceStatus,
    ReviewDecision,
    ReviewerKind,
    Stance,
    review_id,
)

PROMPT_FILE = "reviewer.md"
PLACEHOLDERS = frozenset({"assumption", "quote", "context"})
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
    """The item must not get an AI review. Nothing was reviewed; it stays as it was."""


class NeedsHumanReaderError(NotReviewableError):
    """The quote is not in English. The item stays open for an expert who reads the language."""


class _ReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "dismiss"]
    reason: StrictStr = Field(min_length=1, max_length=MAX_REASON_CHARS)


def _validate(obj: dict[str, object]) -> _ReviewOut:
    try:
        out = _ReviewOut.model_validate(obj)
    except ValidationError as e:
        raise BadModelOutput(f"wrong shape: {e.errors(include_url=False)}", None) from None
    if not out.reason.strip():
        raise BadModelOutput("empty reason", None)
    return out


def check_reviewable(item: EvidenceItem, prior_reviews: int = 0) -> None:
    if item.stance != Stance.SUPPORTS:
        raise NotReviewableError(f"{item.id}: reviewer only reviews supports, got {item.stance}")
    if item.status != EvidenceStatus.OPEN:
        raise NotReviewableError(f"{item.id}: status is {item.status}, not open")
    if prior_reviews:
        raise NotReviewableError(f"{item.id}: already reviewed ({prior_reviews} decisions)")
    if item.quote_verified is not True or not item.quote.strip():
        raise NotReviewableError(f"{item.id}: quote is not verified")
    if needs_human_reader(item.quote):
        raise NeedsHumanReaderError(f"{item.id}: quote needs a human reader")


def is_reviewable(item: EvidenceItem, prior_reviews: int = 0) -> bool:
    """For the pipeline: call review() only where this is True. Other items stay as they are."""
    try:
        check_reviewable(item, prior_reviews)
    except NotReviewableError:
        return False
    return True


class LocalEvidenceReviewer:
    """Implements core.contracts.EvidenceReviewer on a local JsonModel.

    `model_name` names the model file in the reviewer field ('ai:<model_name>').
    `prior_reviews(evidence_id)` returns how many decisions the item already has; in the
    pipeline pass `lambda eid: review_count(conn, eid)`.
    """

    def __init__(
        self,
        model: JsonModel,
        *,
        model_name: str,
        template: str | None = None,
        prompts_dir: Path = PROMPTS_DIR,
        recorder: CallRecorder | None = None,
        prior_reviews: Callable[[str], int] = lambda _evidence_id: 0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name is required")
        self.model = model
        self.reviewer = f"ai:{model_name.strip()}"
        self.template = template if template is not None else load_prompt(PROMPT_FILE, prompts_dir)
        missing = PLACEHOLDERS - required_placeholders(self.template)
        if missing:
            raise ValueError(f"reviewer prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)
        self.recorder = recorder if recorder is not None else CallRecorder(clock=clock)
        self.prior_reviews = prior_reviews
        self.clock = clock

    def build_prompt(self, assumption: Assumption, item: EvidenceItem, context: str) -> str:
        # item.rationale is deliberately not an input: the reviewer judges the quote cold.
        return fill_prompt(
            self.template,
            {"assumption": assumption.text, "quote": item.quote, "context": context},
        )

    def review(self, assumption: Assumption, item: EvidenceItem, context: str) -> ReviewDecision:
        check_reviewable(item, self.prior_reviews(item.id))
        if item.assumption_id != assumption.id:
            raise NotReviewableError(f"{item.id} belongs to {item.assumption_id}")
        run_id = model_run_id(self.model)
        if run_id is None:
            # An AI decision must name its model run; with none, nothing is decided.
            raise NotReviewableError(f"{item.id}: the reviewer model has no run id")

        if not context.strip():
            return self._decision(
                item, run_id, None, EvidenceStatus.DISMISSED, _failed("no context")
            )
        prompt = self.build_prompt(assumption, item, context)
        try:
            out, call = run_json_call(
                self.model, self.recorder, run_id, (item.id,), prompt, REVIEW_SCHEMA, _validate
            )
        except BadModelOutput as e:
            call_id = e.call.id if e.call is not None else None
            return self._decision(
                item, run_id, call_id, EvidenceStatus.DISMISSED, _failed(e.reason)
            )
        accepted = out.decision == "accept"
        status = EvidenceStatus.AI_ACCEPTED if accepted else EvidenceStatus.DISMISSED
        return self._decision(item, run_id, call.id, status, out.reason.strip())

    def _decision(
        self,
        item: EvidenceItem,
        run_id: str,
        call_id: str | None,
        status: EvidenceStatus,
        reason: str,
    ) -> ReviewDecision:
        seq = self.prior_reviews(item.id) + 1
        return ReviewDecision(
            id=review_id(item.id, seq),
            evidence_id=item.id,
            seq=seq,
            reviewer_kind=ReviewerKind.AI,
            reviewer=self.reviewer,
            status=status,
            reason=reason,
            model_run_id=run_id,
            model_call_id=call_id,
            decided_at_utc=self.clock(),
        )


def _failed(why: str) -> str:
    return f"Dismissed because the AI review could not be completed ({why})."


# ---------------------------------------------------------------- storage


def review_count(conn: sqlite3.Connection, evidence_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM evidence_reviews WHERE evidence_id = ?", (evidence_id,)
    ).fetchone()
    return int(row[0])


def insert_review(conn: sqlite3.Connection, d: ReviewDecision) -> None:
    """Append one decision. evidence_reviews is append-only; a human override is a new row."""
    conn.execute(
        "INSERT INTO evidence_reviews (id, evidence_id, seq, reviewer_kind, reviewer, status,"
        " reason, model_run_id, model_call_id, decided_at_utc)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            d.id,
            d.evidence_id,
            d.seq,
            d.reviewer_kind.value,
            d.reviewer,
            d.status.value,
            d.reason,
            d.model_run_id,
            d.model_call_id,
            d.decided_at_utc.isoformat().replace("+00:00", "Z"),
        ),
    )
