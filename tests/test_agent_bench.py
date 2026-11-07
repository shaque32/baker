"""eval/bench/agent_bench.py: hosted models as filler and testability agent, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.bench import agent_bench
from eval.bench.claude_bench import DataSafetyError
from eval.bench.open_bench import HostedModel, model


@pytest.mark.parametrize("case", ["case06", "case02", "case01", "case03", "case99"])
def test_only_spent_testability_cases_may_go_out(case: str) -> None:
    with pytest.raises(DataSafetyError):
        agent_bench.check_agent_case(case)


def test_a_refused_case_stops_before_any_model_is_made(monkeypatch, tmp_path: Path) -> None:
    made = []
    monkeypatch.setattr(agent_bench, "HostedModel", lambda *a, **k: made.append(a))
    with pytest.raises(DataSafetyError):
        agent_bench.main(["--cases", "case05,case06", "--dry-run", "--out", str(tmp_path)])
    assert made == []


def test_held_out_and_hidden_cases_stay_refused() -> None:
    assert "case06" not in agent_bench.ALLOWED_CASES
    assert "case02" not in agent_bench.ALLOWED_CASES


@pytest.fixture(scope="module")
def dry_case05(tmp_path_factory) -> tuple[dict, list[dict], Path]:
    out = tmp_path_factory.mktemp("agent_bench") / "case05"
    sent: list[dict] = []

    def post(body, key, timeout):  # noqa: ANN001, ANN202
        sent.append(body)
        return agent_bench.dry_post(body, key, timeout)

    hosted = HostedModel(model("deepseek-v4.1-flash-1017"), "medium", post=post)
    return agent_bench.run_bench(hosted, "case05", out), sent, out


def test_one_hosted_model_does_both_jobs_at_the_dev_check_settings(dry_case05) -> None:
    res, sent, out = dry_case05
    t, fp = res["step"], res["first_pass"]
    assert t["cap"] == agent_bench.CAP == 2
    assert t["prompt"] == "signed"
    assert t["stance"] == "skipped"
    # Every call went to the one model: the first pass once per claim, then the step twice
    # per claim it worked on (an empty answer is refused, so each claim gets its retry).
    assert res["calls"] == len(sent) == fp["claims"] + t["tries"]
    assert t["tries"] == 2 * t["claims_the_filler_left_untested"]
    assert {b["model"] for b in sent} == {"deepseek/deepseek-v4.1-flash-1017"}
    assert all(b["provider"]["data_collection"] == "deny" for b in sent)
    assert res["cost_usd"] == 0.0 and res["failed_calls"] == 0
    assert len((out / "served.jsonl").read_text("utf-8").splitlines()) == res["calls"]
    assert json.loads((out / "bench.json").read_text("utf-8"))["case"] == "case05"


def test_no_stance_prompt_goes_out(dry_case05) -> None:
    _, sent, _ = dry_case05
    for b in sent:
        assert set(b["response_format"]["json_schema"]["schema"]["properties"]) == {"assumptions"}


def test_first_pass_counts_what_code_and_model_kept(dry_case05) -> None:
    res, _, out = dry_case05
    fp = agent_bench.first_pass(out / "case05.db", "case05")
    assert fp == res["first_pass"]
    # The model kept nothing, so what the first pass kept is code's own fills from the claim's
    # wording, and the step got every other claim.
    assert fp["kept_core_assumptions"] + fp["left_to_the_step"] == fp["claims"] == 48
    assert fp["left_to_the_step"] == res["step"]["claims_the_filler_left_untested"]
    assert fp["of_them_name_only_what_the_sheet_names"] <= fp["kept_core_assumptions"]
    assert res["with_assumptions_after_both"] == fp["kept_core_assumptions"]


def test_summary_marks_a_step_with_too_few_testable_claims(dry_case05) -> None:
    res, _, _ = dry_case05
    text = agent_bench.summary([res], dry=True)
    assert "DRY RUN" in text and "14B run of record on case05" in text
    few = {**res, "step_scorable": False}
    assert "not scorable as written" in agent_bench.summary([few], dry=True)


def test_estimate_prices_every_model_from_one_dry_run(dry_case05) -> None:
    res, _, _ = dry_case05
    specs = [model(n) for n in agent_bench.DEFAULT_MODELS]
    text = agent_bench.estimate([res], specs)
    assert f"{res['calls']} calls" in text
    assert all(m.name in text for m in specs)
