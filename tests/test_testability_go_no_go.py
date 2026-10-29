"""The testability step's go/no-go (plans/agentic.md, approved 2026-10-27), read from one eval
run: GO only when every bar holds against Arsh's X, Y, cap and least denominator, none given
until he sets them and the run has the signed prompt, a held-out case, the rubber-stamp expert
and --repeat, and "insufficient" when too few refusals are testable to decide.

Synthetic case01 only, with the scripted fake model of tests/test_testability.py.
"""

from __future__ import annotations

import json

import pytest

from core.llm.runtime import FakeModel as RuntimeFake
from eval import run_pipeline as rp
from tests.test_testability import ROOT, _eval_answers

SET = {
    "x_percent": 40.0,
    "y_budget": {"calls": 2, "seconds": 120},
    "cap_set": 2,
    "min_testable": 15,
}


def _measures(**changed: object) -> dict:
    """A run's testability measures that pass every bar under SET, with `changed` applied."""
    t = {
        "prompt": "signed",
        "cap": 2,
        "claims_the_filler_left_untested": 20,
        "of_them_the_sheet_makes_testable": 16,
        "converted_and_accepted": 8,
        "mismatch_person_phone_or_window": 0,
        "tries": 30,
        "invalid_outputs": 0,
        "seconds": 1800.0,
        "go_no_go_case": True,
        **SET,
    }
    return {**t, **changed}


SAME = {"identical": True, "predictions": True, "model_calls": True, "calls_compared": 50}


def _decide(
    t: dict,
    expert: str = "rubber-stamp",
    fs: int | None = 0,
    repeat=SAME,  # noqa: ANN001
    gold: str | None = "signed",
) -> dict:
    return rp.testability_go_no_go(t, expert=expert, false_supported=fs, repeat=repeat, gold=gold)


def test_every_bar_held_is_a_go():
    r = _decide(_measures())
    assert r["decision"] == "GO" and r["why"] == []
    assert len(r["checks"]) == 7 and all(c["ok"] for c in r["checks"])
    (conv,) = [c for c in r["checks"] if c["bar"].startswith("conversion")]
    assert conv["value"] == "8 of 16 (50%, Wilson 95% 28% to 72%)"


def test_conversion_exactly_at_x_passes():
    r = _decide(_measures(converted_and_accepted=6, of_them_the_sheet_makes_testable=15))
    assert r["decision"] == "GO"  # 6 of 15 is 40%


@pytest.mark.parametrize(
    ("changed", "fs", "repeat", "bar"),
    [
        ({"converted_and_accepted": 5}, 0, SAME, "conversion at least 40%"),
        ({"mismatch_person_phone_or_window": 1}, 0, SAME, "no try names a different person"),
        ({}, 1, SAME, "0 false supported under the rubber-stamp expert"),
        ({"invalid_outputs": 1}, 0, SAME, "100% valid outputs"),
        ({}, 0, {**SAME, "identical": False, "model_calls": False}, "a byte-identical repeat"),
        ({"tries": 41}, 0, SAME, "at most 2 calls per claim"),
        ({"seconds": 2401.0}, 0, SAME, "at most 120 s per claim"),
    ],
)
def test_any_bar_missed_is_a_no_go_that_names_it(changed, fs, repeat, bar):  # noqa: ANN001
    r = _decide(_measures(**changed), fs=fs, repeat=repeat)
    assert r["decision"] == "NO-GO"
    assert len(r["why"]) == 1 and r["why"][0].startswith(bar)


def test_a_repeat_that_differs_says_what_differs():
    r = _decide(_measures(), repeat={**SAME, "identical": False, "model_calls": False})
    (rep,) = [c for c in r["checks"] if c["bar"] == "a byte-identical repeat"]
    assert rep["value"] == "different (model_calls), 50 filler and step calls compared"


def test_too_few_testable_refusals_is_insufficient_not_a_decision():
    r = _decide(_measures(of_them_the_sheet_makes_testable=14, converted_and_accepted=14))
    assert r["decision"] == "insufficient" and r["checks"] == []
    assert "14 refusals the sheet makes testable, fewer than the 15" in r["why"][0]


def test_no_decision_until_arsh_sets_the_values_and_the_run_can_measure_every_bar():
    unset = {k: None for k in rp.GO_NO_GO_SETTINGS}
    r = _decide(
        _measures(**unset, prompt="DRAFT, not signed by Arsh", go_no_go_case=False),
        expert="simulated",
        fs=None,
        repeat=None,
    )
    assert r["decision"] == "none given" and r["checks"] == []
    assert r["why"] == [
        "x_percent, y_budget, cap_set, min_testable not set by Arsh",
        "the prompt is a draft",
        "this is not a held-out go/no-go case",
        "the false-supported bar needs --expert rubber-stamp",
        "the byte-identical repeat needs --repeat",
        "no gold key to score false supported",
    ]
    r = _decide(_measures(cap=3))
    assert r["decision"] == "none given" and r["why"] == ["the run's cap is 3, not Arsh's 2"]


def test_a_draft_gold_key_gives_none():
    """False supported is scored against Arsh's signed key only, never the builder's draft."""
    r = _decide(_measures(), gold="draft, not signed by Arsh (48/48 claims marked DRAFT)")
    assert r["decision"] == "none given"
    assert r["why"] == ["the gold key is a draft, not signed by Arsh"]


def test_the_wilson_interval():
    low, high = rp.wilson(6, 15)
    assert (round(low, 3), round(high, 3)) == (0.198, 0.643)
    assert rp.wilson(1, 1)[1] == 1.0


def _run(tmp_path, monkeypatch, answers=_eval_answers):  # noqa: ANN001, ANN202
    """One eval run of C01 with the step, under the rubber-stamp expert, as a go/no-go case."""
    monkeypatch.setattr(rp, "TESTABILITY_GO_NO_GO_CASES", frozenset({"case01"}))
    monkeypatch.setattr(rp, "TESTABILITY_X_PERCENT", 40.0)
    monkeypatch.setattr(rp, "TESTABILITY_Y_BUDGET", {"calls": 1, "seconds": 600})
    monkeypatch.setattr(rp, "TESTABILITY_CAP", 1)
    monkeypatch.setattr(rp, "TESTABILITY_MIN_TESTABLE", 1)
    model = RuntimeFake(respond=answers)
    return rp.run_once(
        "case01",
        "real",
        "accept",
        tmp_path,
        None,
        "rubber-stamp",
        labeler_model=model,
        claim_ids=["C01"],
        filler_model=model,
        testability_cap=1,
        testability_model=model,
    )


def test_a_run_and_its_repeat_give_a_go_with_the_hardware_recorded(tmp_path, monkeypatch, capsys):
    assert (ROOT / rp.TESTABILITY_SIGNED_PROMPT).exists()  # the run uses Arsh's signed prompt
    first = _run(tmp_path, monkeypatch)
    second = _run(tmp_path / "repeat", monkeypatch)
    r = rp.report_go_no_go("case01", tmp_path, "rubber-stamp", first, second)
    assert r["decision"] == "GO", r
    record = json.loads((tmp_path / "go_no_go.json").read_text("utf-8"))
    assert record["decision"] == "GO" and record["repeat"]["identical"]
    assert record["gold"]["status"] == "signed"
    assert record["repeat"]["calls_compared"] > 0  # the filler's and the step's calls
    assert set(record["hardware"]) >= {
        "platform",
        "machine",
        "cpus",
        "memory_gb",
        "measured_at_utc",
    }
    assert record["testability"]["prompt"] == "signed"
    printed = capsys.readouterr().out
    assert "pipeline: testability go/no-go: GO\n" in printed
    assert "pipeline: testability go/no-go: pass: 0 false supported" in printed


def test_a_repeat_whose_step_answers_differ_is_a_no_go(tmp_path, monkeypatch, capsys):
    first = _run(tmp_path, monkeypatch)

    def reworded(prompt: str) -> str:  # the filler's and the step's answers, one byte longer
        out = _eval_answers(prompt)
        return out if '"stance"' in out else out + " "

    second = _run(tmp_path / "repeat", monkeypatch, answers=reworded)
    r = rp.report_go_no_go("case01", tmp_path, "rubber-stamp", first, second)
    assert r["decision"] == "NO-GO" and r["why"] == ["a byte-identical repeat"]
    assert "FAIL: a byte-identical repeat: different (model_calls)" in capsys.readouterr().out


def test_without_the_repeat_or_the_rubber_stamp_expert_none_is_given(tmp_path, monkeypatch):
    first = _run(tmp_path, monkeypatch)
    r = rp.report_go_no_go("case01", tmp_path, "rubber-stamp", first, None)
    assert r["decision"] == "none given"
    assert r["why"] == ["the byte-identical repeat needs --repeat"]
    r = rp.report_go_no_go("case01", tmp_path, "simulated", first, None)
    assert "the false-supported bar needs --expert rubber-stamp" in r["why"]
