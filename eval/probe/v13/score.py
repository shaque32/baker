"""Score the stance v1.3 re-probe of the local 14B against its preregistered criteria.

The plan and the criteria are in eval/probe/v13/PREREGISTERED.md, written before any item or
call. eval/probe/mac_v13.sh runs the probe and calls this; nothing here loads a model.

Usage:
  python -m eval.probe.v13.score report OUT       # RESULTS.md text on stdout
  python -m eval.probe.v13.score decide OUT a     # exit 0 only if v1.3a meets every criterion
  python -m eval.probe.v13.score baseline-ok OUT  # exit 0 if the 2026-10-19 v1.1 run can stand
                                                  # in for v1.1 on the signed set
  python -m eval.probe.v13.score baseline-file CALLS OUT_JSONL
      # how eval/probe/results/2026-10-19-qwen3-14b-stance-v1-1.jsonl was made, from that run's
      # call log

OUT holds one run_probe folder per prompt and set, named "<prompt>_<set>" (base_fresh,
a_signed, ...). Every label is the product's: the first answer, after the quote check
(run_probe.tally_answer), so a quote the product would discard is "dropped" here too.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from core.llm.runtime import ModelOutput, parse_json_output
from eval.probe import prompts
from eval.probe.from_draft import convert
from eval.probe.run_probe import StanceScore, is_gated, load_items, tally_answer, wilson

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
LAYOUT = "product_members"
SETS = {
    "signed": ROOT / "eval/gold/probe/probe.jsonl",
    "fresh": HERE / "heldout.jsonl",
    "tf24": HERE / "told_frame_24.jsonl",
    "r26": HERE / "rules_12_23_26.jsonl",
}
SET_NAMES = {
    "signed": "signed probe set",
    "fresh": "fresh set (this test)",
    "tf24": "told-frame 24 (2026-10-15)",
    "r26": "rules 12 and 23, 26 (2026-10-15)",
}
PROMPTS = {
    "base": ROOT / "eval/probe/stance_v1_1_signed.md",
    "a": ROOT / "eval/probe/stance_v1_3a_draft.md",
    "b": ROOT / "eval/probe/stance_v1_3b_draft.md",
}
PROMPT_NAMES = {"base": "v1.1", "a": "v1.3a", "b": "v1.3b"}
# Items left out of the criteria: T022 and T023 as on 2026-10-15 (blind readers split), and the
# fresh items a majority of this test's blind readers labeled otherwise (heldout_left_out.json).
LEFT_OUT_FILE = HERE / "heldout_left_out.json"
TF24_LEFT_OUT = frozenset({"T022", "T023"})
TARGET_TRAPS = frozenset({"told_frame", "undated_denial"})
BASELINE = ROOT / "eval/probe/results/2026-10-19-qwen3-14b-stance-v1-1.jsonl"


def items(set_name: str) -> list[dict[str, Any]]:
    return [convert(row, LAYOUT)[1] for row in load_items(SETS[set_name])]


def left_out(set_name: str) -> frozenset[str]:
    if set_name == "tf24":
        return TF24_LEFT_OUT
    if set_name == "fresh" and LEFT_OUT_FILE.exists():
        return frozenset(json.loads(LEFT_OUT_FILE.read_text(encoding="utf-8"))["left_out"])
    return frozenset()


def scored(set_name: str) -> list[dict[str, Any]]:
    """The items a criterion counts: the signed set's gated ones, every other set's items but
    the ones left out."""
    out = left_out(set_name)
    if set_name == "signed":
        return [i for i in items(set_name) if is_gated(i)]
    return [i for i in items(set_name) if i["id"] not in out]


def prompt_text(it: dict[str, Any], path: Path) -> str:
    """The prompt run_probe.score_stance sends for one item."""
    record = it.get("record") or prompts.record_line(it["record_text"], it["context"])
    claim = (
        (it.get("claim") or prompts.NO_CLAIM) if prompts.has_placeholder(path, "claim") else None
    )
    return prompts.stance_prompt(it["assumption"], record, it["context"], path, claim)


def read_calls(folder: Path) -> list[dict[str, Any]]:
    logs = sorted(folder.glob("*.calls.jsonl"))
    if len(logs) != 1:
        raise SystemExit(f"{folder}: expected one call log, found {len(logs)}")
    return [json.loads(x) for x in logs[0].read_text(encoding="utf-8").splitlines() if x.strip()]


def first_labels(calls: list[dict[str, Any]], set_items: list[dict[str, Any]]) -> dict[str, str]:
    """Each item's first answer as run_probe scored it."""
    first: dict[str, dict[str, Any]] = {}
    for c in calls:
        first.setdefault(c["item_id"], c)
    labels = {}
    for it in set_items:
        c = first.get(it["id"])
        if c is None:
            labels[it["id"]] = "missing"
            continue
        parsed, err = parse_json_output(c["raw_text"], prompts.STANCE_SCHEMA)
        labels[it["id"]] = tally_answer(StanceScore(), it, ModelOutput(c["raw_text"], parsed, err))
    return labels


class Run:
    """One prompt on one set: labels, the model's SHA-256 and timing."""

    def __init__(
        self, labels: dict[str, str], sha: str, seconds: list[float], tokens: list[int], where: str
    ) -> None:
        self.labels, self.sha, self.where = labels, sha, where
        self.seconds, self.tokens = seconds, tokens


def load_run(out: Path, prompt: str, set_name: str) -> Run | None:
    folder = out / f"{prompt}_{set_name}"
    if (folder / "summary.json").exists():
        calls = read_calls(folder)
        shas = {c["model_sha256"] for c in calls}
        if len(shas) != 1:
            raise SystemExit(f"{folder}: more than one model in the call log")
        return Run(
            first_labels(calls, items(set_name)),
            shas.pop(),
            [c["seconds"] for c in calls],
            [c["prompt_tokens"] for c in calls],
            folder.name,
        )
    if prompt == "base" and set_name == "signed":
        rows = [json.loads(x) for x in BASELINE.read_text(encoding="utf-8").splitlines()]
        return Run(
            {r["item_id"]: r["first"] for r in rows},
            rows[0]["model_sha256"],
            [],
            [],
            f"{BASELINE.name} (Mac run of 2026-10-19)",
        )
    return None


def _n(labels: dict[str, str], its: list[dict[str, Any]], gold: str | None, got: str) -> int:
    return sum(labels[i["id"]] == got for i in its if gold is None or i["expected"] == gold)


def recall(labels: dict[str, str], its: list[dict[str, Any]], gold: str) -> tuple[int, int]:
    pool = [i for i in its if i["expected"] == gold]
    return _n(labels, pool, gold, gold), len(pool)


def signed_metrics(labels: dict[str, str]) -> dict[str, Any]:
    its = scored("signed")
    said = [i for i in its if labels[i["id"]] == "contradicts"]
    right = sum(i["expected"] == "contradicts" for i in said)
    capable = [i for i in said if i.get("kind") != "meaning"]
    return {
        "valid": sum(labels[i["id"]] not in ("invalid", "missing") for i in its),
        "n": len(its),
        "supports_recall": recall(labels, its, "supports"),
        "contradicts_precision": (right, len(said)),
        "contradicts_recall": recall(labels, its, "contradicts"),
        "contradicts_shown_as_supports": _n(labels, its, "contradicts", "supports"),
        "traps_shown_as_supports": sum(
            labels[i["id"]] == "supports"
            for i in its
            if i["expected"] in ("complicates", "irrelevant")
        ),
        "wrong_contradicts": sorted(i["id"] for i in said if i["expected"] != "contradicts"),
        "verdict_capable_wrong_contradicts": sum(i["expected"] != "contradicts" for i in capable),
    }


def new_set_metrics(labels: dict[str, str], set_name: str) -> dict[str, Any]:
    its = scored(set_name)
    targets = [i for i in its if i.get("trap") in TARGET_TRAPS]
    return {
        "valid": sum(labels[i["id"]] not in ("invalid", "missing") for i in its),
        "n": len(its),
        "target_items": len(targets),
        "wrong_contradicts": sorted(i["id"] for i in targets if labels[i["id"]] == "contradicts"),
        "contradicts_recall": recall(labels, its, "contradicts"),
        "supports_recall": recall(labels, its, "supports"),
    }


def _ge(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """a's rate at least b's, on the same items."""
    return a[0] * max(b[1], 1) >= b[0] * max(a[1], 1)


def _rate(x: tuple[int, int], bar: float) -> bool:
    return x[1] > 0 and x[0] / x[1] >= bar


def criteria(out: Path, cand: str) -> list[tuple[str, str, bool]]:
    """(set, criterion, met) for one candidate, as PREREGISTERED.md states them."""
    res: list[tuple[str, str, bool]] = []
    base = {s: load_run(out, "base", s) for s in SETS}
    runs = {s: load_run(out, cand, s) for s in SETS}
    for s in SETS:
        if runs[s] is None or base[s] is None:
            missing = PROMPT_NAMES[cand] if runs[s] is None else "v1.1"
            res.append((s, f"{missing} was run on this set", False))
    if any(not ok for *_, ok in res):
        return res
    # A decision compares one model with itself: every run it reads, the reused 2026-10-19
    # baseline included, must come from the same model file.
    shas = {r.sha for r in [*base.values(), *runs.values()] if r is not None}
    if len(shas) != 1:
        return [("all", f"every run from one model file (found {len(shas)})", False)]
    sm, bm = signed_metrics(runs["signed"].labels), signed_metrics(base["signed"].labels)
    cp, cr = sm["contradicts_precision"], sm["contradicts_recall"]
    res += [
        ("signed", "valid output 100%", sm["valid"] == sm["n"]),
        ("signed", "supports recall >= 90%", _rate(sm["supports_recall"], 0.90)),
        ("signed", "contradicts precision >= 90%", cp[1] > 0 and cp[0] / cp[1] >= 0.90),
        (
            "signed",
            "0 gold contradicts shown as supports",
            sm["contradicts_shown_as_supports"] == 0,
        ),
        ("signed", f"contradicts recall >= {cr[1] - 1} of {cr[1]}", cr[0] >= cr[1] - 1),
        (
            "signed",
            f"traps shown as supports <= v1.1's {bm['traps_shown_as_supports']}",
            sm["traps_shown_as_supports"] <= bm["traps_shown_as_supports"],
        ),
    ]
    for s in ("fresh", "tf24", "r26"):
        m, b = new_set_metrics(runs[s].labels, s), new_set_metrics(base[s].labels, s)
        res.append(
            (
                s,
                "at most 1 wrong contradicts on told-frame and undated-denial items",
                len(m["wrong_contradicts"]) <= 1,
            )
        )
        res.append(
            (
                s,
                "contradicts recall on controls >= v1.1's",
                _ge(m["contradicts_recall"], b["contradicts_recall"]),
            )
        )
        if s == "fresh":
            res.append(
                (s, "contradicts recall on controls >= 80%", _rate(m["contradicts_recall"], 0.80))
            )
        res.append(
            (
                s,
                "supports recall on controls >= v1.1's",
                _ge(m["supports_recall"], b["supports_recall"]),
            )
        )
    return res


def passes(out: Path, cand: str) -> bool:
    return all(ok for *_, ok in criteria(out, cand))


def baseline_ok(out: Path) -> tuple[bool, str]:
    """The 2026-10-19 v1.1 run stands in for v1.1 on the signed set only when this Mac's model
    is the same file and every v1.1 prompt renders byte for byte as that run sent it."""
    rows = [json.loads(x) for x in BASELINE.read_text(encoding="utf-8").splitlines()]
    here = load_run(out, "base", "fresh")
    if here is None:
        return False, "v1.1 has not run on the fresh set yet"
    if here.sha != rows[0]["model_sha256"]:
        return False, f"model differs: {here.sha[:16]} here, {rows[0]['model_sha256'][:16]} then"
    by_id = {r["item_id"]: r for r in rows}
    path = PROMPTS["base"]
    differ = [
        it["id"]
        for it in items("signed")
        if hashlib.sha256(prompt_text(it, path).encode("utf-8")).hexdigest()
        != by_id[it["id"]]["prompt_sha256"]
    ]
    if differ:
        return False, f"{len(differ)} v1.1 prompts render differently ({', '.join(differ[:5])})"
    return True, "same model file and the same 105 prompts as the 2026-10-19 run"


def _pct(x: tuple[int, int]) -> str:
    if not x[1]:
        return "n/a"
    lo, hi = wilson(*x) or (0, 0)
    return f"{x[0]}/{x[1]} ({x[0] / x[1]:.0%}, 95% CI {lo:.0%} to {hi:.0%})"


def report(out: Path) -> str:
    lines = ["# Stance v1.3 re-probe of the local 14B", ""]
    runs = {(p, s): load_run(out, p, s) for p in PROMPTS for s in SETS}
    shas = {r.sha for r in runs.values() if r is not None}
    lines.append(f"Model SHA-256: {', '.join(sorted(shas))}")
    _, why = baseline_ok(out)
    signed_base = runs["base", "signed"]
    where = signed_base.where if signed_base else "not run"
    lines.append(f"v1.1 on the signed set: {where} (baseline check: {why})")
    for p, path in PROMPTS.items():
        body = prompts._body(path)  # noqa: SLF001 - the text the model sees
        lines.append(
            f"Prompt {PROMPT_NAMES[p]}: {path.name}, file {prompts.prompt_version(path)},"
            f" body sha256 {hashlib.sha256(body.encode()).hexdigest()[:16]}"
        )
    for s in SETS:
        sha = hashlib.sha256(SETS[s].read_bytes()).hexdigest()[:16]
        lines.append(
            f"Set {s} ({SET_NAMES[s]}): {SETS[s].relative_to(ROOT)}, sha256 {sha},"
            f" {len(scored(s))} scored, left out: {', '.join(sorted(left_out(s))) or 'none'}"
        )
    lines += ["", "## Decision (PREREGISTERED.md)", ""]
    verdict = []
    for cand in ("a", "b"):
        if not any(runs[cand, s] for s in SETS):
            lines.append(f"{PROMPT_NAMES[cand]}: not run.")
            continue
        res = criteria(out, cand)
        met = all(ok for *_, ok in res)
        verdict.append((cand, met))
        lines.append(f"### {PROMPT_NAMES[cand]}: {'meets every criterion' if met else 'FAILS'}")
        lines += [f"- {'met' if ok else 'NOT met'}: {s}, {c}" for s, c, ok in res]
        lines.append("")
    rec = next((c for c, met in verdict if met), None)
    lines.append(f"Recommendation: {'sign ' + PROMPT_NAMES[rec] if rec else 'no prompt change'}.")
    lines += ["", "## Numbers (first answers)", ""]
    for p in PROMPTS:
        r = runs[p, "signed"]
        if r is None:
            continue
        m = signed_metrics(r.labels)
        lines.append(
            f"- {PROMPT_NAMES[p]}, signed: supports recall {_pct(m['supports_recall'])};"
            f" contradicts precision {_pct(m['contradicts_precision'])}; contradicts recall"
            f" {_pct(m['contradicts_recall'])}; traps shown as supports"
            f" {m['traps_shown_as_supports']}; wrong contradicts"
            f" {', '.join(m['wrong_contradicts']) or 'none'}"
            f" ({m['verdict_capable_wrong_contradicts']} on non-meaning assumptions)"
        )
    for s in ("fresh", "tf24", "r26"):
        for p in PROMPTS:
            r = runs[p, s]
            if r is None:
                continue
            m = new_set_metrics(r.labels, s)
            lines.append(
                f"- {PROMPT_NAMES[p]}, {s}: wrong contradicts on {m['target_items']}"
                f" told-frame and denial items: {', '.join(m['wrong_contradicts']) or 'none'};"
                f" contradicts recall {_pct(m['contradicts_recall'])}; supports recall"
                f" {_pct(m['supports_recall'])}"
            )
    lines += ["", "## Time per call (this Mac)", ""]
    for p in PROMPTS:
        sec = [x for s in SETS if runs[p, s] for x in runs[p, s].seconds]
        tok = [x for s in SETS if runs[p, s] for x in runs[p, s].tokens]
        if sec:
            lines.append(
                f"- {PROMPT_NAMES[p]}: {len(sec)} calls, mean {sum(sec) / len(sec):.1f} s,"
                f" mean prompt {sum(tok) / len(tok):.0f} tokens"
            )
    lines += [
        "",
        "## Every item (first answer; * marks an item left out of the criteria)",
        "",
        "| Set | Item | Gold | Trap | " + " | ".join(PROMPT_NAMES.values()) + " |",
        "|---|---|---|---|" + "---|" * len(PROMPTS),
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


def baseline_file(calls_path: Path, dest: Path) -> None:
    """Per-item rows for the 2026-10-19 v1.1 signed-set run: ids, labels, the model's SHA-256
    and each prompt's SHA-256. No item text."""
    calls = [json.loads(x) for x in calls_path.read_text(encoding="utf-8").splitlines()]
    its = items("signed")
    labels = first_labels(calls, its)
    first = {}
    for c in calls:
        first.setdefault(c["item_id"], c)
    set_sha = hashlib.sha256(SETS["signed"].read_bytes()).hexdigest()[:16]
    rows = [
        {
            "set": "signed",
            "set_sha256": set_sha,
            "item_id": it["id"],
            "gold": it["expected"],
            "scored": is_gated(it),
            "first": labels[it["id"]],
            "model_sha256": first[it["id"]]["model_sha256"],
            "prompt_version": first[it["id"]]["prompt_version"],
            "prompt_sha256": first[it["id"]]["prompt_sha256"],
        }
        for it in its
    ]
    dest.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report").add_argument("out", type=Path)
    d = sub.add_parser("decide")
    d.add_argument("out", type=Path)
    d.add_argument("candidate", choices=["a", "b"])
    sub.add_parser("baseline-ok").add_argument("out", type=Path)
    bf = sub.add_parser("baseline-file")
    bf.add_argument("calls", type=Path)
    bf.add_argument("dest", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "report":
        sys.stdout.write(report(args.out))
        return 0
    if args.cmd == "decide":
        return 0 if passes(args.out, args.candidate) else 1
    if args.cmd == "baseline-ok":
        ok, why = baseline_ok(args.out)
        print(why)
        return 0 if ok else 1
    baseline_file(args.calls, args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
