"""The cloud benchmark (eval/bench/claude_bench.py) on a stand-in client. No network, no key."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.bench import claude_bench as cb
from eval.probe import prompts


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class ScriptedClient:
    """Returns the queued responses in order and keeps every request."""

    def __init__(self, *responses):
        self.messages = self
        self.queue = list(responses)
        self.requests = []

    def create(self, **kw):
        self.requests.append(kw)
        return self.queue.pop(0)


def _resp(text="", stop="end_turn", inp=100, out=10):
    usage = _Obj(input_tokens=inp, output_tokens=out, cache_read_input_tokens=0,
                 cache_creation_input_tokens=0)  # fmt: skip
    return _Obj(stop_reason=stop, content=[_Obj(type="text", text=text)], usage=usage)


def test_only_synthetic_probe_files_may_reach_the_api(tmp_path):
    assert cb.check_probe_path(cb.SIGNED_PROBE) == cb.SIGNED_PROBE.resolve()
    assert cb.check_probe_path(Path("eval/probe/smoke_stance.jsonl"))
    outside = tmp_path / "items.jsonl"
    outside.write_text("{}\n")
    with pytest.raises(cb.DataSafetyError):
        cb.check_probe_path(outside)
    with pytest.raises(cb.DataSafetyError):
        cb.check_probe_path(Path("eval/gold/case01/gold.jsonl"))
    with pytest.raises(cb.DataSafetyError):
        cb.check_probe_path(Path("eval/gold/probe/../case01/gold.jsonl"))


def test_the_hidden_case_never_reaches_the_api():
    assert cb.check_case("case01") == "case01"
    with pytest.raises(cb.DataSafetyError):
        cb.check_case("case02")


def test_run_case_refuses_case02_before_any_call():
    model = cb.ClaudeModel("claude-haiku-5-5", client=ScriptedClient())
    with pytest.raises(cb.DataSafetyError):
        cb.run_case(model, "case02", Path("unused"), None)
    assert model.client.requests == []


def test_api_schema_drops_length_limits_and_keeps_the_rest():
    from core.audit.stance import STANCE_SCHEMA

    sent = cb.api_schema(STANCE_SCHEMA)
    text = json.dumps(sent)
    assert "maxLength" not in text and "minLength" not in text
    assert sent["required"] == STANCE_SCHEMA["required"]
    assert sent["additionalProperties"] is False
    assert sent["properties"]["stance"]["enum"] == STANCE_SCHEMA["properties"]["stance"]["enum"]
    assert "maxLength" in json.dumps(STANCE_SCHEMA)  # the input is not edited


def test_a_good_answer_is_parsed_and_costed():
    body = json.dumps({"stance": "supports", "quote": "q", "rationale": "r"})
    client = ScriptedClient(_resp(body, inp=1_000_000, out=100_000))
    model = cb.ClaudeModel("claude-sonnet-5-5", effort="high", client=client)
    out = model.generate_json("prompt", prompts.STANCE_SCHEMA)
    assert out.ok and out.parsed["stance"] == "supports"
    req = client.requests[0]
    assert req["model"] == "claude-sonnet-5-5"
    assert req["output_config"]["effort"] == "high"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in req and "fallbacks" not in req
    assert model.usage.cost_usd("claude-sonnet-5-5") == pytest.approx(2.0 + 1.0)


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_a_refusal_or_cut_off_answer_is_invalid_output(stop):
    model = cb.ClaudeModel("claude-haiku-5-5", client=ScriptedClient(_resp("{", stop=stop)))
    out = model.generate_json("prompt", prompts.STANCE_SCHEMA)
    assert not out.ok and out.error == stop
    assert model.usage.refusals == (stop == "refusal")


def test_an_answer_off_the_schema_is_invalid_output():
    body = json.dumps({"stance": "proves", "quote": "q", "rationale": "r"})
    model = cb.ClaudeModel("claude-haiku-5-5", client=ScriptedClient(_resp(body)))
    assert not model.generate_json("prompt", prompts.STANCE_SCHEMA).ok


def test_dry_run_probe_sends_only_signed_probe_items(tmp_path):
    client = cb.DryRunClient()
    model = cb.ClaudeModel("claude-haiku-5-5", client=client)
    res = cb.run_probe(model, cb.SIGNED_PROBE, 1, tmp_path)
    rows = [json.loads(x) for x in cb.SIGNED_PROBE.read_text(encoding="utf-8").splitlines()]
    assert len(client.requests) == 2 * len(rows)  # one reviewer and one stance call per item
    targets = {r["target"]["text"] for r in rows}
    for req in client.requests:
        prompt = req["messages"][0]["content"]
        assert any(t in prompt for t in targets)
    assert res["usage"]["calls"] == len(client.requests)
    assert res["expert_confirms"]["contradicts_shown_as_supports"] == 0


def test_decision_rule_needs_probe_bars_and_the_case_gate():
    good_probe = {"expert_confirms": {"passes_all": True, "bars": {}}}
    missed = {"no_contradicts_shown_as_supports": False}
    bad_probe = {"expert_confirms": {"passes_all": False, "bars": missed}}
    good_case = {"claims_run": "all", "n_false_supported": 0, "verdict_accuracy": 0.85}
    assert cb.decide({"probe": good_probe, "case": good_case})["candidate"] is True
    assert cb.decide({"probe": bad_probe, "case": good_case})["candidate"] is False
    one_false = {**good_case, "n_false_supported": 1}
    assert cb.decide({"probe": good_probe, "case": one_false})["candidate"] is False
    low = {**good_case, "verdict_accuracy": 0.79}
    assert cb.decide({"probe": good_probe, "case": low})["candidate"] is False
    subset = {**good_case, "claims_run": ["C02"]}
    assert cb.decide({"probe": good_probe, "case": subset})["candidate"] is None
    assert cb.decide({"probe": good_probe})["candidate"] is None


def test_report_names_the_local_baseline_and_each_decision():
    probe = {
        "expert_confirms": {"supports_recall": 1.0, "contradicts_precision": 1.0,
                            "contradicts_shown_as_supports": 0, "stance_valid_output": 1.0,
                            "contradicts_recall": 0.9, "expert_load_supports_shown": 30,
                            "expert_load_precision": 0.8, "passes_all": True, "bars": {}},
        "mean_seconds_per_stance_call": 3.1, "overreach_false_accepts": 0, "overreach_items": 28,
        "reviewer_false_accept_rate": 0.0, "reviewer_clear_accept_rate": 0.9,
        "reviewer_accuracy": 0.95, "reviewer_valid_output": 1.0, "stance_repeat_identical": 0.9,
        "reviewer_repeat_identical": 0.95, "usage": {"cost_usd": 0.5, "refusals": 0},
    }  # fmt: skip
    res = {"model": "claude-sonnet-5-5", "probe": probe}
    res["decision"] = cb.decide(res)
    md = cb.results_markdown([res], {"at_utc": "t", "probe_set": "p", "effort": "medium",
                                     "repeat": 2, "dry_run": False})  # fmt: skip
    assert "Qwen3-14B" in md and "| 22 | 5 |" in md  # the 14B's traps and moved traps shown
    assert "Probe input layout: legacy" in md  # a run from before the layout was recorded
    assert "claude-sonnet-5-5: **undecided**" in md
