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
import sys
from pathlib import Path
from typing import Any

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
TIMED_CLAIMS = "C02,C05,C12"
MIN_SPEEDUP = 0.15  # criterion 6: mean seconds per stance call at least 15% below v1.1's


def ran(out: Path, prompt: str, set_name: str) -> Run | None:
    """One prompt on one set, only from this sitting's own folder (the v1.3 reader would fall
    back to the 2026-10-19 v1.1 file for the signed set; this test compares one sitting)."""
    if not (out / f"{prompt}_{set_name}" / "summary.json").exists():
        return None
    return load_run(out, prompt, set_name)


def timed(out: Path, prompt: str) -> dict[str, Any] | None:
    """The cold run of one timed audit, with its model's SHA-256, or None if it did not run."""
    path = out / f"time_{prompt}" / "summary.json"
    if not path.exists():
        return None
    models = json.loads(path.read_text(encoding="utf-8")).get("models") or []
    if len(models) != 1 or "cold" not in models[0]:
        return None
    m = models[0]
    stance = m["cold"]["passes"].get("stance", {})
    return {
        "sha256": m["sha256"],
        "calls": stance.get("calls"),
        "mean_s": stance.get("mean_seconds_per_call"),
        "wall_s": m["cold"]["wall_seconds"],
        "verdicts": m["cold"]["verdicts"],
        "stored_items": m["cold"]["stored_items"],
    }


def pooled(runs: dict[str, Run]) -> dict[str, tuple[int, int]]:
    """Criteria 4 and 5 over every scored item of all four sets."""
    traps = sup = sup_n = con = con_n = 0
    for s, r in runs.items():
        for it in scored(s):
            got, gold = r.labels[it["id"]], it["expected"]
            traps += got == "supports" and gold in ("complicates", "irrelevant")
            sup_n += gold == "supports"
            sup += gold == "supports" and got == "supports"
            con_n += gold == "contradicts"
            con += gold == "contradicts" and got == "contradicts"
    return {"traps": (traps, 0), "supports": (sup, sup_n), "contradicts": (con, con_n)}


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
    pc, pb = pooled(c), pooled(b)
    res.append(
        (
            "all sets",
            f"4. gold complicates or irrelevant shown as supports <= v1.1's {pb['traps'][0]}"
            f" (v1.4: {pc['traps'][0]})",
            pc["traps"][0] <= pb["traps"][0],
        )
    )
    for kind in ("supports", "contradicts"):
        res.append(
            (
                "all sets",
                f"5. {kind} recall >= v1.1's {pb[kind][0]} of {pb[kind][1]}, less one item"
                f" (v1.4: {pc[kind][0]})",
                pc[kind][0] >= pb[kind][0] - 1,
            )
        )
    tb, tc = t_base["mean_s"], t_cand["mean_s"]
    fast = bool(tb and tc) and tc <= (1 - MIN_SPEEDUP) * tb
    res.append(
        (
            "timed audit",
            f"6. mean s per stance call at least {MIN_SPEEDUP:.0%} below v1.1's"
            f" (v1.1 {tb} s, v1.4 {tc} s)",
            fast,
        )
    )
    return res


def passes(out: Path) -> bool:
    return all(ok for *_, ok in criteria(out))


def report(out: Path) -> str:
    lines = ["# Stance v1.4 test of the local 14B (instructions first)", ""]
    runs = {(p, s): ran(out, p, s) for p in PROMPTS for s in SETS}
    for p, path in PROMPTS.items():
        body = prompts._body(path)  # noqa: SLF001 - the text the model sees
        lines.append(
            f"Prompt {PROMPT_NAMES[p]}: {path.name}, body sha256"
            f" {hashlib.sha256(body.encode()).hexdigest()[:16]}"
        )
    for s in SETS:
        sha = hashlib.sha256(SETS[s].read_bytes()).hexdigest()[:16]
        lines.append(
            f"Set {s}: {SETS[s].relative_to(ROOT)}, sha256 {sha}, {len(scored(s))} scored,"
            f" left out: {', '.join(sorted(left_out(s))) or 'none'}"
        )
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
        done = [r for s in SETS if (r := runs[p, s]) is not None]
        sec = [x for r in done for x in r.seconds]
        tok = [x for r in done for x in r.tokens]
        if sec:
            lines.append(
                f"- {PROMPT_NAMES[p]}, probe: {len(sec)} calls, mean {sum(sec) / len(sec):.1f} s,"
                f" mean prompt {sum(tok) / max(len(tok), 1):.0f} tokens"
            )
        t = timed(out, p)
        if t is not None:
            lines.append(
                f"- {PROMPT_NAMES[p]}, timed audit {TIMED_CLAIMS}: {t['calls']} stance calls,"
                f" mean {t['mean_s']} s, wall {t['wall_s']} s, verdicts {t['verdicts']},"
                f" stored items {t['stored_items']}"
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
