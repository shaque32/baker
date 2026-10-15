"""Faster calls, round 2: the runtime speed settings and stance prompt v1.1, in one Mac sitting.

Usage (repo root, venv active; bash eval/probe/mac_speed_round2.sh wraps this):
  python -m eval.probe.speed_round2 --models eval/probe/models.local.json [--model NAME]
      [--claims C02,C05,C12] [--n-ctx 8192] [--out eval/out/speed_round2]
  python -m eval.probe.speed_round2 --report-only [--out ...]   # rebuild RESULTS.md

One model (the 14B unless --model names another), five steps, each a separate process:

  step      stance prompt   runtime            chat template  runs
  A         v1.0 (signed)   plain              gguf           probe + timed audit  (before)
  B         v1.0 (signed)   flash              gguf           probe
  C         v1.0 (signed)   flash-lookup       gguf           probe
  D         v1.1 (draft)    chosen after A-C   gguf           probe + timed audit  (after)
  E         v1.1 (draft)    chosen after A-C   no-think       probe

A quick preflight loads the model once per setting and labels two probe items, so a setting
that crashes on this machine stops the run in minutes, not hours. A step whose results exist
is skipped, so a stopped run resumes where it was. Everything is synthetic and offline.

Decision rules, fixed before the run (eval/probe/README.md, "Faster calls, round 2"):
1. Runtime. A runtime "holds the bars" against plain on the signed, undisputed probe items
   when it meets every Expert-confirms bar plain meets, and on a bar plain misses it is no
   worse. Chosen: the fastest runtime that holds the bars and is at least 5% faster per stance
   call than plain, and whose peak memory is at most 2 GB above plain's; otherwise plain.
   Identical output is reported, not required: the settings change the order of
   floating-point sums, so a near-tie can flip. (Prompt lookup makes llama-cpp-python keep
   every token's logits, about 5 GB more at n_ctx 8192, hence the memory limit.)
2. Stance prompt v1.1 is ready for Arsh to sign when it holds the bars against v1.0 on the
   same runtime (D against the v1.0 step on the chosen runtime).
3. The no-think template is recommended only when it holds the bars against D and shows fewer
   contradicting items as support (the 14B's one missed bar). It changes no words of the
   prompt but changes what the model reads, so Arsh decides it with v1.1.
4. The stance output cap stays at 1024 tokens: a valid answer may quote up to 2,000
   characters (core/audit/stance.py), and a lower cap would drop such a label. The run counts
   answers that reached the cap and their time, so the cost is known.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import subprocess  # noqa: S404 - runs this repo's own eval modules with fixed arguments
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.probe.run_probe import EXPERT_CONFIRMS_BARS

# Round 2 ran on 2026-10-12 against v1.0. core/audit/prompts/stance.md is v1.1 since 2026-10-14
# and the product's labeler refuses a prompt without {claim}, so this round no longer re-runs
# as is; its results are in eval/probe/README.md.
PROMPTS = {
    "v1_0": Path("core/audit/prompts/stance.md"),
    "v1_1": Path("eval/probe/stance_v1_1_draft.md"),
}
GOLD_PROBE = Path("eval/gold/probe/probe.jsonl")
DEFAULT_OUT = Path("eval/out/speed_round2")
MIN_GAIN = 0.05  # a runtime must be at least 5% faster per stance call to replace plain
MAX_EXTRA_GB = 2.0  # and use at most this much more peak memory
MAX_TOKENS = 1024
CHOSEN = "chosen"  # placeholder runtime for D and E, resolved after A to C


@dataclass(frozen=True)
class Step:
    key: str
    prompt: str
    runtime: str
    template: str
    audit: bool
    note: str


STEPS = (
    Step("A", "v1_0", "plain", "gguf", True, "before: signed prompt, plain runtime"),
    Step("B", "v1_0", "flash", "gguf", False, "flash attention, larger batch"),
    Step("C", "v1_0", "flash-lookup", "gguf", False, "B plus prompt-lookup decoding"),
    Step("D", "v1_1", CHOSEN, "gguf", True, "after: prompt v1.1 on the chosen runtime"),
    Step("E", "v1_1", CHOSEN, "no-think", False, "D with Qwen3's non-thinking template"),
)
V10_STEP = {"plain": "A", "flash": "B", "flash-lookup": "C"}

# The four bars, as (key in expert_confirms, bar key, higher is better).
MEASURES = (
    ("supports_recall", "supports_recall_90", True),
    ("contradicts_precision", "contradicts_precision_90", True),
    ("contradicts_shown_as_supports", "no_contradicts_shown_as_supports", False),
    ("stance_valid_output", "valid_output_100", True),
)


# ---------------------------------------------------------------- reading results


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def probe_result(out: Path, key: str) -> dict[str, Any] | None:
    rows = _load(out / key / "probe" / "summary.json")
    if not rows:
        return None
    row = rows[0]
    return None if row.get("load_error") else row


def audit_result(out: Path, key: str) -> dict[str, Any] | None:
    summary = _load(out / key / "audit" / "summary.json")
    if not summary or not summary.get("models"):
        return None
    row = summary["models"][0]
    return None if "error" in row else {**row, "dry_run": summary["dry_run"], **_machine(summary)}


def _machine(summary: dict[str, Any]) -> dict[str, Any]:
    return {"machine": summary.get("machine", {})}


def stance_calls(out: Path, key: str) -> dict[str, dict[str, Any]]:
    """The probe step's stance calls by item id (the first answer per item)."""
    calls: dict[str, dict[str, Any]] = {}
    for path in sorted((out / key / "probe").glob("*.calls.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row["purpose"] == "stance":
                    calls.setdefault(row["item_id"], row)
    return calls


def _stance_of(call: dict[str, Any]) -> str:
    try:
        return str(json.loads(call["raw_text"])["stance"])
    except (ValueError, KeyError, TypeError):
        return "invalid"


# ---------------------------------------------------------------- the rules


def holds_bars(cand: dict[str, Any], base: dict[str, Any]) -> tuple[bool, list[str]]:
    """Rule 1 and 2: every bar the baseline meets is met, and no missed bar gets worse."""
    c_ec, b_ec = cand["expert_confirms"], base["expert_confirms"]
    reasons = []
    for measure, bar, higher in MEASURES:
        cv, bv = c_ec.get(measure), b_ec.get(measure)
        if b_ec["bars"][bar]:
            if not c_ec["bars"][bar]:
                reasons.append(f"misses {bar} ({_pct(cv)}), which the baseline meets")
        elif cv is not None and bv is not None and (cv < bv if higher else cv > bv):
            reasons.append(f"{measure} worse than the baseline ({_pct(cv)} vs {_pct(bv)})")
    return not reasons, reasons


def choose_runtime(out: Path) -> dict[str, Any]:
    """Rule 1, from the probe results of A, B and C."""
    plain = probe_result(out, "A")
    if plain is None:
        raise RuntimeError("step A has no probe result")
    base_s = plain["mean_seconds_per_stance_call"]
    base_gb = probe_peak_gb(out, "A")
    rows = []
    best, best_s = "plain", base_s
    for runtime, key in V10_STEP.items():
        if runtime == "plain":
            continue
        res = probe_result(out, key)
        if res is None:
            rows.append({"runtime": runtime, "step": key, "result": "no result"})
            continue
        ok, why = holds_bars(res, plain)
        s = res["mean_seconds_per_stance_call"]
        fast_enough = bool(s and base_s and s <= base_s * (1 - MIN_GAIN))
        gb = probe_peak_gb(out, key)
        memory_ok = gb is None or base_gb is None or gb <= base_gb + MAX_EXTRA_GB
        rows.append({"runtime": runtime, "step": key, "holds_bars": ok, "why_not": why,
                     "seconds_per_call": s, "faster_by_5pct": fast_enough,
                     "peak_gb": gb, "memory_ok": memory_ok})  # fmt: skip
        if ok and fast_enough and memory_ok and s < best_s:
            best, best_s = runtime, s
    return {"chosen": best, "plain_seconds_per_call": base_s, "plain_peak_gb": base_gb,
            "candidates": rows}  # fmt: skip


def probe_peak_gb(out: Path, key: str) -> float | None:
    runs = _load(out / key / "runs.json") or {}
    return runs.get("probe", {}).get("peak_gb")


def chosen_runtime(out: Path) -> str:
    path = out / "choice.json"
    choice = _load(path)
    if choice is None:
        choice = choose_runtime(out)
        path.write_text(json.dumps(choice, indent=2) + "\n", encoding="utf-8")
    return str(choice["chosen"])


# ---------------------------------------------------------------- running


def pick_model(models: Path, name: str | None) -> dict[str, Any]:
    entries = json.loads(models.read_text(encoding="utf-8"))
    if name:
        hits = [e for e in entries if e["name"] == name]
    elif len(entries) == 1:
        hits = entries
    else:
        hits = [e for e in entries if "14b" in e["name"].lower()]
    if len(hits) != 1:
        names = ", ".join(e["name"] for e in entries)
        raise SystemExit(f"pick one model with --model (in {models}: {names})")
    return hits[0]


def run(cmd: list[str], log: Path) -> dict[str, Any]:
    """Run one eval module, its output into log, and return its exit code, time and peak
    memory (each step is its own process, so its peak is its own)."""
    print(f"  $ {' '.join(cmd)}", file=sys.stderr, flush=True)
    start = time.perf_counter()
    with log.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)  # noqa: S603
        if hasattr(os, "wait4"):
            _, status, usage = os.wait4(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
            # ru_maxrss is in bytes on macOS and in kilobytes on Linux.
            scale = 1 if sys.platform == "darwin" else 1024
            peak = round(usage.ru_maxrss * scale / 2**30, 1)
        else:  # pragma: no cover - Windows has no wait4
            proc.wait()
            peak = None
    return {"exit": proc.returncode, "seconds": round(time.perf_counter() - start), "peak_gb": peak}


def run_step(step: Step, runtime: str, args: argparse.Namespace, models: Path) -> None:
    py = [sys.executable, "-m"]
    common = ["--models", str(models), "--n-ctx", str(args.n_ctx),
              "--stance-prompt", str(PROMPTS[step.prompt]),
              "--runtime", runtime, "--chat-template", step.template]  # fmt: skip
    parts = {"probe": py + ["eval.probe.run_probe", "--probe-set", str(args.probe_set),
                            "--stance-only", "--repeat", "1"] + common}  # fmt: skip
    if step.audit:
        parts["audit"] = py + ["eval.probe.time_case", "--claims", args.claims] + common
    step_dir = args.out / step.key
    runs = _load(step_dir / "runs.json") or {}
    for part, cmd in parts.items():
        done = (step_dir / part / "summary.json").is_file() and runs.get(part, {}).get("exit") == 0
        if done:
            print(f"step {step.key} {part}: already done, skipped", file=sys.stderr)
            continue
        shutil.rmtree(step_dir / part, ignore_errors=True)  # a partial run starts over
        (step_dir / part).mkdir(parents=True)
        print(f"step {step.key} {part} ({step.note}; runtime {runtime}, template "
              f"{step.template}, prompt {step.prompt})", file=sys.stderr, flush=True)  # fmt: skip
        runs[part] = run(cmd + ["--out", str(step_dir / part)], step_dir / f"{part}.log")
        runs[part]["runtime"] = runtime
        (step_dir / "runs.json").write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
        if runs[part]["exit"] != 0:
            raise SystemExit(f"step {step.key} {part} failed; see {step_dir / part}.log")


def preflight(entry: dict[str, Any], args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """Load the model once per setting the run uses and label two probe items with each."""
    from core.llm.runtime import GenerationParams, LlamaCppModel, ModelSpec, with_runtime
    from eval.probe import prompts
    from eval.probe.from_draft import convert

    rows = [json.loads(x) for x in args.probe_set.read_text(encoding="utf-8").splitlines() if x]
    items = [convert(r)[1] for r in rows[:2]]
    spec = ModelSpec(name=entry["name"], path=Path(entry["path"]).expanduser(),
                     sha256=entry.get("sha256"))  # fmt: skip
    problems, notes = [], []
    verify = True  # hash the file once; later loads reuse the checked digest
    for runtime, template in (("plain", "gguf"), ("flash", "gguf"), ("flash-lookup", "gguf"),
                              ("flash-lookup", "no-think")):  # fmt: skip
        params = with_runtime(GenerationParams(n_ctx=args.n_ctx), runtime, template)
        label = f"{runtime}/{template}"
        try:
            model = LlamaCppModel(spec, params, verify_hash=verify)
            if verify:
                spec = ModelSpec(name=spec.name, path=spec.path, sha256=model.sha256)
                verify = False
            for it in items:
                record = it.get("record") or prompts.record_line(it["record_text"], it["context"])
                prompt = prompts.stance_prompt(
                    it["assumption"], record, it["context"], PROMPTS["v1_1"]
                )
                out = model.generate_json(prompt, prompts.STANCE_SCHEMA, params)
                if out.error and out.error.startswith("runtime_error"):
                    problems.append(f"{label}: {it['id']}: {out.error}")
                elif not out.ok:  # a model's own miss, scored by the probe; not a crash
                    notes.append(f"{label}: invalid output on {it['id']} ({out.error})")
            print(f"preflight {label}: ok", file=sys.stderr, flush=True)
            del model
        except Exception as e:  # noqa: BLE001 - report every setting that fails
            problems.append(f"{label}: {type(e).__name__}: {e}")
        gc.collect()
    return problems, notes


# ---------------------------------------------------------------- report


def _fmt(v: object) -> str:
    return "n/a" if v is None else str(v)


def _pct(v: object) -> str:
    return f"{v:.0%}" if isinstance(v, float) else _fmt(v)


def compare_labels(out: Path, key: str, base: str) -> dict[str, Any]:
    """Stance outputs of one probe step against another, item by item."""
    a, b = stance_calls(out, base), stance_calls(out, key)
    gold = {r["probe_id"]: r["gold_stance"] for r in _gold_rows()}
    shared = sorted(set(a) & set(b))
    same = sum(a[i]["raw_text"] == b[i]["raw_text"] for i in shared)
    changed = [
        {"id": i, "gold": gold.get(i, "?"), "from": _stance_of(a[i]), "to": _stance_of(b[i])}
        for i in shared
        if _stance_of(a[i]) != _stance_of(b[i])
    ]
    return {"items": len(shared), "identical_output": same, "label_changes": changed}


def _gold_rows() -> list[dict[str, Any]]:
    if not GOLD_PROBE.is_file():
        return []
    lines = GOLD_PROBE.read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def output_lengths(out: Path) -> dict[str, Any]:
    """Rule 4: how long the answers were, and what reaching the cap cost."""
    tokens, hit, hit_seconds = [], 0, 0.0
    for step in STEPS:
        for call in stance_calls(out, step.key).values():
            tokens.append(call["completion_tokens"])
            if call["completion_tokens"] >= MAX_TOKENS:
                hit += 1
                hit_seconds += call["seconds"]
    audit_max = [
        r["cold"]["passes"]["stance"].get("max_completion_tokens")
        for r in (audit_result(out, s.key) for s in STEPS if s.audit)
        if r and "stance" in r["cold"]["passes"]
    ]
    tokens.sort()
    return {
        "probe_answers": len(tokens),
        "max_probe_tokens": tokens[-1] if tokens else None,
        "p99_probe_tokens": tokens[int(0.99 * (len(tokens) - 1))] if tokens else None,
        "max_audit_tokens": max((t for t in audit_max if t is not None), default=None),
        "reached_cap": hit,
        "seconds_at_cap": round(hit_seconds),
    }


def report(out: Path) -> str:
    meta = _load(out / "meta.json") or {}
    choice = _load(out / "choice.json")
    chosen = choice["chosen"] if choice else None
    lines = [
        f"# Faster calls, round 2 ({meta.get('model', '?')})",
        "",
        f"Run started {meta.get('started', '?')}; n_ctx {meta.get('n_ctx', '?')}; claims timed "
        f"{meta.get('claims', '?')}; {meta.get('versions', '')}",
    ]
    a_audit = audit_result(out, "A")
    if a_audit:
        m = a_audit["machine"]
        lines.append(f"Machine: {m.get('cpu')}, {m.get('ram_gb')} GB, {m.get('platform')}")
    if meta.get("preflight_problems"):
        lines += ["", "Preflight problems: " + "; ".join(meta["preflight_problems"])]
    if meta.get("preflight_notes"):
        lines += ["", "Preflight notes: " + "; ".join(meta["preflight_notes"])]

    lines += ["", "## Speed", "",
              "| step | prompt | runtime | template | probe s/call | audit s/call | prompt tok "
              "| output tok | full case01 h (projected) | peak memory GB |",
              "|" + "---|" * 10]  # fmt: skip
    for s in STEPS:
        runtime = chosen if s.runtime == CHOSEN else s.runtime
        pr, au = probe_result(out, s.key), audit_result(out, s.key)
        runs = _load(out / s.key / "runs.json") or {}
        peak = max((r.get("peak_gb") or 0 for r in runs.values()), default=0) or None
        st = au["cold"]["passes"].get("stance", {}) if au else {}
        lines.append("| " + " | ".join(str(x) for x in (
            s.key, s.prompt, runtime or "not chosen yet", s.template,
            _fmt(pr and pr.get("mean_seconds_per_stance_call")),
            _fmt(st.get("mean_seconds_per_call")), _fmt(st.get("mean_prompt_tokens")),
            _fmt(st.get("mean_completion_tokens")),
            _fmt(au and au.get("projected_full_case_stance_hours")), _fmt(peak),
        )) + " |")  # fmt: skip
    d_audit = audit_result(out, "D")
    if a_audit and d_audit:
        calls = a_audit["dry_run"]["stance_calls"]
        before = a_audit["cold"]["passes"]["stance"]["mean_seconds_per_call"]
        after = d_audit["cold"]["passes"]["stance"]["mean_seconds_per_call"]
        lines += ["", f"Before: {before} s per stance call, about "
                  f"{a_audit.get('projected_full_case_stance_hours')} h for case01's {calls} "
                  f"stance calls. After (v1.1, {chosen}): {after} s per call, about "
                  f"{d_audit.get('projected_full_case_stance_hours')} h"
                  + (f", {before / after:.2f}x faster." if after else ".")]  # fmt: skip

    lines += ["", "## Expert-confirms bars (signed, undisputed probe items)", "",
              "| step | supports recall | contradicts precision | contradicts shown as supports "
              "| valid output | contradicts recall | supports shown to expert | all four |",
              "|" + "---|" * 8]  # fmt: skip
    for s in STEPS:
        pr = probe_result(out, s.key)
        if pr is None:
            lines.append(f"| {s.key} | no result |" + " |" * 6)
            continue
        ec = pr["expert_confirms"]
        lines.append("| " + " | ".join(_pct(x) for x in (
            s.key, ec["supports_recall"], ec["contradicts_precision"],
            ec["contradicts_shown_as_supports"], ec["stance_valid_output"],
            ec["contradicts_recall"], ec["expert_load_supports_shown"], ec["passes_all"],
        )) + " |")  # fmt: skip
    lines.append(f"\nBars: supports recall >= {EXPERT_CONFIRMS_BARS['supports_recall']:.0%}, "
                 f"contradicts precision >= {EXPERT_CONFIRMS_BARS['contradicts_precision']:.0%}, "
                 "0 contradicts shown as supports, valid output 100%.")  # fmt: skip

    lines += ["", "## Same output?", ""]
    pairs = [("B", "A", "runtime flash vs plain"), ("C", "A", "runtime flash-lookup vs plain")]
    if chosen:
        pairs += [("D", V10_STEP[chosen], f"prompt v1.1 vs v1.0 on {chosen}"),
                  ("E", "D", "no-think vs model template, v1.1")]  # fmt: skip
    for key, base, what in pairs:
        if probe_result(out, key) is None or probe_result(out, base) is None:
            continue
        c = compare_labels(out, key, base)
        changes = ", ".join(f"{x['id']} {x['from']}->{x['to']} (gold {x['gold']})"
                            for x in c["label_changes"]) or "none"  # fmt: skip
        lines.append(f"- {key} vs {base} ({what}): identical output on {c['identical_output']} "
                     f"of {c['items']} items; label changes: {changes}.")  # fmt: skip

    lengths = output_lengths(out)
    lines += ["", "## Output length", "",
              f"Longest probe answer {_fmt(lengths['max_probe_tokens'])} tokens (99th "
              f"percentile {_fmt(lengths['p99_probe_tokens'])}); longest audit answer "
              f"{_fmt(lengths['max_audit_tokens'])}. Answers that reached the {MAX_TOKENS}-token "
              f"cap: {lengths['reached_cap']}, costing {lengths['seconds_at_cap']} s."]  # fmt: skip

    lines += ["", "## Decisions (rules fixed before the run)", ""]
    lines += decisions(out, choice)
    return "\n".join(lines) + "\n"


def decisions(out: Path, choice: dict[str, Any] | None) -> list[str]:
    if choice is None:
        return ["Not reached: steps A to C are not finished."]
    chosen = choice["chosen"]
    lines = []
    for c in choice["candidates"]:
        if "holds_bars" not in c:
            lines.append(f"- {c['runtime']}: {c['result']}.")
            continue
        bars = "yes" if c["holds_bars"] else "no (" + "; ".join(c["why_not"]) + ")"
        memory = "" if c.get("memory_ok", True) else " (more than 2 GB above plain)"
        lines.append(
            f"- {c['runtime']}: {c['seconds_per_call']} s per call vs plain "
            f"{choice['plain_seconds_per_call']}; holds the bars: {bars}; at least 5% faster: "
            f"{'yes' if c['faster_by_5pct'] else 'no'}; peak memory {_fmt(c.get('peak_gb'))} GB "
            f"vs plain {_fmt(choice.get('plain_peak_gb'))} GB{memory}."
        )
    lines.append(f"1. Runtime: **{chosen}**.")
    d, base = probe_result(out, "D"), probe_result(out, V10_STEP[chosen])
    if d and base:
        ok, why = holds_bars(d, base)
        verdict = ("holds the bars against v1.0. Ready for Arsh to sign." if ok else
                   "does not hold the bars against v1.0 (" + "; ".join(why) +
                   "). Do not sign.")  # fmt: skip
        lines.append(f"2. Stance prompt v1.1 {verdict}")
    else:
        lines.append("2. Stance prompt v1.1: not reached.")
    e = probe_result(out, "E")
    if d and e:
        ok, why = holds_bars(e, d)
        fewer = (e["expert_confirms"]["contradicts_shown_as_supports"]
                 < d["expert_confirms"]["contradicts_shown_as_supports"])  # fmt: skip
        if ok and fewer:
            lines.append("3. No-think template: recommended (holds the bars and shows fewer "
                         "contradicting items as support). Arsh decides it with v1.1.")  # fmt: skip
        else:
            reason = "; ".join(why) if not ok else "no fewer contradicting items shown as support"
            lines.append(f"3. No-think template: not recommended ({reason}).")
    else:
        lines.append("3. No-think template: not reached.")
    lines.append(f"4. Output cap: stays at {MAX_TOKENS} tokens (a valid answer may quote up to "
                 "2,000 characters).")  # fmt: skip
    return lines


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", type=Path, default=Path("eval/probe/models.local.json"))
    ap.add_argument("--model", default=None, help="the model's name in the models file")
    ap.add_argument("--probe-set", type=Path, default=GOLD_PROBE)
    ap.add_argument("--claims", default="C02,C05,C12", help="the claims the earlier runs timed")
    ap.add_argument("--n-ctx", type=int, default=8192)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--skip-preflight", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    if not args.report_only:
        entry = pick_model(args.models, args.model)
        one = args.out / "model.json"
        one.write_text(json.dumps([entry], indent=2) + "\n", encoding="utf-8")
        meta = _load(args.out / "meta.json") or {}
        if meta.get("model") not in (None, entry["name"]):
            raise SystemExit(f"{args.out} holds a run of {meta['model']}; use another --out")
        meta.update(model=entry["name"], n_ctx=args.n_ctx, claims=args.claims,
                    probe_set=str(args.probe_set), versions=_versions())  # fmt: skip
        meta.setdefault("started", datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"))
        if not args.skip_preflight and not meta.get("preflight_passed"):
            problems, notes = preflight(entry, args)
            meta["preflight_problems"], meta["preflight_notes"] = problems, notes
            (args.out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", "utf-8")
            if problems:
                print("Preflight failed:\n  " + "\n  ".join(problems), file=sys.stderr)
                print("Paste this back. Nothing long has run yet.", file=sys.stderr)
                return 1
            meta["preflight_passed"] = True
        (args.out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", "utf-8")
        for step in STEPS:
            runtime = step.runtime if step.runtime != CHOSEN else chosen_runtime(args.out)
            run_step(step, runtime, args, one)

    md = report(args.out)
    (args.out / "RESULTS.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


def _versions() -> str:
    try:
        import llama_cpp  # local runtime, optional

        version = llama_cpp.__version__
    except ImportError:
        version = "not installed"
    return f"llama-cpp-python {version}, Python {sys.version.split()[0]}"


if __name__ == "__main__":
    sys.exit(main())
