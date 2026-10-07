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


def _body(path: Path) -> str:
    """The prompt text the model sees: everything from the first line that starts the prompt."""
    text = path.read_text(encoding="utf-8")
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


def stance_prompt(assumption: str, record: str, context: str) -> str:
    return render(STANCE_DRAFT, assumption=assumption, record=record, context=context)
