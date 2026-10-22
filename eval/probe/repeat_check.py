"""Repeat check: does a local model give the same output when asked the same thing again?

Usage:
  python -m eval.probe.repeat_check --models eval/probe/models.local.json [--model NAME]
      [--stance-prompt core/audit/prompts/stance.md] [--cpu-items 20] [--claims C01,C03,...]
      [--stages A,B,C,D] [--chat-template gguf|no-think] [--out eval/out/repeat/<time>]
  python -m eval.probe.repeat_check --dry-run
      No model: prints the calls each stage makes and a time estimate.

Mabillon records each local model run's file SHA-256, prompt, settings and seed, and decodes
greedily (temperature 0, core/llm/runtime.py), so a repeat is expected to match. That is
measured here, not assumed; until it passes, nothing may say local labels can be regenerated.
Each stage runs in its own process, so a fresh load is a fresh load:

  A  the signed probe set (stance only), the model loaded once, every item asked twice in a row
  B  the same items in a new process, asked once: compared with A's first answers
  C  the first --cpu-items items with no GPU offload (n_gpu_layers=0): compared with A
  D  a case01 audit on a subset of claims, twice, each in a new process on a fresh database,
     through the product's own wiring: stored model outputs and evidence rows compared

For each comparison it reports how many answers are identical byte for byte, how many give the
same stance and quote (the label), and lists every difference. Writes <out>/summary.md (paste
it back) and <out>/summary.json, with the llama-cpp-python version, the machine and the commit.
Synthetic data only; case02 is never read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess  # noqa: S404 - this script and git only, fixed arguments
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.probe import prompts
from eval.probe.from_draft import convert
from eval.probe.run_probe import load_items, split_gated

PROBE_SET = Path("eval/gold/probe/probe.jsonl")
LAYOUT = "product_members"  # the layout the product sends (eval/probe/mac_v12.sh)
# A case01 subset of about 85 stance calls (time_case.py --dry-run, 2026-10-20): every claim
# type the full case has, at a third of a full pass's time.
CLAIMS = ("C01", "C03", "C09", "C13", "C15", "C18")
STAGES = ("A", "B", "C", "D")
# Mac run 2026-10-12, flash runtime, Qwen3-14B Q4: 22.5 s per probe call. CPU only is not
# measured; 5x is a guess for the estimate only.
SECONDS_PER_CALL = 22.5
CPU_FACTOR = 5


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _label(raw: str) -> tuple[str | None, str | None]:
    try:
        obj = json.loads(raw)
    except ValueError:
        return None, None
    if not isinstance(obj, dict):
        return None, None
    return obj.get("stance"), obj.get("quote")


# ---------------------------------------------------------------- one stage, in its own process


def _entry(models: Path, name: str | None) -> dict[str, Any]:
    from eval.bench.fair_steps import pick_entry

    return pick_entry(json.loads(models.read_text(encoding="utf-8")), name)


def _probe_items_all() -> list[dict[str, Any]]:
    """The signed probe set's stance items, gated first, as the probe asks them."""
    stance = [convert(row, LAYOUT)[1] for row in load_items(PROBE_SET)]
    gated, extra = split_gated(stance)
    return gated + extra


def _probe_items(limit: int | None = None) -> list[dict[str, Any]]:
    items = _probe_items_all()
    return items[:limit] if limit else items


def _probe_prompt(it: dict[str, Any], stance_path: Path) -> str:
    """The prompt run_probe.score_stance sends for one item."""
    record = it.get("record") or prompts.record_line(it["record_text"], it["context"])
    takes_claim = prompts.has_placeholder(stance_path, "claim")
    claim = (it.get("claim") or prompts.NO_CLAIM) if takes_claim else None
    return prompts.stance_prompt(it["assumption"], record, it["context"], stance_path, claim)


def _load(entry: dict[str, Any], n_ctx: int, gpu: bool, chat_template: str = "gguf") -> Any:
    from core.llm.runtime import (
        PRODUCT_RUNTIME,
        GenerationParams,
        LlamaCppModel,
        ModelSpec,
        with_runtime,
    )

    params = with_runtime(GenerationParams(n_ctx=n_ctx), PRODUCT_RUNTIME, chat_template)
    if not gpu:
        params = replace(params, n_gpu_layers=0)
    spec = ModelSpec(
        name=entry["name"],
        path=Path(entry["path"]).expanduser(),
        sha256=entry.get("sha256"),
        license=entry.get("license"),
    )
    return LlamaCppModel(spec, params), params


def stage_probe(args: argparse.Namespace, stage: str) -> None:
    entry = _entry(args.models, args.model)
    model, params = _load(entry, args.n_ctx, gpu=stage != "C", chat_template=args.chat_template)
    items = _probe_items(args.cpu_items if stage == "C" else None)
    asks = 2 if stage == "A" else 1
    out = args.out / f"{stage}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for n, it in enumerate(items, 1):
            prompt = _probe_prompt(it, args.stance_prompt)
            for ask in range(1, asks + 1):
                print(f"  {stage} {n}/{len(items)} {it['id']} ask {ask}", file=sys.stderr)
                start = time.perf_counter()
                res = model.generate_json(prompt, prompts.STANCE_SCHEMA, params)
                row = {
                    "key": it["id"],
                    "ask": ask,
                    "prompt_sha256": _sha(prompt),
                    "raw": res.raw_text,
                    "seconds": round(time.perf_counter() - start, 2),
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
    _meta(args, stage, entry, params.as_record(), len(items) * asks)


def stage_case(args: argparse.Namespace, stage: str) -> None:
    from core.audit._local_model import LazyModel, ModelConfig
    from core.llm.runtime import PRODUCT_RUNTIME, sha256_file, with_runtime
    from eval import run_pipeline as rp
    from eval.probe import time_case

    entry = _entry(args.models, args.model)
    path = Path(entry["path"]).expanduser()
    model = LazyModel(
        ModelConfig(
            name=entry["name"],
            path=path,
            sha256=entry.get("sha256") or sha256_file(path),
            n_ctx=args.n_ctx,
        )
    )
    model.params = with_runtime(model.params, PRODUCT_RUNTIME, args.chat_template)
    conn = rp.build_case("case01", args.out / stage / "case01.db")
    try:
        # The product's stance prompt (core/audit/prompts/stance.md) through the product's wiring.
        time_case.audit_once(conn, model, time_case.default_spec(), False, list(args.claims))
        rows = conn.execute(
            "SELECT subject_json, prompt, raw_output, outcome FROM model_calls ORDER BY rowid"
        ).fetchall()
        evidence = conn.execute(
            "SELECT id, stance, quote, rationale FROM evidence_items ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    with (args.out / f"{stage}.jsonl").open("w", encoding="utf-8") as f:
        for subject, prompt, raw, outcome in rows:
            key = f"{subject} {_sha(prompt)[:12]}"
            f.write(
                json.dumps(
                    {
                        "key": key,
                        "ask": 1,
                        "prompt_sha256": _sha(prompt),
                        "raw": raw,
                        "outcome": outcome,
                    },
                    ensure_ascii=False,
                )  # fmt: skip
                + "\n"
            )
    with (args.out / f"{stage}.evidence.jsonl").open("w", encoding="utf-8") as f:
        for eid, stance, quote, rationale in evidence:
            row = {"id": eid, "stance": stance, "quote": quote, "rationale": rationale}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _meta(args, stage, entry, model.params.as_record(), len(rows))


def _meta(
    args: argparse.Namespace, stage: str, entry: dict[str, Any], params: dict, n: int
) -> None:
    try:
        import llama_cpp

        llama = getattr(llama_cpp, "__version__", "unknown")
    except ImportError:
        llama = "not installed"
    meta = {
        "stage": stage,
        "model": entry["name"],
        "model_sha256": entry.get("sha256"),
        "params": params,
        "calls": n,
        "llama_cpp_python": llama,
        "finished_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (args.out / f"{stage}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")


# ---------------------------------------------------------------- comparing


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def compare(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> dict[str, Any]:
    """Answers matched by (key, prompt): identical bytes, same label, and every difference."""
    a = {(r["key"], r["prompt_sha256"]): r["raw"] for r in first}
    b = {(r["key"], r["prompt_sha256"]): r["raw"] for r in second}
    both = sorted(set(a) & set(b))
    diffs = []
    same_raw = same_label = 0
    for k in both:
        if a[k] == b[k]:
            same_raw += 1
            same_label += 1
            continue
        if _label(a[k]) == _label(b[k]):
            same_label += 1
        diffs.append({"key": k[0], "first": a[k], "second": b[k]})
    return {
        "compared": len(both),
        "only_in_first": len(set(a) - set(b)),
        "only_in_second": len(set(b) - set(a)),
        "raw_identical": same_raw,
        "label_identical": same_label,
        "differences": diffs,
    }


def _evidence_compare(first: Path, second: Path) -> dict[str, Any]:
    a = {r["id"]: r for r in _read(first)}
    b = {r["id"]: r for r in _read(second)}
    return {
        "items_first": len(a),
        "items_second": len(b),
        "same_ids": set(a) == set(b),
        "same_rows": a == b,
        "only_in_first": sorted(set(a) - set(b))[:20],
        "only_in_second": sorted(set(b) - set(a))[:20],
    }


def summarize(out: Path) -> dict[str, Any]:
    a = _read(out / "A.jsonl")
    a1 = [r for r in a if r["ask"] == 1]
    a2 = [{**r, "ask": 1} for r in a if r["ask"] == 2]
    result: dict[str, Any] = {"stages": {}}
    for stage in STAGES:
        meta = out / f"{stage}.meta.json"
        result["stages"][stage] = json.loads(meta.read_text()) if meta.exists() else None
    if a:
        result["A_same_process_repeat"] = compare(a1, a2)
    if (out / "B.jsonl").exists():
        result["B_fresh_load_vs_A"] = compare(a1, _read(out / "B.jsonl"))
    if (out / "C.jsonl").exists():
        result["C_cpu_vs_A"] = compare(a1, _read(out / "C.jsonl"))
    if (out / "D1.jsonl").exists() and (out / "D2.jsonl").exists():
        result["D_case01_two_audits"] = compare(_read(out / "D1.jsonl"), _read(out / "D2.jsonl"))
        result["D_case01_evidence"] = _evidence_compare(
            out / "D1.evidence.jsonl", out / "D2.evidence.jsonl"
        )
    return result


def markdown(summary: dict[str, Any]) -> str:
    lines = [f"# Repeat check ({summary.get('run_at_utc')})", ""]
    for key in ("commit", "machine", "model", "model_sha256", "llama_cpp_python",
                "stance_prompt"):  # fmt: skip
        lines.append(f"- {key}: {summary.get(key)}")
    lines += ["", "| comparison | compared | identical bytes | same label | differences |",
              "|---|---|---|---|---|"]  # fmt: skip
    names = {
        "A_same_process_repeat": "A: asked twice, model loaded once",
        "B_fresh_load_vs_A": "B: fresh load vs A",
        "C_cpu_vs_A": "C: CPU only vs A",
        "D_case01_two_audits": "D: two case01 audits (stored outputs)",
    }
    for key, title in names.items():
        c = summary.get(key)
        if c is None:
            lines.append(f"| {title} | not run | | | |")
            continue
        lines.append(
            f"| {title} | {c['compared']} | {c['raw_identical']} | {c['label_identical']} "
            f"| {len(c['differences'])} |"
        )
    ev = summary.get("D_case01_evidence")
    if ev:
        lines += ["", f"case01 evidence rows identical across the two audits: {ev['same_rows']} "
                  f"({ev['items_first']} vs {ev['items_second']} items)"]  # fmt: skip
    for key, title in names.items():
        c = summary.get(key)
        if c and c["differences"]:
            lines += ["", f"## Differences, {title}", ""]
            for d in c["differences"][:20]:
                lines += [f"- {d['key']}", f"  - first:  {d['first'][:400]}",
                          f"  - second: {d['second'][:400]}"]  # fmt: skip
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- driver


def _git_commit() -> str:
    try:
        out = subprocess.run(  # noqa: S603 - fixed arguments
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True, text=True, check=True, timeout=10,
        )  # fmt: skip
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def estimate(cpu_items: int, claims: tuple[str, ...]) -> dict[str, Any]:
    """Calls per stage and a rough time, from the 2026-10-12 Mac speed (unverified today)."""
    probe = len(_probe_items())
    case_calls = None
    try:
        from eval.probe import time_case

        tmp = Path("eval/out/repeat/dry_run")
        per_claim = time_case.dry_run("case01", time_case.default_spec(), tmp)["calls_per_claim"]
        case_calls = sum(per_claim.get(c, 0) for c in claims)
    except Exception as e:  # noqa: BLE001 - the estimate is a convenience
        print(f"case01 dry run failed: {e}", file=sys.stderr)
    calls = {"A": 2 * probe, "B": probe, "C": min(cpu_items, probe), "D": 2 * (case_calls or 0)}
    seconds = (calls["A"] + calls["B"] + calls["D"]) * SECONDS_PER_CALL
    seconds += calls["C"] * SECONDS_PER_CALL * CPU_FACTOR
    return {"calls": calls, "estimated_hours": round(seconds / 3600, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", type=Path, help="the probe's models.local.json")
    ap.add_argument("--model", default=None, help="the entry's name (default: the 14B)")
    ap.add_argument("--stance-prompt", type=Path, default=prompts.STANCE_SIGNED,
                    help="stance prompt for stages A to C (default: the 14B's own)")  # fmt: skip
    ap.add_argument("--chat-template", choices=["gguf", "no-think"], default="gguf",
                    help="no-think for a model whose template opens a thinking block")  # fmt: skip
    ap.add_argument("--cpu-items", type=int, default=20)
    ap.add_argument("--claims", default=",".join(CLAIMS))
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--n-ctx", type=int, default=8192)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true", help="no model: calls and a time estimate")
    ap.add_argument("--stage", default=None, help=argparse.SUPPRESS)  # one stage, internal
    args = ap.parse_args(argv)
    args.claims = tuple(c.strip() for c in args.claims.split(",") if c.strip())

    if args.dry_run:
        print(json.dumps(estimate(args.cpu_items, args.claims), indent=2))
        return 0
    if args.models is None:
        ap.error("pass --models (or --dry-run)")
    if args.stage is not None:
        if args.stage in ("A", "B", "C"):
            stage_probe(args, args.stage)
        else:
            stage_case(args, args.stage)
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    args.out = args.out or Path("eval/out/repeat") / stamp
    if args.out.exists():
        ap.error(f"{args.out} already exists; give a new --out")
    args.out.mkdir(parents=True)
    entry = _entry(args.models, args.model)
    print(json.dumps(estimate(args.cpu_items, args.claims)), file=sys.stderr)
    wanted = [s.strip() for s in args.stages.split(",")]
    runs = [s for s in ("A", "B", "C") if s in wanted]
    runs += ["D1", "D2"] if "D" in wanted else []
    failed = []
    for stage in runs:
        cmd = [sys.executable, "-m", "eval.probe.repeat_check", "--stage", stage,
               "--models", str(args.models), "--stance-prompt", str(args.stance_prompt),
               "--cpu-items", str(args.cpu_items), "--claims", ",".join(args.claims),
               "--n-ctx", str(args.n_ctx), "--out", str(args.out),
               "--chat-template", args.chat_template]  # fmt: skip
        if args.model:
            cmd += ["--model", args.model]
        print(f"stage {stage}: starting {datetime.now(UTC):%H:%M}Z", file=sys.stderr, flush=True)
        if subprocess.run(cmd, check=False).returncode != 0:  # noqa: S603 - this script
            failed.append(stage)
    summary = {
        "run_at_utc": stamp,
        "commit": _git_commit(),
        "machine": platform.platform(),
        "model": entry["name"],
        "model_sha256": entry.get("sha256"),
        "llama_cpp_python": next(
            (m["llama_cpp_python"] for m in summarize(args.out)["stages"].values() if m), None
        ),
        "stance_prompt": f"{args.stance_prompt}@{prompts.prompt_version(args.stance_prompt)}",
        "failed_stages": failed,
        **summarize(args.out),
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md = markdown(summary)
    if failed:
        md += f"\nStages that failed: {', '.join(failed)} (see the output above).\n"
    (args.out / "summary.md").write_text(md, encoding="utf-8")
    print(md)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
