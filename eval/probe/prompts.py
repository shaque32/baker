"""Render the reviewer prompt (human-owned) and the probe-only stance draft.

The prompts contain literal JSON braces, so placeholders are replaced by name, not str.format.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEWER_PROMPT = ROOT / "core" / "audit" / "prompts" / "reviewer.md"
STANCE_DRAFT = Path(__file__).with_name("stance_draft.md")

REVIEWER_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["accept", "dismiss"]},
        "reason": {"type": "string"},
    },
    "required": ["decision", "reason"],
    "additionalProperties": False,
}

STANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "stance": {
            "type": "string",
            "enum": ["supports", "contradicts", "complicates", "irrelevant"],
        },
        "quote": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["stance", "quote", "rationale"],
    "additionalProperties": False,
}


PROMPT_START = "<!-- prompt starts -->"


def _body(path: Path) -> str:
    """The prompt text the model sees.

    A prompt file may carry a human header above a line that is exactly PROMPT_START (the
    convention in docs/prompts/); only the text after it is sent. Older files without that line
    start at their first prompt sentence.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for n, line in enumerate(lines):
        if line.strip() == PROMPT_START:
            return "".join(lines[n + 1 :]).strip() + "\n"
    marker = "You are reviewing" if path == REVIEWER_PROMPT else "You label one message"
    i = text.find(marker)
    if i < 0:
        raise ValueError(f"prompt start not found in {path}")
    return text[i:]


def prompt_version(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def render(path: Path, **fields: str) -> str:
    text = _body(path)
    for key, value in fields.items():
        token = "{" + key + "}"
        if token not in text:
            raise KeyError(f"placeholder {token} not in {path.name}")
        text = text.replace(token, value)
    return text


def reviewer_prompt(assumption: str, quote: str, context: str) -> str:
    return render(REVIEWER_PROMPT, assumption=assumption, quote=quote, context=context)


def stance_prompt(assumption: str, record: str, context: str, path: Path = STANCE_DRAFT) -> str:
    return render(path, assumption=assumption, record=record, context=context)


def record_line(record_text: str, context: str) -> str:
    """The context line holding the record, so the model sees its sender and local time.

    The quote check still runs against the bare record text, so a quote that copies the
    header fails, as it would in the product.
    """
    for line in context.splitlines():
        if line.endswith(record_text):
            return line
    return record_text
