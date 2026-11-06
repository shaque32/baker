"""Repeat check: does a local model give the same output when asked the same thing again?

Usage:
  python -m eval.probe.repeat_check --models eval/probe/models.local.json [--model NAME]
      [--stance-prompt core/audit/prompts/stance.md] [--cpu-items 20] [--claims C01,C03,...]
      [--stages A,B,C,D] [--chat-template gguf|no-think] [--out eval/out/repeat/<time>]
  python -m eval.probe.repeat_check --dry-run
      No model: prints the calls each stage makes and a time estimate.
  python -m eval.probe.repeat_check --compare FIRST SECOND [--out DIR]
      No model: two finished runs' folders (two machines, for example AWS and the Mac) compared
      on what both asked: the probe answers (A, first asks) and the case01 audit (D1).

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
same stance and quote (the label), and lists every difference. A failed generation or an answer
that is not a stance object never counts as a match: it is counted under "failed" instead.
Writes <out>/summary.md (paste it back) and <out>/summary.json, with the llama-cpp-python
version, the machine and its graphics card and driver, the model file's digest and the commit
(marked if the checkout had uncommitted changes). `--host FILE` adds what a cloud machine is
(eval/probe/aws_repeat.sh passes the AWS image, instance type and CUDA compiler).
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


def _label(raw: str | None) -> tuple[str | None, str | None]:
    try:
        obj = json.loads(raw or "")
    except ValueError:
        return None, None
    if not isinstance(obj, dict):
        return None, None
    return obj.get("stance"), obj.get("quote")


def _usable(row: dict[str, Any]) -> bool:
    """An answer the model actually gave: no generation error, and a stance object."""
    return not row.get("error") and _label(row.get("raw"))[0] is not None


# ---------------------------------------------------------------- one stage, in its own process


def _entry(models: Path, name: str | None) -> dict[str, Any]:
    from eval.probe.model_entry import pick_entry

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
                    "error": res.error,
                    "seconds": round(time.perf_counter() - start, 2),
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
    sha = getattr(model, "sha256", None) or entry.get("sha256")
    _meta(args, stage, entry, sha, params.as_record(), len(items) * asks)


def stage_case(args: argparse.Namespace, stage: str) -> None:
    from core.audit._local_model import LazyModel, ModelConfig
    from core.llm.runtime import PRODUCT_RUNTIME, sha256_file, with_runtime
    from eval import run_pipeline as rp
    from eval.probe import time_case

    entry = _entry(args.models, args.model)
    path = Path(entry["path"]).expanduser()
    sha = entry.get("sha256") or sha256_file(path)
    model = LazyModel(ModelConfig(name=entry["name"], path=path, sha256=sha, n_ctx=args.n_ctx))
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
                        # quote_failed is a usable answer whose quote did not check out
                        "error": outcome if outcome in ("invalid_output", "error") else None,
                    },
                    ensure_ascii=False,
                )  # fmt: skip
                + "\n"
            )
    with (args.out / f"{stage}.evidence.jsonl").open("w", encoding="utf-8") as f:
        for eid, stance, quote, rationale in evidence:
            row = {"id": eid, "stance": stance, "quote": quote, "rationale": rationale}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _meta(args, stage, entry, sha, model.params.as_record(), len(rows))


def _meta(
    args: argparse.Namespace,
    stage: str,
    entry: dict[str, Any],
    sha: str | None,
    params: dict,
    n: int,
) -> None:
    """sha: the model file's digest as the run resolved it (computed when the entry has none)."""
    try:
        import llama_cpp

        llama = getattr(llama_cpp, "__version__", "unknown")
    except ImportError:
        llama = "not installed"
    meta = {
        "stage": stage,
        "model": entry["name"],
        "model_sha256": sha,
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
    """Answers matched by (key, prompt): identical bytes, same label, and every difference. A
    pair where either answer failed (_usable) counts as failed, never as a match."""
    a = {(r["key"], r["prompt_sha256"]): r for r in first}
    b = {(r["key"], r["prompt_sha256"]): r for r in second}
    both = sorted(set(a) & set(b))
    diffs, failures = [], []
    same_raw = same_label = 0
    for k in both:
        ra, rb = a[k]["raw"] or "", b[k]["raw"] or ""
        if not (_usable(a[k]) and _usable(b[k])):
            failures.append(
                {"key": k[0], "first": a[k].get("error") or ra, "second": b[k].get("error") or rb}
            )
            continue
        if ra == rb:
            same_raw += 1
            same_label += 1
            continue
        if _label(ra) == _label(rb):
            same_label += 1
        diffs.append({"key": k[0], "first": ra, "second": rb})
    return {
        "compared": len(both),
        "only_in_first": len(set(a) - set(b)),
        "only_in_second": len(set(b) - set(a)),
        "failed": len(failures),
        "raw_identical": same_raw,
        "label_identical": same_label,
        "differences": diffs,
        "failures": failures,
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
    for stage in ("A", "B", "C", "D1", "D2"):
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
    for key in ("commit", "machine", "gpu", "model", "model_sha256", "llama_cpp_python",
                "stance_prompt"):  # fmt: skip
        lines.append(f"- {key}: {summary.get(key)}")
    for key, value in (summary.get("host") or {}).items():
        lines.append(f"- {key}: {value}")
    lines += ["", "| comparison | compared | failed | identical bytes | same label | differences |",
              "|---|---|---|---|---|---|"]  # fmt: skip
    names = {
        "A_same_process_repeat": "A: asked twice, model loaded once",
        "B_fresh_load_vs_A": "B: fresh load vs A",
        "C_cpu_vs_A": "C: CPU only vs A",
        "D_case01_two_audits": "D: two case01 audits (stored outputs)",
    }
    for key, title in names.items():
        c = summary.get(key)
        if c is None:
            lines.append(f"| {title} | not run | | | | |")
            continue
        lines.append(
            f"| {title} | {c['compared']} | {c['failed']} | {c['raw_identical']} "
            f"| {c['label_identical']} "
            f"| {len(c['differences'])} |"
        )
    ev = summary.get("D_case01_evidence")
    if ev:
        lines += ["", f"case01 evidence rows identical across the two audits: {ev['same_rows']} "
                  f"({ev['items_first']} vs {ev['items_second']} items)"]  # fmt: skip
    for key, title in names.items():
        c = summary.get(key) or {}
        for part, head in (("failures", "Failed answers"), ("differences", "Differences")):
            if not c.get(part):
                continue
            lines += ["", f"## {head}, {title}", ""]
            for d in c[part][:20]:
                lines += [f"- {d['key']}", f"  - first:  {d['first'][:400]}",
                          f"  - second: {d['second'][:400]}"]  # fmt: skip
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- two machines


CROSS = {
    "probe": ("A.jsonl", "probe set, first asks (A)"),
    "case01": ("D1.jsonl", "case01 audit, first (D1)"),
}

# What each run says about itself, printed above the comparison.
RUN_KEYS = ("run_at_utc", "commit", "machine", "gpu", "model_sha256", "llama_cpp_python",
            "stance_prompt")  # fmt: skip


def _first_asks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("ask", 1) == 1]


def compare_runs(first: Path, second: Path) -> dict[str, Any]:
    """Two finished runs, usually on two machines, compared on the answers both gave to the same
    prompt (matched by item and prompt digest, as in compare). The runs are only comparable for
    the same model file: a different digest is reported and nothing is compared."""
    runs = []
    for folder in (first, second):
        path = folder / "summary.json"
        summary = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        runs.append(
            {
                "folder": str(folder),
                **{k: summary.get(k) for k in RUN_KEYS},
                "host": summary.get("host"),
            }
        )
    result: dict[str, Any] = {"runs": runs}
    shas = {r["model_sha256"] for r in runs}
    if len(shas) != 1 or None in shas:
        result["refused"] = f"not the same model file: {sorted(map(str, shas))}"
        return result
    for key, (name, _title) in CROSS.items():
        a, b = _read(first / name), _read(second / name)
        if a and b:
            result[key] = compare(_first_asks(a), _first_asks(b))
    if (first / "D1.evidence.jsonl").exists() and (second / "D1.evidence.jsonl").exists():
        result["case01_evidence"] = _evidence_compare(
            first / "D1.evidence.jsonl", second / "D1.evidence.jsonl"
        )
    return result


def cross_markdown(result: dict[str, Any]) -> str:
    lines = ["# Repeat check across two runs", ""]
    for n, run in enumerate(result["runs"], 1):
        lines.append(f"## Run {n}: {run['folder']}")
        lines.append("")
        for key, value in run.items():
            if key == "host":
                for hk, hv in (value or {}).items():
                    lines.append(f"- {hk}: {hv}")
            elif key != "folder":
                lines.append(f"- {key}: {value}")
        lines.append("")
    if result.get("refused"):
        return "\n".join([*lines, f"Not compared: {result['refused']}."]) + "\n"
    lines += ["| comparison | compared | only in run 1 | only in run 2 | failed "
              "| identical bytes | same label | differences |",
              "|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for key, (_name, title) in CROSS.items():
        c = result.get(key)
        if c is None:
            lines.append(f"| {title} | not in both runs | | | | | | |")
            continue
        lines.append(
            f"| {title} | {c['compared']} | {c['only_in_first']} | {c['only_in_second']} "
            f"| {c['failed']} | {c['raw_identical']} | {c['label_identical']} "
            f"| {len(c['differences'])} |"
        )
    ev = result.get("case01_evidence")
    if ev:
        lines += ["", f"case01 evidence rows identical across the two runs: {ev['same_rows']} "
                  f"({ev['items_first']} vs {ev['items_second']} items)"]  # fmt: skip
    for key, (_name, title) in CROSS.items():
        c = result.get(key) or {}
        for part, head in (("failures", "Failed answers"), ("differences", "Differences")):
            if not c.get(part):
                continue
            lines += ["", f"## {head}, {title}", ""]
            for d in c[part][:20]:
                lines += [f"- {d['key']}", f"  - run 1: {d['first'][:400]}",
                          f"  - run 2: {d['second'][:400]}"]  # fmt: skip
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- driver


def _git(*args: str) -> str:
    out = subprocess.run(  # noqa: S603 - fixed arguments
        ["git", *args],  # noqa: S607
        capture_output=True, text=True, check=True, timeout=10,
    )  # fmt: skip
    return out.stdout.strip()


def _git_commit() -> str:
    """The commit, marked when tracked files differ from it (the run is then not that commit)."""
    try:
        commit = _git("rev-parse", "--short", "HEAD")
        dirty = _git("status", "--porcelain", "--untracked-files=no")
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    return f"{commit} with uncommitted changes" if dirty else commit


def _gpu() -> str | None:
    """The NVIDIA card, driver and memory as nvidia-smi reports them; None without one."""
    try:
        out = subprocess.run(  # noqa: S603 - fixed arguments
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",  # noqa: S607
             "--format=csv,noheader"],
            capture_output=True, text=True, check=True, timeout=20,
        )  # fmt: skip
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout.strip() or None


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
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("FIRST", "SECOND"),
                    help="no model: compare two finished runs' folders")  # fmt: skip
    ap.add_argument("--host", type=Path, default=None,
                    help="JSON describing the machine, added to the summary")  # fmt: skip
    ap.add_argument("--stage", default=None, help=argparse.SUPPRESS)  # one stage, internal
    args = ap.parse_args(argv)
    args.claims = tuple(c.strip() for c in args.claims.split(",") if c.strip())

    if args.dry_run:
        print(json.dumps(estimate(args.cpu_items, args.claims), indent=2))
        return 0
    if args.compare:
        result = compare_runs(*args.compare)
        md = cross_markdown(result)
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "cross.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            (args.out / "cross.md").write_text(md, encoding="utf-8")
        print(md)
        return 1 if result.get("refused") else 0
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
    metas = [m for m in summarize(args.out)["stages"].values() if m]
    summary = {
        "run_at_utc": stamp,
        "commit": _git_commit(),
        "machine": platform.platform(),
        "gpu": _gpu(),
        "host": json.loads(args.host.read_text(encoding="utf-8")) if args.host else None,
        "model": entry["name"],
        "model_sha256": next((m["model_sha256"] for m in metas), entry.get("sha256")),
        "llama_cpp_python": next((m["llama_cpp_python"] for m in metas), None),
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
