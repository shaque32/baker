"""The local model repeat check (eval/probe/repeat_check.py), on scripted models: no model file
is needed. Synthetic case01 and the signed probe set only."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

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


def test_failed_or_unparsed_answers_never_count_as_a_match():
    """Empty answers from failed generations, or malformed text, are failures, not matches."""
    a = [{"key": "P1", "prompt_sha256": "p", "raw": "", "error": "llama failed"},
         {"key": "P2", "prompt_sha256": "p", "raw": "not json"},
         {"key": "P3", "prompt_sha256": "p", "raw": ANSWER % "x"}]  # fmt: skip
    b = [{"key": "P1", "prompt_sha256": "p", "raw": "", "error": "llama failed"},
         {"key": "P2", "prompt_sha256": "p", "raw": "also not json"},
         {"key": "P3", "prompt_sha256": "p", "raw": ANSWER % "x"}]  # fmt: skip
    c = rc.compare(a, b)
    assert (c["compared"], c["failed"], c["raw_identical"], c["label_identical"]) == (3, 2, 1, 1)
    assert [f["key"] for f in c["failures"]] == ["P1", "P2"]
    assert "Failed answers" in rc.markdown({"A_same_process_repeat": c})


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
    assert s["stages"]["D1"] and s["stages"]["D2"]  # both audits' metadata is summarized


def test_the_metadata_records_the_digest_the_run_computed(tmp_path, monkeypatch):
    """An entry with no sha256 (models.example.json) records the digest the run worked out."""
    import core.llm.runtime as runtime

    models = tmp_path / "models.example.json"
    models.write_text(json.dumps([{"name": "qwen3-14b", "path": "x.gguf", "sha256": None}]))
    monkeypatch.setattr(runtime, "sha256_file", lambda path: "f" * 64)
    import core.audit._local_model as lm

    monkeypatch.setattr(lm, "LazyModel", _Lazy)
    rc.stage_case(_args(tmp_path, models=models), "D1")
    assert json.loads((tmp_path / "D1.meta.json").read_text())["model_sha256"] == "f" * 64


def test_the_dry_run_estimates_without_a_model(capsys):
    assert rc.main(["--dry-run", "--claims", "C01"]) == 0
    est = json.loads(capsys.readouterr().out)
    assert est["calls"]["A"] == 2 * est["calls"]["B"] > 0 and est["estimated_hours"] > 0


def _finished_run(folder: Path, sha: str, a_rows: list[dict], machine: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "A.jsonl").write_text("".join(json.dumps(r) + "\n" for r in a_rows))
    summary = {"model_sha256": sha, "machine": machine, "gpu": None, "host": {"aws_ami_id": None}}
    (folder / "summary.json").write_text(json.dumps(summary))
    return folder


def test_two_machines_are_compared_on_first_asks_only(tmp_path, capsys):
    """AWS against the Mac: each run's first asks, matched by item and prompt digest."""
    sha = "5" * 64
    first = _finished_run(
        tmp_path / "aws",
        sha,
        [
            {"key": "P1", "ask": 1, "prompt_sha256": "p", "raw": ANSWER % "x"},
            {"key": "P1", "ask": 2, "prompt_sha256": "p", "raw": ANSWER % "second ask"},
            {"key": "P2", "ask": 1, "prompt_sha256": "p", "raw": ANSWER % "y"},
        ],  # fmt: skip
        "Linux-x86_64",
    )
    second = _finished_run(
        tmp_path / "mac",
        sha,
        [
            {"key": "P1", "ask": 1, "prompt_sha256": "p", "raw": ANSWER % "x"},
            {"key": "P2", "ask": 1, "prompt_sha256": "p", "raw": ANSWER % "reworded"},
            {"key": "P3", "ask": 1, "prompt_sha256": "p", "raw": ANSWER % "z"},
        ],  # fmt: skip
        "macOS-15.6.1-arm64",
    )
    out = tmp_path / "cross"
    assert rc.main(["--compare", str(first), str(second), "--out", str(out)]) == 0
    result = json.loads((out / "cross.json").read_text())
    probe = result["probe"]
    assert (probe["compared"], probe["raw_identical"], probe["label_identical"]) == (2, 1, 2)
    assert probe["only_in_second"] == 1 and "case01" not in result
    md = capsys.readouterr().out
    assert "Linux-x86_64" in md and "macOS-15.6.1-arm64" in md and "not in both runs" in md


def test_runs_of_different_model_files_are_never_compared(tmp_path):
    row = [{"key": "P1", "ask": 1, "prompt_sha256": "p", "raw": ANSWER % "x"}]
    first = _finished_run(tmp_path / "a", "1" * 64, row, "m")
    second = _finished_run(tmp_path / "b", "2" * 64, row, "m")
    result = rc.compare_runs(first, second)
    assert "refused" in result and "probe" not in result
    assert "Not compared" in rc.cross_markdown(result)
    assert rc.main(["--compare", str(first), str(second)]) == 1


def test_the_summary_names_the_cloud_machine(tmp_path, monkeypatch):
    """--host (eval/probe/aws_repeat.sh) lands in the summary and its markdown."""
    _scripted(monkeypatch, lambda p: ANSWER % "same")
    monkeypatch.setattr(rc.subprocess, "run", _no_subprocess)
    host = tmp_path / "host.json"
    host.write_text(json.dumps({"aws_ami_id": "ami-0abc", "aws_instance_type": "g5.xlarge"}))
    models = tmp_path / "models.json"
    models.write_text(json.dumps([{"name": "qwen3-14b", "path": "x.gguf", "sha256": "0" * 64}]))
    out = tmp_path / "run"
    rc.main(["--models", str(models), "--stages", "A", "--out", str(out), "--host", str(host)])
    summary = json.loads((out / "summary.json").read_text())
    assert summary["host"]["aws_instance_type"] == "g5.xlarge"
    assert "- aws_ami_id: ami-0abc" in (out / "summary.md").read_text()


def _no_subprocess(cmd, **kw):  # noqa: ANN001, ANN003, ANN202
    """Stage processes run in-process here; git and nvidia-smi report nothing."""
    import subprocess

    if cmd[:3] == [rc.sys.executable, "-m", "eval.probe.repeat_check"]:
        args = rc.argparse.Namespace(
            models=Path(cmd[cmd.index("--models") + 1]), model=None,
            stance_prompt=rc.prompts.STANCE_SIGNED, cpu_items=2, claims=("C01",), n_ctx=4096,
            chat_template="gguf", out=Path(cmd[cmd.index("--out") + 1]),
        )  # fmt: skip
        rc.stage_probe(args, cmd[cmd.index("--stage") + 1])
        return subprocess.CompletedProcess(cmd, 0, "", "")
    raise OSError("not on this machine")


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize(
    "script", ["eval/aws_setup.sh", "eval/validation/aws_run.sh", "eval/probe/aws_repeat.sh"]
)
def test_the_aws_scripts_parse(script):
    root = Path(__file__).resolve().parents[1]
    bash = shutil.which("bash")
    assert subprocess.run([bash, "-n", str(root / script)], check=False).returncode == 0  # noqa: S603
