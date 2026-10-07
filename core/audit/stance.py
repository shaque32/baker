"""StanceLabeler: one model label per (assumption, evidence candidate). Never a verdict.

The prompt is human-owned (core/audit/prompts/stance.md). This module only fills it, asks the
local model for JSON constrained to STANCE_SCHEMA, and validates the result. It fails closed:
output that is not exactly the expected object is dropped, with the raw text kept for the log.

The model never supplies ids. assumption_id and record_id come from the inputs, and
model_run_id from the model. The quote is still untrusted here; core/audit/quotes.py verifies
it verbatim before the label can become an EvidenceItem.
"""

from __future__ import annotations

from collections.abc import Callable
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
from core.contracts import Assumption, EvidenceCandidate, Stance, StanceLabel

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
    The pipeline stores raw_output for every call, kept or dropped."""

    assumption_id: str
    record_id: str
    model_run_id: str | None
    prompt_version: str
    label: StanceLabel | None
    dropped_reason: str | None
    raw_output: str | None


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
    ) -> None:
        self.model = model
        self.template = template if template is not None else load_prompt(PROMPT_FILE, prompts_dir)
        missing = PLACEHOLDERS - required_placeholders(self.template)
        if missing:
            raise ValueError(f"stance prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)
        self.render_record = render_record
        self.render_context = render_context

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
        raw: str | None = None
        try:
            if run_id is None:
                raise BadModelOutput("model has no run id", None)
            prompt = self.build_prompt(assumption, candidate)
            raw, obj = call_model(self.model, prompt, STANCE_SCHEMA)
            out = validate_stance_output(obj)
        except BadModelOutput as e:
            return self._result(assumption, candidate, run_id, None, e.reason, raw or e.raw)
        label = StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance(out.stance),
            quote=out.quote,
            rationale=out.rationale,
            model_run_id=run_id,
        )
        return self._result(assumption, candidate, run_id, label, None, raw)

    def _result(
        self,
        assumption: Assumption,
        candidate: EvidenceCandidate,
        run_id: str | None,
        label: StanceLabel | None,
        dropped_reason: str | None,
        raw: str | None,
    ) -> StanceResult:
        return StanceResult(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            model_run_id=run_id,
            prompt_version=self.prompt_version,
            label=label,
            dropped_reason=dropped_reason,
            raw_output=raw,
        )

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        result = self.try_label(assumption, candidate)
        if result.label is None:
            raise DroppedStanceLabel(result)
        return result.label
