"""The one cloud model in core/: Claude as the stance labeler, on the expert's own key.

This is the only file in core/ that makes a network call, and it is used only by the stance
labeler (core/audit/stance.py), only for a case the expert attested may use cloud AI
(core/casework/cloud.py). Everything else in core/ stays offline: the AI reviewer, claim
proposal and assumption filling run on the local model.

What goes out: the filled-in stance prompt for one (assumption, record) pair, which holds the
assumption, the record, its nearby messages and the claim. Never an input file or the case
database. What comes back is checked exactly like the local model's answer: strict JSON, and a
quote that code verifies verbatim before anything is stored.

The key is the expert's own Anthropic key (bring your own key; Baker runs no server). It is read
from $BAKER_ANTHROPIC_API_KEY, else ~/.baker/cloud.json:

    {"api_key": "sk-ant-...", "model": "claude-opus-5-5", "effort": "medium"}

The API address is pinned to https://api.anthropic.com, the recipient the expert's per-case
consent names; a config naming any other host is refused, and an ANTHROPIC_BASE_URL left in the
environment can never redirect case data.

Failures never pass silently. A call that cannot be answered raises CloudError; the stance
labeler then asks the local model instead (core/audit/_local_model.py, FallbackPort).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.llm.runtime import ModelOutput, parse_json_output

KEY_ENV = "BAKER_ANTHROPIC_API_KEY"
CONFIG_ENV = "BAKER_CLOUD_CONFIG"
DEFAULT_CONFIG = Path.home() / ".baker" / "cloud.json"
DEFAULT_MODEL = "claude-opus-5-5"
# Opus 5.5 at medium effort is the setting the cloud bench measured on case01 (85% accuracy,
# 0 false supported) with the signed v1.1 prompt (cloud-bench 2026-10-14c, "Audit our model
# scoring"). Another model or effort is the expert's choice and is recorded with every run.
DEFAULT_EFFORT = "medium"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
API_BASE_URL = "https://api.anthropic.com"
SHA_PREFIX = "api:"  # model_runs.model_sha256 of a cloud model: there is no file to hash

# JSON Schema keywords the API's structured outputs do not take. They are dropped from the
# schema sent; the full schema is still checked here on the answer.
UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "multipleOf",
        "format",
        "minItems",
        "maxItems",
    }  # fmt: skip
)


class CloudConfigError(RuntimeError):
    """No usable cloud key or config. The case runs on the local model instead."""


class CloudError(RuntimeError):
    """A cloud call that produced no answer. `sticky` failures (no network, a rejected key, the
    API down after its retries) send the rest of the run to the local model; the others (a
    refusal, an answer cut off) send only this call."""

    def __init__(self, reason: str, *, sticky: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.sticky = sticky


@dataclass(frozen=True)
class CloudConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    base_url: str = API_BASE_URL

    def __repr__(self) -> str:  # never print the key
        return f"CloudConfig(model={self.model!r}, effort={self.effort!r}, key=<hidden>)"


def config_path() -> Path:
    env = os.environ.get(CONFIG_ENV, "").strip()
    return Path(env).expanduser() if env else DEFAULT_CONFIG


def load_config(path: Path | None = None) -> CloudConfig:
    """The expert's cloud settings. The key in $BAKER_ANTHROPIC_API_KEY wins over the file's."""
    path = path or config_path()
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise CloudConfigError(f"bad cloud config {path}: {e}") from None
        if not isinstance(raw, dict):
            raise CloudConfigError(f"bad cloud config {path}: not a JSON object")
    key = os.environ.get(KEY_ENV, "").strip() or str(raw.get("api_key") or "").strip()
    if not key:
        raise CloudConfigError(f"no Anthropic key: set {KEY_ENV} or put api_key in {path}")
    model = str(raw.get("model") or DEFAULT_MODEL).strip()
    effort = str(raw.get("effort") or DEFAULT_EFFORT).strip()
    if effort not in EFFORTS:
        raise CloudConfigError(f"bad cloud config {path}: effort must be one of {EFFORTS}")
    base_url = str(raw.get("base_url") or API_BASE_URL).strip().rstrip("/")
    if base_url != API_BASE_URL:  # the setup screen tells the expert the prompts go to Anthropic
        raise CloudConfigError(f"bad cloud config {path}: base_url must be {API_BASE_URL}")
    return CloudConfig(api_key=key, model=model, effort=effort, base_url=base_url)


def key_from_environment() -> bool:
    return bool(os.environ.get(KEY_ENV, "").strip())


def save_key(api_key: str, path: Path | None = None) -> Path:
    """Write the key to the expert's cloud config, readable by this user only. Refused while
    $BAKER_ANTHROPIC_API_KEY is set: that key wins, so a saved one would never be used."""
    if key_from_environment():
        raise CloudConfigError(
            f"the key in {KEY_ENV} is the one in use; change or unset it there instead"
        )
    path = path or config_path()
    key = api_key.strip()
    if not key:
        raise CloudConfigError("empty key")
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            data = old if isinstance(old, dict) else {}
        except (OSError, ValueError):
            data = {}
    data["api_key"] = key
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return path


def api_schema(schema: Any) -> Any:
    """The schema without keywords the API rejects, recursively. Never edits the input."""
    if isinstance(schema, dict):
        return {k: api_schema(v) for k, v in schema.items() if k not in UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(schema, list):
        return [api_schema(v) for v in schema]
    return schema


def is_cloud_sha(sha: str | None) -> bool:
    return bool(sha) and str(sha).startswith(SHA_PREFIX)


@dataclass(frozen=True)
class CloudParams:
    """What a model run records for a cloud call, in place of the local settings."""

    model: str
    effort: str
    max_tokens: int = 16000
    seed: int | None = None  # the API takes no seed
    endpoint: str = API_BASE_URL  # part of the run's identity: another service never reuses

    def as_record(self) -> dict[str, str | int | float | bool]:
        return {"api_model": self.model, "effort": self.effort, "max_tokens": self.max_tokens,
                "grammar": "json_schema", "where": "cloud", "endpoint": self.endpoint}  # fmt: skip


class ClaudeModel:
    """The local runtime's generate_json surface, backed by the Claude API.

    Unlike core.llm.runtime, a call that gets no answer raises CloudError instead of returning
    an empty output, so the caller can ask the local model instead of dropping the item.
    """

    where = "cloud"

    def __init__(self, cfg: CloudConfig, client: Any = None) -> None:
        self.cfg = cfg
        self.name = cfg.model
        self.sha256 = f"{SHA_PREFIX}{cfg.model}"
        self.params = CloudParams(cfg.model, cfg.effort, endpoint=cfg.base_url)
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic  # optional dependency: pip install ".[cloud]"
            except ImportError as e:
                raise CloudError(
                    'the Anthropic client is not installed (pip install ".[cloud]")', sticky=True
                ) from e
            self._client = anthropic.Anthropic(
                api_key=self.cfg.api_key, base_url=self.cfg.base_url, max_retries=6
            )
        return self._client

    def generate_json(self, prompt: str, schema: dict[str, Any], params: Any = None) -> ModelOutput:
        client = self._get_client()
        start = time.perf_counter()
        try:
            resp = client.messages.create(
                model=self.cfg.model,
                max_tokens=self.params.max_tokens,
                output_config={
                    "effort": self.cfg.effort,
                    "format": {"type": "json_schema", "schema": api_schema(schema)},
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:  # noqa: BLE001 - network, key, rate limit, server: all sticky
            raise CloudError(f"{type(e).__name__}: {e}", sticky=True) from e
        elapsed = time.perf_counter() - start
        if resp.stop_reason == "refusal":
            raise CloudError("the cloud model declined to answer", sticky=False)
        if resp.stop_reason == "max_tokens":
            raise CloudError("the cloud model's answer was cut off", sticky=False)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        parsed, error = parse_json_output(text, schema)
        u = resp.usage
        return ModelOutput(
            raw_text=text,
            parsed=parsed,
            error=error,
            prompt_tokens=int(getattr(u, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(u, "output_tokens", 0) or 0),
            seconds=elapsed,
        )
