"""Machine translation to English, as a reading aid. Never citable, never more than inferred.

Rules this module enforces:
- The original text stays the only citable text. A translation is stored beside it (the
  `translations` table) and quotes are always verified against the original.
- Every translation is ProvenanceTier.INFERRED. Only an expert who reads the language can
  confirm it; that is an expert action, not something this module or the AI reviewer does.
- Fails closed: malformed output, an empty translation, or a number that is not in the
  original (or a number in the original that went missing) drops the translation. The expert
  then sees the original only.
- `needs_human_reader` tells the AI reviewer to leave an item for a person: a machine reading
  of a foreign-language quote never raises a claim to "supported" on its own.

The prompt is human-owned (core/audit/prompts/translation.md); the draft is in docs/prompts/.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

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
from core.contracts import Message, ProvenanceTier

PROMPT_FILE = "translation.md"
PLACEHOLDERS = frozenset({"text"})
TARGET_LANG = "en"
TIER = ProvenanceTier.INFERRED
MAX_TRANSLATION_CHARS = 8000

TRANSLATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "translation": {"type": "string", "minLength": 1, "maxLength": MAX_TRANSLATION_CHARS},
    },
    "required": ["translation"],
    "additionalProperties": False,
}


def non_latin_letters(text: str) -> bool:
    """True if any letter is outside the Latin script (Cyrillic, Arabic, CJK, ...)."""
    for ch in text:
        if ch.isalpha() and not unicodedata.name(ch, "").startswith("LATIN"):
            return True
    return False


def needs_human_reader(text: str, lang: str | None = None) -> bool:
    """True when reading `text` needs more than English: the source tagged it with another
    language, or it contains letters outside the Latin script."""
    if lang is not None and lang.strip() and lang.strip().lower().split("-")[0] != TARGET_LANG:
        return True
    return non_latin_letters(text)


class _TranslationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translation: StrictStr = Field(min_length=1, max_length=MAX_TRANSLATION_CHARS)


@dataclass(frozen=True)
class Translation:
    """A kept translation. `tier` is always INFERRED."""

    id: str
    message_id: str
    target_lang: str
    text: str
    model_run_id: str
    prompt_version: str
    tier: ProvenanceTier = TIER


@dataclass(frozen=True)
class TranslationResult:
    message_id: str
    model_run_id: str | None
    prompt_version: str
    translation: Translation | None
    dropped_reason: str | None
    raw_output: str | None


def translation_id(message_id: str, run_id: str) -> str:
    return f"tr:{message_id}:{TARGET_LANG}:{run_id}"


def check_numbers(original: str, translated: str) -> None:
    """Digits must survive translation exactly, both ways."""
    added = digit_runs(translated) - digit_runs(original)
    lost = digit_runs(original) - digit_runs(translated)
    if added or lost:
        raise BadModelOutput(f"numbers changed: added {sorted(added)}, lost {sorted(lost)}", None)


class LocalTranslator:
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
            raise ValueError(f"translation prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)

    def translate(self, message: Message) -> TranslationResult | None:
        """None when the message does not need translating (English, Latin script only)."""
        if not message.body.strip() or not needs_human_reader(message.body, message.lang):
            return None
        run_id = model_run_id(self.model)
        raw: str | None = None
        try:
            if run_id is None:
                raise BadModelOutput("model has no run id", None)
            prompt = fill_prompt(self.template, {"text": message.body})
            raw, obj = call_model(self.model, prompt, TRANSLATION_SCHEMA)
            try:
                out = _TranslationOut.model_validate(obj)
            except ValidationError as e:
                raise BadModelOutput(f"wrong shape: {e.errors(include_url=False)}", raw) from None
            text = out.translation.strip()
            if not text:
                raise BadModelOutput("empty translation", raw)
            if text == message.body.strip():
                raise BadModelOutput("translation is the original text", raw)
            check_numbers(message.body, text)
        except BadModelOutput as e:
            return TranslationResult(
                message.id, run_id, self.prompt_version, None, e.reason, raw or e.raw
            )
        t = Translation(
            id=translation_id(message.id, run_id),
            message_id=message.id,
            target_lang=TARGET_LANG,
            text=text,
            model_run_id=run_id,
            prompt_version=self.prompt_version,
        )
        return TranslationResult(message.id, run_id, self.prompt_version, t, None, raw)


def insert_translation(conn: sqlite3.Connection, t: Translation) -> None:
    """Store a kept translation. The model_runs row for t.model_run_id must already exist."""
    conn.execute(
        "INSERT INTO translations (id, message_id, target_lang, text, model_run_id)"
        " VALUES (?, ?, ?, ?, ?)",
        (t.id, t.message_id, t.target_lang, t.text, t.model_run_id),
    )
