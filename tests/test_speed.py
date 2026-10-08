"""Fewer model calls: stored-output reuse, lazy model loading, the optional AI reviewer.

Fake models only; no weights, no network.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core import pipeline
from core.audit import _local_model as lm
from core.audit._llm_json import ModelUnavailable
from core.contracts import EvidenceStatus, Stance, canonical_json
from core.db import connect
from eval import run_pipeline
from eval.pipeline_fakes import fake_components

SHA = "cd" * 32
SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}}
NOW = datetime(2026, 10, 8, tzinfo=UTC)


@dataclass
class Out:
    raw_text: str
    seconds: float = 0.5
    prompt_tokens: int = 100
    completion_tokens: int = 20


@dataclass
class Counting:
    reply: str = '{"x": "y"}'
    name: str = "fake-14b"
    sha256: str = SHA
    prompts: list[str] = field(default_factory=list)

    def generate_json(self, prompt, schema, params=None):
        self.prompts.append(prompt)
        return Out(self.reply)


def _store(conn: sqlite3.Connection, opened: lm.OpenedRun, prompt: str, raw: str, outcome: str):
    r = opened.run
    conn.execute(
        "INSERT OR IGNORE INTO model_runs (id, pipeline_run_id, purpose, model_name, model_sha256,"
        " prompt_version, prompt_sha256, params_json, seed, started_at_utc)"
        " VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 't')",
        (
            r.id,
            r.purpose,
            r.model_name,
            r.model_sha256,
            r.prompt_version,
            r.prompt_sha256,
            canonical_json(r.params),
            r.seed,
        ),
    )
    seq = lm.next_call_seq(conn, r.id)
    conn.execute(
        "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt, raw_output,"
        " outcome, at_utc) VALUES (?, ?, ?, '[]', ?, ?, ?, 't')",
        (f"mc:{r.id}#{seq}", r.id, seq, prompt, raw, outcome),
    )


_TICK = iter(range(1, 10_000))


def _open(conn, model, template="T {a}", schema=SCHEMA, purpose="stance", **kw):
    """Each run opens one second after the last, so run ids differ as they do in a real run."""
    at = datetime.fromtimestamp(NOW.timestamp() + next(_TICK), UTC)
    return lm.open_run(conn, purpose, template, model=model, schema=schema, clock=lambda: at, **kw)


# ---------------------------------------------------------------- stored-output reuse


def test_identical_prompt_reuses_the_stored_output(case_db):
    model = Counting()
    first = _open(case_db, model)
    assert first.run.params[lm.REUSE_PARAM] is True
    assert first.port.generate("P1", SCHEMA) == '{"x": "y"}'
    _store(case_db, first, "P1", '{"x": "stored"}', "ok")

    second = _open(case_db, model)
    assert second.run.id != first.run.id
    assert second.port.generate("P1", SCHEMA) == '{"x": "stored"}'
    assert model.prompts == ["P1"]  # the second call never reached the model
    assert second.port.reused == 1 and second.port.stats[0].reused


@pytest.mark.parametrize(
    "change",
    [
        {"template": "T2 {a}"},  # another prompt file
        {"schema": {"type": "object"}},  # another output schema
        {"purpose": "review"},
    ],
)
def test_anything_else_changed_calls_the_model(case_db, change):
    model = Counting()
    first = _open(case_db, model)
    _store(case_db, first, "P1", '{"x": "stored"}', "ok")
    second = _open(case_db, model, **change)
    assert second.port.generate("P1", SCHEMA) == '{"x": "y"}'
    assert second.port.reused == 0


def test_another_model_file_or_prompt_calls_the_model(case_db):
    first = _open(case_db, Counting())
    _store(case_db, first, "P1", '{"x": "stored"}', "ok")
    other = _open(case_db, Counting(sha256="ef" * 32))
    assert other.port.generate("P1", SCHEMA) == '{"x": "y"}'
    same = _open(case_db, Counting())
    assert same.port.generate("P2", SCHEMA) == '{"x": "y"}'


def test_other_generation_settings_call_the_model(case_db):
    @dataclass
    class Params:
        seed: int

        def as_record(self):
            return {"seed": self.seed, "temperature": 0.0}

    a, b = Counting(), Counting()
    a.params, b.params = Params(1), Params(2)  # type: ignore[attr-defined]
    first = _open(case_db, a)
    _store(case_db, first, "P1", '{"x": "stored"}', "ok")
    assert _open(case_db, b).port.generate("P1", SCHEMA) == '{"x": "y"}'
    assert _open(case_db, a).port.generate("P1", SCHEMA) == '{"x": "stored"}'


def test_runtime_errors_are_never_reused_but_bad_output_is(case_db):
    first = _open(case_db, Counting())
    _store(case_db, first, "P1", "", "error")
    _store(case_db, first, "P2", "not json", "invalid_output")
    second = _open(case_db, Counting())
    assert second.port.generate("P1", SCHEMA) == '{"x": "y"}'
    assert second.port.generate("P2", SCHEMA) == "not json"  # fails again, the same way


def test_reuse_off_always_calls_the_model(case_db):
    model = Counting()
    first = _open(case_db, model)
    _store(case_db, first, "P1", '{"x": "stored"}', "ok")
    cold = _open(case_db, model, reuse=False)
    assert lm.REUSE_PARAM not in cold.run.params
    assert cold.port.generate("P1", SCHEMA) == '{"x": "y"}'
    stat = cold.port.stats[0]
    assert (stat.seconds, stat.prompt_tokens, stat.completion_tokens) == (0.5, 100, 20)


# ---------------------------------------------------------------- lazy loading


def _cfg(tmp_path: Path, **over) -> lm.ModelConfig:
    path = tmp_path / "m.gguf"
    path.write_bytes(b"not a real model")
    return lm.ModelConfig(name="m", path=path, sha256=SHA, **over)


def test_config_takes_an_optional_context_size(tmp_path):
    cfg = {"name": "m", "path": str(tmp_path / "m.gguf"), "sha256": SHA, "n_ctx": 4096}
    (tmp_path / "model.json").write_text(json.dumps(cfg))
    assert lm.load_config(tmp_path / "model.json").n_ctx == 4096
    (tmp_path / "model.json").write_text(json.dumps({**cfg, "n_ctx": 10}))
    with pytest.raises(lm.ModelConfigError):
        lm.load_config(tmp_path / "model.json")


def test_lazy_model_opens_a_run_without_loading(tmp_path, case_db):
    lazy = lm.LazyModel(_cfg(tmp_path, n_ctx=4096))
    opened = _open(case_db, lazy)
    assert not lazy.loaded
    assert opened.run.model_sha256 == SHA and opened.run.params["n_ctx"] == 4096


def test_lazy_model_refuses_a_missing_file(tmp_path):
    with pytest.raises(lm.ModelConfigError):
        lm.LazyModel(lm.ModelConfig(name="m", path=tmp_path / "nope.gguf", sha256=SHA))


def test_a_model_that_cannot_load_stops_the_run(tmp_path, monkeypatch, conn):
    """A wrong hash is found on first use. It must stop the run, never look like 'no evidence'."""
    from core.audit import stance

    def broken(*a, **kw):
        raise ValueError("sha256 mismatch")

    monkeypatch.setattr("core.llm.runtime.LlamaCppModel", broken)
    lazy = lm.LazyModel(_cfg(tmp_path))
    comps = fake_components()
    comps.labeler = stance.create(conn, model=lazy)
    comps.model_runs = (*comps.model_runs, *comps.labeler.model_runs)
    with pytest.raises(ModelUnavailable, match="sha256 mismatch"):
        pipeline.run_audit(conn, comps)
    status = conn.execute("SELECT status FROM pipeline_runs").fetchone()[0]
    assert status == "failed"
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 0


# ---------------------------------------------------------------- optional AI reviewer


@pytest.fixture(scope="module")
def built_case(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("case") / "case01.db"
    run_pipeline.build_case("case01", path).close()  # type: ignore[attr-defined]
    return path


@pytest.fixture
def conn(built_case, tmp_path):
    copy = tmp_path / "case.db"
    shutil.copy(built_case, copy)
    c = connect(copy)
    yield c
    c.close()


def test_without_the_ai_reviewer_items_stay_open_for_the_expert(conn):
    comps = fake_components(accept=True)
    comps.reviewer = None
    result = pipeline.run_audit(conn, comps)
    assert result.stored_items > 0 and result.reviewer_failures == 0
    assert conn.execute("SELECT COUNT(*) FROM evidence_reviews").fetchone()[0] == 0
    run = pipeline.last_run(conn)
    assert run["components"]["reviewer"] == "none"
    supports = [
        e
        for ids in run["manifest"].values()
        for e in pipeline.load_evidence(conn, ids["evidence"])
        if e.stance == Stance.SUPPORTS
    ]
    assert supports and all(e.status == EvidenceStatus.OPEN for e in supports)


def test_real_components_leave_out_the_reviewer_unless_asked(conn, monkeypatch):
    monkeypatch.setenv(lm.MODEL_CONFIG_ENV, "/nonexistent/model.json")
    fakes = fake_components()
    replace = {"labeler": fakes.labeler}
    filler = run_pipeline.spec_filler(Path("eval/probe_draft/case01_assumptions.jsonl"))
    comps = pipeline.real_components(conn, replace=replace, filler=filler)
    assert comps.reviewer is None
    assert not any(m.purpose == "review" for m in comps.model_runs)
    with pytest.raises(lm.ModelConfigError):  # asking for it needs the model config
        pipeline.real_components(conn, replace=replace, filler=filler, ai_review=True)
    given = pipeline.real_components(
        conn, replace={**replace, "reviewer": fakes.reviewer}, filler=filler
    )
    assert given.reviewer is fakes.reviewer


def test_a_rerun_reuses_every_stance_output(conn):
    """The expert's rerun after accepting evidence costs no model calls."""
    from core.audit import stance
    from core.llm.runtime import FakeModel

    model = FakeModel(respond=lambda p: '{"stance": "irrelevant", "quote": "", "rationale": "n"}')
    filler = run_pipeline.spec_filler(Path("eval/probe_draft/case01_assumptions.jsonl"))

    def run():
        lab = stance.create(conn, model=model)
        comps = pipeline.real_components(conn, replace={"labeler": lab}, filler=filler)
        return pipeline.run_audit(conn, comps, claim_ids=["C02", "C05"]), lab

    first, lab1 = run()
    n = len(model.calls)
    assert n > 0 and first.model_outputs_reused == 0
    second, lab2 = run()
    assert len(model.calls) == n  # nothing new reached the model
    assert second.model_outputs_reused == n
    rows = conn.execute(
        "SELECT COUNT(*) FROM model_calls WHERE model_run_id = ?", (lab2.model_runs[0].id,)
    ).fetchone()[0]
    assert rows == n  # still recorded under the new run
    assert pipeline.last_run(conn)["model_outputs_reused"] == n
