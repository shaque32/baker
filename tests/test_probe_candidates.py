"""The local-model screen (eval/probe/candidates.py): entries, the stage 1 rule, the verdict."""

from __future__ import annotations

import json
from pathlib import Path

from eval.probe import candidates as cand

BARS_MET = {
    "valid_output_100": True,
    "supports_recall_90": True,
    "contradicts_precision_90": True,
    "no_contradicts_shown_as_supports": True,
}


def row(moved: int = 0, **bars: bool) -> dict:
    return {
        "model": "m",
        "mean_seconds_per_stance_call": 9.5,
        "tokens_per_second": 21.3,
        "sha256": "ab" * 32,
        "params": {"seed": 1234, "temperature": 0.0, "n_ctx": 8192},
        "stance_prompt": "stance_cloud.md@1.2",
        "stance_failures": [
            {"id": "P039", "category": "c", "expected": "complicates", "got": "contradicts"},
            {"id": "P050", "error": "bad_json", "raw": ""},
        ],
        "expert_confirms": {
            "supports_recall": 0.95,
            "contradicts_precision": 1.0,
            "contradicts_shown_as_supports": 0,
            "moved_traps_shown_as_supports": moved,
            "stance_valid_output": 1.0,
            "bars": {**BARS_MET, **bars},
            "confusion": {"contradicts": {"contradicts": 9}, "complicates": {"contradicts": 1}},
            "reported": {
                "gold_supports": 40,
                "supports_recall_95ci": [0.83, 0.99],
                "contradicts_precision_95ci": [0.6, 0.98],
            },
        },
    }


def test_candidates_are_pinned_and_commercially_licensed():
    for c in cand.CANDIDATES:
        assert len(c.revision) == 40 and len(c.sha256) == 64
        assert c.license == "Apache-2.0"
        assert c.chat_template in ("gguf", "no-think")
    assert cand.BY_NAME["qwen3.8-27b-ud-iq4_xs"].chat_template == "no-think"
    assert set(cand.PROMPTS) == {"v1.1", "v1.2"}
    for path in cand.PROMPTS.values():
        assert Path(path).is_file()


def test_models_entry_carries_the_hash_the_loader_checks(tmp_path):
    c = cand.CANDIDATES[0]
    entry = cand.models_entry(c, tmp_path)
    assert entry["path"] == str(tmp_path / c.file)
    assert entry["sha256"] == c.sha256 and entry["license"] == "Apache-2.0"
    assert c.revision in entry["source"]


def test_stage1_needs_every_bar_and_no_moved_traps():
    assert cand.stage1(row()) == (True, [])
    ok, missed = cand.stage1(row(contradicts_precision_90=False))
    assert not ok and missed == ["contradicts_precision_90"]
    ok, missed = cand.stage1(row(moved=2))
    assert not ok and missed == ["moved traps shown as supports: 2"]
    assert cand.stage1({"model": "m", "load_error": "boom"}) == (False, ["did not load: boom"])
    assert not cand.stage1({"model": "m"})[0]


def write(out: Path, name: str, version: str, rows: list[dict]) -> None:
    folder = out / name / version
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps(rows), encoding="utf-8")


def test_verdict_names_the_passing_model_and_prompt(tmp_path):
    first, second = cand.CANDIDATES[0].name, cand.CANDIDATES[1].name
    write(tmp_path, first, "v1.1", [row(moved=1)])
    write(tmp_path, first, "v1.2", [row()])
    write(tmp_path, second, "v1.1", [{"model": second, "load_error": "no such file"}])
    text = cand.verdict(tmp_path)
    assert f"Stage 1 PASS: {first} with v1.2" in text
    assert f"| {second} | v1.1 | n/a" in text and "did not load: no such file" in text
    assert f"| {second} | v1.2 | not run |" in text
    assert "| 95% of 40 [83%-99%] | 100% of 10 [60%-98%] |" in text
    assert "9.5 | 21.3 |" in text
    wrong = "P039 (complicates -> contradicts), P050 (no valid answer: bad_json)"
    assert f"- {first} v1.1: {wrong}" in text
    assert "sha256 " + "ab" * 32 + ", seed 1234" in text
    assert "fresh held-out items" in text


def test_verdict_says_plainly_when_nothing_passes(tmp_path):
    for c in cand.CANDIDATES:
        for version in cand.PROMPTS:
            write(tmp_path, c.name, version, [row(supports_recall_90=False)])
    assert "no candidate passes. The 14B stays the local model." in cand.verdict(tmp_path)


def test_an_unfinished_screen_decides_nothing(tmp_path):
    first, second = cand.CANDIDATES[0].name, cand.CANDIDATES[1].name
    write(tmp_path, first, "v1.1", [row(supports_recall_90=False)])
    write(tmp_path, second, "v1.1", [{"model": second, "load_error": "boom"}])
    text = cand.verdict(tmp_path)
    assert "Stage 1 INCOMPLETE" in text and f"{first} v1.2" in text and f"{second} v1.1" in text
    assert "The 14B stays" not in text
