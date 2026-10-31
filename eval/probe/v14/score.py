"""Score the stance v1.4 test (signed v1.1 wording, instructions first) against its criteria.

The plan and the criteria are in eval/probe/v14/PREREGISTERED.md, written before any call.
eval/probe/mac_v14.sh runs the probe and the timed audits and calls this; nothing here loads a
model.

Usage:
  python -m eval.probe.v14.score report OUT   # RESULTS.md text on stdout
  python -m eval.probe.v14.score decide OUT   # exit 0 only if v1.4 meets every criterion

OUT holds one run_probe folder per prompt and set, named "<prompt>_<set>" (base_signed,
v14_fresh, ...), and one time_case folder per prompt (time_base, time_v14). Labels are read
as the v1.3 test reads them (eval/probe/v13/score.py): the first answer, after the product's
quote check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from eval.loss_report import open_readonly
from eval.probe import prompts
from eval.probe.v13.score import (
    ROOT,
    SETS,
    Run,
    _pct,
    _rate,
    items,
    left_out,
    load_run,
    scored,
    signed_metrics,
)

PROMPTS = {
    "base": ROOT / "eval/probe/stance_v1_1_signed.md",
    "v14": ROOT / "eval/probe/stance_v1_4_draft.md",
}
PROMPT_NAMES = {"base": "v1.1", "v14": "v1.4"}
SET_NAMES = {
    "signed": "signed probe set",
    "fresh": "the v1.3 test's fresh set, 2026-10-21",
    "tf24": "told-frame 24, 2026-10-15",
    "r26": "rules 12 and 23, 26 items, 2026-10-15",
}
TIMED_CLAIMS = "C02,C05,C12"
MIN_SPEEDUP = 0.15  # criterion 6: mean seconds per stance call at least 15% below v1.1's
FAILED = ("error", "invalid_output")  # criterion 6: calls that ran without a usable answer
NOT_FRESH = (
    "None of these items is new to the 14B: it answered all four sets on 2026-10-22 (the v1.3"
    " test). That is acceptable for a pure reorder with the criteria fixed in advance, but a"
    " pass here is not a held-out result: signing v1.4 for pilots also needs a check on fresh"
    " items (PREREGISTERED.md)."
)


def ran(out: Path, prompt: str, set_name: str) -> Run | None:
    """One prompt on one set, only from this sitting's own folder (the v1.3 reader would fall
    back to the 2026-10-19 v1.1 file for the signed set; this test compares one sitting)."""
    if not (out / f"{prompt}_{set_name}" / "summary.json").exists():
        return None
    return load_run(out, prompt, set_name)


def db_outcomes(db: Path) -> dict[str, int] | None:
    """The cold run's stance call outcomes from a timed audit's own database, for a folder
    written before time_case recorded them (2026-10-31). Each timed audit builds its case
    database new, so its first stance model run is the cold run."""
    if not db.exists():
        return None
    conn = open_readonly(db)
    try:
        first = conn.execute(
            "SELECT id FROM model_runs WHERE purpose = 'stance' ORDER BY started_at_utc, id"
        ).fetchone()
        if first is None:
            return None
        return dict(
            conn.execute(
                "SELECT outcome, COUNT(*) FROM model_calls WHERE model_run_id = ? GROUP BY outcome",
                first,
            ).fetchall()
        )
    finally:
        conn.close()


def timed(out: Path, prompt: str) -> dict[str, Any] | None:
    """The cold run of one timed audit, with its model's SHA-256, or None if it did not run."""
    path = out / f"time_{prompt}" / "summary.json"
    if not path.exists():
        return None
    summary = json.loads(path.read_text(encoding="utf-8"))
    models = summary.get("models") or []
    if len(models) != 1 or "cold" not in models[0]:
        return None
    m = models[0]
    stance = m["cold"]["passes"].get("stance", {})
    outcomes = stance.get("outcomes")
    if outcomes is None:
        db = path.parent / str(m.get("model", "")) / f"{summary.get('case', 'case01')}.db"
        outcomes = db_outcomes(db)
    return {
        "sha256": m["sha256"],
        "calls": stance.get("calls"),
        "mean_s": stance.get("mean_seconds_per_call"),
        "call_seconds": stance.get("call_seconds") or [],  # not recorded before 2026-10-31
        "tokens_per_second": stance.get("tokens_per_second"),
        "wall_s": m["cold"]["wall_seconds"],
        "verdicts": m["cold"]["verdicts"],
        "stored_items": m["cold"]["stored_items"],
        "seed": (m.get("params") or {}).get("seed"),
        "n_ctx": m.get("n_ctx"),
        "runtime": m.get("runtime"),
        "peak_rss_gb": m.get("peak_rss_gb"),
        "outcomes": outcomes,  # None: not recorded
        "failed": None if outcomes is None else sum(outcomes.get(k, 0) for k in FAILED),
    }


def _failed_calls(t: dict[str, Any]) -> str:
    return "not recorded" if t["failed"] is None else f"{t['failed']} failed"


def probe_record(out: Path, prompt: str, set_name: str) -> dict[str, Any] | None:
    """How one probe step ran: settings, speed and memory, from its summary.json."""
    path = out / f"{prompt}_{set_name}" / "summary.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not rows:
        return None
    r = rows[0]
    params = r.get("params") or {}
    return {
        "seed": params.get("seed"),
        "n_ctx": params.get("n_ctx"),
        "runtime": r.get("runtime"),
        "tokens_per_second": r.get("tokens_per_second"),
        "peak_rss_gb": r.get("peak_rss_gb"),
    }


def traps(labels: dict[str, str], set_name: str) -> int:
    """Criterion 4 on one set: gold complicates or irrelevant items answered supports."""
    return sum(
        labels[i["id"]] == "supports"
        for i in scored(set_name)
        if i["expected"] in ("complicates", "irrelevant")
    )


def pooled(runs: dict[str, Run]) -> dict[str, tuple[int, int]]:
    """Criterion 5 over every scored item of all four sets."""
    sup = sup_n = con = con_n = 0
    for s, r in runs.items():
        for it in scored(s):
            got, gold = r.labels[it["id"]], it["expected"]
            sup_n += gold == "supports"
            sup += gold == "supports" and got == "supports"
            con_n += gold == "contradicts"
            con += gold == "contradicts" and got == "contradicts"
    return {"supports": (sup, sup_n), "contradicts": (con, con_n)}


def _bar(name: str, cand: bool, base: bool, no_worse: bool) -> tuple[str, str, bool]:
    if base:
        return ("signed", f"{name} (v1.1 meets it)", cand)
    return ("signed", f"{name}: v1.1 misses it, so v1.4 no worse than v1.1", no_worse)


def criteria(out: Path) -> list[tuple[str, str, bool]]:
    """(scope, criterion, met), as PREREGISTERED.md states them."""
    base = {s: ran(out, "base", s) for s in SETS}
    cand = {s: ran(out, "v14", s) for s in SETS}
    t_base, t_cand = timed(out, "base"), timed(out, "v14")
    missing = [
        f"{PROMPT_NAMES[p]} on {s}"
        for p, by_set in (("base", base), ("v14", cand))
        for s in SETS
        if by_set[s] is None
    ]
    missing += [
        f"timed audit with {PROMPT_NAMES[p]}"
        for p, t in (("base", t_base), ("v14", t_cand))
        if t is None
    ]
    if missing or t_base is None or t_cand is None:
        return [("all", f"1. everything ran (missing: {', '.join(missing)})", False)]
    b = {s: r for s, r in base.items() if r is not None}
    c = {s: r for s, r in cand.items() if r is not None}
    shas = {r.sha for r in [*b.values(), *c.values()]} | {t_base["sha256"], t_cand["sha256"]}
    res = [("all", f"1. every run from one model file (found {len(shas)})", len(shas) == 1)]
    invalid = [
        s
        for s, r in c.items()
        if any(r.labels[i["id"]] in ("invalid", "missing") for i in scored(s))
    ]
    res.append(
        (
            "all",
            f"2. valid output 100% on every set ({', '.join(invalid) or 'all valid'})",
            not invalid,
        )
    )
    sm, bm = signed_metrics(c["signed"].labels), signed_metrics(b["signed"].labels)
    for name, bar in (
        ("supports recall >= 90%", "supports_recall"),
        ("contradicts precision >= 90%", "contradicts_precision"),
    ):
        x, y = sm[bar], bm[bar]
        no_worse = x[0] * max(y[1], 1) >= y[0] * max(x[1], 1)
        res.append(_bar(f"3. {name}", _rate(x, 0.90), _rate(y, 0.90), no_worse))
    cs, bs = sm["contradicts_shown_as_supports"], bm["contradicts_shown_as_supports"]
    res.append(_bar("3. 0 gold contradicts shown as supports", cs == 0, bs == 0, cs <= bs))
    for s in SETS:  # each set on its own, so a rise on one cannot hide behind a drop on another
        tc, tb = traps(c[s].labels, s), traps(b[s].labels, s)
        res.append(
            (
                s,
                f"4. gold complicates or irrelevant shown as supports <= v1.1's {tb} (v1.4: {tc})",
                tc <= tb,
            )
        )
    pc, pb = pooled(c), pooled(b)
    for kind in ("supports", "contradicts"):
        res.append(
            (
                "all sets",
                f"5. {kind} recall >= v1.1's {pb[kind][0]} of {pb[kind][1]}, less one item"
                f" (v1.4: {pc[kind][0]})",
                pc[kind][0] >= pb[kind][0] - 1,
            )
        )
    # A call that fails returns at once and still counts in the mean, so the times count only
    # when every stance call of both audits was answered.
    answered = t_base["failed"] == 0 and t_cand["failed"] == 0
    res.append(
        (
            "timed audit",
            "6. every stance call of both timed audits answered, no runtime error or invalid"
            f" output (v1.1: {_failed_calls(t_base)}, v1.4: {_failed_calls(t_cand)})",
            answered,
        )
    )
    why = ""
    if not answered:
        unrecorded = t_base["failed"] is None or t_cand["failed"] is None
        why = "; not counted" + (": call outcomes not recorded" if unrecorded else "")
    tb, tc = t_base["mean_s"], t_cand["mean_s"]
    fast = answered and bool(tb and tc) and tc <= (1 - MIN_SPEEDUP) * tb
    res.append(
        (
            "timed audit",
            f"6. mean s per stance call at least {MIN_SPEEDUP:.0%} below v1.1's"
            f" (v1.1 {tb} s, v1.4 {tc} s{why})",
            fast,
        )
    )
    return res


def passes(out: Path) -> bool:
    return all(ok for *_, ok in criteria(out))


def spread(seconds: list[float]) -> str:
    """Mean, SD, median and middle half of a list of call times."""
    if not seconds:
        return "per-call times not recorded"
    q = statistics.quantiles(seconds, n=4) if len(seconds) > 1 else [seconds[0]] * 3
    sd = statistics.stdev(seconds) if len(seconds) > 1 else 0.0
    return (
        f"{len(seconds)} calls, mean {statistics.fmean(seconds):.1f} s (SD {sd:.1f}),"
        f" median {q[1]:.1f} s, middle half {q[0]:.1f} to {q[2]:.1f} s"
    )


def paired(base: list[float], cand: list[float]) -> str | None:
    """The timed audits make the same stance calls in the same order, so call i of one is call
    i of the other: v1.4's time over v1.1's, call by call."""
    if not base or len(base) != len(cand):
        return None
    ratios = [c / b for b, c in zip(base, cand, strict=True) if b > 0]
    if len(ratios) < 2:
        return None
    q = statistics.quantiles(ratios, n=4)
    faster = sum(c < b for b, c in zip(base, cand, strict=True))
    return (
        f"call by call, v1.4's time over v1.1's: median {q[1]:.2f}, middle half {q[0]:.2f} to"
        f" {q[2]:.2f}; v1.4 faster on {faster} of {len(base)} calls"
    )


def _cell(x: object) -> str:
    return "not recorded" if x is None else str(x)


def report(out: Path) -> str:
    lines = ["# Stance v1.4 test of the local 14B (instructions first)", ""]
    runs = {(p, s): ran(out, p, s) for p in PROMPTS for s in SETS}
    shas = {r.sha for r in runs.values() if r is not None}
    shas |= {t["sha256"] for p in PROMPTS if (t := timed(out, p)) is not None}
    lines.append(f"Model SHA-256: {', '.join(sorted(shas)) or 'no run yet'}")
    for p, path in PROMPTS.items():
        body = prompts._body(path)  # noqa: SLF001 - the text the model sees
        lines.append(
            f"Prompt {PROMPT_NAMES[p]}: {path.name}, body sha256"
            f" {hashlib.sha256(body.encode()).hexdigest()[:16]}"
        )
    for s in SETS:
        sha = hashlib.sha256(SETS[s].read_bytes()).hexdigest()[:16]
        lines.append(
            f"Set {s} ({SET_NAMES[s]}): {SETS[s].relative_to(ROOT)}, sha256 {sha},"
            f" {len(scored(s))} scored, left out: {', '.join(sorted(left_out(s))) or 'none'}"
        )
    lines += ["", NOT_FRESH]
    res = criteria(out)
    met = all(ok for *_, ok in res)
    lines += ["", "## Decision (PREREGISTERED.md)", ""]
    lines += [f"- {'met' if ok else 'NOT met'}: {scope}, {text}" for scope, text, ok in res]
    lines += ["", f"Recommendation: {'sign v1.4' if met else 'no prompt change'}.", ""]
    lines += ["## Numbers (first answers)", ""]
    for p in PROMPTS:
        r = runs[p, "signed"]
        if r is not None:
            m = signed_metrics(r.labels)
            lines.append(
                f"- {PROMPT_NAMES[p]}, signed: supports recall {_pct(m['supports_recall'])};"
                f" contradicts precision {_pct(m['contradicts_precision'])}; traps shown as"
                f" supports {m['traps_shown_as_supports']}"
            )
    for s in SETS:
        cells = [
            f"{PROMPT_NAMES[p]} {traps(r.labels, s)}"
            for p in PROMPTS
            if (r := runs[p, s]) is not None
        ]
        if cells:
            lines.append(
                f"- {s}: gold complicates or irrelevant shown as supports, {', '.join(cells)}"
            )
    lines += [
        "",
        "## Time per call (this Mac)",
        "",
        f"The timed audit is one cold run of {TIMED_CLAIMS} on case01: a go/no-go for criterion 6,"
        " not a product runtime figure.",
        "",
    ]
    for p in PROMPTS:
        done = [r for s in SETS if (r := runs[p, s]) is not None]
        sec = [x for r in done for x in r.seconds]
        tok = [x for r in done for x in r.tokens]
        if sec:
            lines.append(
                f"- {PROMPT_NAMES[p]}, probe: {spread(sec)};"
                f" mean prompt {sum(tok) / max(len(tok), 1):.0f} tokens"
            )
        t = timed(out, p)
        if t is not None:
            calls = (
                spread(t["call_seconds"])
                if t["call_seconds"]
                else f"{t['calls']} calls, mean {t['mean_s']} s; per-call times not recorded"
            )
            ended = (
                ", ".join(f"{k} {v}" for k, v in sorted(t["outcomes"].items()))
                if t["outcomes"] is not None
                else "not recorded"
            )
            lines.append(
                f"- {PROMPT_NAMES[p]}, timed audit stance calls: {calls}; wall {t['wall_s']} s,"
                f" verdicts {t['verdicts']}, stored items {t['stored_items']}, call outcomes"
                f" {ended}"
            )
    t_base, t_cand = timed(out, "base"), timed(out, "v14")
    if t_base is not None and t_cand is not None:
        both = paired(t_base["call_seconds"], t_cand["call_seconds"])
        if both:
            lines.append(f"- timed audits, {both}")
    lines += [
        "",
        "## Run record",
        "",
        "Peak memory is each step's peak resident memory (ru_maxrss, as speed round 2 measured it);"
        " a Mac has no separate GPU memory to report.",
        "",
        "| Step | Seed | n_ctx | Runtime | Tokens/s | Peak memory GB |",
        "|---|---|---|---|---|---|",
    ]
    for p in PROMPTS:
        for s in SETS:
            rec = probe_record(out, p, s)
            if rec is not None:
                lines.append(
                    f"| {PROMPT_NAMES[p]} on {s} | {_cell(rec['seed'])} | {_cell(rec['n_ctx'])}"
                    f" | {_cell(rec['runtime'])} | {_cell(rec['tokens_per_second'])}"
                    f" | {_cell(rec['peak_rss_gb'])} |"
                )
        t = timed(out, p)
        if t is not None:
            lines.append(
                f"| {PROMPT_NAMES[p]} timed audit | {_cell(t['seed'])} | {_cell(t['n_ctx'])}"
                f" | {_cell(t['runtime'])} | {_cell(t['tokens_per_second'])}"
                f" | {_cell(t['peak_rss_gb'])} |"
            )
    lines += ["", "## Items whose first answer differs", ""]
    lines += ["| Set | Item | Gold | v1.1 | v1.4 |", "|---|---|---|---|---|"]
    for s in SETS:
        b, c = runs["base", s], runs["v14", s]
        if b is None or c is None:
            continue
        for it in items(s):
            if b.labels.get(it["id"]) != c.labels.get(it["id"]):
                lines.append(
                    f"| {s} | {it['id']} | {it['expected']} | {b.labels.get(it['id'])}"
                    f" | {c.labels.get(it['id'])} |"
                )
    lines += [
        "",
        "## Every item (first answer; * marks an item left out of the criteria)",
        "",
        "| Set | Item | Gold | Trap | v1.1 | v1.4 |",
        "|---|---|---|---|---|---|",
    ]
    for s in SETS:
        keep = {i["id"] for i in scored(s)}
        for it in items(s):
            cells = [(runs[p, s].labels.get(it["id"], "") if runs[p, s] else "") for p in PROMPTS]
            mark = "" if it["id"] in keep else "*"
            lines.append(
                f"| {s} | {it['id']}{mark} | {it['expected']} | {it.get('trap') or ''} | "
                + " | ".join(cells)
                + " |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["report", "decide"])
    ap.add_argument("out", type=Path)
    args = ap.parse_args(argv)
    if args.command == "report":
        print(report(args.out), end="")
        return 0
    res = criteria(args.out)
    for scope, text, ok in res:
        print(f"{'met' if ok else 'NOT met'}: {scope}, {text}")
    return 0 if all(ok for *_, ok in res) else 1


if __name__ == "__main__":
    sys.exit(main())
