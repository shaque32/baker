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
from dataclasses import dataclass, field, replace
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


CHAT_TEMPLATES = ("gguf", "no-think")


@dataclass(frozen=True)
class GenerationParams:
    """Deterministic by default: greedy decoding with a fixed seed.

    The speed settings (flash_attn, n_batch, prompt_lookup, chat_template) apply when the model
    file loads; a different value passed to one call is ignored. The defaults are PRODUCT_RUNTIME,
    picked by the Mac speed run (eval/probe/README.md, "Faster calls, round 2"). RUNTIMES names
    every runtime that run compared; "plain" is the one the signed probe results were first
    measured with.
    """

    max_tokens: int = 1024  # stance and review; translation callers pass more
    temperature: float = 0.0
    seed: int = 1234
    n_ctx: int = 8192
    n_gpu_layers: int = -1  # -1 offloads every layer to the GPU
    flash_attn: bool = True
    n_batch: int = 1024  # prompt tokens read per step (llama.cpp's n_batch and n_ubatch)
    prompt_lookup: int = 0  # draft tokens per step copied from the prompt; 0 is off
    chat_template: str = "gguf"  # "no-think": the model's own template, Qwen3 non-thinking mode

    def __post_init__(self) -> None:
        if self.chat_template not in CHAT_TEMPLATES:
            raise ValueError(f"chat_template must be one of {CHAT_TEMPLATES}")
        if self.n_batch < 1 or self.prompt_lookup < 0:
            raise ValueError("n_batch must be at least 1 and prompt_lookup at least 0")

    def as_record(self) -> dict[str, str | int | float | bool]:
        record: dict[str, str | int | float | bool] = {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "seed": self.seed,
            "n_ctx": self.n_ctx,
            "n_gpu_layers": self.n_gpu_layers,
            "grammar": "json_schema",
        }
        # A speed setting is recorded only when it differs from the plain runtime, so runs made
        # before these settings existed keep the same record and their stored outputs stay
        # reusable. A run on any other setting never reuses them.
        for key, plain in PLAIN_SPEED.items():
            value = getattr(self, key)
            if value != plain:
                record[key] = value
        return record


PLAIN_SPEED: dict[str, str | int | bool] = {
    "flash_attn": False,
    "n_batch": 512,
    "prompt_lookup": 0,
    "chat_template": "gguf",
}

# Runtimes the Mac speed run compares. Under greedy decoding none of them should change what
# the model says, but each changes the arithmetic order, so that is measured, not assumed.
RUNTIMES: dict[str, dict[str, int | bool]] = {
    "plain": {},
    "flash": {"flash_attn": True, "n_batch": 1024},
    "flash-lookup": {"flash_attn": True, "n_batch": 1024, "prompt_lookup": 10},
}

# What the product runs on. Mac run 2026-10-12 (Qwen3-14B Q4, M4 24 GB): "flash" gave the same
# output as "plain" on all 88 signed probe items, 22.5 s instead of 28.3 s per probe call, at
# the same peak memory. "flash-lookup" was no faster (28.5 s) and used 0.9 GB more.
PRODUCT_RUNTIME = "flash"


def with_runtime(
    params: GenerationParams, runtime: str = "plain", chat_template: str | None = None
) -> GenerationParams:
    """params on one of RUNTIMES, optionally with another chat template."""
    if runtime not in RUNTIMES:
        raise ValueError(f"unknown runtime {runtime!r}; one of {sorted(RUNTIMES)}")
    out = replace(params, **{**PLAIN_SPEED, **RUNTIMES[runtime]})
    template = chat_template if chat_template is not None else params.chat_template
    return replace(out, chat_template=template)


@dataclass(frozen=True)
class ModelOutput:
    raw_text: str
    parsed: dict[str, Any] | None
    error: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    # A cloud answer only (core/llm/cloud.py): what the API reported about it, for the audit
    # log's cloud.received entry. A local model leaves these empty.
    served_model: str | None = None
    message_id: str | None = None
    request_id: str | None = None
    stop_reason: str | None = None

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
            **speed_kwargs(self.params),
        )
        if self.params.chat_template == "no-think":
            self._llm.chat_handler = no_think_handler(self._llm)

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


def speed_kwargs(params: GenerationParams) -> dict[str, Any]:
    """Llama() arguments for the speed settings. The plain runtime passes none, so it loads
    exactly as before these settings existed."""
    kwargs: dict[str, Any] = {}
    if params.flash_attn:
        kwargs["flash_attn"] = True
    if params.n_batch != PLAIN_SPEED["n_batch"]:
        kwargs["n_batch"] = params.n_batch
        kwargs["n_ubatch"] = params.n_batch
    if params.prompt_lookup:
        # Prompt-lookup decoding: guesses the next tokens by copying from the prompt (quotes
        # are copied from it) and keeps a guess only where the model's own greedy choice agrees.
        from llama_cpp.llama_speculative import LlamaPromptLookupDecoding

        kwargs["draft_model"] = LlamaPromptLookupDecoding(num_pred_tokens=params.prompt_lookup)
        # llama-cpp-python (0.3.36) sizes its logits buffer from this argument but fills one row
        # per token whenever a draft model is set, so without it any prompt longer than n_batch
        # fails. The buffer is n_ctx rows by the vocabulary (about 5 GB for Qwen3 at 8192).
        kwargs["logits_all"] = True
    return kwargs


NO_THINK_SUFFIX = "<think>\n\n</think>\n\n"


def no_think_handler(llm: Any) -> Any:
    """A chat handler that renders the model file's own template with enable_thinking=False.

    For Qwen3 that is the template the model was trained on for answers without a thinking
    block: the same text plus an empty <think></think> block after the assistant header. The
    JSON grammar already stops the model from writing a thinking block, so this changes what
    the model reads, not how long it writes; its effect on labels is measured on the probe.
    Refuses (raises) unless rendering differs from the plain template by exactly that block.
    """
    from llama_cpp import llama_chat_format

    template = llm.metadata.get("tokenizer.chat_template")
    if not template or "enable_thinking" not in template:
        raise ValueError("chat_template 'no-think' needs a chat template with enable_thinking")
    eos_id, bos_id = llm.token_eos(), llm.token_bos()
    eos = llm._model.token_get_text(eos_id) if eos_id != -1 else ""
    bos = llm._model.token_get_text(bos_id) if bos_id != -1 else ""

    class NoThink(llama_chat_format.Jinja2ChatFormatter):
        def __call__(self, **kwargs: Any) -> Any:
            return super().__call__(enable_thinking=False, **kwargs)

    plain = llama_chat_format.Jinja2ChatFormatter(
        template=template, eos_token=eos, bos_token=bos, stop_token_ids=[eos_id]
    )
    no_think = NoThink(template=template, eos_token=eos, bos_token=bos, stop_token_ids=[eos_id])
    sample = [{"role": "user", "content": "x"}]
    if no_think(messages=sample).prompt != plain(messages=sample).prompt + NO_THINK_SUFFIX:
        raise ValueError("chat_template 'no-think' did not render as the plain template plus "
                         "an empty thinking block; refusing to guess")  # fmt: skip
    return no_think.to_chat_handler()


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
