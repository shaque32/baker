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
from $BAKER_ANTHROPIC_API_KEY; else, for an encrypted case, from the key saved in that case,
sealed under the case key (core/encryption.py seal_secret), so it is unreadable while the case is
locked; else from ~/.baker/cloud.json (owner-only), which also holds the other settings:

    {"api_key": "sk-ant-...", "model": "claude-opus-5-5", "effort": "medium"}

The API address is pinned to https://api.anthropic.com, the recipient the expert's per-case
consent names; a config naming any other host is refused, and an ANTHROPIC_BASE_URL left in the
environment can never redirect case data.

Failures never pass silently. A call that cannot be answered raises CloudError. A case's labels
never mix models: a sticky failure pauses the audit (core/audit/_local_model.py, CloudPort), and
the expert chooses to retry the cloud model or run the whole case locally.
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
# One stance answer takes seconds (about 4 s on synthetic case01), so a stalled request gives up
# after two minutes and at most two retries (SentLog sends and logs each), then the audit pauses.
# (model, effort, stance prompt version) entries that passed the signed stance probe set:
# supports recall >= 90%, contradicts precision >= 90%, nothing contradicting labeled supports.
# A case uses the cloud model only with an entry listed here (core/casework/cloud.py). Adding
# one needs a recorded, preregistered run of that exact model, effort and prompt version that
# meets those bars on
# the signed set AND on new held-out items nobody used to write or tune the prompt, plus Arsh's
# sign-off on the entry (its comment names the results file).
# The prompt version is the cloud stance prompt's (core/audit/prompts/stance_cloud.md), the one
# a cloud model reads, so any change to that prompt drops its entries until it passes again.
# With stance prompt v1.1 (2026-10-15) Opus 5.5 scored 73% contradicts precision on the signed set
# (bar 90%). With the cloud prompt, v1.2, at medium effort (preregistered, 2026-10-15): on the
# signed set contradicts precision 10/10, supports recall 33/33, nothing contradicting labeled
# supports; on 50 new items, both sets at medium (24, of which 22 were scored, and 26), no
# wrong contradicts and every scored control kept; on synthetic case01 with the signed sheet,
# 95% accuracy and 0 false supported (2026-10-20, cloud-bench/2026-10-20-case01-v12). Every
# item's answers:
# eval/probe/results/2026-10-15-opus-5-5-medium-stance-v1-2.jsonl. Signed by Arsh on
# 2026-10-20 ("Sign the entry", 00:39Z, "Audit our model scoring").
PROBE_PASSED: frozenset[tuple[str, str, str]] = frozenset(
    {("claude-opus-5-5", "medium", "sha256:2863d8dbf66960f6")}
)
REQUEST_TIMEOUT_SECONDS = 120.0
MAX_RETRIES = 2
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
    API down) pause the audit; the others (a refusal, an answer cut off) drop this label only.
    `retryable` ones (no connection, a timeout, 408, 409, 429, 5xx) may be sent again; Baker
    retries them itself (core/audit/_local_model.py SentLog), so every send is logged first."""

    def __init__(self, reason: str, *, sticky: bool, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.sticky = sticky
        self.retryable = retryable


RETRY_STATUS = frozenset({408, 409, 429})


def is_retryable(e: BaseException) -> bool:
    """The failures Anthropic's SDK would retry: no connection, a timeout, 408/409/429, 5xx."""
    status = getattr(e, "status_code", None)
    if isinstance(status, int):
        return status in RETRY_STATUS or status >= 500
    name = type(e).__name__
    return "Connection" in name or "Timeout" in name


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


CASE_SECRET = "cloud-key"  # case.db -> case.cloud-key


def case_key(case_db: Path | None) -> str | None:
    """The key saved in an encrypted case, or None (no case, a plain case, or none saved)."""
    from core import encryption

    if case_db is None or not encryption.is_encrypted_case(case_db):
        return None
    try:
        return encryption.open_secret(case_db, CASE_SECRET)
    except (encryption.CaseLocked, encryption.EncryptionError) as e:
        raise CloudConfigError(f"the case's saved key cannot be read: {e}") from None


def load_config(path: Path | None = None, case_db: Path | None = None) -> CloudConfig:
    """The expert's cloud settings. The key in $BAKER_ANTHROPIC_API_KEY wins; then, for an
    encrypted case, the key sealed in it; then the config file's."""
    path = path or config_path()
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise CloudConfigError(f"bad cloud config {path}: {e}") from None
        if not isinstance(raw, dict):
            raise CloudConfigError(f"bad cloud config {path}: not a JSON object")
    key = (
        os.environ.get(KEY_ENV, "").strip()
        or (case_key(case_db) or "").strip()
        or str(raw.get("api_key") or "").strip()
    )
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


def save_key(api_key: str, path: Path | None = None, case_db: Path | None = None) -> Path:
    """Save the key. In an encrypted case it is sealed under the case key, beside the case,
    and the plain config file is not touched; otherwise it goes in the expert's cloud config,
    readable by this user only. Refused while $BAKER_ANTHROPIC_API_KEY is set: that key wins,
    so a saved one would never be used."""
    from core import encryption

    if key_from_environment():
        raise CloudConfigError(
            f"the key in {KEY_ENV} is the one in use; change or unset it there instead"
        )
    key = api_key.strip()
    if not key:
        raise CloudConfigError("empty key")
    if case_db is not None and encryption.is_encrypted_case(case_db):
        try:
            return encryption.seal_secret(case_db, CASE_SECRET, key)
        except (encryption.CaseLocked, encryption.EncryptionError) as e:
            raise CloudConfigError(f"could not save the key in this case: {e}") from None
    path = path or config_path()
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
    an empty output: a sticky one pauses the audit (core/audit/_local_model.py, CloudPort), so a
    failure is never mistaken for a run that found nothing.
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
            try:
                self._client = anthropic.Anthropic(
                    api_key=self.cfg.api_key,
                    base_url=self.cfg.base_url,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    max_retries=0,  # Baker retries itself, logging each send (SentLog)
                )
            except Exception as e:  # noqa: BLE001 - a bad local proxy or HTTP setting
                raise CloudError(
                    f"the Anthropic client could not be set up ({type(e).__name__}: {e})",
                    sticky=True,
                ) from e
        return self._client

    def prepare(self) -> None:
        """Build the client (CloudError if it cannot be), so nothing is logged as sent unless a
        request can actually go out."""
        self._get_client()

    def request(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """The request body sent to the API, exactly (the key travels in a header, not here)."""
        return {
            "model": self.cfg.model,
            "max_tokens": self.params.max_tokens,
            "output_config": {
                "effort": self.cfg.effort,
                "format": {"type": "json_schema", "schema": api_schema(schema)},
            },
            "messages": [{"role": "user", "content": prompt}],
        }

    def generate_json(self, prompt: str, schema: dict[str, Any], params: Any = None) -> ModelOutput:
        client = self._get_client()
        start = time.perf_counter()
        try:
            resp = client.messages.create(**self.request(prompt, schema))
        except Exception as e:  # noqa: BLE001 - network, key, rate limit, server: all sticky
            raise CloudError(
                f"{type(e).__name__}: {e}", sticky=True, retryable=is_retryable(e)
            ) from e
        elapsed = time.perf_counter() - start
        served = getattr(resp, "model", None)
        if served != self.cfg.model:
            # Only the model that passed the signed stance test may label, and a case's labels
            # never mix models, so an answer from any other model pauses the run.
            raise CloudError(f"the API answered as {served!r}, not {self.cfg.model!r}", sticky=True)
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
            served_model=served,
            message_id=_text_or_none(getattr(resp, "id", None)),
            request_id=_text_or_none(getattr(resp, "_request_id", None)),
            stop_reason=_text_or_none(resp.stop_reason),
        )


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
