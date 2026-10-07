"""Append-only log of every model call, kept or dropped, so a run can be reproduced.

Contracts v0.2 adds a `model_calls` table. Until it lands, calls go to a JSONL file with the
same fields. Raw output is stored even when it failed to parse.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.llm.runtime import GenerationParams, ModelOutput


@dataclass(frozen=True)
class ModelCallRecord:
    at_utc: str
    model_name: str
    model_sha256: str
    purpose: str  # 'review', 'stance', ...
    prompt_version: str
    prompt_sha256: str
    params: dict[str, str | int | float | bool]
    item_id: str
    raw_text: str
    ok: bool
    error: str | None
    prompt_tokens: int
    completion_tokens: int
    seconds: float


def make_record(
    *,
    model_name: str,
    model_sha256: str,
    purpose: str,
    prompt_version: str,
    prompt: str,
    params: GenerationParams,
    item_id: str,
    output: ModelOutput,
) -> ModelCallRecord:
    return ModelCallRecord(
        at_utc=datetime.now(UTC).isoformat(),
        model_name=model_name,
        model_sha256=model_sha256,
        purpose=purpose,
        prompt_version=prompt_version,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        params=params.as_record(),
        item_id=item_id,
        raw_text=output.raw_text,
        ok=output.ok,
        error=output.error,
        prompt_tokens=output.prompt_tokens,
        completion_tokens=output.completion_tokens,
        seconds=round(output.seconds, 4),
    )


class CallLog:
    """Writes one JSON line per call. Opens in append mode; never rewrites earlier lines."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: ModelCallRecord) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
