"""Build the model passes for the pipeline: `create(conn)` in stance.py and review.py.

The model is a GGUF file on local disk, named in a small JSON config:

    {"name": "qwen2.5-14b-instruct-q4_k_m", "path": "/models/qwen.gguf", "sha256": "<64 hex>",
     "n_ctx": 4096}

found at $BAKER_MODEL_CONFIG, else ~/.baker/model.json. The sha256 is required: a run must be
reproducible, so the exact model file is pinned and checked before loading. n_ctx is optional
(a 14B model on a 16 GB laptop only fits with 4096). Nothing here makes network calls.
core/llm/ (the model-runtime thread) loads the file; it is imported lazily so the rest of
core/ works without llama-cpp-python installed.

Speed. A laptop runs a 14B model at a few tokens a second, so two things keep reruns cheap:
- The model file loads (and is hash-checked) on the first call that needs it, not when a pass
  is built. A rerun whose prompts were all answered before never loads it.
- Stored outputs are reused. A call whose fully rendered prompt was already answered in this
  case database by the same model file, the same prompt file, the same output schema and the
  same generation settings gets that stored raw output back instead of a new generation. That
  is what greedy decoding with a fixed seed would produce anyway ("outputs are stored, not
  regenerated", ARCHITECTURE.md). Runtime errors are never reused. The new call is still
  recorded under the new run, and the run's params say reuse was on.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from core.audit._llm_json import CallRecorder, ModelUnavailable, prompt_version
from core.contracts import ModelRun, canonical_json, short_hash

MODEL_CONFIG_ENV = "BAKER_MODEL_CONFIG"
DEFAULT_CONFIG = Path.home() / ".baker" / "model.json"
REUSE_PARAM = "reuse_stored_outputs"
SCHEMA_PARAM = "output_schema"


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
    n_ctx: int | None = None


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
            n_ctx=int(raw["n_ctx"]) if raw.get("n_ctx") is not None else None,
        )
    except (ValueError, KeyError, TypeError) as e:
        raise ModelConfigError(f"bad model config {path}: {e}") from None
    if not cfg.name:
        raise ModelConfigError(f"bad model config {path}: empty name")
    if not re.fullmatch(r"[0-9a-f]{64}", cfg.sha256):
        raise ModelConfigError(f"bad model config {path}: sha256 must be 64 hex characters")
    if cfg.n_ctx is not None and cfg.n_ctx < 512:
        raise ModelConfigError(f"bad model config {path}: n_ctx must be at least 512")
    return cfg


class LazyModel:
    """A configured model file that loads on the first generate_json call.

    name, sha256 and params come from the config, so a pass can open its ModelRun (and reuse
    stored outputs) without reading 9 GB of weights. The load checks the file's SHA-256
    against the config and raises on a mismatch, before any output is produced.
    """

    def __init__(self, cfg: ModelConfig) -> None:
        from core.llm.runtime import GenerationParams  # no llama import at module level

        if not cfg.path.is_file():
            raise ModelConfigError(f"model file not found: {cfg.path}")
        self.cfg = cfg
        self.name = cfg.name
        self.sha256 = cfg.sha256
        self.params = (
            GenerationParams(n_ctx=cfg.n_ctx) if cfg.n_ctx is not None else GenerationParams()
        )
        self._model: LocalModel | None = None
        self.load_seconds: float | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> LocalModel:
        if self._model is None:
            from core.llm.runtime import LlamaCppModel, ModelSpec  # local runtime, lazy

            spec = ModelSpec(
                name=self.cfg.name,
                path=self.cfg.path,
                sha256=self.cfg.sha256,
                chat_format=self.cfg.chat_format,
            )
            start = time.perf_counter()
            try:
                self._model = LlamaCppModel(spec, self.params)
            except Exception as e:  # noqa: BLE001 - wrong hash, missing runtime, bad file
                raise ModelUnavailable(f"could not load {self.cfg.path}: {e}") from e
            self.load_seconds = time.perf_counter() - start
        return self._model

    def generate_json(self, prompt: str, schema: Mapping[str, Any], params: Any = None) -> Any:
        return self.load().generate_json(prompt, schema, params)


_LOADED: dict[tuple[Path, str, int | None], LazyModel] = {}


def load_model(cfg: ModelConfig) -> LocalModel:
    """The configured model, once per process. It loads and hash-checks on first use."""
    key = (cfg.path, cfg.sha256, cfg.n_ctx)
    if key not in _LOADED:
        _LOADED[key] = LazyModel(cfg)
    return _LOADED[key]


@dataclass(frozen=True)
class CallStat:
    """Time and size of one call, for the speed test. Not stored: model_calls has the call."""

    seconds: float
    prompt_tokens: int
    completion_tokens: int
    reused: bool


StoredOutput = Callable[[str], str | None]


class RunPort:
    """A JsonModel for one model run: generate(prompt, schema) -> raw text.
    Runtime errors come back as '' (core.llm does this), which never parses.
    `stored(prompt)` returns an earlier raw output to reuse, or None to call the model."""

    def __init__(self, model: LocalModel, run_id: str, stored: StoredOutput | None = None) -> None:
        self._model = model
        self._run_id = run_id
        self._stored = stored
        self.stats: list[CallStat] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def reused(self) -> int:
        return sum(s.reused for s in self.stats)

    def generate(self, prompt: str, json_schema: Mapping[str, Any]) -> str:
        if self._stored is not None:
            raw = self._stored(prompt)
            if raw is not None:
                self.stats.append(CallStat(0.0, 0, 0, True))
                return raw
        start = time.perf_counter()
        out = self._model.generate_json(prompt, json_schema)
        self.stats.append(
            CallStat(
                seconds=float(getattr(out, "seconds", 0.0) or time.perf_counter() - start),
                prompt_tokens=int(getattr(out, "prompt_tokens", 0)),
                completion_tokens=int(getattr(out, "completion_tokens", 0)),
                reused=False,
            )
        )
        return out.raw_text


def _reuse_key(params: Mapping[str, Any]) -> str:
    return canonical_json({k: v for k, v in params.items() if k != REUSE_PARAM})


def stored_output_lookup(conn: sqlite3.Connection, run: ModelRun) -> StoredOutput:
    """Find a raw output this case database already holds for the same prompt, model file,
    prompt file, output schema and settings. Outputs of failed calls ('error') never count;
    unusable output ('invalid_output', 'quote_failed') is reused, and fails the same way."""
    key = _reuse_key(run.params)

    def lookup(prompt: str) -> str | None:
        try:
            rows = conn.execute(
                "SELECT mc.raw_output, mr.params_json FROM model_calls mc"
                " JOIN model_runs mr ON mr.id = mc.model_run_id"
                " WHERE mr.purpose = ? AND mr.model_sha256 = ? AND mr.prompt_sha256 = ?"
                " AND mc.prompt = ? AND mc.outcome != 'error'"
                " ORDER BY mc.at_utc, mc.id",
                (run.purpose, run.model_sha256, run.prompt_sha256, prompt),
            ).fetchall()
        except sqlite3.OperationalError:  # schema without model_calls (pre-v0.2)
            return None
        for raw, params_json in rows:
            if _reuse_key(json.loads(params_json)) == key:
                return raw
        return None

    return lookup


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
    schema: Mapping[str, Any] | None = None,
    reuse: bool = True,
) -> OpenedRun:
    """One ModelRun per pass per pipeline run. Its id is unique per process start time, and
    call numbering continues from any calls already stored for it. `schema` (the pass's output
    schema) is recorded by hash, so a schema change never reuses older outputs. `reuse` turns
    stored-output reuse on (the default) or off (the speed test's cold run)."""
    if model is None:
        model = load_model(load_config())
    started = clock()
    params_obj = getattr(model, "params", None)
    params: dict[str, str | int | float | bool] = (
        dict(params_obj.as_record()) if params_obj is not None else {}
    )
    if schema is not None:
        params[SCHEMA_PARAM] = short_hash(dict(schema))
    if reuse:
        params[REUSE_PARAM] = True
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
    stored = stored_output_lookup(conn, run) if reuse else None
    return OpenedRun(RunPort(model, run_id, stored), run, recorder, model.name)
