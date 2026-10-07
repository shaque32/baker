"""create(conn) wiring for the pipeline, on a fake local model (no weights, no network)."""

import json
import sqlite3
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from core.audit import review as review_mod
from core.audit import stance as stance_mod
from core.audit._llm_json import PromptMissingError, prompt_body
from core.audit._local_model import ModelConfigError, load_config
from core.contracts import (
    EvidenceCandidate,
    EvidenceItem,
    EvidenceStatus,
    ProvenanceTier,
    SourceRef,
    Stance,
)
from tests.fake_model import make_assumption

SHA = "ab" * 32


@dataclass
class _Out:
    raw_text: str


@dataclass
class FakeLocal:
    replies: list[str]
    name: str = "fake-14b"
    sha256: str = SHA
    prompts: list[str] = field(default_factory=list)

    def generate_json(self, prompt, schema, params=None):
        self.prompts.append(prompt)
        return _Out(self.replies.pop(0))


def write_cfg(tmp_path: Path, **over) -> Path:
    cfg = {"name": "m", "path": str(tmp_path / "m.gguf"), "sha256": SHA, **over}
    p = tmp_path / "model.json"
    p.write_text(json.dumps(cfg))
    return p


def test_config_loads(tmp_path):
    cfg = load_config(write_cfg(tmp_path))
    assert cfg.name == "m" and cfg.sha256 == SHA


@pytest.mark.parametrize("over", [{"sha256": "abc"}, {"name": " "}, {"sha256": None}])
def test_bad_config_is_refused(tmp_path, over):
    with pytest.raises(ModelConfigError):
        load_config(write_cfg(tmp_path, **over))


def test_missing_config_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("BAKER_MODEL_CONFIG", str(tmp_path / "nope.json"))
    with pytest.raises(ModelConfigError):
        load_config()


def _v02(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(evidence_reviews)")}
    if "reason" not in cols:
        pytest.skip("schema v0.2 not applied yet")
    conn.execute("PRAGMA foreign_keys = OFF")


def test_review_create_wires_run_recorder_and_prior_reviews(case_db):
    _v02(case_db)
    model = FakeLocal(['{"decision": "accept", "reason": "Plainly says so."}'])
    rev = review_mod.create(case_db, model=model)
    (run,) = rev.model_runs
    assert run.purpose == "review" and run.model_name == "fake-14b" and run.model_sha256 == SHA
    assert run.prompt_version == rev.prompt_version
    assert rev.reviewer == "ai:fake-14b"

    a = make_assumption("The sender asked to meet at the garage.")
    item = EvidenceItem(
        id="ev:x",
        assumption_id=a.id,
        record_id="msg:1",
        ref=SourceRef(source_id="s", locator="l"),
        stance=Stance.SUPPORTS,
        quote="meet me at the garage",
        quote_verified=True,
        rationale="",
        tier=ProvenanceTier.OBSERVED,
        status=EvidenceStatus.OPEN,
        model_run_id="r",
    )
    # A call row already stored for this run: numbering continues after it.
    case_db.execute(
        "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt, raw_output,"
        " outcome, at_utc) VALUES (?, ?, 1, '[]', 'p', '', 'error', 't')",
        (f"mc:{run.id}#1", run.id),
    )
    d = rev.review(a, item, ">> line")
    assert d.status is EvidenceStatus.AI_ACCEPTED
    assert d.model_run_id == run.id and d.model_call_id == f"mc:{run.id}#2"
    review_mod.insert_review(case_db, d)
    with pytest.raises(review_mod.NotReviewableError):
        rev.review(a, item, ">> line")  # already has a decision in the table


def test_stance_create_needs_signed_prompt(case_db, monkeypatch):
    monkeypatch.setitem(sys.modules, "core.audit.context", types.SimpleNamespace())
    if (stance_mod.PROMPTS_DIR / "stance.md").exists():
        pytest.skip("signed stance prompt exists")
    with pytest.raises((PromptMissingError, ImportError)):
        stance_mod.create(case_db, model=FakeLocal([]))


def test_stance_create_uses_context_renderer(case_db, monkeypatch):
    draft = prompt_body((Path(__file__).parents[1] / "docs/prompts/stance.md").read_text("utf-8"))
    fake_ctx = types.ModuleType("core.audit.context")
    fake_ctx.render_for = lambda conn, rid: f">> CONTEXT FOR {rid}"
    monkeypatch.setitem(sys.modules, "core.audit.context", fake_ctx)
    monkeypatch.setattr(stance_mod, "load_prompt", lambda name: draft)
    model = FakeLocal(['{"stance": "supports", "quote": "garage", "rationale": "Says so."}'])
    lab = stance_mod.create(case_db, model=model)
    (run,) = lab.model_runs
    assert run.purpose == "stance"
    cand = EvidenceCandidate(
        record_id="msg:7",
        ref=SourceRef(source_id="s", locator="l"),
        text="meet me at the garage",
        tier=ProvenanceTier.OBSERVED,
        retrieval_score=1.0,
    )
    label = lab.label(make_assumption("They met at the garage."), cand)
    assert label.model_run_id == run.id and label.model_call_id == f"mc:{run.id}#1"
    assert ">> CONTEXT FOR msg:7" in model.prompts[0]
