import ast
import json
from pathlib import Path

import pytest

from core.llm.calls import CallLog, make_record
from core.llm.runtime import (
    FakeModel,
    GenerationParams,
    LlamaCppModel,
    ModelSpec,
    parse_json_output,
)
from eval.probe import prompts
from eval.probe.run_probe import load_items, run_model

REVIEWER = prompts.REVIEWER_SCHEMA
ROOT = Path(__file__).resolve().parents[1]


def test_parse_accepts_valid_reviewer_output():
    obj, err = parse_json_output('{"decision": "accept", "reason": "r"}', REVIEWER)
    assert err is None and obj == {"decision": "accept", "reason": "r"}


@pytest.mark.parametrize(
    "text, error",
    [
        ("not json", "invalid_json"),
        ("[]", "not_an_object"),
        ('{"decision": "accept"}', "missing_key"),
        ('{"decision": "maybe", "reason": "r"}', "bad_enum"),
        ('{"decision": "accept", "reason": 3}', "wrong_type"),
        ('{"decision": "accept", "reason": "r", "verdict": "supported"}', "extra_keys"),
    ],
)
def test_parse_fails_closed(text, error):
    obj, err = parse_json_output(text, REVIEWER)
    assert obj is None and err.startswith(error)


def test_llamacpp_refuses_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        LlamaCppModel(ModelSpec(name="x", path=tmp_path / "none.gguf"))


def test_llamacpp_refuses_hash_mismatch(tmp_path):
    f = tmp_path / "m.gguf"
    f.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        LlamaCppModel(ModelSpec(name="x", path=f, sha256="0" * 64))


def test_call_log_keeps_failed_output(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    model = FakeModel(respond=lambda _p: "garbage")
    out = model.generate_json("p", REVIEWER)
    log.append(make_record(model_name=model.name, model_sha256=model.sha256, purpose="review",
                           prompt_version="v", prompt="p", params=GenerationParams(),
                           item_id="R01", output=out))  # fmt: skip
    row = json.loads(log.path.read_text(encoding="utf-8"))
    assert row["ok"] is False and row["raw_text"] == "garbage"


def test_reviewer_prompt_renders_every_placeholder():
    text = prompts.reviewer_prompt("A", "Q", "C")
    assert "{assumption}" not in text and "{quote}" not in text and "{context}" not in text
    assert '{"decision"' in text  # literal JSON example survives


def test_smoke_items_quotes_are_verbatim():
    for it in load_items(ROOT / "eval/probe/smoke_reviewer.jsonl"):
        assert it["quote"] in it["context"]
        assert it["expected"] in {"accept", "dismiss"}
        assert not (it["overreach"] and it["expected"] == "accept")
    for it in load_items(ROOT / "eval/probe/smoke_stance.jsonl"):
        assert it["record_text"] in it["context"]


def _oracle(items_by_assumption):
    def respond(prompt: str) -> str:
        for it in items_by_assumption:
            if it["assumption"] in prompt and ("record_text" in it) == ("Message (the" in prompt):
                if "record_text" in it:
                    return json.dumps({"stance": it["expected"], "quote": it["record_text"],
                                       "rationale": "oracle"})  # fmt: skip
                return json.dumps({"decision": it["expected"], "reason": "oracle"})
        return "{}"

    return respond


def test_oracle_model_passes_all_bars(tmp_path):
    rev = load_items(ROOT / "eval/probe/smoke_reviewer.jsonl")
    st = load_items(ROOT / "eval/probe/smoke_stance.jsonl")
    model = FakeModel(respond=_oracle(rev + st))
    res = run_model(model, rev, st, GenerationParams(), 2, tmp_path)
    assert res["passes_all"], res["bars"]


def test_always_accept_reviewer_fails_overreach_bar(tmp_path):
    rev = load_items(ROOT / "eval/probe/smoke_reviewer.jsonl")
    model = FakeModel(respond=lambda _p: '{"decision": "accept", "reason": "x"}')
    res = run_model(model, rev, [], GenerationParams(), 1, tmp_path)
    assert res["overreach_false_accepts"] == sum(it["overreach"] for it in rev)
    assert not res["bars"]["zero_overreach_false_accepts"]


def test_invalid_reviewer_output_counts_as_dismissal(tmp_path):
    rev = [it for it in load_items(ROOT / "eval/probe/smoke_reviewer.jsonl") if it["overreach"]]
    model = FakeModel(respond=lambda _p: "accept!")
    res = run_model(model, rev, [], GenerationParams(), 1, tmp_path)
    assert res["overreach_false_accepts"] == 0
    assert not res["bars"]["valid_output_100"]


def test_core_llm_has_no_network_imports():
    banned = {"anthropic", "requests", "httpx", "httpx2", "urllib", "socket", "huggingface_hub"}
    for path in (ROOT / "core").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert n.split(".")[0] not in banned, f"{path}: imports {n}"
