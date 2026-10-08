"""Run a local model and get back JSON, or a recorded failure.

Two implementations of `LocalModel`:
- `LlamaCppModel`: a GGUF file on local disk through llama-cpp-python (optional dependency).
- `FakeModel`: scripted outputs for tests and for building the pipeline before a model exists.

Fail closed: `generate_json` never raises on bad model output. It returns a `ModelOutput` with
`parsed=None` and an `error`, and the caller drops the item (a reviewer error is a dismissal).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

JsonSchema = Mapping[str, Any]


@dataclass(frozen=True)
class ModelSpec:
    """A model file on local disk. `sha256` is checked before loading when given."""

    name: str
    path: Path
    sha256: str | None = None
    license: str | None = None  # SPDX id, checked by a person against the model card
    chat_format: str | None = None  # None: use the template stored in the GGUF


@dataclass(frozen=True)
class GenerationParams:
    """Deterministic by default: greedy decoding with a fixed seed."""

    max_tokens: int = 1024  # stance and review; translation callers pass more
    temperature: float = 0.0
    seed: int = 1234
    n_ctx: int = 8192
    n_gpu_layers: int = -1  # -1 offloads every layer to the GPU

    def as_record(self) -> dict[str, str | int | float | bool]:
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "seed": self.seed,
            "n_ctx": self.n_ctx,
            "n_gpu_layers": self.n_gpu_layers,
            "grammar": "json_schema",
        }


@dataclass(frozen=True)
class ModelOutput:
    raw_text: str
    parsed: dict[str, Any] | None
    error: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.parsed is not None


class LocalModel(Protocol):
    name: str
    sha256: str

    def generate_json(
        self, prompt: str, schema: JsonSchema, params: GenerationParams | None = None
    ) -> ModelOutput: ...


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


# Length and count limits are not sent to the decoder. llama.cpp unrolls each one into nested
# optional rules ("maxLength": 2000 becomes 2000 nested copies of a char rule), which fails to
# parse past its limits and has crashed the process (Wave 3 Mac run, 2026-10-08). Every pass
# checks the same limits on the decoded output with pydantic, so an over-long answer is still
# dropped, never kept; max_tokens bounds the generation itself.
GRAMMAR_DROPPED_KEYS = frozenset({"maxLength", "minLength", "maxItems", "minItems"})


def grammar_schema(schema: Any) -> Any:
    """The schema as the decoder sees it: the same shape, without length and count limits."""
    if isinstance(schema, Mapping):
        return {k: grammar_schema(v) for k, v in schema.items() if k not in GRAMMAR_DROPPED_KEYS}
    if isinstance(schema, list):
        return [grammar_schema(v) for v in schema]
    return schema


def parse_json_output(text: str, schema: JsonSchema) -> tuple[dict[str, Any] | None, str | None]:
    """Strict parse: one JSON object, required keys present, enum values respected, no extras.

    This is a small subset of JSON Schema (object, string, enum, required, additionalProperties),
    enough for the reviewer and stance outputs. Anything else is a failure, not a guess.
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"invalid_json: {e.msg}"
    if not isinstance(obj, dict):
        return None, "not_an_object"
    props: Mapping[str, Any] = schema.get("properties", {})
    for key in schema.get("required", ()):
        if key not in obj:
            return None, f"missing_key: {key}"
    if schema.get("additionalProperties") is False:
        extra = sorted(set(obj) - set(props))
        if extra:
            return None, f"extra_keys: {','.join(extra)}"
    for key, spec in props.items():
        if key not in obj:
            continue
        value = obj[key]
        if spec.get("type") == "string" and not isinstance(value, str):
            return None, f"wrong_type: {key}"
        if "enum" in spec and value not in spec["enum"]:
            return None, f"bad_enum: {key}"
    return obj, None


class LlamaCppModel:
    """A GGUF model run by llama-cpp-python, with output constrained to a JSON schema."""

    def __init__(
        self,
        spec: ModelSpec,
        params: GenerationParams | None = None,
        *,
        verify_hash: bool = True,
    ) -> None:
        if not spec.path.is_file():
            raise FileNotFoundError(f"model file not found: {spec.path}")
        digest = sha256_file(spec.path) if (verify_hash or spec.sha256 is None) else spec.sha256
        if spec.sha256 is not None and digest != spec.sha256:
            raise ValueError(f"sha256 mismatch for {spec.path}: got {digest}")
        try:
            from llama_cpp import Llama  # optional dependency, local only
        except ImportError as e:  # pragma: no cover - depends on the machine
            raise RuntimeError("llama-cpp-python is not installed (pip install .[local])") from e

        self.spec = spec
        self.name = spec.name
        self.sha256 = digest
        self.params = params or GenerationParams()
        self._llm = Llama(
            model_path=str(spec.path),
            n_ctx=self.params.n_ctx,
            n_gpu_layers=self.params.n_gpu_layers,
            seed=self.params.seed,
            chat_format=spec.chat_format,
            verbose=False,
        )

    def generate_json(
        self, prompt: str, schema: JsonSchema, params: GenerationParams | None = None
    ) -> ModelOutput:
        p = params or self.params
        start = time.perf_counter()
        try:
            resp = self._llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object", "schema": grammar_schema(schema)},
                temperature=p.temperature,
                max_tokens=p.max_tokens,
                seed=p.seed,
            )
        except Exception as e:  # noqa: BLE001 - any runtime failure is a failed call, never a pass
            return ModelOutput("", None, f"runtime_error: {e}", seconds=time.perf_counter() - start)
        elapsed = time.perf_counter() - start
        text = resp["choices"][0]["message"].get("content") or ""
        usage = resp.get("usage", {})
        parsed, error = parse_json_output(text, schema)
        return ModelOutput(
            raw_text=text,
            parsed=parsed,
            error=error,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            seconds=elapsed,
        )


@dataclass
class FakeModel:
    """Scripted model. `respond` maps a prompt to raw output text; the default always dismisses."""

    name: str = "fake"
    sha256: str = "0" * 64
    respond: Callable[[str], str] = field(
        default=lambda _prompt: '{"decision": "dismiss", "reason": "fake model"}'
    )
    calls: list[str] = field(default_factory=list)

    def generate_json(
        self, prompt: str, schema: JsonSchema, params: GenerationParams | None = None
    ) -> ModelOutput:
        self.calls.append(prompt)
        text = self.respond(prompt)
        parsed, error = parse_json_output(text, schema)
        return ModelOutput(raw_text=text, parsed=parsed, error=error)


class JsonModelPort:
    """The port thread 6 (stance and review) builds against: generate(prompt, schema) -> raw str.

    Returns the raw text even when it is not valid JSON, so the caller parses it and fails closed.
    A runtime error comes back as an empty string, which never parses. Every call is kept in
    `outputs` so the caller can log it with its run id.
    """

    def __init__(
        self, model: LocalModel, run_id: str, params: GenerationParams | None = None
    ) -> None:
        self._model = model
        self._run_id = run_id
        self._params = params or GenerationParams()
        self.outputs: list[ModelOutput] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    def generate(self, prompt: str, json_schema: JsonSchema) -> str:
        out = self._model.generate_json(prompt, json_schema, self._params)
        self.outputs.append(out)
        return out.raw_text
