"""StanceLabeler: one model label per (assumption, evidence candidate). Never a verdict.

The prompt is human-owned (core/audit/prompts/stance.md; a cloud model reads its own signed
stance_cloud.md). This module only fills it, asks the model for JSON constrained to
STANCE_SCHEMA, and validates the result. It fails closed:
output that is not exactly the expected object is dropped, with the raw text kept for the log.

The model never supplies ids. assumption_id and record_id come from the inputs, and
model_run_id from the model. The quote is still untrusted here; core/audit/quotes.py verifies
it verbatim before the label can become an EvidenceItem.

Prompt v1.1 (signed 2026-10-14) shows the claim for the meaning, role and event templates, which
say "the claim", and "(not needed for this assumption)" for the others. The cloud prompt is v1.2
(signed 2026-10-15): v1.1 with the told-frame sentences in "contradicts". Arsh chose on
2026-10-19 to give it to the cloud model only ("Opus only", "Audit our model scoring"), since on
the signed probe set it took the local 14B's contradicts precision from 58% to 50%. The model
reads the case's names, never Baker's ids: the assumption through core/audit/readable.py and the
context through core/audit/context.py with the same CaseNames. The stored Assumption.text keeps
the ids.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

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
from core.audit._local_model import (
    CloudPort,
    LocalModel,
    SentLog,
    open_run,
)
from core.audit.quotes import find_quote
from core.contracts import (
    Assumption,
    EvidenceCandidate,
    ModelCall,
    ModelRun,
    Stance,
    StanceLabel,
)

if TYPE_CHECKING:
    from core.llm.cloud import CloudConfig

PROMPT_FILE = "stance.md"  # the local model's prompt
CLOUD_PROMPT_FILE = "stance_cloud.md"  # a cloud model's prompt (core/llm/cloud.py)
PLACEHOLDERS = frozenset({"assumption", "record", "context", "claim"})
# Templates whose wording says "the claim"; the prompt shows the claim's text for these only.
CLAIM_TEMPLATES = frozenset({"meaning", "role", "event"})
NO_CLAIM = "(not needed for this assumption)"  # as eval/probe/prompts.py shows it
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
AssumptionRenderer = Callable[[Assumption], str]
ClaimText = Callable[[str], str | None]  # claim id -> the claim's text, None if unknown

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


def default_assumption(assumption: Assumption) -> str:
    return assumption.text


def no_claim_text(claim_id: str) -> str | None:
    return None


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
        render_assumption: AssumptionRenderer = default_assumption,
        claim_text: ClaimText = no_claim_text,
        recorder: CallRecorder | None = None,
    ) -> None:
        self.model = model
        self.template = template if template is not None else load_prompt(PROMPT_FILE, prompts_dir)
        missing = PLACEHOLDERS - required_placeholders(self.template)
        if missing:
            raise ValueError(f"stance prompt lacks placeholders: {sorted(missing)}")
        # fill_prompt leaves a slot it has no value for in place, so a prompt with a slot this
        # labeler does not fill is refused, never sent.
        unfilled = required_placeholders(self.template) - PLACEHOLDERS
        if unfilled:
            raise ValueError(f"stance prompt has placeholders the labeler does not fill: "
                             f"{sorted(unfilled)}")  # fmt: skip
        self.prompt_version = prompt_version(self.template)
        self.render_record = render_record
        self.render_context = render_context
        self.render_assumption = render_assumption
        self.claim_text = claim_text
        self.recorder = recorder if recorder is not None else CallRecorder()
        self.model_runs: tuple[ModelRun, ...] = ()  # set by create(); the pipeline stores them

    def claim_for(self, assumption: Assumption) -> str:
        """The {claim} slot: the claim's text for a template that says "the claim", else
        NO_CLAIM. A claim whose text cannot be found shows NO_CLAIM too, never another text."""
        if assumption.template_id not in CLAIM_TEMPLATES:
            return NO_CLAIM
        return self.claim_text(assumption.claim_id) or NO_CLAIM

    def build_prompt(self, assumption: Assumption, candidate: EvidenceCandidate) -> str:
        return fill_prompt(
            self.template,
            {
                "assumption": self.render_assumption(assumption),
                "record": self.render_record(candidate),
                "context": self.render_context(candidate),
                "claim": self.claim_for(assumption),
            },
        )

    def try_label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceResult:
        return self._try_label(assumption, candidate)

    def _try_label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceResult:
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


def prompt_file(model: object | None) -> str:
    """The signed prompt a stance model reads: CLOUD_PROMPT_FILE for a cloud model (its
    model_sha256 starts "api:", as the cloud benchmarks pass one in), else PROMPT_FILE. None is
    the configured local model."""
    from core.llm.cloud import is_cloud_sha  # no network library is imported here

    return CLOUD_PROMPT_FILE if is_cloud_sha(getattr(model, "sha256", None)) else PROMPT_FILE


def create(
    conn: sqlite3.Connection,
    *,
    model: LocalModel | None = None,
    template: str | None = None,
    cloud: CloudConfig | None = None,
    cloud_model: LocalModel | None = None,
) -> LocalStanceLabeler:
    """The pipeline's stance labeler: the signed prompt, the configured local model, and the
    context thread's renderer, which shows the record's own line (sender, account, device-local
    time) marked '>>' among its neighbours. Raises if the signed prompt or the model config is
    missing; nothing falls back to a draft.

    The case's names are read once, here: the pipeline builds its components per audit, after
    the expert's stipulations and identity decisions for that audit are in. `template` is for
    the speed test's draft prompts only (eval/probe/time_case.py); the product passes none.

    `cloud` (a case whose cloud choice allows it, core/casework/cloud.py) makes the cloud model
    the only stance labeler for the case (CloudPort): no local model is needed for stance, a
    sticky cloud failure pauses the run, and every request is logged in the case's audit log
    before it is sent (SentLog). `cloud_model` stands in for the API in tests. A cloud model,
    on either path, reads the cloud prompt (prompt_file)."""
    from core.audit.context import render_for  # retrieval and context thread
    from core.audit.readable import assumption_text, case_names

    if template is None:
        cloud_path = cloud is not None or cloud_model is not None
        template = load_prompt(CLOUD_PROMPT_FILE if cloud_path else prompt_file(model))
    port: JsonModel
    if cloud is None and cloud_model is None:
        opened = open_run(conn, "stance", template, model=model, schema=STANCE_SCHEMA)
        port, recorder, runs = opened.port, opened.recorder, (opened.run,)
    else:
        if cloud_model is None:
            from core.llm.cloud import ClaudeModel

            assert cloud is not None  # noqa: S101 - narrowed by the branch
            cloud_model = ClaudeModel(cloud)
        logged = SentLog(cloud_model, conn)
        up = open_run(
            conn, "stance", template, model=logged, schema=STANCE_SCHEMA, reuse_unusable=False
        )
        port, recorder, runs = CloudPort(up), up.recorder, (up.run,)
    names = case_names(conn)

    def claim_text(claim_id: str) -> str | None:
        row = conn.execute("SELECT text FROM claims WHERE id = ?", (claim_id,)).fetchone()
        return row[0] if row else None

    labeler = LocalStanceLabeler(
        port,
        template=template,
        render_context=lambda c: render_for(conn, c.record_id, names=names),
        render_assumption=lambda a: assumption_text(a, names),
        claim_text=claim_text,
        recorder=recorder,
    )
    labeler.model_runs = runs
    return labeler
