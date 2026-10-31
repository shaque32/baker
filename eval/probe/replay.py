"""Replay a recorded audit's stance calls under a variant on a local model, and compare labels.

Usage (repo root, venv active):
  python -m eval.probe.replay check --db <case.db>
      No model. Rebuilds every recorded stance prompt with today's code and says how many match
      the recorded text byte for byte, and how long each variant's prompts are.
  python -m eval.probe.replay run --db <case.db> --models eval/probe/models.local.json
      --prompt signed|v14 --window 20 [--sample 2] --out <dir>
  python -m eval.probe.replay report <dir> [--gold eval/gold/case04/gold.jsonl]

A variant is a stance prompt (the signed core/audit/prompts/stance.md, or the v1.4 draft
eval/probe/stance_v1_4_draft.md) and a context size: how many messages either side of the
record the context shows (the product shows 20, core/audit/context.py). Each prompt is built
the way the product builds it (core/audit/stance.py, with the case's names and the claim), from
the record that today's retrieval returns for the recorded assumption. Only calls whose signed,
20-message prompt rebuilds byte for byte as recorded are replayed, so a difference in labels
comes from the variant, not from code that changed since the run.

The signed prompt at 20 messages is the recorded run itself. On the Mac's GPU the same prompt
gives the same answer (repeat check, 2026-10-24), so that variant is a same-sitting timing
baseline and a repeat check on real audit prompts.

Calls keep the recorded order, so llama.cpp's prefix reuse works as it did in the audit.
--sample K keeps every K-th assumption, in the order the run first labelled it, with all of its
calls. Labels are read the way the product stores them, for the recorded answer and the replayed
one alike: an invalid output is "invalid", a quote that fails the quote check is "dropped", and
otherwise the stance after the product's own adjustments (stance.subject_stance; forwarded
words become "complicates").

Eval only, synthetic cases only: it refuses a case02 path.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.audit import quotes, stance
from core.audit._llm_json import load_prompt, prompt_body
from core.audit.context import DEFAULT_WINDOW, render_for
from core.audit.readable import assumption_text, case_names
from core.audit.retrieval import SqlRetriever
from core.contracts import Assumption, EvidenceCandidate, Stance
from core.enrich.records import get_record
from core.ingest import forwarded
from core.llm.runtime import parse_json_output
from core.pipeline import load_assumptions
from eval.loss_report import open_readonly, stance_run
from eval.probe.run_probe import peak_rss_gb
from eval.probe.v14.score import spread

VERSION = "1.0.0"
HERE = Path(__file__).parent
PROMPT_FILES = {"signed": None, "v14": HERE / "stance_v1_4_draft.md"}
K = 20  # candidates per assumption (core/pipeline.py Components.k)
RISKY_TO_LEAVE = ("complicates", "contradicts")  # labels that block SUPPORTED until dismissed


def template(prompt: str) -> str:
    path = PROMPT_FILES[prompt]
    if path is None:
        return load_prompt(stance.PROMPT_FILE)
    return prompt_body(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Call:
    seq: int
    assumption_id: str
    record_id: str
    prompt: str
    raw_output: str


@dataclass(frozen=True)
class Recorded:
    """The recorded stance run: its calls in order and the model file it used."""

    model_run_id: str
    model_sha256: str
    calls: list[Call]


def recorded(conn: sqlite3.Connection, model_run_id: str | None = None) -> Recorded:
    run = stance_run(conn, model_run_id)
    (sha,) = conn.execute("SELECT model_sha256 FROM model_runs WHERE id = ?", (run,)).fetchone()
    calls = []
    for seq, subject, prompt, raw in conn.execute(
        "SELECT seq, subject_json, prompt, raw_output FROM model_calls WHERE model_run_id = ?"
        " ORDER BY seq",
        (run,),
    ):
        ids = json.loads(subject)
        calls.append(Call(seq, ids[0], ids[1], prompt, raw))
    return Recorded(run, sha, calls)


def sample(calls: list[Call], every: int) -> list[Call]:
    """Every `every`-th assumption in the order the run first labelled it, with all its calls."""
    order: list[str] = []
    for c in calls:
        if c.assumption_id not in order:
            order.append(c.assumption_id)
    keep = set(order[::every])
    return [c for c in calls if c.assumption_id in keep]


class Builder:
    """Builds the stance prompt the product sends for a recorded (assumption, record) pair."""

    def __init__(self, conn: sqlite3.Connection, prompt: str, window: int) -> None:
        self.conn = conn
        names = case_names(conn)
        self.labeler = stance.LocalStanceLabeler(
            None,  # type: ignore[arg-type]  # prompts only; nothing is sent from here
            template=template(prompt),
            render_context=lambda c: render_for(conn, c.record_id, window, names=names),
            render_assumption=lambda a: assumption_text(a, names),
            claim_text=self._claim_text,
        )
        self.assumptions: dict[str, Assumption] = {}
        self.candidates: dict[str, dict[str, EvidenceCandidate]] = {}

    def _claim_text(self, claim_id: str) -> str | None:
        row = self.conn.execute("SELECT text FROM claims WHERE id = ?", (claim_id,)).fetchone()
        return row[0] if row else None

    def assumption(self, aid: str) -> Assumption | None:
        if aid not in self.assumptions:
            found = load_assumptions(self.conn, [aid])
            if not found:
                return None
            self.assumptions[aid] = found[0]
        return self.assumptions[aid]

    def prompt(self, aid: str, record_id: str) -> str | None:
        """The prompt, or None when the assumption is gone or retrieval no longer returns the
        record for it."""
        a = self.assumption(aid)
        if a is None:
            return None
        if aid not in self.candidates:
            got = SqlRetriever().retrieve(a, self.conn, K)
            self.candidates[aid] = {c.record_id: c for c in got}
        cand = self.candidates[aid].get(record_id)
        return None if cand is None else self.labeler.build_prompt(a, cand)


def shown_label(
    conn: sqlite3.Connection, a: Assumption, record_id: str, raw: str, fwd: dict[str, str]
) -> str:
    """The label as the product would store it from this raw output (core/pipeline.py _label)."""
    parsed, error = parse_json_output(raw, stance.STANCE_SCHEMA)
    if parsed is None or error:
        return "invalid"
    try:
        out = stance.validate_stance_output(parsed)
    except stance.BadModelOutput:
        return "invalid"
    if out.stance == Stance.IRRELEVANT:
        return "irrelevant"
    rec = get_record(conn, record_id)
    if (
        rec is None
        or rec.text is None
        or not quotes.verify_quote(out.quote, rec.text)
        or not quotes.cites_record(out.quote, rec.text, rec.own)
    ):
        return "dropped"
    s = stance.subject_stance(a, rec.text, Stance(out.stance))
    if record_id in fwd and s in (Stance.SUPPORTS, Stance.CONTRADICTS):
        s = Stance.COMPLICATES
    return s.value


def check(conn: sqlite3.Connection, calls: list[Call]) -> dict[str, Any]:
    """No model: how many recorded prompts rebuild exactly, and each variant's prompt length."""
    base = Builder(conn, "signed", DEFAULT_WINDOW)
    rebuilt = [c for c in calls if base.prompt(c.assumption_id, c.record_id) == c.prompt]
    out: dict[str, Any] = {
        "replay": VERSION,
        "recorded_calls": len(calls),
        "rebuilt_exactly": len(rebuilt),
        "recorded_prompt_chars": round(statistics.mean(len(c.prompt) for c in calls))
        if calls
        else 0,
        "variants": {},
    }
    for prompt in PROMPT_FILES:
        for window in (DEFAULT_WINDOW, 8, 5):
            b = Builder(conn, prompt, window)
            texts = [t for c in rebuilt if (t := b.prompt(c.assumption_id, c.record_id))]
            out["variants"][f"{prompt}_w{window}"] = {
                "prompt_chars": round(statistics.mean(map(len, texts))) if texts else 0,
                "new_chars": round(_new_chars(texts) / len(texts)) if texts else 0,
            }
    return out


def _new_chars(prompts: list[str]) -> int:
    """Characters the model must read: each prompt less the start it shares with the one before."""
    total, prev = 0, ""
    for p in prompts:
        total += len(p) - len(os.path.commonprefix([prev, p]))
        prev = p
    return total


def _perf(model: Any) -> Callable[[], dict[str, float] | None]:
    """Prompt tokens llama.cpp actually read, and the read and write times, for the last call.
    Best effort: llama-cpp-python's perf counters; None where they are not available."""
    try:
        import llama_cpp

        ctx = model._llm._ctx.ctx  # noqa: SLF001 - eval only, read-only counters
    except (ImportError, AttributeError):
        return lambda: None

    def read() -> dict[str, float] | None:
        try:
            d = llama_cpp.llama_perf_context(ctx)
            llama_cpp.llama_perf_context_reset(ctx)
        except Exception:  # noqa: BLE001 - counters are a report, never a reason to stop
            return None
        return {"read_tokens": d.n_p_eval, "read_ms": d.t_p_eval_ms, "write_ms": d.t_eval_ms}

    read()  # start from zero
    return read


def run(  # noqa: PLR0913
    conn: sqlite3.Connection,
    model: Any,
    calls: list[Call],
    prompt: str,
    window: int,
    out: Path,
    recorded_sha256: str | None = None,
) -> dict[str, Any]:
    base = Builder(conn, "signed", DEFAULT_WINDOW)
    variant = Builder(conn, prompt, window)
    fwd = forwarded.affected(conn)
    perf = _perf(model)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "calls.jsonl"
    done = (
        {json.loads(x)["seq"] for x in log.read_text(encoding="utf-8").splitlines()}
        if log.exists()
        else set()
    )
    skipped = 0
    with log.open("a", encoding="utf-8") as f:
        for c in calls:
            if base.prompt(c.assumption_id, c.record_id) != c.prompt:
                skipped += 1
                continue
            if c.seq in done:
                continue
            text = variant.prompt(c.assumption_id, c.record_id)
            a = base.assumption(c.assumption_id)
            assert text is not None and a is not None  # noqa: S101 - rebuilt just above
            start = time.perf_counter()
            res = model.generate_json(text, stance.STANCE_SCHEMA)
            seconds = getattr(res, "seconds", 0.0) or time.perf_counter() - start
            row = {
                "seq": c.seq,
                "template": a.template_id,
                "claim_id": a.claim_id,
                "record_id": c.record_id,
                "recorded": shown_label(conn, a, c.record_id, c.raw_output, fwd),
                "replayed": shown_label(conn, a, c.record_id, res.raw_text, fwd),
                "same_raw": res.raw_text == c.raw_output,
                "error": getattr(res, "error", None),  # "runtime_error: ..." on a failed call
                "seconds": round(seconds, 3),
                "prompt_chars": len(text),
                "prompt_tokens": getattr(res, "prompt_tokens", 0),
                "completion_tokens": getattr(res, "completion_tokens", 0),
                "perf": perf(),
            }
            f.write(json.dumps(row) + "\n")
            f.flush()
    params = getattr(model, "params", None)
    meta = {
        "replay": VERSION,
        "prompt": prompt,
        "window": window,
        "model": getattr(model, "name", None),
        "model_sha256": getattr(model, "sha256", None),
        "recorded_model_sha256": recorded_sha256,
        "params": params.as_record() if params is not None else None,
        "calls_asked": len(calls),
        "not_rebuilt": skipped,
        "peak_rss_gb": peak_rss_gb(),
    }
    (out / "run.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return meta


# ---------------------------------------------------------------- report


def read_rows(folder: Path) -> list[dict[str, Any]]:
    log = folder / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


def compare(rows: list[dict[str, Any]], key: set[tuple[str, str]] | None = None) -> dict[str, Any]:
    """The replayed labels against the recorded ones, on the same calls."""
    n = len(rows)
    changed = [r for r in rows if r["replayed"] != r["recorded"]]
    out: dict[str, Any] = {
        "calls": n,
        "same_label": n - len(changed),
        "same_raw_output": sum(r["same_raw"] for r in rows),
        "new_supports": sum(r["replayed"] == "supports" != r["recorded"] for r in rows),
        "left_complicates_or_contradicts": sum(
            r["recorded"] in RISKY_TO_LEAVE and r["replayed"] != r["recorded"] for r in rows
        ),
        "lost_supports": sum(r["recorded"] == "supports" != r["replayed"] for r in rows),
        "failed": sum(r["replayed"] == "invalid" for r in rows),  # runtime error or bad output
        "changes": dict(Counter(f"{r['recorded']} -> {r['replayed']}" for r in changed)),
        "mean_seconds": round(statistics.mean(r["seconds"] for r in rows), 2) if rows else None,
        "mean_prompt_chars": round(statistics.mean(r["prompt_chars"] for r in rows))
        if rows
        else None,
    }
    read = [r["perf"]["read_tokens"] for r in rows if r.get("perf")]
    out["mean_prompt_tokens_read"] = round(statistics.mean(read)) if read else None
    if key is not None:
        mine = [r for r in rows if (r["claim_id"], r["record_id"]) in key]
        out["key_records"] = len(mine)
        out["key_label_changed"] = sum(r["replayed"] != r["recorded"] for r in mine)
    return out


def load_key(gold: Path) -> set[tuple[str, str]]:
    rows = [json.loads(x) for x in gold.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {(r["claim_id"], rec) for r in rows for rec in r.get("key_evidence", ())}


BASE, SHORT = "signed_w20", "signed_w8"  # the folders eval/probe/mac_replay.sh writes
MIN_SAME_RAW = 0.99  # REPLAY_PREREGISTERED.md, criterion 2
MIN_FASTER = 0.10  # criterion 6


def window_criteria(out: Path, gold: Path | None) -> list[tuple[str, bool]]:
    """The shorter-context decision (eval/probe/REPLAY_PREREGISTERED.md): signed_w8 against the
    same sitting's signed_w20, call by call."""
    folders = {name: out / name for name in (BASE, SHORT)}
    metas = {}
    for name, folder in folders.items():
        if not (folder / "run.json").exists():
            return [(f"1. {name} ran", False)]
        metas[name] = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    base = {r["seq"]: r for r in read_rows(folders[BASE])}
    short = {r["seq"]: r for r in read_rows(folders[SHORT])}
    same_file = all(m["model_sha256"] == m["recorded_model_sha256"] for m in metas.values())
    res = [("1. both ran the same calls on the recorded model file",
            bool(base) and base.keys() == short.keys() and same_file)]  # fmt: skip
    if not res[0][1]:
        return res
    same_raw = sum(r["same_raw"] for r in base.values())
    res.append(
        (
            f"2. the 20-message replay repeats the recorded answer on at least"
            f" {MIN_SAME_RAW:.0%} of calls ({same_raw} of {len(base)})",
            same_raw >= MIN_SAME_RAW * len(base),
        )
    )
    pairs = [(base[k], short[k]) for k in sorted(base)]
    new_sup = sum(s["replayed"] == "supports" != b["replayed"] for b, s in pairs)
    left = sum(b["replayed"] in RISKY_TO_LEAVE and s["replayed"] != b["replayed"] for b, s in pairs)
    res.append((f"3. no call newly labelled supports ({new_sup})", new_sup == 0))
    res.append((f"4. no call leaves complicates or contradicts ({left})", left == 0))
    if gold is not None:
        key = load_key(gold)
        moved = sum(
            s["replayed"] != b["replayed"]
            for b, s in pairs
            if (b["claim_id"], b["record_id"]) in key
        )
        res.append((f"5. no key record changes its label ({moved})", moved == 0))
    else:
        res.append(("5. the gold key was given", False))
    # A failed call (a runtime error comes back empty, at once) still counts in the mean, so the
    # times count only when every call of both replays was answered.
    fb, fs = (sum(r["replayed"] == "invalid" for r in rows.values()) for rows in (base, short))
    answered = fb == fs == 0
    res.append(
        (
            "6. every replayed call answered, no runtime error or invalid output"
            f" ({fb} failed with 20 messages, {fs} with 8)",
            answered,
        )
    )
    tb = statistics.mean(r["seconds"] for r in base.values())
    ts = statistics.mean(r["seconds"] for r in short.values())
    res.append(
        (
            f"6. mean s per call at least {MIN_FASTER:.0%} below the 20-message replay's"
            f" ({tb:.1f} s, {ts:.1f} s{'' if answered else '; not counted'})",
            answered and ts <= (1 - MIN_FASTER) * tb,
        )
    )
    return res


def report(out: Path, gold: Path | None = None) -> str:
    key = load_key(gold) if gold else None
    lines = [f"# Replay of recorded stance calls (replay {VERSION})", ""]
    if (out / BASE).exists() and (out / SHORT).exists():
        res = window_criteria(out, gold)
        met = all(ok for _, ok in res)
        lines += ["## Shorter context (REPLAY_PREREGISTERED.md)", ""]
        lines += [f"- {'met' if ok else 'NOT met'}: {text}" for text, ok in res]
        lines += ["", f"Recommendation: {'show 8 messages' if met else 'keep 20 messages'}"
                  " each side in the stance prompt.", "", "## Every replay", ""]  # fmt: skip
    folders = sorted(p for p in out.iterdir() if (p / "run.json").exists())
    for folder in folders:
        meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        c = compare(read_rows(folder), key)
        same_file = meta["model_sha256"] == meta["recorded_model_sha256"]
        lines.append(
            f"- {folder.name} (prompt {meta['prompt']}, {meta['window']} messages each side,"
            f" model {meta['model']}, {'the recorded' if same_file else 'NOT the recorded'}"
            f" model file): {c['calls']} calls, same label {c['same_label']},"
            f" same raw output {c['same_raw_output']}; new supports {c['new_supports']};"
            f" left complicates or contradicts {c['left_complicates_or_contradicts']}; lost"
            f" supports {c['lost_supports']}; failed calls {c['failed']}; mean"
            f" {c['mean_seconds']} s per call, prompt"
            f" {c['mean_prompt_chars']} chars, read {c['mean_prompt_tokens_read']} tokens"
            + (
                f"; key records {c['key_records']}, label changed {c['key_label_changed']}"
                if key is not None
                else ""
            )  # fmt: skip
        )
        if c["changes"]:
            lines.append(
                "  changes: " + ", ".join(f"{k} x{v}" for k, v in sorted(c["changes"].items()))
            )
        lines.append(f"  time per call: {spread([r['seconds'] for r in read_rows(folder)])}")
    ratio = _ratio(out)
    if ratio:
        lines += ["", ratio]
    lines += ["", "## Run record", "", "Peak memory is the replay's peak resident memory"
              " (ru_maxrss); a Mac has no separate GPU memory to report.", "",
              "| Replay | Model SHA-256 | Seed | n_ctx | Tokens/s | Peak memory GB |",
              "|---|---|---|---|---|---|"]  # fmt: skip
    for folder in folders:
        meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        params = meta.get("params") or {}
        rows = read_rows(folder)
        secs = sum(r["seconds"] for r in rows)
        toks = sum(r.get("completion_tokens", 0) for r in rows)
        lines.append(
            f"| {folder.name} | {meta['model_sha256']} | {params.get('seed')} |"
            f" {params.get('n_ctx')} | {round(toks / secs, 1) if secs else None} |"
            f" {meta.get('peak_rss_gb')} |"
        )
    return "\n".join(lines) + "\n"


def _ratio(out: Path) -> str | None:
    """The shorter context's time over the 20-message replay's, call by call (same calls)."""
    base = {r["seq"]: r["seconds"] for r in read_rows(out / BASE)}
    short = {r["seq"]: r["seconds"] for r in read_rows(out / SHORT)}
    pairs = [(base[k], short[k]) for k in sorted(base) if k in short and base[k] > 0]
    if len(pairs) < 2:
        return None
    q = statistics.quantiles([s / b for b, s in pairs], n=4)
    faster = sum(s < b for b, s in pairs)
    return (
        f"Call by call, {SHORT}'s time over {BASE}'s: median {q[1]:.2f}, middle half"
        f" {q[0]:.2f} to {q[2]:.2f}; faster on {faster} of {len(pairs)} calls."
    )


# ---------------------------------------------------------------- command line


def _refuse_hidden(db: Path) -> None:
    if "case02" in str(db):
        raise SystemExit("case02 is the hidden held-out case; replay it only when a task names it")


def _load_model(models: Path, name: str | None, n_ctx: int) -> Any:
    from core.llm.runtime import (
        PRODUCT_RUNTIME,
        GenerationParams,
        LlamaCppModel,
        ModelSpec,
        with_runtime,
    )
    from eval.bench.fair_steps import pick_entry

    entry = pick_entry(json.loads(models.read_text(encoding="utf-8")), name)
    spec = ModelSpec(name=entry["name"], path=Path(entry["path"]).expanduser(),
                     sha256=entry.get("sha256"), license=entry.get("license"))  # fmt: skip
    return LlamaCppModel(spec, with_runtime(GenerationParams(n_ctx=n_ctx), PRODUCT_RUNTIME))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    c.add_argument("--db", type=Path, required=True)
    c.add_argument("--model-run")
    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--model-run")
    r.add_argument("--models", type=Path, required=True)
    r.add_argument("--model", default=None)
    r.add_argument("--prompt", choices=sorted(PROMPT_FILES), default="signed")
    r.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    r.add_argument("--sample", type=int, default=1)
    r.add_argument("--n-ctx", type=int, default=8192)
    r.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("report")
    p.add_argument("out", type=Path)
    p.add_argument("--gold", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.command == "report":
        print(report(args.out, args.gold), end="")
        return 0
    _refuse_hidden(args.db)
    conn = open_readonly(args.db)
    try:
        rec = recorded(conn, args.model_run)
        if args.command == "check":
            print(json.dumps(check(conn, rec.calls), indent=1))
            return 0
        model = _load_model(args.models, args.model, args.n_ctx)
        calls = sample(rec.calls, args.sample)
        meta = run(conn, model, calls, args.prompt, args.window, args.out, rec.model_sha256)
    finally:
        conn.close()
    print(json.dumps(meta, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
