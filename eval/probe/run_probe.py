"""GPU test: run the probe items through each local model and score them against the pass bars.

Usage:
  python -m eval.probe.run_probe --models eval/probe/models.local.json [--repeat 2]
      [--reviewer eval/probe/smoke_reviewer.jsonl] [--stance eval/probe/smoke_stance.jsonl]
      [--out eval/out/probe]

Pass bars (wave2-consensus.md, section 4): valid output 100%, quote check >= 95%,
"supports" precision >= 95% and recall >= 90%, zero reviewer false accepts on overreach items,
identical output on a repeat run. Results on the smoke items are provisional: the signed probe
set replaces them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # noqa: S404 - nvidia-smi only, fixed arguments
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.llm.calls import CallLog, make_record
from core.llm.runtime import GenerationParams, LocalModel, ModelOutput
from eval.probe import prompts

HERE = Path(__file__).parent
BARS = {
    "valid_output": 1.0,
    "quote_verified": 0.95,
    "supports_precision": 0.95,
    "supports_recall": 0.90,
    "overreach_false_accepts": 0,
    "repeat_identical": 1.0,
}


def load_items(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


@dataclass
class ReviewerScore:
    n: int = 0
    valid: int = 0
    correct: int = 0
    overreach_items: int = 0
    overreach_false_accepts: int = 0
    clear_items: int = 0
    clear_accepted: int = 0
    repeat_identical: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StanceScore:
    n: int = 0
    valid: int = 0
    correct: int = 0
    quote_verified: int = 0
    predicted_supports: int = 0
    true_supports_predicted: int = 0
    gold_supports: int = 0
    repeat_identical: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)


def _call(
    model: LocalModel,
    prompt: str,
    schema: dict[str, Any],
    params: GenerationParams,
    repeat: int,
    log: CallLog | None,
    *,
    purpose: str,
    version: str,
    item_id: str,
) -> list[ModelOutput]:
    outs = []
    for _ in range(repeat):
        out = model.generate_json(prompt, schema, params)
        outs.append(out)
        if log is not None:
            log.append(
                make_record(
                    model_name=model.name,
                    model_sha256=model.sha256,
                    purpose=purpose,
                    prompt_version=version,
                    prompt=prompt,
                    params=params,
                    item_id=item_id,
                    output=out,
                )
            )
    return outs


def score_reviewer(
    model: LocalModel,
    items: Iterable[dict[str, Any]],
    params: GenerationParams,
    repeat: int = 2,
    log: CallLog | None = None,
) -> ReviewerScore:
    s = ReviewerScore()
    version = prompts.prompt_version(prompts.REVIEWER_PROMPT)
    for it in items:
        prompt = prompts.reviewer_prompt(it["assumption"], it["quote"], it["context"])
        outs = _call(model, prompt, prompts.REVIEWER_SCHEMA, params, repeat, log,
                     purpose="review", version=version, item_id=it["id"])  # fmt: skip
        first = outs[0]
        s.n += 1
        s.repeat_identical += all(o.raw_text == first.raw_text for o in outs)
        # Fail closed: an invalid output is a dismissal.
        decision = first.parsed["decision"] if first.parsed else "dismiss"
        s.valid += first.ok
        s.correct += first.ok and decision == it["expected"]
        if it["overreach"]:
            s.overreach_items += 1
            s.overreach_false_accepts += decision == "accept"
        if it["expected"] == "accept":
            s.clear_items += 1
            s.clear_accepted += decision == "accept"
        if not first.ok or decision != it["expected"]:
            s.failures.append({"id": it["id"], "category": it["category"],
                               "expected": it["expected"], "got": decision,
                               "error": first.error, "raw": first.raw_text[:300]})  # fmt: skip
    return s


def score_stance(
    model: LocalModel,
    items: Iterable[dict[str, Any]],
    params: GenerationParams,
    repeat: int = 2,
    log: CallLog | None = None,
    stance_path: Path = prompts.STANCE_DRAFT,
) -> StanceScore:
    s = StanceScore()
    version = prompts.prompt_version(stance_path)
    for it in items:
        record = prompts.record_line(it["record_text"], it["context"])
        prompt = prompts.stance_prompt(it["assumption"], record, it["context"], stance_path)
        outs = _call(model, prompt, prompts.STANCE_SCHEMA, params, repeat, log,
                     purpose="stance", version=version, item_id=it["id"])  # fmt: skip
        first = outs[0]
        s.n += 1
        s.repeat_identical += all(o.raw_text == first.raw_text for o in outs)
        s.gold_supports += it["expected"] == "supports"
        if not first.ok:
            s.failures.append({"id": it["id"], "error": first.error, "raw": first.raw_text[:300]})
            continue
        s.valid += 1
        quote_ok = bool(first.parsed["quote"]) and first.parsed["quote"] in it["record_text"]
        s.quote_verified += quote_ok
        # An unverified quote is discarded, so its label cannot count as "supports".
        stance = first.parsed["stance"] if quote_ok else "dropped"
        s.correct += stance == it["expected"]
        if stance == "supports":
            s.predicted_supports += 1
            s.true_supports_predicted += it["expected"] == "supports"
        if stance != it["expected"]:
            s.failures.append({"id": it["id"], "category": it["category"],
                               "expected": it["expected"], "got": stance,
                               "quote": first.parsed["quote"][:200]})  # fmt: skip
    return s


def summarize(r: ReviewerScore, st: StanceScore) -> dict[str, Any]:
    m = {
        "reviewer_valid_output": _ratio(r.valid, r.n),
        "reviewer_accuracy": _ratio(r.correct, r.n),
        "overreach_false_accepts": r.overreach_false_accepts,
        "overreach_items": r.overreach_items,
        "reviewer_clear_accept_rate": _ratio(r.clear_accepted, r.clear_items),
        "reviewer_repeat_identical": _ratio(r.repeat_identical, r.n),
        "stance_valid_output": _ratio(st.valid, st.n),
        "stance_accuracy": _ratio(st.correct, st.n),
        "quote_verified": _ratio(st.quote_verified, st.valid),
        "supports_precision": _ratio(st.true_supports_predicted, st.predicted_supports),
        "supports_recall": _ratio(st.true_supports_predicted, st.gold_supports),
        "stance_repeat_identical": _ratio(st.repeat_identical, st.n),
    }
    m["bars"] = check_bars(m)
    m["passes_all"] = all(m["bars"].values())
    return m


def check_bars(m: dict[str, Any]) -> dict[str, bool]:
    def ge(value: float | None, bar: float) -> bool:
        return value is not None and value >= bar

    return {
        "valid_output_100": ge(m["reviewer_valid_output"], 1.0)
        and ge(m["stance_valid_output"], 1.0),
        "quote_verified_95": ge(m["quote_verified"], BARS["quote_verified"]),
        "supports_precision_95": ge(m["supports_precision"], BARS["supports_precision"]),
        "supports_recall_90": ge(m["supports_recall"], BARS["supports_recall"]),
        "zero_overreach_false_accepts": m["overreach_false_accepts"] == 0,
        "repeat_identical": ge(m["reviewer_repeat_identical"], 1.0)
        and ge(m["stance_repeat_identical"], 1.0),
    }


def gpu_memory_mib() -> int | None:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed arguments, local binary
            [exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        )  # fmt: skip
    except (subprocess.SubprocessError, OSError):
        return None
    return int(out.stdout.split()[0])


def run_model(
    model: LocalModel,
    reviewer_items: list[dict[str, Any]],
    stance_items: list[dict[str, Any]],
    params: GenerationParams,
    repeat: int,
    out_dir: Path,
    stance_path: Path = prompts.STANCE_DRAFT,
) -> dict[str, Any]:
    log = CallLog(out_dir / f"{model.name}.calls.jsonl")
    r = score_reviewer(model, reviewer_items, params, repeat, log)
    st = score_stance(model, stance_items, params, repeat, log, stance_path)
    result = {"model": model.name, "sha256": model.sha256, **summarize(r, st)}
    result["stance_prompt"] = f"{stance_path.name}@{prompts.prompt_version(stance_path)}"
    result["reviewer_failures"] = r.failures
    result["stance_failures"] = st.failures
    calls = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
    tokens = sum(c["completion_tokens"] for c in calls)
    seconds = sum(c["seconds"] for c in calls)
    result["tokens_per_second"] = round(tokens / seconds, 1) if seconds else None
    result["mean_seconds_per_call"] = round(seconds / len(calls), 2) if calls else None
    return result


def table(results: list[dict[str, Any]]) -> str:
    def f(v: object) -> str:
        if v is None:
            return "n/a"
        return f"{v:.0%}" if isinstance(v, float) else str(v)

    cols = ["model", "reviewer_valid_output", "reviewer_accuracy", "overreach_false_accepts",
            "reviewer_clear_accept_rate", "stance_valid_output", "quote_verified",
            "supports_precision", "supports_recall", "reviewer_repeat_identical",
            "stance_repeat_identical", "tokens_per_second", "passes_all"]  # fmt: skip
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for res in results:
        lines.append("| " + " | ".join(f(res.get(c)) for c in cols) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--reviewer", type=Path, default=HERE / "smoke_reviewer.jsonl")
    ap.add_argument("--stance", type=Path, default=HERE / "smoke_stance.jsonl")
    ap.add_argument("--stance-prompt", type=Path, default=prompts.STANCE_DRAFT,
                    help="stance prompt file, e.g. thread 6's docs/prompts/stance.md")  # fmt: skip
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--n-ctx", type=int, default=8192)
    ap.add_argument("--out", type=Path, default=Path("eval/out/probe"))
    args = ap.parse_args(argv)

    from core.llm.runtime import LlamaCppModel, ModelSpec

    args.out.mkdir(parents=True, exist_ok=True)
    reviewer_items = load_items(args.reviewer)
    stance_items = load_items(args.stance)
    params = GenerationParams(n_ctx=args.n_ctx)
    results = []
    for entry in json.loads(args.models.read_text(encoding="utf-8")):
        spec = ModelSpec(name=entry["name"], path=Path(entry["path"]),
                         sha256=entry.get("sha256"), license=entry.get("license"))  # fmt: skip
        before = gpu_memory_mib()
        try:
            model = LlamaCppModel(spec, params)
        except Exception as e:  # noqa: BLE001 - report and move on to the next model
            results.append({"model": spec.name, "load_error": str(e), "passes_all": False})
            continue
        loaded = gpu_memory_mib()
        res = run_model(model, reviewer_items, stance_items, params, args.repeat, args.out,
                        args.stance_prompt)  # fmt: skip
        res["license"] = spec.license
        res["vram_used_mib"] = None if loaded is None or before is None else loaded - before
        results.append(res)
        del model
        print(f"{spec.name}: passes_all={res['passes_all']}", file=sys.stderr)
    (args.out / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = table(results)
    (args.out / "summary.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
