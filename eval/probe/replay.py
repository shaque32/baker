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

A replay folder holds one replay. identity.json, written before the first call, names the model
file, its settings, the prompt, the context size, the recorded calls and the exact prompts to
send; a stopped replay resumes only when all of it is the same, and anything else is refused,
never mixed into the same log.

Eval only, synthetic cases only: it refuses a case02 path.
"""

from __future__ import annotations

import argparse
import hashlib
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
from eval.probe.run_probe import peak_rss_gb, wilson
from eval.probe.v14.score import spread

VERSION = "1.0.0"
HERE = Path(__file__).parent
PROMPT_FILES = {"signed": None, "v14": HERE / "stance_v1_4_draft.md"}
K = 20  # candidates per assumption (core/pipeline.py Components.k)
RISKY_TO_LEAVE = ("complicates", "contradicts")  # labels that block SUPPORTED until dismissed
IDENTITY = "identity.json"


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
    plan: dict[int, str] = {}  # seq -> the variant's prompt, for calls that rebuild exactly
    for c in calls:
        if base.prompt(c.assumption_id, c.record_id) == c.prompt:
            text = variant.prompt(c.assumption_id, c.record_id)
            assert text is not None  # noqa: S101 - the same retrieval found the record above
            plan[c.seq] = text
    ident = identity(model, calls, plan, prompt, window, recorded_sha256)
    out.mkdir(parents=True, exist_ok=True)
    done = _resume(out, ident)
    fwd = forwarded.affected(conn)
    perf = _perf(model)
    log = out / "calls.jsonl"
    with log.open("a", encoding="utf-8") as f:
        for c in calls:
            text = plan.get(c.seq)
            if text is None or c.seq in done:
                continue
            a = base.assumption(c.assumption_id)
            assert a is not None  # noqa: S101 - rebuilt just above
            start = time.perf_counter()
            res = model.generate_json(text, stance.STANCE_SCHEMA)
            seconds = getattr(res, "seconds", 0.0) or time.perf_counter() - start
            row = {
                "seq": c.seq,
                "assumption_id": c.assumption_id,
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
                "rss_gb": peak_rss_gb(),  # this sitting's peak so far, so a resume keeps it
            }
            f.write(json.dumps(row) + "\n")
            f.flush()
    peaks = [r["rss_gb"] for r in read_rows(out) if r.get("rss_gb") is not None]
    meta = {
        **ident,
        "model": getattr(model, "name", None),
        "calls_asked": len(calls),
        "not_rebuilt": len(calls) - len(plan),
        "peak_rss_gb": max(peaks, default=peak_rss_gb()),
    }
    (out / "run.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return meta


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()


def identity(  # noqa: PLR0913
    model: Any,
    calls: list[Call],
    plan: dict[int, str],
    prompt: str,
    window: int,
    recorded_sha256: str | None,
) -> dict[str, Any]:
    """What makes two sittings the same replay: the replay version, the model file and its
    settings, the prompt and context size, the recorded calls asked for (the audit and the
    sample), and the exact prompts that will be sent (so a changed prompt file or prompt code
    counts too)."""
    params = getattr(model, "params", None)
    return {
        "replay": VERSION,
        "prompt": prompt,
        "window": window,
        "model_sha256": getattr(model, "sha256", None),
        "params": params.as_record() if params is not None else None,
        "recorded_model_sha256": recorded_sha256,
        "recorded_calls_sha256": _sha(
            [[c.seq, c.assumption_id, c.record_id, c.prompt, c.raw_output] for c in calls]
        ),
        "prompts_sha256": _sha(sorted(plan.items())),
    }


def _resume(out: Path, ident: dict[str, Any]) -> set[int]:
    """The seqs this folder already answered, when it holds this same replay. A folder with
    answers from any other replay, or with answers and no identity, is refused, never mixed."""
    ident = json.loads(json.dumps(ident))  # as it reads back from the file
    path, log = out / IDENTITY, out / "calls.jsonl"
    if path.exists():
        before = json.loads(path.read_text(encoding="utf-8"))
        differ = sorted(k for k in before.keys() | ident.keys() if before.get(k) != ident.get(k))
        if differ:
            raise SystemExit(
                f"{out} holds another replay (it differs in {', '.join(differ)});"
                " use a new --out folder"
            )
    elif log.exists():
        raise SystemExit(
            f"{log} has no {IDENTITY}, so its replay is unknown; use a new --out folder"
        )
    else:
        path.write_text(json.dumps(ident, indent=1) + "\n", encoding="utf-8")
    return {r["seq"] for r in read_rows(out)}


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
# What each folder must hold, by its run record and not its name (criterion 1).
TESTED = {BASE: ("signed", DEFAULT_WINDOW), SHORT: ("signed", 8)}
MIN_SAME_RAW = 0.99  # REPLAY_PREREGISTERED.md, criterion 2
MIN_FASTER = 0.10  # criterion 6
MAX_LOST_SUPPORTS = 0.05  # criterion 7
# What the two replays must share, beside the calls themselves (criterion 1).
SAME_SETUP = ("replay", "model_sha256", "params", "recorded_model_sha256", "recorded_calls_sha256")

Pair = tuple[dict[str, Any], dict[str, Any]]  # one call: the 20-message row, the 8-message row


Rows = dict[int, dict[str, Any]]  # a replay's calls by seq


def _replays(out: Path) -> tuple[dict[str, dict[str, Any]], Rows, Rows] | None:
    """Both replays' run records and calls, or None when one has not run."""
    metas = {}
    for name in (BASE, SHORT):
        if not (out / name / "run.json").exists():
            return None
        metas[name] = json.loads((out / name / "run.json").read_text(encoding="utf-8"))
    base = {r["seq"]: r for r in read_rows(out / BASE)}
    short = {r["seq"]: r for r in read_rows(out / SHORT)}
    return metas, base, short


def _pairs(base: Rows, short: Rows) -> list[Pair]:
    return [(base[k], short[k]) for k in sorted(base) if k in short]


def safety_counts(
    pairs: list[Pair], key: set[tuple[str, str]] | None
) -> dict[str, tuple[int, int]]:
    """Each count the decision needs at zero (or under its cap), with the calls it is out of."""
    not_sup = [(b, s) for b, s in pairs if b["replayed"] != "supports"]
    risky = [(b, s) for b, s in pairs if b["replayed"] in RISKY_TO_LEAVE]
    keyed = [(b, s) for b, s in pairs if key and (b["claim_id"], b["record_id"]) in key]
    sup = [(b, s) for b, s in pairs if b["replayed"] == "supports"]
    return {
        "new supports": (sum(s["replayed"] == "supports" for _, s in not_sup), len(not_sup)),
        "left complicates or contradicts": (
            sum(s["replayed"] != b["replayed"] for b, s in risky),
            len(risky),
        ),
        "key record label changes": (
            sum(s["replayed"] != b["replayed"] for b, s in keyed),
            len(keyed),
        ),
        "supports lost": (sum(s["replayed"] != "supports" for _, s in sup), len(sup)),
    }


def window_criteria(out: Path, gold: Path | None) -> list[tuple[str, bool]]:
    """The shorter-context decision (eval/probe/REPLAY_PREREGISTERED.md): signed_w8 against the
    same sitting's signed_w20, call by call."""
    got = _replays(out)
    if got is None:
        missing = next(n for n in (BASE, SHORT) if not (out / n / "run.json").exists())
        return [(f"1. {missing} ran", False)]
    metas, base, short = got
    pairs = _pairs(base, short)
    same_file = all(m["model_sha256"] == m["recorded_model_sha256"] for m in metas.values())
    same_setup = all(metas[BASE].get(k) == metas[SHORT].get(k) for k in SAME_SETUP)
    as_named = all((metas[n].get("prompt"), metas[n].get("window")) == TESTED[n] for n in TESTED)
    res = [("1. the signed prompt with 20 and with 8 messages, by both run records, on the same"
            " calls of the same recorded audit, the recorded model file and the same settings",
            bool(base) and base.keys() == short.keys() and as_named and same_file
            and same_setup)]  # fmt: skip
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
    key = load_key(gold) if gold is not None else None
    n = safety_counts(pairs, key)
    new_sup = n["new supports"][0]
    left = n["left complicates or contradicts"][0]
    moved = n["key record label changes"][0]
    res.append((f"3. no call newly labelled supports ({new_sup})", new_sup == 0))
    res.append((f"4. no call leaves complicates or contradicts ({left})", left == 0))
    if key is not None:
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
    lost, had = n["supports lost"]
    res.append(
        (
            f"7. supports lost on at most {MAX_LOST_SUPPORTS:.0%} of the calls the 20-message"
            f" replay labels supports ({lost} of {had})",
            lost <= MAX_LOST_SUPPORTS * had,
        )
    )
    backed = {b.get("assumption_id") for b, _ in pairs if b["replayed"] == "supports"}
    still = {s.get("assumption_id") for _, s in pairs if s["replayed"] == "supports"}
    res.append(
        (
            "8. no assumption loses every supports label it had with 20 messages"
            f" ({len(backed - still)})",
            not backed - still,
        )
    )
    return res


def _bounds(pairs: list[Pair], key: set[tuple[str, str]] | None) -> list[str]:
    """How large each rate could still be: a pass on a few dozen calls is not evidence of no
    effect, so each count is printed with its 95% Wilson upper bound."""
    out = []
    for name, (k, n) in safety_counts(pairs, key).items():
        w = wilson(k, n)
        out.append(f"- {name}: {k} of {n}" + (f", up to {w[1]:.1%}" if w else ""))
    return out


def _call_lists(base: Rows, pairs: list[Pair], key: set[tuple[str, str]] | None) -> list[str]:
    """Every call behind criterion 2 and every label change, by seq and ids, no text."""

    def ids(r: dict[str, Any]) -> str:
        star = " (gold key record)" if key and (r["claim_id"], r["record_id"]) in key else ""
        return f"seq {r['seq']}, claim {r['claim_id']}, record {r['record_id']}{star}"

    lines = ["", f"### {BASE}: calls whose answer is not the recorded one, byte for byte", ""]
    miss = [r for _, r in sorted(base.items()) if not r["same_raw"]]
    lines += [f"- {ids(r)}: recorded {r['recorded']}, replayed {r['replayed']}" for r in miss]
    lines += [] if miss else ["- none"]
    lines += ["", f"### {SHORT} against {BASE}: every label change", ""]
    moved = [(b, s) for b, s in pairs if s["replayed"] != b["replayed"]]
    lines += [f"- {ids(b)}: {b['replayed']} -> {s['replayed']}" for b, s in moved]
    return lines + ([] if moved else ["- none"])


def report(out: Path, gold: Path | None = None) -> str:
    key = load_key(gold) if gold else None
    lines = [f"# Replay of recorded stance calls (replay {VERSION})", ""]
    if (out / BASE).exists() and (out / SHORT).exists():
        res = window_criteria(out, gold)
        met = all(ok for _, ok in res)
        lines += ["## Shorter context (REPLAY_PREREGISTERED.md)", ""]
        lines += [f"- {'met' if ok else 'NOT met'}: {text}" for text, ok in res]
        lines += ["", f"Recommendation: {'show 8 messages' if met else 'keep 20 messages'}"
                  " each side in the stance prompt."]  # fmt: skip
        got = _replays(out)
        if got is not None:
            pairs = _pairs(got[1], got[2])
            lines += ["", "A pass is not evidence of no effect: each count, out of the calls it"
                      " could move, and the 95% Wilson upper bound on its rate.", ""]  # fmt: skip
            lines += _bounds(pairs, key) + _call_lists(got[1], pairs, key)
        lines += ["", "## Every replay", ""]
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
