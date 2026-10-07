"""Shared plumbing for the model passes in core/audit/ and core/claims/.

Three jobs, all fail-closed:
- `JsonModel`: the narrow port the passes call. core/llm/ provides the real local model;
  tests use a fake. No implementation here makes network calls.
- `fill_prompt`: substitutes `{name}` placeholders in one pass, so text from evidence can never
  inject a second placeholder, and literal JSON braces in a prompt are left alone.
- `parse_json_object`: strict parse of one JSON object. Anything else raises `BadModelOutput`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_OUTPUT_CHARS = 20_000


class JsonModel(Protocol):
    """A local model that returns text constrained to a JSON schema (grammar-constrained
    decoding in llama.cpp). Deterministic settings and the ModelRun row are the model's job."""

    @property
    def run_id(self) -> str: ...

    def generate(self, prompt: str, json_schema: Mapping[str, Any]) -> str: ...


class BadModelOutput(ValueError):
    """The model returned something we will not use. The raw text is kept for the log."""

    def __init__(self, reason: str, raw: str | None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw = raw


class PromptMissingError(FileNotFoundError):
    """The signed prompt is not in core/audit/prompts/ yet. Drafts live in docs/prompts/."""


PROMPT_START = "<!-- prompt starts -->"


def prompt_body(file_text: str) -> str:
    """The text sent to the model. A prompt file may carry a human header (owner, version,
    notes) above a line that is exactly PROMPT_START; only the text after it is sent.
    Without that line, the whole file is the prompt."""
    lines = file_text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() == PROMPT_START:
            return "".join(lines[i + 1 :]).strip() + "\n"
    return file_text


def load_prompt(name: str, prompts_dir: Path = PROMPTS_DIR) -> str:
    path = prompts_dir / name
    if not path.is_file():
        raise PromptMissingError(f"signed prompt {path} not found; drafts are in docs/prompts/")
    return prompt_body(path.read_text(encoding="utf-8"))


def prompt_version(template: str) -> str:
    """Content hash of the prompt template, recorded with every call."""
    return "sha256:" + hashlib.sha256(template.encode("utf-8")).hexdigest()[:16]


_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def required_placeholders(template: str) -> set[str]:
    return set(_PLACEHOLDER.findall(template))


def fill_prompt(template: str, values: Mapping[str, str]) -> str:
    """Single-pass substitution of `{name}` for names in `values`. Every placeholder in
    `values` must appear in the template, so a renamed placeholder fails loudly instead of
    silently dropping an input."""
    missing = set(values) - required_placeholders(template)
    if missing:
        raise ValueError(f"prompt has no placeholder for: {sorted(missing)}")

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        return values[key] if key in values else m.group(0)

    return _PLACEHOLDER.sub(sub, template)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def parse_json_object(raw: object) -> dict[str, Any]:
    """Exactly one JSON object, nothing around it (whitespace aside), no duplicate keys."""
    if not isinstance(raw, str):
        raise BadModelOutput("model output is not text", None)
    if len(raw) > MAX_OUTPUT_CHARS:
        raise BadModelOutput("model output too long", raw[:MAX_OUTPUT_CHARS])
    try:
        obj = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, RecursionError) as e:
        raise BadModelOutput(f"not valid JSON: {e}", raw) from None
    if not isinstance(obj, dict):
        raise BadModelOutput("JSON is not an object", raw)
    return obj


def call_model(
    model: JsonModel, prompt: str, schema: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Run the model and parse its output; returns (raw text, object). Any exception from
    the model becomes BadModelOutput, so callers have one failure path."""
    try:
        raw = model.generate(prompt, schema)
    except Exception as e:  # any model failure is a dropped output
        raise BadModelOutput(f"model call failed: {type(e).__name__}: {e}", None) from e
    return raw, parse_json_object(raw)


def model_run_id(model: JsonModel) -> str | None:
    """The model's run id, or None if it has no usable one (which drops every output)."""
    try:
        rid = model.run_id
    except Exception:  # a broken model object is treated like a failed call
        return None
    return rid if isinstance(rid, str) and rid else None
