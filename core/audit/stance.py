"""StanceLabeler: one model label per (assumption, evidence candidate). Never a verdict.

The prompt is human-owned (core/audit/prompts/stance.md). This module only fills it, asks the
local model for JSON constrained to STANCE_SCHEMA, and validates the result. It fails closed:
output that is not exactly the expected object is dropped, with the raw text kept for the log.

The model never supplies ids. assumption_id and record_id come from the inputs, and
model_run_id from the model. The quote is still untrusted here; core/audit/quotes.py verifies
it verbatim before the label can become an EvidenceItem.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
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
)
from core.audit._local_model import LocalModel, open_run
from core.audit.quotes import find_quote
from core.contracts import (
    Assumption,
    EvidenceCandidate,
    ModelCall,
    ModelRun,
    Stance,
    StanceLabel,
)

PROMPT_FILE = "stance.md"
PLACEHOLDERS = frozenset({"assumption", "record", "context"})
MAX_QUOTE_CHARS = 2000
MAX_RATIONALE_CHARS = 1000

STANCE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "stance": {"type": "string", "enum": [s.value for s in Stance]},
        "quote": {"type": "string", "maxLength": MAX_QUOTE_CHARS},
        "rationale": {"type": "string", "minLength": 1, "maxLength": MAX_RATIONALE_CHARS},
    },
    "required": ["stance", "quote", "rationale"],
    "additionalProperties": False,
}

Renderer = Callable[[EvidenceCandidate], str]

# Templates about one message, named by its quoted text. The deterministic sender and time
# checks pick that message the same way (verbatim, word-aligned).
ONE_MESSAGE_TEMPLATES = frozenset({"sender", "record_time"})
NOT_THE_MESSAGE = (
    "Recorded as complicates, not contradicts: this record is not the message the assumption "
    "names, so it cannot rule that message out. Model's rationale: "
)


def subject_stance(assumption: Assumption, record_text: str, stance: Stance) -> Stance:
    """The stance to store for a label on one record.

    "The message X was sent by Y" or "... was sent on Z" can only be contradicted by the
    message X itself: another message with another sender or time says nothing against it.
    A model's "contradicts" on any other record is kept in front of the expert as
    "complicates", so it still blocks SUPPORTED but never makes the claim CONTRADICTED alone.
    """
    quoted = assumption.params.quoted_text
    if (
        stance is Stance.CONTRADICTS
        and assumption.template_id in ONE_MESSAGE_TEMPLATES
        and quoted
        and find_quote(quoted, record_text) is None
    ):
        return Stance.COMPLICATES
    return stance


def default_record(candidate: EvidenceCandidate) -> str:
    return candidate.text


def default_context(candidate: EvidenceCandidate) -> str:
    return "(no surrounding messages provided)"


class _StanceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stance: Literal["supports", "contradicts", "complicates", "irrelevant"]
    quote: StrictStr = Field(max_length=MAX_QUOTE_CHARS)
    rationale: StrictStr = Field(min_length=1, max_length=MAX_RATIONALE_CHARS)


class DroppedStanceLabel(ValueError):
    """Raised by label() when the model output was dropped. `result` has the details."""

    def __init__(self, result: StanceResult) -> None:
        super().__init__(result.dropped_reason)
        self.result = result


@dataclass(frozen=True)
class StanceResult:
    """What happened on one call. Exactly one of label / dropped_reason is set.
    `call` is the recorded ModelCall (prompt and raw output), kept or dropped; None only when
    no call was made. If the quote later fails verification, the pipeline records that.
    """

    assumption_id: str
    record_id: str
    model_run_id: str | None
    prompt_version: str
    label: StanceLabel | None
    dropped_reason: str | None
    call: ModelCall | None

    @property
    def raw_output(self) -> str | None:
        return self.call.raw_output if self.call is not None else None


def validate_stance_output(obj: dict[str, object]) -> _StanceOut:
    try:
        out = _StanceOut.model_validate(obj)
    except ValidationError as e:
        raise BadModelOutput(f"wrong shape: {e.errors(include_url=False)}", None) from None
    if not out.rationale.strip():
        raise BadModelOutput("empty rationale", None)
    if out.stance != Stance.IRRELEVANT and not out.quote.strip():
        raise BadModelOutput(f"stance {out.stance!r} with no quote", None)
    return out


class LocalStanceLabeler:
    """Implements core.contracts.StanceLabeler on a local JsonModel."""

    def __init__(
        self,
        model: JsonModel,
        *,
        template: str | None = None,
        prompts_dir: Path = PROMPTS_DIR,
        render_record: Renderer = default_record,
        render_context: Renderer = default_context,
        recorder: CallRecorder | None = None,
    ) -> None:
        self.model = model
        self.template = template if template is not None else load_prompt(PROMPT_FILE, prompts_dir)
        missing = PLACEHOLDERS - required_placeholders(self.template)
        if missing:
            raise ValueError(f"stance prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)
        self.render_record = render_record
        self.render_context = render_context
        self.recorder = recorder if recorder is not None else CallRecorder()
        self.model_runs: tuple[ModelRun, ...] = ()  # set by create(); the pipeline stores them

    def build_prompt(self, assumption: Assumption, candidate: EvidenceCandidate) -> str:
        return fill_prompt(
            self.template,
            {
                "assumption": assumption.text,
                "record": self.render_record(candidate),
                "context": self.render_context(candidate),
            },
        )

    def try_label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceResult:
        run_id = model_run_id(self.model)
        if run_id is None:
            return self._result(assumption, candidate, None, None, "model has no run id", None)
        prompt = self.build_prompt(assumption, candidate)
        subject = (assumption.id, candidate.record_id)
        try:
            out, call = run_json_call(
                self.model,
                self.recorder,
                run_id,
                subject,
                prompt,
                STANCE_SCHEMA,
                validate_stance_output,
            )
        except BadModelOutput as e:
            return self._result(assumption, candidate, run_id, None, e.reason, e.call)
        label = StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance(out.stance),
            quote=out.quote,
            rationale=out.rationale,
            model_run_id=run_id,
            model_call_id=call.id,
        )
        return self._result(assumption, candidate, run_id, label, None, call)

    def _result(
        self,
        assumption: Assumption,
        candidate: EvidenceCandidate,
        run_id: str | None,
        label: StanceLabel | None,
        dropped_reason: str | None,
        call: ModelCall | None,
    ) -> StanceResult:
        return StanceResult(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            model_run_id=run_id,
            prompt_version=self.prompt_version,
            label=label,
            dropped_reason=dropped_reason,
            call=call,
        )

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        result = self.try_label(assumption, candidate)
        if result.label is None:
            raise DroppedStanceLabel(result)
        return result.label


def create(conn: sqlite3.Connection, *, model: LocalModel | None = None) -> LocalStanceLabeler:
    """The pipeline's stance labeler: the signed prompt, the configured local model, and the
    context thread's renderer, which shows the record's own line (sender, account, device-local
    time) marked '>>' among its neighbours. Raises if the signed prompt or the model config is
    missing; nothing falls back to a draft."""
    from core.audit.context import render_for  # retrieval and context thread

    template = load_prompt(PROMPT_FILE)
    opened = open_run(conn, "stance", template, model=model, schema=STANCE_SCHEMA)
    labeler = LocalStanceLabeler(
        opened.port,
        template=template,
        render_context=lambda c: render_for(conn, c.record_id),
        recorder=opened.recorder,
    )
    labeler.model_runs = (opened.run,)
    return labeler
