"""Build the model passes for the pipeline: `create(conn)` in stance.py and review.py.

The model is a GGUF file on local disk, named in a small JSON config:

    {"name": "qwen2.5-14b-instruct-q4_k_m", "path": "/models/qwen.gguf", "sha256": "<64 hex>"}

found at $BAKER_MODEL_CONFIG, else ~/.baker/model.json. The sha256 is required: a run must be
reproducible, so the exact model file is pinned and checked before loading. Nothing here makes
network calls. core/llm/ (the model-runtime thread) loads the file; it is imported lazily so
the rest of core/ works without llama-cpp-python installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from core.audit._llm_json import CallRecorder, prompt_version
from core.contracts import ModelRun, short_hash

MODEL_CONFIG_ENV = "BAKER_MODEL_CONFIG"
DEFAULT_CONFIG = Path.home() / ".baker" / "model.json"


class ModelConfigError(RuntimeError):
    """No usable local model config. The pass cannot run; nothing is guessed."""


class LocalModel(Protocol):
    """What core.llm.runtime models provide (LlamaCppModel, FakeModel)."""

    name: str
    sha256: str

    def generate_json(self, prompt: str, schema: Mapping[str, Any], params: Any = None) -> Any: ...


@dataclass(frozen=True)
class ModelConfig:
    name: str
    path: Path
    sha256: str
    chat_format: str | None = None


def config_path() -> Path:
    env = os.environ.get(MODEL_CONFIG_ENV, "").strip()
    return Path(env) if env else DEFAULT_CONFIG


def load_config(path: Path | None = None) -> ModelConfig:
    path = path or config_path()
    if not path.is_file():
        raise ModelConfigError(f"no model config at {path}; set {MODEL_CONFIG_ENV}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg = ModelConfig(
            name=str(raw["name"]).strip(),
            path=Path(raw["path"]).expanduser(),
            sha256=str(raw["sha256"]).strip().lower(),
            chat_format=raw.get("chat_format"),
        )
    except (ValueError, KeyError, TypeError) as e:
        raise ModelConfigError(f"bad model config {path}: {e}") from None
    if not cfg.name:
        raise ModelConfigError(f"bad model config {path}: empty name")
    if not re.fullmatch(r"[0-9a-f]{64}", cfg.sha256):
        raise ModelConfigError(f"bad model config {path}: sha256 must be 64 hex characters")
    return cfg


_LOADED: dict[tuple[Path, str], LocalModel] = {}


def load_model(cfg: ModelConfig) -> LocalModel:
    """Load (once per process) and hash-check the model file through core.llm."""
    key = (cfg.path, cfg.sha256)
    if key not in _LOADED:
        from core.llm.runtime import LlamaCppModel, ModelSpec  # local runtime, lazy

        spec = ModelSpec(
            name=cfg.name, path=cfg.path, sha256=cfg.sha256, chat_format=cfg.chat_format
        )
        _LOADED[key] = LlamaCppModel(spec)
    return _LOADED[key]


class RunPort:
    """A JsonModel for one model run: generate(prompt, schema) -> raw text.
    Runtime errors come back as '' (core.llm does this), which never parses."""

    def __init__(self, model: LocalModel, run_id: str) -> None:
        self._model = model
        self._run_id = run_id

    @property
    def run_id(self) -> str:
        return self._run_id

    def generate(self, prompt: str, json_schema: Mapping[str, Any]) -> str:
        out = self._model.generate_json(prompt, json_schema)
        return out.raw_text


def next_call_seq(conn: sqlite3.Connection, run_id: str) -> int:
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM model_calls WHERE model_run_id = ?", (run_id,)
        ).fetchone()
    except sqlite3.OperationalError:  # schema without model_calls (pre-v0.2)
        return 1
    return int(row[0])


@dataclass(frozen=True)
class OpenedRun:
    port: RunPort
    run: ModelRun
    recorder: CallRecorder
    model_name: str


def open_run(
    conn: sqlite3.Connection,
    purpose: str,
    template: str,
    *,
    model: LocalModel | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> OpenedRun:
    """One ModelRun per pass per pipeline run. Its id is unique per process start time, and
    call numbering continues from any calls already stored for it."""
    if model is None:
        model = load_model(load_config())
    started = clock()
    params_obj = getattr(model, "params", None)
    params: dict[str, str | int | float | bool] = (
        dict(params_obj.as_record()) if params_obj is not None else {}
    )
    seed = params_obj.seed if params_obj is not None and hasattr(params_obj, "seed") else None
    version = prompt_version(template)
    run_id = (
        f"mr:{purpose}:{started.strftime('%Y%m%dT%H%M%S%fZ')}:"
        f"{short_hash([model.sha256, version, params])}"
    )
    run = ModelRun(
        id=run_id,
        purpose=purpose,
        model_name=model.name,
        model_sha256=model.sha256,
        prompt_version=version,
        prompt_sha256=hashlib.sha256(template.encode("utf-8")).hexdigest(),
        params=params,
        seed=seed,
        started_at_utc=started,
    )
    recorder = CallRecorder(clock=clock, start_seq=lambda rid: next_call_seq(conn, rid))
    return OpenedRun(RunPort(model, run_id), run, recorder, model.name)
