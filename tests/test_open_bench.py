"""The hosted open-model screen (eval/bench/open_bench.py), with no network: a stand-in answers
every request. Synthetic probe items only."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from eval.bench import open_bench as ob
from eval.bench.claude_bench import DataSafetyError
from eval.probe import prompts

ANSWER = {"stance": "supports", "quote": "q", "rationale": "r"}


def _resp(content: str, finish: str = "stop", provider: str = "Prov") -> dict:
    return {
        "id": "gen-1",
        "model": "x/y",
        "provider": provider,
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "cost": 0.0012},
    }


def _hosted(post, **kw) -> ob.HostedModel:  # noqa: ANN001, ANN003
    return ob.HostedModel(ob.model("minimax-m3.1-flash"), post=post, key="k", **kw)


def test_the_request_is_greedy_seeded_schema_bound_and_keeps_no_prompts():
    body = _hosted(ob.dry_post).body("PROMPT", prompts.STANCE_SCHEMA)
    assert body["temperature"] == 0.0 and body["seed"] == 1234
    assert body["provider"]["data_collection"] == "deny"
    assert body["provider"]["require_parameters"] is True
    assert "fp4" not in body["provider"]["quantizations"]
    fmt = body["response_format"]["json_schema"]
    assert fmt["strict"] is True and fmt["schema"]["additionalProperties"] is False
    assert body["reasoning"] == {"effort": "medium", "exclude": True}
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]


def test_an_answer_is_parsed_and_its_provider_and_cost_recorded():
    m = _hosted(lambda body, key, timeout: _resp(json.dumps(ANSWER)))
    out = m.generate_json("p", prompts.STANCE_SCHEMA)
    assert out.parsed == ANSWER and out.error is None
    assert out.stop_reason == "stop via Prov" and out.prompt_tokens == 1000
    assert m.usage.providers == {"Prov": 1} and m.usage.cost_usd == pytest.approx(0.0012)


def test_a_cut_off_or_off_schema_answer_fails_closed():
    cut = _hosted(lambda body, key, timeout: _resp('{"stance": "sup', finish="length"))
    assert cut.generate_json("p", prompts.STANCE_SCHEMA).error == "max_tokens"
    bad = _hosted(
        lambda body, key, timeout: _resp('{"stance": "maybe", "quote": "", "rationale": ""}')
    )
    out = bad.generate_json("p", prompts.STANCE_SCHEMA)
    assert out.parsed is None and out.error


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(ob.API_URL, code, "x", {}, io.BytesIO(b""))  # type: ignore[arg-type]


def test_rate_limits_are_retried_and_other_errors_are_not(monkeypatch):
    monkeypatch.setattr(ob.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def limited(body, key, timeout):  # noqa: ANN001, ANN202
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return _resp(json.dumps(ANSWER))

    assert _hosted(limited).generate_json("p", prompts.STANCE_SCHEMA).parsed == ANSWER
    assert calls["n"] == 3

    calls["n"] = 0

    def refused(body, key, timeout):  # noqa: ANN001, ANN202
        calls["n"] += 1
        raise _http_error(400)

    m = _hosted(refused)
    out = m.generate_json("p", prompts.STANCE_SCHEMA)
    assert out.parsed is None and out.error == "http 400" and calls["n"] == 1
    assert m.usage.failed == 1


def test_no_key_and_no_stand_in_stops_before_any_request(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        ob.HostedModel(ob.model("minimax-m3.1-flash"))


def test_only_the_signed_prompt_files_may_be_sent(tmp_path):
    other = tmp_path / "stance.md"
    other.write_text("{assumption} {record}")
    with pytest.raises(DataSafetyError):
        ob.run_one(_hosted(ob.dry_post), other, 1, tmp_path / "out")


def test_a_dry_run_writes_the_verdict_with_cost_providers_and_repeats(tmp_path, monkeypatch):
    from eval.probe import candidates

    full = ob.probe_items
    monkeypatch.setattr(
        ob,
        "probe_items",
        lambda path, layout: (full(path, layout)[0][:4], full(path, layout)[1][:4]),
    )
    assert ob.main(["--dry-run", "--models", "minimax-m3.1-flash", "--out", str(tmp_path)]) == 0
    text = (tmp_path / "VERDICT.md").read_text()
    for version in candidates.PROMPTS:
        row = json.loads((tmp_path / "minimax-m3.1-flash" / version / "summary.json").read_text())
        assert row[0]["providers_this_run"] == {"dry-run": 8}  # 4 items, asked twice
        assert row[0]["weights"].startswith("MiniMaxAI/MiniMax-M3.1-Flash@ce7f4df8")
    assert "no hosted open model passes" in text and "providers {'dry-run': 8}" in text
    assert "byte-identical on 100%" in text


def test_every_model_pins_its_weights():
    for m in ob.MODELS:
        assert len(m.revision) == 40 and "/" in m.weights and "/" in m.api_model


def test_each_answer_records_who_served_it_in_call_order(tmp_path, monkeypatch):
    """The call log keeps no provider, so served.jsonl does, one row per call."""
    full = ob.probe_items
    monkeypatch.setattr(ob, "probe_items", lambda path, layout: ([], full(path, layout)[1][:2]))
    turns = iter(["A", "B", "A", "C"])
    m = _hosted(lambda body, key, timeout: _resp(json.dumps(ANSWER), provider=next(turns)))
    ob.run_one(m, ob.ROOT / "core/audit/prompts/stance_cloud.md", 2, tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "served.jsonl").read_text().splitlines()]
    calls = [
        json.loads(line) for line in next(tmp_path.glob("*.calls.jsonl")).read_text().splitlines()
    ]
    assert [r["provider"] for r in rows] == ["A", "B", "A", "C"]
    assert [r["prompt_sha256"] for r in rows] == [c["prompt_sha256"] for c in calls]
    assert rows[0]["request_id"] == "gen-1" and rows[0]["finish_reason"] == "stop"


def test_a_model_without_a_thinking_mode_is_not_asked_to_reason():
    body = ob.HostedModel(ob.model("llama-4-maverick"), post=ob.dry_post, key="k").body(
        "PROMPT", prompts.STANCE_SCHEMA
    )
    assert "reasoning" not in body and body["seed"] == 1234
    assert ob.HostedModel(ob.model("llama-4-maverick"), post=ob.dry_post).params.reasoning == "none"


def test_a_model_may_widen_only_its_own_precision_list():
    body = ob.HostedModel(ob.model("mistral-large-4"), post=ob.dry_post, key="k").body(
        "P", prompts.STANCE_SCHEMA
    )
    assert "unknown" in body["provider"]["quantizations"]
    assert body["provider"]["data_collection"] == "deny"
    assert "fp4" not in ob.PROVIDER["quantizations"]


def test_on_case01_a_hosted_model_reads_the_cloud_stance_prompt():
    from core.audit import stance

    labeler = ob.CaseLabeler(_hosted(ob.dry_post))
    assert stance.prompt_file(labeler) == stance.CLOUD_PROMPT_FILE
    assert labeler.generate_json("p", prompts.STANCE_SCHEMA).parsed["stance"] == "irrelevant"
