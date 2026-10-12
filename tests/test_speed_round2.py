"""Faster calls, round 2: runtime speed settings and the one-sitting Mac comparison.

No model runs here. The settings are checked for what they record and pass to llama.cpp, and
the comparison's decision rules (eval/probe/speed_round2.py) are checked on made-up results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.llm.runtime import (
    PLAIN_SPEED,
    RUNTIMES,
    GenerationParams,
    speed_kwargs,
    with_runtime,
)
from eval.probe import speed_round2 as r2

OLD_RECORD_KEYS = {"max_tokens", "temperature", "seed", "n_ctx", "n_gpu_layers", "grammar"}


# ---------------------------------------------------------------- runtime settings


def test_plain_runtime_records_and_loads_as_before():
    # Stored outputs are reused only under the same recorded params, so the plain runtime
    # must record exactly what runs recorded before the speed settings existed.
    p = GenerationParams()
    assert set(p.as_record()) == OLD_RECORD_KEYS
    assert speed_kwargs(p) == {}
    assert with_runtime(p, "plain") == p


def test_fast_runtime_is_recorded_so_it_never_reuses_plain_outputs():
    flash = with_runtime(GenerationParams(n_ctx=4096), "flash")
    rec = flash.as_record()
    assert rec["flash_attn"] is True and rec["n_batch"] == 1024 and rec["n_ctx"] == 4096
    assert rec != GenerationParams(n_ctx=4096).as_record()
    assert speed_kwargs(flash) == {"flash_attn": True, "n_batch": 1024, "n_ubatch": 1024}


def test_no_think_template_is_recorded():
    p = with_runtime(GenerationParams(), "plain", "no-think")
    assert p.as_record()["chat_template"] == "no-think"
    assert speed_kwargs(p) == {}  # the template is set on the loaded model, not in Llama()


def test_runtime_switch_resets_settings_it_does_not_name():
    lookup = with_runtime(GenerationParams(), "flash-lookup")
    assert with_runtime(lookup, "flash").prompt_lookup == 0
    assert with_runtime(lookup, "plain").as_record() == GenerationParams().as_record()


def test_prompt_lookup_keeps_every_logit():
    pytest.importorskip("llama_cpp")
    kw = speed_kwargs(with_runtime(GenerationParams(), "flash-lookup"))
    assert kw["logits_all"] is True and kw["draft_model"].num_pred_tokens == 10


@pytest.mark.parametrize(
    "bad",
    [
        {"chat_template": "chatml"},
        {"n_batch": 0},
        {"prompt_lookup": -1},
    ],
)
def test_bad_settings_refused(bad):
    with pytest.raises(ValueError):
        GenerationParams(**bad)


def test_unknown_runtime_refused():
    with pytest.raises(ValueError, match="unknown runtime"):
        with_runtime(GenerationParams(), "turbo")


def test_runtimes_only_name_speed_settings():
    for settings in RUNTIMES.values():
        assert set(settings) <= set(PLAIN_SPEED)


# ---------------------------------------------------------------- decision rules


def _probe(recall=1.0, precision=1.0, shown=5, valid=1.0, seconds=40.0):
    bars = {
        "supports_recall_90": recall >= 0.9,
        "contradicts_precision_90": precision >= 0.9,
        "no_contradicts_shown_as_supports": shown == 0,
        "valid_output_100": valid == 1.0,
    }
    return {
        "model": "m",
        "mean_seconds_per_stance_call": seconds,
        "expert_confirms": {
            "supports_recall": recall,
            "contradicts_precision": precision,
            "contradicts_shown_as_supports": shown,
            "stance_valid_output": valid,
            "contradicts_recall": 0.5,
            "expert_load_supports_shown": 49,
            "bars": bars,
            "passes_all": all(bars.values()),
        },
    }


def _write(out: Path, key: str, probe: dict, peak: float = 10.0, calls=None) -> None:
    d = out / key / "probe"
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps([probe]))
    (out / key / "runs.json").write_text(json.dumps({"probe": {"exit": 0, "peak_gb": peak}}))
    if calls:
        lines = [
            json.dumps(
                {
                    "purpose": "stance",
                    "item_id": i,
                    "raw_text": raw,
                    "completion_tokens": 60,
                    "seconds": 30.0,
                }
            )  # fmt: skip
            for i, raw in calls.items()
        ]
        (d / "m.calls.jsonl").write_text("\n".join(lines) + "\n")


def test_holds_bars_against_a_baseline_that_misses_one():
    base = _probe(shown=5)
    assert r2.holds_bars(_probe(shown=5), base) == (True, [])
    assert r2.holds_bars(_probe(shown=3), base)[0]
    ok, why = r2.holds_bars(_probe(shown=6), base)
    assert not ok and "contradicts_shown_as_supports" in why[0]
    ok, why = r2.holds_bars(_probe(recall=0.88), base)
    assert not ok and "supports_recall_90" in why[0]
    # A lower recall that still meets the bar holds it.
    assert r2.holds_bars(_probe(recall=0.92), base)[0]
    assert not r2.holds_bars(_probe(valid=0.99), base)[0]


def test_runtime_choice_takes_the_fastest_that_holds_the_bars(tmp_path):
    _write(tmp_path, "A", _probe(seconds=40.0), peak=11.0)
    _write(tmp_path, "B", _probe(seconds=30.0), peak=11.5)
    _write(tmp_path, "C", _probe(seconds=25.0), peak=11.8)
    assert r2.choose_runtime(tmp_path)["chosen"] == "flash-lookup"


def test_runtime_choice_skips_a_faster_one_that_breaks_a_bar(tmp_path):
    _write(tmp_path, "A", _probe(seconds=40.0))
    _write(tmp_path, "B", _probe(seconds=30.0))
    _write(tmp_path, "C", _probe(seconds=20.0, shown=7))
    assert r2.choose_runtime(tmp_path)["chosen"] == "flash"


def test_runtime_choice_needs_five_percent_and_bounded_memory(tmp_path):
    _write(tmp_path, "A", _probe(seconds=40.0), peak=11.0)
    _write(tmp_path, "B", _probe(seconds=39.0), peak=11.0)  # 2.5% faster: not enough
    _write(tmp_path, "C", _probe(seconds=20.0), peak=16.5)  # 5.5 GB more: too much
    choice = r2.choose_runtime(tmp_path)
    assert choice["chosen"] == "plain"
    by = {c["runtime"]: c for c in choice["candidates"]}
    assert by["flash"]["faster_by_5pct"] is False and by["flash-lookup"]["memory_ok"] is False


def test_choice_is_kept_once_made(tmp_path):
    _write(tmp_path, "A", _probe(seconds=40.0))
    _write(tmp_path, "B", _probe(seconds=30.0))
    _write(tmp_path, "C", _probe(seconds=35.0))
    assert r2.chosen_runtime(tmp_path) == "flash"
    _write(tmp_path, "C", _probe(seconds=10.0))  # a later rewrite does not change a resumed run
    assert r2.chosen_runtime(tmp_path) == "flash"


def test_label_comparison_counts_identical_output_and_changes(tmp_path):
    sup = '{"stance": "supports", "quote": "q", "rationale": "r"}'
    con = '{"stance": "contradicts", "quote": "q", "rationale": "r"}'
    _write(tmp_path, "A", _probe(), calls={"P001": sup, "P002": sup, "P003": con})
    _write(tmp_path, "B", _probe(), calls={"P001": sup, "P002": con, "P003": "garbage"})
    c = r2.compare_labels(tmp_path, "B", "A")
    assert c["items"] == 3 and c["identical_output"] == 1
    assert [(x["id"], x["from"], x["to"]) for x in c["label_changes"]] == [
        ("P002", "supports", "contradicts"),
        ("P003", "contradicts", "invalid"),
    ]


def test_report_on_a_partial_run_and_the_v1_1_decision(tmp_path):
    _write(tmp_path, "A", _probe(seconds=40.0))
    assert "Not reached" in r2.report(tmp_path)
    _write(tmp_path, "B", _probe(seconds=30.0))
    _write(tmp_path, "C", _probe(seconds=35.0))
    r2.chosen_runtime(tmp_path)
    _write(tmp_path, "D", _probe(seconds=20.0, shown=4))
    _write(tmp_path, "E", _probe(seconds=20.0, shown=4))
    md = r2.report(tmp_path)
    assert "1. Runtime: **flash**" in md
    assert "v1.1 holds the bars against v1.0. Ready for Arsh to sign." in md
    assert "No-think template: not recommended" in md
    assert "Output cap: stays at 1024" in md
    _write(tmp_path, "D", _probe(seconds=20.0, shown=6))
    assert "Do not sign." in r2.report(tmp_path)


def test_no_think_recommended_only_when_it_fixes_the_missed_bar(tmp_path):
    for key, shown in (("A", 5), ("B", 5), ("C", 5), ("D", 5), ("E", 2)):
        _write(tmp_path, key, _probe(seconds=40.0 if key == "A" else 30.0, shown=shown))
    r2.chosen_runtime(tmp_path)
    assert "No-think template: recommended" in r2.report(tmp_path)


def test_one_model_picked_from_the_models_file(tmp_path):
    f = tmp_path / "models.json"
    f.write_text(json.dumps([{"name": "qwen3-8b-q4"}, {"name": "qwen3-14b-q4_k_m"}]))
    assert r2.pick_model(f, None)["name"] == "qwen3-14b-q4_k_m"
    assert r2.pick_model(f, "qwen3-8b-q4")["name"] == "qwen3-8b-q4"
    f.write_text(json.dumps([{"name": "a"}, {"name": "b"}]))
    with pytest.raises(SystemExit):
        r2.pick_model(f, None)


def test_steps_compare_one_change_at_a_time():
    by = {s.key: s for s in r2.STEPS}
    assert (by["A"].prompt, by["A"].runtime, by["A"].template) == ("v1_0", "plain", "gguf")
    assert {by["B"].runtime, by["C"].runtime} == set(RUNTIMES) - {"plain"}
    assert by["D"].prompt == "v1_1" and by["D"].runtime == r2.CHOSEN and by["D"].audit
    assert by["E"].template == "no-think" and by["E"].runtime == r2.CHOSEN
    assert set(r2.V10_STEP) == set(RUNTIMES)
    assert all(path.is_file() for path in r2.PROMPTS.values())
