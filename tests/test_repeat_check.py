"""The local model repeat check (eval/probe/repeat_check.py), on scripted models: no model file
is needed. Synthetic case01 and the signed probe set only."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from core.llm.runtime import FakeModel, GenerationParams
from eval.probe import repeat_check as rc

ANSWER = '{"stance": "irrelevant", "quote": "", "rationale": "%s"}'


def _args(tmp_path: Path, **kw) -> argparse.Namespace:  # noqa: ANN003
    models = tmp_path / "models.json"
    models.write_text(json.dumps([{"name": "qwen3-14b", "path": "x.gguf", "sha256": "0" * 64}]))
    base = {
        "models": models,
        "model": None,
        "stance_prompt": rc.prompts.STANCE_SIGNED,
        "cpu_items": 2,
        "claims": ("C01",),
        "n_ctx": 4096,
        "chat_template": "gguf",
        "out": tmp_path,
    }
    return argparse.Namespace(**{**base, **kw})


def _scripted(monkeypatch, respond) -> None:  # noqa: ANN001
    monkeypatch.setattr(rc, "_probe_items", lambda limit=None: rc._probe_items_all()[: limit or 3])
    monkeypatch.setattr(
        rc,
        "_load",
        lambda entry, n_ctx, gpu, chat_template="gguf": (
            FakeModel(respond=respond),
            GenerationParams(),
        ),
    )


def test_compare_counts_identical_bytes_and_labels_apart():
    a = [{"key": "P1", "prompt_sha256": "p", "raw": ANSWER % "x"},
         {"key": "P2", "prompt_sha256": "p", "raw": ANSWER % "y"}]  # fmt: skip
    b = [{"key": "P1", "prompt_sha256": "p", "raw": ANSWER % "x"},
         {"key": "P2", "prompt_sha256": "p", "raw": ANSWER % "other words"}]  # fmt: skip
    c = rc.compare(a, b)
    assert (c["compared"], c["raw_identical"], c["label_identical"]) == (2, 1, 2)
    assert [d["key"] for d in c["differences"]] == ["P2"]
    other = [{"key": "P2", "prompt_sha256": "q", "raw": ANSWER % "y"}]  # another prompt
    assert rc.compare(a, other)["compared"] == 0


def test_a_deterministic_model_repeats_exactly(tmp_path, monkeypatch):
    _scripted(monkeypatch, lambda p: ANSWER % "same")
    rc.stage_probe(_args(tmp_path), "A")
    rc.stage_probe(_args(tmp_path), "B")
    s = rc.summarize(tmp_path)
    assert (
        s["A_same_process_repeat"]["raw_identical"] == 3 == s["A_same_process_repeat"]["compared"]
    )
    assert s["B_fresh_load_vs_A"]["raw_identical"] == 3
    assert "identical bytes" in rc.markdown(s)


def test_drift_in_wording_is_reported_even_when_the_label_holds(tmp_path, monkeypatch):
    n = {"calls": 0}

    def drifting(prompt: str) -> str:
        n["calls"] += 1
        return ANSWER % f"wording {n['calls']}"

    _scripted(monkeypatch, drifting)
    rc.stage_probe(_args(tmp_path), "A")
    c = rc.summarize(tmp_path)["A_same_process_repeat"]
    assert c["raw_identical"] == 0 and c["label_identical"] == 3 and len(c["differences"]) == 3


def test_the_cpu_stage_asks_only_the_first_items(tmp_path, monkeypatch):
    _scripted(monkeypatch, lambda p: ANSWER % "same")
    rc.stage_probe(_args(tmp_path), "A")
    rc.stage_probe(_args(tmp_path, cpu_items=2), "C")
    c = rc.summarize(tmp_path)["C_cpu_vs_A"]
    assert c["compared"] == 2 and c["raw_identical"] == 2


@dataclass
class _Lazy:
    """Stands in for core.audit._local_model.LazyModel."""

    cfg: object
    name: str = "qwen3-14b"
    sha256: str = "0" * 64
    params: GenerationParams = field(default_factory=GenerationParams)

    def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
        return FakeModel(respond=lambda p: ANSWER % "case").generate_json(prompt, schema, params)


def test_two_case01_audits_are_compared_by_stored_output(tmp_path, monkeypatch):
    import core.audit._local_model as lm

    monkeypatch.setattr(lm, "LazyModel", _Lazy)
    for stage in ("D1", "D2"):
        rc.stage_case(_args(tmp_path), stage)
    s = rc.summarize(tmp_path)
    c = s["D_case01_two_audits"]
    assert c["compared"] > 0 and c["raw_identical"] == c["compared"]
    assert s["D_case01_evidence"]["same_rows"]
    meta = json.loads((tmp_path / "D1.meta.json").read_text())
    assert meta["model"] == "qwen3-14b" and meta["calls"] == c["compared"]


def test_the_dry_run_estimates_without_a_model(capsys):
    assert rc.main(["--dry-run", "--claims", "C01"]) == 0
    est = json.loads(capsys.readouterr().out)
    assert est["calls"]["A"] == 2 * est["calls"]["B"] > 0 and est["estimated_hours"] > 0
