"""Big open-weight models on the signed probe set, through a hosted API (stance only).

EVAL ONLY: core/ never imports this. Arsh (thread "Run Mabillon reproducibly on cloud
open-weight model", 2026-11-05) asked to try the large open-weight models that no Mac or
examiner PC can hold. Plan: /mnt/project-files/baker/plans/cloud-open-weight-repro.md.

This is a screen, not the product: a hosted API batches requests and picks kernels on its side,
so its answers are not reproducible, and a third party sees every prompt. So only the synthetic
signed probe set and the signed stance prompts may go out (the same allow lists as
eval/bench/claude_bench.py); anything else is refused before a request is made. A model that
passes is then self-hosted from the pinned weights below and repeat-checked
(eval/probe/aws_repeat.sh) before anyone may call it reproducible.

Fixed before any run (2026-11-05), the same screen as eval/probe/candidates.py:
- The signed probe set (eval/gold/probe/probe.jsonl), stance only, layout product_members, with
  both signed stance prompts, v1.1 (the 14B's) and v1.2 (the cloud prompt Opus ran).
- Temperature 0, seed 1234, the stance JSON schema as structured output, reasoning effort
  medium with the reasoning text left out of the answer, each item asked twice (the first
  answer scores, the second measures whether the hosted model repeats itself).
- Routing: providers that keep no prompts (data_collection deny), serve 8-bit or wider weights,
  and honor every parameter sent (require_parameters). The provider that served each answer
  is recorded.
- Stage 1 pass, on either prompt: all four Expert-confirms bars and 0 moved traps shown as
  supports (candidates.stage1). A pass earns stage 2 only: the self-hosted repeat check, then
  case01 and fresh held-out items. Switching the product's model is Arsh's call, and running
  one for real cases needs his signed cloud rule.

Usage:
  OPENROUTER_API_KEY=... python -m eval.bench.open_bench [--models NAME,...]
      [--out eval/out/open_bench] [--repeat 2] [--reasoning medium]
  python -m eval.bench.open_bench --dry-run     no network: a stand-in answers every call
  python -m eval.bench.open_bench --list        the screened models and their pinned weights
Writes <out>/<model>/<prompt>/summary.json per run, served.jsonl beside its call log (one row
per call, in call order: the provider, served model and request id of each answer) and
<out>/VERDICT.md (with cost and the providers that answered). Synthetic data only; case02 is
never read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.llm.runtime import ModelOutput, parse_json_output
from eval.bench.claude_bench import (
    ROOT,
    SIGNED_PROBE,
    api_schema,
    check_case,
    check_prompt_path,
    probe_items,
)
from eval.probe import candidates

API_URL = "https://openrouter.ai/api/v1/chat/completions"
LAYOUT = "product_members"
SEED = 1234
MAX_TOKENS = 8000  # reasoning plus the answer; the answer itself is short


@dataclass(frozen=True)
class OpenModel:
    name: str
    api_model: str  # the OpenRouter model id
    weights: str  # the Hugging Face repo a self-hosted run would load
    revision: str  # that repo's commit on 2026-11-05, so stage 2 loads the same weights
    license: str  # from the model card, 2026-11-05; read it before any commercial use
    parameters_b: int  # total parameters, billions (Hugging Face safetensors metadata)
    usd_per_mtok: tuple[float, float]  # OpenRouter list price (input, output), 2026-11-05
    reasons: bool = True  # False for a model with no thinking mode: the request then omits it
    # Weights precisions accepted for this model, when no provider serves it at 8-bit or wider
    # with every parameter we send. None keeps the default (8-bit or wider). A pass on narrower
    # or undisclosed weights is weaker evidence: the self-hosted repeat must use 8-bit or wider.
    quantizations: tuple[str, ...] | None = None


# Names, revisions, licenses and sizes read from huggingface.co and openrouter.ai on
# 2026-11-05. Cheapest first, so results arrive early.
MODELS = (
    OpenModel(
        name="minimax-m3.1-flash",
        api_model="minimax/minimax-m3.1-flash",
        weights="MiniMaxAI/MiniMax-M3.1-Flash",
        revision="ce7f4df87d2e05262f5775f373dac4772f134041",
        license="other (minimax-community)",
        parameters_b=220,
        usd_per_mtok=(0.075, 0.30),
    ),
    OpenModel(
        name="deepseek-v4.1-flash-1017",
        api_model="deepseek/deepseek-v4.1-flash-1017",
        weights="deepseek-ai/DeepSeek-V4.1-Flash-1017",
        revision="1bae0e1088993b9b82de08f59de5be5a34e42170",
        license="MIT",
        parameters_b=763,
        usd_per_mtok=(0.15, 0.60),
    ),
    OpenModel(
        name="beam-1.0-501b-a23b",
        api_model="reflection/beam-1.0-501b-a23b",
        weights="reflection/Beam-1.0-501B-A23B",
        revision="12950ae640b48cbbe9b5bb7735bf197507d6383f",
        license="Apache-2.0",
        parameters_b=501,
        usd_per_mtok=(0.30, 1.00),
    ),
    OpenModel(
        name="kimi-k3.1-pro",
        api_model="moonshotai/kimi-k3.1-pro",
        weights="moonshotai/Kimi-K3.1-Pro",
        revision="d9e99b0792a5e93b78ea9bea62a68167e36ddd9e",
        license="other (kimi-k3.1-pro)",
        parameters_b=2780,
        usd_per_mtok=(2.00, 10.00),
    ),
    # Single-GPU candidates for a hosted endpoint we run ourselves: each fits one 48 GB card
    # at 8-bit, so it can be served one request at a time on one pinned machine.
    OpenModel(
        name="qwen3.6-35b-a3b",
        api_model="qwen/qwen3.6-35b-a3b",
        weights="Qwen/Qwen3.6-35B-A3B",
        revision="345d467b117d1fd5eda9b879a5988de9ae5f47a7",
        license="Apache-2.0",
        parameters_b=36,
        usd_per_mtok=(0.10, 0.90),
    ),
    OpenModel(
        name="nemotron-3.5-lightning",
        api_model="nvidia/nemotron-3.5-lightning",
        weights="nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
        revision="a9904d24bcc1d289a1950fa9d2b978c47cf903b9",
        license="other (openmdw-1.1)",
        parameters_b=32,
        usd_per_mtok=(0.07, 0.20),
    ),
    OpenModel(
        name="qwen3.8-27b",
        api_model="qwen/qwen3.8-27b",
        weights="Qwen/Qwen3.8-27B",
        revision="37561816e66b5b9153b1b64c10968c18c1e6f4a0",
        license="Apache-2.0",
        parameters_b=28,
        usd_per_mtok=(0.15, 1.875),
    ),
    # US and EU origin (added 2026-11-07, after the Chinese-origin question).
    OpenModel(
        name="gpt-oss-120b",
        api_model="openai/gpt-oss-120b",
        weights="openai/gpt-oss-120b",
        revision="b5c939de8f754692c1647ca79fbf85e8c1e70f8a",
        license="Apache-2.0",
        parameters_b=117,
        usd_per_mtok=(0.013, 0.047),
    ),
    OpenModel(
        name="nemotron-3-ultra",
        api_model="nvidia/nemotron-3-ultra-550b-a55b",
        weights="nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16",
        revision="77df655d5e9f8362164ed14dd8b48f8bce657498",
        license="other (openmdw-1.1)",
        parameters_b=561,
        usd_per_mtok=(0.60, 2.40),
        quantizations=("fp4", "fp8", "bf16"),  # only 4-bit providers honor seed and schema
    ),
    OpenModel(
        name="mistral-large-4",
        api_model="mistralai/mistral-large-4-0",
        weights="mistralai/Mistral-Large-4-1T-A52B",
        revision="af26e7869af601441d5cdf75a1272469ddc3d059",
        license="other (unread)",
        parameters_b=1000,
        usd_per_mtok=(0.70, 2.10),
        quantizations=("unknown", "fp8", "bf16"),  # only Mistral serves it, precision unstated
    ),
    OpenModel(
        name="llama-4-maverick",
        api_model="meta-llama/llama-4-maverick",
        weights="meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        revision="73d14711bcc77c16df3470856949c3764056b617",
        license="other (llama4)",
        parameters_b=402,
        usd_per_mtok=(0.35, 1.00),
        reasons=False,
    ),
)
PROVIDER = {
    "data_collection": "deny",
    "require_parameters": True,
    "quantizations": ["fp8", "bf16", "fp16", "fp32"],
}


def model(name: str) -> OpenModel:
    for m in MODELS:
        if m.name == name:
            return m
    raise SystemExit(f"unknown model {name!r}; one of {', '.join(m.name for m in MODELS)}")


@dataclass(frozen=True)
class OpenParams:
    """What the call log and run record keep for a hosted call, in place of local settings."""

    api_model: str
    reasoning: str
    seed: int = SEED
    temperature: float = 0.0
    max_tokens: int = MAX_TOKENS

    def as_record(self) -> dict[str, str | int | float | bool]:
        return {"api_model": self.api_model, "reasoning": self.reasoning, "seed": self.seed,
                "temperature": self.temperature, "max_tokens": self.max_tokens,
                "grammar": "json_schema", "where": "hosted", "n_ctx": "provider's",
                "chat_template": "provider's"}  # fmt: skip


@dataclass
class Usage:
    calls: int = 0
    failed: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    providers: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"calls": self.calls, "failed": self.failed, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "cost_usd": round(self.cost_usd, 4),
                "seconds": round(self.seconds, 1), "providers": dict(self.providers)}  # fmt: skip


def _post(body: dict[str, Any], key: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "Mabillon eval",
        },  # fmt: skip
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class HostedModel:
    """Same `generate_json` surface as the local runtime, backed by a hosted open model.

    Never raises: a failed request, a refusal or an answer outside the schema comes back as a
    ModelOutput with an error, which the probe scores as invalid output (fail closed)."""

    spec: OpenModel
    reasoning: str = "medium"
    post: Any = None  # (body, key, timeout) -> response dict; tests and --dry-run pass one
    key: str | None = None
    retries: int = 4
    timeout: float = 180.0
    usage: Usage = field(default_factory=Usage)
    # One row per call, in call order, beside the call log (which keeps no provider): who
    # served each answer, so a changed repeat can be traced to a provider switch.
    served: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = self.spec.name
        self.sha256 = f"hosted:{self.spec.api_model}"
        self.params = OpenParams(
            self.spec.api_model, self.reasoning if self.spec.reasons else "none"
        )
        if self.post is None:
            self.post = _post
            self.key = self.key or os.environ.get("OPENROUTER_API_KEY")
            if not self.key:
                raise SystemExit("set OPENROUTER_API_KEY (or use --dry-run)")

    def body(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        p = self.params
        body: dict[str, Any] = {
            "model": p.api_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": p.temperature,
            "seed": p.seed,
            "max_tokens": p.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "strict": True, "schema": api_schema(schema)},
            },
            "reasoning": {"effort": p.reasoning, "exclude": True},
            "provider": (
                PROVIDER
                if self.spec.quantizations is None
                else {**PROVIDER, "quantizations": list(self.spec.quantizations)}
            ),
            "usage": {"include": True},
        }
        if not self.spec.reasons:
            del body["reasoning"]
        return body

    def generate_json(self, prompt: str, schema: dict[str, Any], params: Any = None) -> ModelOutput:
        out = self._generate(prompt, schema)
        resp = getattr(self, "_last", None) or {}
        self.served.append(
            {
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "provider": resp.get("provider"),
                "served_model": resp.get("model"),
                "request_id": resp.get("id"),
                "finish_reason": ((resp.get("choices") or [{}])[0]).get("finish_reason"),
                "raw_sha256": hashlib.sha256(out.raw_text.encode("utf-8")).hexdigest(),
                "error": out.error,
            }
        )
        return out

    def _generate(self, prompt: str, schema: dict[str, Any]) -> ModelOutput:
        self._last: dict[str, Any] | None = None
        start = time.perf_counter()
        resp, error = None, None
        for attempt in range(self.retries + 1):
            try:
                resp = self.post(self.body(prompt, schema), self.key, self.timeout)
                break
            except urllib.error.HTTPError as e:
                error = f"http {e.code}"
                if e.code not in (408, 429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
                error = f"request failed: {type(e).__name__}"
            time.sleep(min(2**attempt, 30))
        elapsed = time.perf_counter() - start
        self.usage.calls += 1
        self.usage.seconds += elapsed
        self._last = resp if isinstance(resp, dict) else None
        if resp is None or "choices" not in resp:
            self.usage.failed += 1
            reason = error or f"no answer: {str((resp or {}).get('error'))[:200]}"
            return ModelOutput("", None, reason, seconds=elapsed)
        u = resp.get("usage") or {}
        prompt_tokens = int(u.get("prompt_tokens") or 0)
        completion_tokens = int(u.get("completion_tokens") or 0)
        self.usage.input_tokens += prompt_tokens
        self.usage.output_tokens += completion_tokens
        inp, out = self.spec.usd_per_mtok
        cost = u.get("cost")
        self.usage.cost_usd += (
            float(cost)
            if cost is not None
            else (prompt_tokens * inp + completion_tokens * out) / 1_000_000
        )
        provider = str(resp.get("provider") or "unknown")
        self.usage.providers[provider] = self.usage.providers.get(provider, 0) + 1
        choice = resp["choices"][0]
        text = (choice.get("message") or {}).get("content") or ""
        stop = choice.get("finish_reason")
        if stop == "length":
            self.usage.failed += 1
            return ModelOutput(text, None, "max_tokens", prompt_tokens, completion_tokens,
                               elapsed, served_model=resp.get("model"))  # fmt: skip
        parsed, perr = parse_json_output(text, schema)
        return ModelOutput(
            raw_text=text,
            parsed=parsed,
            error=perr,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            seconds=elapsed,
            served_model=resp.get("model"),
            request_id=resp.get("id"),
            stop_reason=f"{stop} via {provider}",
        )


def dry_post(body: dict[str, Any], key: str | None, timeout: float) -> dict[str, Any]:
    """No network: 'irrelevant' for every stance item, as claude_bench's DryRunClient does."""
    answer = {"stance": "irrelevant", "quote": "", "rationale": "dry run"}
    return {
        "id": "dry-run",
        "model": body["model"],
        "provider": "dry-run",
        "choices": [{"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": len(body["messages"][0]["content"]) // 4,
            "completion_tokens": 20,
            "cost": 0.0,
        },  # fmt: skip
    }


def run_one(hosted: HostedModel, prompt_file: Path, repeat: int, out: Path) -> dict[str, Any]:
    from eval.probe.run_probe import run_model

    path = check_prompt_path(prompt_file)
    _reviewer, stance = probe_items(SIGNED_PROBE, LAYOUT)
    cost_before = hosted.usage.cost_usd
    providers_before = dict(hosted.usage.providers)
    served_before = len(hosted.served)
    out.mkdir(parents=True, exist_ok=True)
    res = run_model(hosted, [], stance, hosted.params, repeat, out, path,  # type: ignore[arg-type]
                    stance_only=True)  # fmt: skip
    res["layout"] = LAYOUT
    res["params"] = hosted.params.as_record()
    res["license"] = hosted.spec.license
    res["weights"] = f"{hosted.spec.weights}@{hosted.spec.revision}"
    res["usage"] = hosted.usage.as_dict()
    res["cost_usd_this_run"] = round(hosted.usage.cost_usd - cost_before, 4)
    res["providers_this_run"] = {
        k: n - providers_before.get(k, 0)
        for k, n in hosted.usage.providers.items()
        if n - providers_before.get(k, 0)
    }
    with (out / "served.jsonl").open("w", encoding="utf-8") as f:
        for row in hosted.served[served_before:]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "summary.json").write_text(
        json.dumps([res], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return res


class CaseLabeler:
    """The hosted model as case01's stance labeler. Its sha256 carries the cloud prefix, so the
    pipeline gives it the cloud stance prompt (v1.2, core/audit/prompts/stance_cloud.md), the
    prompt a hosted model would read in the product and the one the probe passes were on."""

    def __init__(self, hosted: HostedModel) -> None:
        self.hosted = hosted
        self.name = hosted.name
        self.sha256 = f"api:open:{hosted.spec.api_model}"
        self.params = hosted.params

    def generate_json(self, prompt: str, schema: dict[str, Any], params: Any = None) -> ModelOutput:
        return self.hosted.generate_json(prompt, schema, params)


def run_case(hosted: HostedModel, out: Path) -> dict[str, Any]:
    """Synthetic case01 through the real pipeline with this model as the stance labeler, then
    the simulated expert and the merge-gate scoring, as claude_bench does for Claude. Stage 2's
    bar: accuracy >= 0.80 and 0 false supported."""
    from core.contracts import GoldClaim
    from eval import run_pipeline as rp
    from eval.run_eval import load_jsonl, score

    case = check_case("case01")
    out.mkdir(parents=True, exist_ok=True)
    cost_before, calls_before = hosted.usage.cost_usd, len(hosted.served)
    start = time.perf_counter()
    preds = rp.run_once(case, "real", "accept", out, rp.assumption_sheet(case), "simulated",
                        labeler_model=CaseLabeler(hosted))  # fmt: skip
    wall = time.perf_counter() - start
    s = score(load_jsonl(rp.gold_path(case), GoldClaim), preds)
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    calls = len(hosted.served) - calls_before
    res = {
        "model": hosted.name,
        "case": case,
        "weights": f"{hosted.spec.weights}@{hosted.spec.revision}",
        "wall_seconds": round(wall, 1),
        "stance_calls": calls,
        "seconds_per_call": round(wall / calls, 2) if calls else None,
        "verdict_accuracy": round(s.verdict_accuracy, 3),
        "n_false_supported": s.n_false_supported,
        "confusion": s.confusion,
        "dropped_labels": run.get("dropped_labels"),
        "cost_usd": round(hosted.usage.cost_usd - cost_before, 4),
        "passes": s.n_false_supported == 0 and s.verdict_accuracy >= 0.80,
    }
    with (out / "served.jsonl").open("w", encoding="utf-8") as f:
        for row in hosted.served[calls_before:]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "case.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    return res


def _pct(v: object) -> str:
    return f"{v:.0%}" if isinstance(v, float) else "n/a"


SWAP_NOTE = (
    "Stage 1: no hosted open model passes. Nothing is self-hosted; the 14B stays the local"
    " model and Opus stays the only cloud option under review."
)


def verdict(out: Path, names: list[str]) -> str:
    text = candidates.verdict(out, names, SWAP_NOTE)
    lines = ["", "## Cost, providers and repeats (hosted; not reproducible by design)", ""]
    for name in names:
        for version in candidates.PROMPTS:
            summary = out / name / version / "summary.json"
            if not summary.is_file():
                continue
            row = json.loads(summary.read_text(encoding="utf-8"))[0]
            rep = (row.get("expert_confirms") or {}).get("reported") or {}
            lines.append(
                f"- {name} {version}: ${row.get('cost_usd_this_run')}, providers"
                f" {row.get('providers_this_run')}, second answer byte-identical on"
                f" {_pct(row.get('stance_repeat_identical'))} of items, same label on"
                f" {_pct(rep.get('labels_identical_across_repeats'))}, weights"
                f" {row.get('weights')}, license {row.get('license')}"
            )
    return text + "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default=",".join(m.name for m in MODELS))
    ap.add_argument("--out", type=Path, default=Path("eval/out/open_bench"))
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--reasoning", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--dry-run", action="store_true", help="stand-in answers, no network")
    ap.add_argument("--list", action="store_true", help="print the screened models and exit")
    ap.add_argument("--case", action="store_true", help="stage 2: synthetic case01, not the probe")
    args = ap.parse_args(argv)

    names = [n.strip() for n in args.models.split(",") if n.strip()]
    specs = [model(n) for n in names]
    if args.list:
        for m in specs:
            inp, out = m.usd_per_mtok
            print(f"{m.name}: {m.api_model}, {m.weights}@{m.revision[:12]}, {m.parameters_b}B,"
                  f" {m.license}, ${inp}/${out} per M tokens")  # fmt: skip
        return 0
    if args.case:
        for spec in specs:
            hosted = HostedModel(spec, args.reasoning, post=dry_post if args.dry_run else None)
            print(json.dumps(run_case(hosted, args.out / spec.name / "case01"), indent=2))
        return 0
    for spec in specs:
        hosted = HostedModel(spec, args.reasoning, post=dry_post if args.dry_run else None)
        for version, prompt_file in candidates.PROMPTS.items():
            print(f"{spec.name} {version}", file=sys.stderr, flush=True)
            run_one(hosted, ROOT / prompt_file, args.repeat,
                    args.out / spec.name / version)  # fmt: skip
        print(f"{spec.name}: ${hosted.usage.cost_usd:.2f} so far", file=sys.stderr, flush=True)
    text = verdict(args.out, names)
    (args.out / "VERDICT.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
