"""ClaimExtractor: the local model proposes atomic claims; the expert edits the list.

Not on the alpha's critical path: the eval scores gold claims, and the expert can enter or
edit claims by hand. Fails closed per claim: a proposed claim is dropped unless it quotes a
span of the paragraph verbatim and every number in its text appears in the paragraph as
written. A paragraph whose whole output is unusable yields no claims and a ClaimDrop, so the
CLI can tell the expert that paragraph needs claims by hand.
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
    digit_runs,
    fill_prompt,
    load_prompt,
    model_run_id,
    prompt_version,
    required_placeholders,
)
from core.contracts import Claim, ClaimStatus, ClaimType, GovDocParagraph

PROMPT_FILE = "claims.md"
PLACEHOLDERS = frozenset({"paragraph"})
MAX_CLAIMS_PER_PARAGRAPH = 20
MAX_CLAIM_CHARS = 600

_TYPES = [t.value for t in ClaimType]

CLAIMS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "maxItems": MAX_CLAIMS_PER_PARAGRAPH,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": MAX_CLAIM_CHARS},
                    "claim_type": {"type": "string", "enum": _TYPES},
                    "span": {"type": "string", "minLength": 1},
                },
                "required": ["text", "claim_type", "span"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


class _ClaimOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: StrictStr = Field(min_length=1, max_length=MAX_CLAIM_CHARS)
    claim_type: Literal[
        "communication",
        "identity",
        "timing",
        "content_meaning",
        "count",
        "absence",
        "role",
        "event",
    ]
    span: StrictStr = Field(min_length=1)


class _ClaimsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[dict[str, object]] = Field(max_length=MAX_CLAIMS_PER_PARAGRAPH)


@dataclass(frozen=True)
class ClaimDrop:
    paragraph_id: str
    index: int | None  # position in the model's list; None if the whole output was dropped
    reason: str
    raw_output: str | None


class LocalClaimExtractor:
    """Implements core.contracts.ClaimExtractor on a local JsonModel."""

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
            raise ValueError(f"claims prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)
        self.drops: list[ClaimDrop] = []

    def extract(self, paragraphs: list[GovDocParagraph]) -> list[Claim]:
        claims: list[Claim] = []
        for p in paragraphs:
            claims.extend(self.extract_paragraph(p))
        return claims

    def extract_paragraph(self, paragraph: GovDocParagraph) -> list[Claim]:
        if not paragraph.text.strip():
            return []
        run_id = model_run_id(self.model)
        raw: str | None = None
        try:
            if run_id is None:
                raise BadModelOutput("model has no run id", None)
            prompt = fill_prompt(self.template, {"paragraph": paragraph.text})
            raw, obj = call_model(self.model, prompt, CLAIMS_SCHEMA)
            try:
                items = _ClaimsOut.model_validate(obj).claims
            except ValidationError as e:
                raise BadModelOutput(f"wrong shape: {e.errors(include_url=False)}", raw) from None
        except BadModelOutput as e:
            self.drops.append(ClaimDrop(paragraph.id, None, e.reason, raw or e.raw))
            return []

        out: list[Claim] = []
        seen: set[str] = set()
        for i, item in enumerate(items):
            try:
                c = _ClaimOut.model_validate(item)
            except ValidationError as e:
                self.drops.append(
                    ClaimDrop(paragraph.id, i, f"wrong shape: {e.error_count()} errors", raw)
                )
                continue
            text = c.text.strip()
            if not text:
                self.drops.append(ClaimDrop(paragraph.id, i, "empty claim text", raw))
                continue
            if not c.span.strip() or c.span not in paragraph.text:
                self.drops.append(ClaimDrop(paragraph.id, i, "span not verbatim in paragraph", raw))
                continue
            invented = digit_runs(text) - digit_runs(paragraph.text)
            if invented:
                reason = f"numbers not in paragraph: {sorted(invented)}"
                self.drops.append(ClaimDrop(paragraph.id, i, reason, raw))
                continue
            if text in seen:
                self.drops.append(ClaimDrop(paragraph.id, i, "duplicate claim", raw))
                continue
            seen.add(text)
            out.append(
                Claim(
                    id=f"claim:{paragraph.id}:{len(out) + 1}",
                    paragraph_id=paragraph.id,
                    text=text,
                    claim_type=ClaimType(c.claim_type),
                    status=ClaimStatus.PROPOSED,
                    model_run_id=run_id,
                )
            )
        return out
