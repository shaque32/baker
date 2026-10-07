import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit._llm_json import PromptMissingError, prompt_body
from core.audit.translation import (
    TRANSLATION_SCHEMA,
    LocalTranslator,
    Translation,
    insert_translation,
    needs_human_reader,
)
from core.contracts import Message, MessageDirection, ProvenanceTier, SourceRef, Timestamp
from tests.fake_model import FakeModel

DRAFT = prompt_body((Path(__file__).parents[1] / "docs/prompts/translation.md").read_text("utf-8"))

RU = Message(
    id="msg:src1:Chats!9",
    ref=SourceRef(source_id="src1", locator="Chats!9"),
    thread_id="t1",
    sender_account_id="acct:1",
    direction=MessageDirection.OUTGOING,
    ts=Timestamp(utc=datetime(2026, 3, 12, 2, 15, tzinfo=UTC), offset_min=0, raw="x"),
    body="встреча в 22:15, 3 человека",
    lang=None,
)
GOOD = {"translation": "meeting at 22:15, 3 people"}


def translator(*replies, **kw):
    model = FakeModel(*replies, **kw)
    return LocalTranslator(model, template=DRAFT), model


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("see you at 9", None, False),
        ("see you at 9", "en", False),
        ("see you at 9", "en-US", False),
        ("nos vemos a las 9", "es", True),
        ("я волнуюсь", None, True),
        ("ok Катя", None, True),
        ("café at 9 👍", None, False),
    ],
)
def test_needs_human_reader(text, lang, expected):
    assert needs_human_reader(text, lang) is expected


def test_translation_is_inferred_and_keeps_original():
    tr, model = translator(GOOD)
    result = tr.translate(RU)
    assert result is not None and result.translation is not None
    t = result.translation
    assert t.tier is ProvenanceTier.INFERRED
    assert t.text == GOOD["translation"]
    assert t.id == "tr:msg:src1:Chats!9:en:run:fake:1"
    assert RU.body in model.prompts[0]
    assert model.schemas[0] is TRANSLATION_SCHEMA
    assert "DRAFT for Arsh" not in model.prompts[0]


def test_english_message_is_not_sent():
    tr, model = translator(GOOD)
    assert tr.translate(RU.model_copy(update={"body": "see you at 9"})) is None
    assert model.prompts == []


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param({"translation": "meeting at 22:15, 4 people"}, id="number-changed"),
        pytest.param({"translation": "meeting at 10:15 PM, 3 people"}, id="time-reformatted"),
        pytest.param({"translation": "meeting, 3 people"}, id="number-lost"),
        pytest.param({"translation": "  "}, id="blank"),
        pytest.param({"translation": "встреча в 22:15, 3 человека"}, id="untranslated"),
        pytest.param({"translation": "x", "confidence": 1}, id="extra-field"),
        pytest.param("meeting at 22:15, 3 people", id="not-json"),
        pytest.param(RuntimeError("boom"), id="model-raises"),
    ],
)
def test_bad_translation_is_dropped(reply):
    tr, _ = translator(reply)
    result = tr.translate(RU)
    assert result is not None
    assert result.translation is None and result.dropped_reason


def test_missing_signed_prompt_fails_loudly(tmp_path):
    with pytest.raises(PromptMissingError):
        LocalTranslator(FakeModel(GOOD), prompts_dir=tmp_path)


def test_insert_translation(case_db: sqlite3.Connection):
    cols = [r[1] for r in case_db.execute("PRAGMA table_info(translations)")]
    assert cols == ["id", "message_id", "target_lang", "text", "model_run_id"]
    case_db.execute("PRAGMA foreign_keys = OFF")
    t = Translation("tr:m:en:r", "m", "en", "hello", "r", "sha256:x")
    insert_translation(case_db, t)
    assert case_db.execute("SELECT text FROM translations").fetchone()[0] == "hello"
