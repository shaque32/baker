"""GPU test: run the probe items through each local model and score them against the pass bars.

Usage:
  python -m eval.probe.run_probe --models eval/probe/models.local.json [--repeat 2]
      [--reviewer eval/probe/smoke_reviewer.jsonl] [--stance eval/probe/smoke_stance.jsonl]
      [--out eval/out/probe]

Pass bars (wave2-consensus.md, section 4): valid output 100%, quote check >= 95%,
"supports" precision >= 95% and recall >= 90%, zero reviewer false accepts on overreach items,
identical output on a repeat run. Results on the smoke items are provisional: the signed probe
set replaces them.

Expert confirms (rules 0.2.0). No claim is SUPPORTED until an expert accepts its key evidence,
so the reviewer decides nothing and the stance labeler's job is to put the right evidence in
front of the expert. `expert_confirms` scores that, from the stance items alone (--stance-only
skips the reviewer items):
- supports recall >= 90%: a true support the model misses, or quotes wrongly, never reaches
  the expert's queue;
- contradicts precision >= 90%: a "contradicts" on an observed record makes the claim
  CONTRADICTED with no expert step (rules.py rule 1b), so a wrong one is a wrong verdict. Rule
  1b treats a model's contradicts on a meaning assumption, or on one whose checks all passed,
  as complicates, so for those items a wrong one costs the expert a look, not a verdict; the
  bar counts every kind, and `reported` gives the precision on the other kinds;
- zero "supports" on an item whose gold is "contradicts": the expert would be shown
  contradicting evidence as support;
- valid output 100%.
Supports precision is reported as expert load (items the expert dismisses), not gated. These
criteria were set before the 8B and 14B were re-run on them (Wave 3, 2026-10-08). Also reported:
items of the trap families stance guide v0.3 moved from contradicts to complicates (MOVED_TRAPS)
shown as supports, which the own-model go bar holds at zero (eval/stancedata/GO_BAR.md).

`expert_confirms(...)["reported"]` (grading audit, 2026-10-14; reported, never gated): every
gold complicates or irrelevant item shown as supports, contradicts precision on non-meaning
assumptions, 95% intervals with the item counts behind them, and each later repeat scored on its
own. With 8 gated gold contradicts, one wrong "contradicts" already puts precision under 90%.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # noqa: S404 - nvidia-smi only, fixed arguments
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.audit.quotes import verify_quote
from core.llm.calls import CallLog, make_record
from core.llm.runtime import (
    PRODUCT_RUNTIME,
    RUNTIMES,
    GenerationParams,
    LocalModel,
    ModelOutput,
    with_runtime,
)
from eval.probe import prompts
from eval.probe.from_draft import LAYOUTS

HERE = Path(__file__).parent
BARS = {
    "valid_output": 1.0,
    "quote_verified": 0.95,
    "supports_precision": 0.95,
    "supports_recall": 0.90,
    "overreach_false_accepts": 0,
    "repeat_identical": 1.0,
}
# Trap families stance guide v0.3 moved from contradicts to complicates (Arsh, 2026-10-14).
MOVED_TRAPS = frozenset(
    {"time_mismatch", "sender_mismatch", "speaker_mismatch", "later_correction"}
)


def load_items(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def wilson(num: int, den: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson interval for num/den: how far a rate on a few dozen items can be trusted."""
    if den == 0:
        return None
    p = num / den
    d = 1 + z * z / den
    c = p + z * z / (2 * den)
    h = z * ((p * (1 - p) / den + z * z / (4 * den * den)) ** 0.5)
    return round((c - h) / d, 3), round((c + h) / d, 3)


@dataclass
class ReviewerScore:
    n: int = 0
    valid: int = 0
    correct: int = 0
    overreach_items: int = 0
    overreach_false_accepts: int = 0
    clear_items: int = 0
    clear_accepted: int = 0
    dismiss_items: int = 0
    false_accepts: int = 0
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
    moved_traps_shown_as_supports: int = 0  # MOVED_TRAPS items labeled supports
    # Reported, not gated (grading audit, 2026-10-14):
    traps_shown_as_supports: int = 0  # gold complicates or irrelevant labeled supports
    overreach_shown_as_supports: int = 0  # of those, overreach-category items
    # "contradicts" on an assumption that is not a meaning assumption: the only kind a model's
    # unreviewed contradicts can turn into a CONTRADICTED verdict (rules.py rule 1b).
    verdict_capable_contradicts: int = 0
    verdict_capable_true_contradicts: int = 0
    repeat_samples: int = 0  # items answered more than once
    labels_identical: int = 0  # of those, items whose answers all got the same scored label
    repeats: list[StanceScore] = field(default_factory=list)  # answers 2.., scored alone
    failures: list[dict[str, Any]] = field(default_factory=list)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)  # gold -> got


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
    print(f"  {purpose} {item_id}", file=sys.stderr, flush=True)
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
    reason_first: bool = False,
) -> ReviewerScore:
    s = ReviewerScore()
    path = prompts.REVIEWER_REASON_FIRST if reason_first else prompts.REVIEWER_PROMPT
    schema = prompts.REVIEWER_SCHEMA_REASON_FIRST if reason_first else prompts.REVIEWER_SCHEMA
    version = prompts.prompt_version(path)
    for it in items:
        prompt = prompts.reviewer_prompt(it["assumption"], it["quote"], it["context"], path)
        outs = _call(model, prompt, schema, params, repeat, log,
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
        else:
            s.dismiss_items += 1
            s.false_accepts += decision == "accept"
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
    stance_path: Path = prompts.STANCE_PROMPT,
) -> StanceScore:
    s = StanceScore()
    version = prompts.prompt_version(stance_path)
    takes_claim = prompts.has_placeholder(stance_path, "claim")
    for it in items:
        record = it.get("record") or prompts.record_line(it["record_text"], it["context"])
        # A prompt with a {claim} slot shows the claim an item carries (eval/probe/from_draft.py);
        # one without it cannot, as in the product.
        claim = (it.get("claim") or prompts.NO_CLAIM) if takes_claim else None
        prompt = prompts.stance_prompt(it["assumption"], record, it["context"], stance_path,
                                       claim)  # fmt: skip
        outs = _call(model, prompt, prompts.STANCE_SCHEMA, params, repeat, log,
                     purpose="stance", version=version, item_id=it["id"])  # fmt: skip
        first = outs[0]
        s.repeat_identical += all(o.raw_text == first.raw_text for o in outs)
        # The first answer decides, as a stored output does in the product. Later answers are
        # scored the same way and reported (StanceScore.repeats), never gated.
        labels = [tally_answer(s, it, first)]
        while len(s.repeats) < len(outs) - 1:
            s.repeats.append(StanceScore())
        labels += [tally_answer(r, it, o) for r, o in zip(s.repeats, outs[1:], strict=False)]
        if len(labels) > 1:
            s.repeat_samples += 1
            s.labels_identical += len(set(labels)) == 1
    return s


def tally_answer(s: StanceScore, it: dict[str, Any], out: ModelOutput) -> str:
    """Score one answer into s; return the label as scored ("dropped" for a failed quote).
    eval/stancedata/score.py counts its predictions through this too, so both agree."""
    s.n += 1
    s.gold_supports += it["expected"] == "supports"
    if not out.ok:
        row = s.confusion.setdefault(it["expected"], {})
        row["invalid"] = row.get("invalid", 0) + 1
        s.failures.append({"id": it["id"], "error": out.error, "raw": out.raw_text[:300]})
        return "invalid"
    s.valid += 1
    # The product's quote check (core/audit/quotes.py): verbatim, word-aligned, in the record's
    # own text. A quote the product would discard is discarded here too.
    quote_ok = verify_quote(out.parsed["quote"], it["record_text"])
    s.quote_verified += quote_ok
    # An unverified quote is discarded, so its label cannot count as "supports".
    stance = out.parsed["stance"] if quote_ok else "dropped"
    # Confusion only: an irrelevant label needs no quote (core/audit/stance.py), and it
    # never reaches the expert either way. stance_accuracy keeps its original definition.
    shown = "irrelevant" if out.parsed["stance"] == "irrelevant" else stance
    row = s.confusion.setdefault(it["expected"], {})
    row[shown] = row.get(shown, 0) + 1
    s.correct += stance == it["expected"]
    if stance == "supports":
        s.predicted_supports += 1
        s.true_supports_predicted += it["expected"] == "supports"
        s.moved_traps_shown_as_supports += it.get("trap") in MOVED_TRAPS
        trap = it["expected"] in ("complicates", "irrelevant")
        s.traps_shown_as_supports += trap
        s.overreach_shown_as_supports += trap and it.get("category") == "overreach"
    if shown == "contradicts" and it.get("kind") != "meaning":
        s.verdict_capable_contradicts += 1
        s.verdict_capable_true_contradicts += it["expected"] == "contradicts"
    if stance != it["expected"]:
        s.failures.append({"id": it["id"], "category": it["category"],
                           "expected": it["expected"], "got": stance,
                           "quote": out.parsed["quote"][:200]})  # fmt: skip
    return shown


def is_gated(item: dict[str, Any]) -> bool:
    """Only signed, undisputed items count toward a pass bar (Arsh's rule, 2026-10-07).

    Items without the fields (the smoke set) count, and stay provisional as a whole.
    """
    if item.get("disputed"):
        return False
    return not str(item.get("labeled_by", "")).startswith("DRAFT")


def split_gated(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return [i for i in items if is_gated(i)], [i for i in items if not is_gated(i)]


EXPERT_CONFIRMS_BARS = {"supports_recall": 0.90, "contradicts_precision": 0.90}


def expert_confirms(st: StanceScore) -> dict[str, Any]:
    """Stance scored for rules 0.2.0, where the expert accepts every SUPPORTED's evidence."""
    got = Counter()
    for row in st.confusion.values():
        got.update(row)
    contra_true = st.confusion.get("contradicts", {}).get("contradicts", 0)
    contra_gold = sum(st.confusion.get("contradicts", {}).values())
    m = {
        "supports_recall": _ratio(st.true_supports_predicted, st.gold_supports),
        "contradicts_precision": _ratio(contra_true, got["contradicts"]),
        "contradicts_recall": _ratio(contra_true, contra_gold),
        "contradicts_shown_as_supports": st.confusion.get("contradicts", {}).get("supports", 0),
        "moved_traps_shown_as_supports": st.moved_traps_shown_as_supports,  # reported here
        "expert_load_supports_shown": got["supports"],
        "expert_load_precision": _ratio(st.true_supports_predicted, st.predicted_supports),
        "stance_valid_output": _ratio(st.valid, st.n),
        "confusion": st.confusion,
    }
    bars = {
        "valid_output_100": m["stance_valid_output"] == 1.0,
        "supports_recall_90": (m["supports_recall"] or 0)
        >= EXPERT_CONFIRMS_BARS["supports_recall"],
        "contradicts_precision_90": m["contradicts_precision"] is None
        or m["contradicts_precision"] >= EXPERT_CONFIRMS_BARS["contradicts_precision"],
        "no_contradicts_shown_as_supports": m["contradicts_shown_as_supports"] == 0,
    }
    m["bars"] = bars
    m["passes_all"] = all(bars.values())
    # Reported beside the bars, never gating them (the bars are Arsh's to change). Added by the
    # grading audit of 2026-10-14: the bars leave false supports on traps ungated, count meaning
    # "contradicts" that rule 1b already treats as complicates, and rest on few items.
    m["reported"] = {
        "traps_shown_as_supports": st.traps_shown_as_supports,
        "overreach_shown_as_supports": st.overreach_shown_as_supports,
        "verdict_capable_contradicts_precision": _ratio(
            st.verdict_capable_true_contradicts, st.verdict_capable_contradicts
        ),
        "verdict_capable_wrong_contradicts": st.verdict_capable_contradicts
        - st.verdict_capable_true_contradicts,
        "gold_supports": st.gold_supports,
        "gold_contradicts": contra_gold,
        "supports_recall_95ci": wilson(st.true_supports_predicted, st.gold_supports),
        "contradicts_precision_95ci": wilson(contra_true, got["contradicts"]),
        "labels_identical_across_repeats": _ratio(st.labels_identical, st.repeat_samples),
        "other_repeats": [
            {k: v for k, v in expert_confirms(r).items() if k not in ("confusion", "reported")}
            for r in st.repeats
        ],
    }
    return m


def summarize(r: ReviewerScore, st: StanceScore) -> dict[str, Any]:
    m = {
        "reviewer_valid_output": _ratio(r.valid, r.n),
        "reviewer_accuracy": _ratio(r.correct, r.n),
        "overreach_false_accepts": r.overreach_false_accepts,
        "overreach_items": r.overreach_items,
        "reviewer_clear_accept_rate": _ratio(r.clear_accepted, r.clear_items),
        "reviewer_false_accept_rate": _ratio(r.false_accepts, r.dismiss_items),
        "reviewer_items": r.n,
        "stance_items": st.n,
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
    m["expert_confirms"] = expert_confirms(st)
    return m


def check_bars(m: dict[str, Any]) -> dict[str, bool]:
    def ge(value: float | None, bar: float) -> bool:
        return value is not None and value >= bar

    # A stance-only run (--stance-only) has no reviewer answers: its reviewer parts are not
    # failed, they are not measured, so only the stance parts decide.
    reviewer_ran = m.get("reviewer_items", 1) > 0

    def rev(value: float | None, bar: float) -> bool:
        return ge(value, bar) if reviewer_ran else True

    return {
        "valid_output_100": rev(m["reviewer_valid_output"], 1.0)
        and ge(m["stance_valid_output"], 1.0),
        "quote_verified_95": ge(m["quote_verified"], BARS["quote_verified"]),
        "supports_precision_95": ge(m["supports_precision"], BARS["supports_precision"]),
        "supports_recall_90": ge(m["supports_recall"], BARS["supports_recall"]),
        "zero_overreach_false_accepts": m["overreach_false_accepts"] == 0,
        "repeat_identical": rev(m["reviewer_repeat_identical"], 1.0)
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
    stance_path: Path = prompts.STANCE_PROMPT,
    reason_first: bool = False,
    stance_only: bool = False,
) -> dict[str, Any]:
    if stance_only:
        reviewer_items = []
    suffix = ".reason_first" if reason_first else ""
    log = CallLog(out_dir / f"{model.name}{suffix}.calls.jsonl")
    rev_gate, rev_extra = split_gated(reviewer_items)
    st_gate, st_extra = split_gated(stance_items)
    r = score_reviewer(model, rev_gate, params, repeat, log, reason_first)
    st = score_stance(model, st_gate, params, repeat, log, stance_path)
    result = {"model": model.name, "sha256": model.sha256, **summarize(r, st)}
    if rev_extra or st_extra:
        # Disputed and unsigned items: scored and reported, never counted toward a pass bar.
        rx = score_reviewer(model, rev_extra, params, repeat, log, reason_first)
        sx = score_stance(model, st_extra, params, repeat, log, stance_path)
        extra = summarize(rx, sx)
        extra.pop("bars")
        extra.pop("passes_all")
        extra["reviewer_failures"] = rx.failures
        extra["stance_failures"] = sx.failures
        result["not_gated"] = extra
    result["reviewer_variant"] = "reason_first" if reason_first else "as_signed"
    result["stance_prompt"] = f"{stance_path.name}@{prompts.prompt_version(stance_path)}"
    result["reviewer_failures"] = r.failures
    result["stance_failures"] = st.failures
    calls = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
    tokens = sum(c["completion_tokens"] for c in calls)
    seconds = sum(c["seconds"] for c in calls)
    result["tokens_per_second"] = round(tokens / seconds, 1) if seconds else None
    result["mean_seconds_per_call"] = round(seconds / len(calls), 2) if calls else None
    stance_calls = [c for c in calls if c["purpose"] == "stance"]
    result["mean_seconds_per_stance_call"] = (
        round(sum(c["seconds"] for c in stance_calls) / len(stance_calls), 2)
        if stance_calls
        else None
    )
    result["stance_only"] = stance_only
    return result


RAW_COLUMNS = {
    "tokens_per_second",
    "mean_seconds_per_call",
    "mean_seconds_per_stance_call",
    "vram_used_mib",
}


def table(results: list[dict[str, Any]]) -> str:
    def f(col: str, v: object) -> str:
        if v is None:
            return "n/a"
        if isinstance(v, float) and col not in RAW_COLUMNS:
            return f"{v:.0%}"
        return str(v)

    cols = ["model", "reviewer_items", "reviewer_valid_output", "reviewer_accuracy",
            "overreach_false_accepts",
            "reviewer_clear_accept_rate", "reviewer_false_accept_rate", "stance_valid_output",
            "quote_verified",
            "supports_precision", "supports_recall", "reviewer_repeat_identical",
            "stance_repeat_identical", "tokens_per_second", "passes_all"]  # fmt: skip
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for res in results:
        lines.append("| " + " | ".join(f(c, res.get(c)) for c in cols) + " |")
    for res in results:
        if res.get("load_error"):
            lines.append(f"\n{res['model']} did not load: {res['load_error']}")
    ec_cols = ["supports_recall", "contradicts_precision", "contradicts_recall",
               "contradicts_shown_as_supports", "moved_traps_shown_as_supports",
               "expert_load_supports_shown", "expert_load_precision", "stance_valid_output",
               "passes_all"]  # fmt: skip
    lines += ["", "Expert confirms (rules 0.2.0): stance scored for surfacing evidence", ""]
    lines += ["| model | " + " | ".join(ec_cols) + " | s/stance call |",
              "|" + "---|" * (len(ec_cols) + 2)]  # fmt: skip
    for res in results:
        ec = res.get("expert_confirms", {})
        cells = [f(c, ec.get(c)) for c in ec_cols]
        cells.append(f("mean_seconds_per_stance_call", res.get("mean_seconds_per_stance_call")))
        lines.append(f"| {res.get('model')} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--reviewer", type=Path, default=HERE / "smoke_reviewer.jsonl")
    ap.add_argument("--stance", type=Path, default=HERE / "smoke_stance.jsonl")
    ap.add_argument("--probe-set", type=Path, default=None,
                    help="signed probe_draft.jsonl; replaces --reviewer, --stance")  # fmt: skip
    ap.add_argument("--stance-prompt", type=Path, default=prompts.STANCE_PROMPT,
                    help="stance prompt file, e.g. thread 6's docs/prompts/stance.md")  # fmt: skip
    ap.add_argument("--reason-first", action="store_true",
                    help="also run a reason-before-decision reviewer variant")  # fmt: skip
    ap.add_argument("--stance-only", action="store_true",
                    help="skip the reviewer items (the reviewer decides nothing)")  # fmt: skip
    ap.add_argument("--layout", choices=list(LAYOUTS), default="product",
                    help="probe input layout (eval/probe/from_draft.py)")  # fmt: skip
    ap.add_argument("--runtime", choices=sorted(RUNTIMES), default=PRODUCT_RUNTIME,
                    help="speed settings the model loads with (core/llm/runtime.py)")  # fmt: skip
    ap.add_argument("--chat-template", choices=["gguf", "no-think"], default="gguf")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--n-ctx", type=int, default=8192)
    ap.add_argument("--out", type=Path, default=Path("eval/out/probe"))
    args = ap.parse_args(argv)

    from core.llm.runtime import LlamaCppModel, ModelSpec

    args.out.mkdir(parents=True, exist_ok=True)
    if args.probe_set is not None:
        from eval.probe.from_draft import convert

        pairs = [convert(row, args.layout) for row in load_items(args.probe_set)]
        reviewer_items = [r for r, _ in pairs]
        stance_items = [s for _, s in pairs]
    else:
        reviewer_items = load_items(args.reviewer)
        stance_items = load_items(args.stance)
    params = with_runtime(GenerationParams(n_ctx=args.n_ctx), args.runtime, args.chat_template)
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
        variants = [False, True] if args.reason_first else [False]
        for reason_first in variants:
            res = run_model(model, reviewer_items, stance_items, params, args.repeat, args.out,
                            args.stance_prompt, reason_first, args.stance_only)  # fmt: skip
            res["model"] = spec.name + (" (reason first)" if reason_first else "")
            res["license"] = spec.license
            res["runtime"] = args.runtime
            res["layout"] = args.layout if args.probe_set is not None else None
            res["params"] = params.as_record()
            res["vram_used_mib"] = None if loaded is None or before is None else loaded - before
            results.append(res)
            print(f"{res['model']}: passes_all={res['passes_all']}", file=sys.stderr)
        del model
    (args.out / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = table(results)
    (args.out / "summary.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
