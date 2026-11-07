"""Hosted open models as the assumption filler and the testability agent, on spent cases.

EVAL ONLY: core/ never imports this. Arsh chose (2026-11-07 08:11Z, thread "Build agents into
the audit") to save the held-out case06 for the plan C stack (plans/secure-cloud-container.md:
every model job, the agents included, on a self-hosted DeepSeek V4.1 Flash or Kimi K3.1 Pro).
Before that stack exists, this asks the hosted copies of those models to do the two jobs the
testability go/no-go measures, on cases already spent, and reports the go/no-go's own measures
beside the 14B's run of record. It is development data: never quoted as evidence that the step
works (plans/testability-pass.md); only case06's first complete run counts.

What goes out: the assumption and testability prompts for synthetic case05 or case04, the
signed prompts in core/audit/prompts/ filled in by the product's own code, and nothing else.
Every other case is refused before a request is made: case02 is hidden and case06 is held out.
There is no stance call (the eval's --no-stance stand-in labels), so no verdict is scored.

Fixed before any run (2026-11-07):
- Routing, temperature 0, seed 1234, reasoning effort, structured output: open_bench's
  HostedModel and PROVIDER, unchanged. One hosted model does both jobs, as plan C would.
- The dev check's settings (plans/testability-pass.md): cap 2, the signed testability prompt
  (v1.2), the rubber-stamp expert, no challenge step, no stance.
- Reported per model and case: the step's measures as the go/no-go reads them
  (eval/run_pipeline.testability_summary), and the first pass's own share: the claims it kept
  core assumptions for, and of those how many name nothing the claim's signed sheet rows do not
  name, and how many name a person, phone or time window the sheet does not (`first_pass`).
- No repeat: a hosted model is served by many providers, so its answers do not repeat byte for
  byte. A pass here is a reason to run case06 on the self-hosted stack, nothing more.

Usage:
  OPENROUTER_API_KEY=... python -m eval.bench.agent_bench [--models NAME,...]
      [--cases case05] [--out eval/out/agent_bench] [--reasoning medium]
  python -m eval.bench.agent_bench --dry-run     no network: every answer is an empty list
  python -m eval.bench.agent_bench --estimate    the dry run's prompt tokens, priced per model
  python -m eval.bench.agent_bench --first-pass DB --cases case05
                                                 the first-pass measures of a recorded run
Writes <out>/<model>/<case>/ (the pipeline's own outputs, served.jsonl, bench.json) and
<out>/SUMMARY.md. Synthetic data only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from eval.bench.claude_bench import DataSafetyError
from eval.bench.open_bench import HostedModel, OpenModel, model

# The testability sets already spent by a go/no-go run of record. case06 is the held-out set
# for the plan C stack and case02 is the hidden case: neither may reach a hosted model.
ALLOWED_CASES = ("case05", "case04")
DEFAULT_MODELS = ("deepseek-v4.1-flash-1017", "kimi-k3.1-pro")
DEFAULT_CASES = ("case05",)
CAP = 2
# For --estimate only: output tokens assumed per call (reasoning plus the answer), unmeasured.
OUTPUT_TOKENS_PER_CALL = 1500
NO_GO_KINDS = ("names the person ", "names the phone ", "names the time window ")
# The 14B's go/no-go run of record on case05 (Arsh's Mac, 2026-11-03, commit c41882d,
# eval/out/case05/rubber_stamp/testability/go_no_go.json): the reference this bench compares to.
REFERENCE_14B = {
    "case05": {
        "claims": 48,
        # eval.bench.agent_bench --first-pass on that run's database (2026-11-07)
        "first_pass_kept": 15,
        "first_pass_match_sheet": 9,
        "first_pass_wrong_entity": 2,
        "claims_the_filler_left_untested": 33,
        "of_them_the_sheet_makes_testable": 33,
        "converted_and_accepted": 5,
        "tries": 62,
        "invalid_outputs": 0,
        "mismatch_person_phone_or_window": 0,
        "seconds_per_claim_the_step_worked_on": 71.2,
        "note": "prompt v1.0; the same answers through today's code convert 6 of 33",
    },
}


def check_agent_case(case: str) -> str:
    if case not in ALLOWED_CASES:
        raise DataSafetyError(
            f"{case}: only {', '.join(ALLOWED_CASES)} may go to a hosted model for this bench"
            " (case06 is held out for the plan C stack, case02 is hidden)"
        )
    return case


def dry_post(body: dict[str, Any], key: str | None, timeout: float) -> dict[str, Any]:
    """No network: an empty list for every call, so the step tries every claim (an upper bound
    on calls) and nothing is kept."""
    return {
        "id": "dry-run",
        "model": body["model"],
        "provider": "dry-run",
        "choices": [
            {"message": {"content": json.dumps({"assumptions": []})}, "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": len(body["messages"][0]["content"]) // 4,
            "completion_tokens": 20,
            "cost": 0.0,
        },
    }


def first_pass(db: Path, case: str) -> dict[str, Any]:
    """What the assumption filler's first pass kept, read from a finished run's database: the
    claims with core assumptions that the testability step never tried, checked against the
    claim's signed sheet rows (testability.mismatch, the go/no-go's own comparison)."""
    from core.audit import testability
    from eval import run_pipeline as rp

    sheet_path = rp.assumption_sheet(case)
    if sheet_path is None:
        raise SystemExit(f"{case}: no assumption sheet")
    rows = [json.loads(x) for x in sheet_path.read_text("utf-8").splitlines() if x.strip()]
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        sheet = testability.sheet_named(
            rows, rp.sheet_people(conn), testability.account_copies(conn)
        )
        claims = [cid for (cid,) in conn.execute("SELECT id FROM claims ORDER BY id")]
        step: set[str] = set()
        first_run = None
        for (payload,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = 'testability.repair' ORDER BY seq"
        ):
            p = json.loads(payload)
            first_run = first_run or p.get("run_id")
            if p.get("run_id") in (None, first_run):
                step.add(p["claim_id"])
        core: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for cid, tid, params in conn.execute(
            "SELECT claim_id, template_id, params_json FROM assumptions WHERE is_core = 1"
            " ORDER BY id"
        ):
            core.setdefault(cid, []).append((tid, json.loads(params)))
    finally:
        conn.close()
    kept = [c for c in claims if c in core and c not in step]
    matches, entity, no_rows = 0, 0, 0
    for c in kept:
        want = sheet.get(c)
        if want is None:
            no_rows += 1
            continue
        diff = testability.mismatch(testability.named(core[c]), want)
        matches += not diff
        entity += any(m.startswith(NO_GO_KINDS) for m in diff)
    return {
        "claims": len(claims),
        "kept_core_assumptions": len(kept),
        "of_them_name_only_what_the_sheet_names": matches,
        "of_them_name_a_person_phone_or_window_the_sheet_does_not": entity,
        "of_them_the_sheet_gives_no_core_row": no_rows,
        "left_to_the_step": len(step),
    }


def run_bench(hosted: HostedModel, case: str, out: Path) -> dict[str, Any]:
    """One case through the real pipeline with the hosted model as both the filler and the
    step, at the dev check's settings."""
    from eval import run_pipeline as rp

    case = check_agent_case(case)
    out.mkdir(parents=True, exist_ok=True)
    cost_before, calls_before = hosted.usage.cost_usd, len(hosted.served)
    tokens_before, failed_before = hosted.usage.input_tokens, hosted.usage.failed
    start = time.perf_counter()
    rp.run_once(case, "real", "accept", out, None, "rubber-stamp", challenge=False,
                filler_model=hosted, testability_cap=CAP, testability_model=hosted,
                stance=False)  # fmt: skip
    wall = time.perf_counter() - start
    t = json.loads((out / "run.json").read_text(encoding="utf-8"))["testability"]
    fp = first_pass(out / f"{case}.db", case)
    calls = len(hosted.served) - calls_before
    worked_on = t["claims_the_filler_left_untested"]
    testable = t["of_them_the_sheet_makes_testable"]
    res = {
        "model": hosted.name,
        "case": case,
        "weights": f"{hosted.spec.weights}@{hosted.spec.revision}",
        "reasoning": hosted.reasoning,
        "wall_seconds": round(wall, 1),
        "calls": calls,
        "failed_calls": hosted.usage.failed - failed_before,
        "input_tokens": hosted.usage.input_tokens - tokens_before,
        "cost_usd": round(hosted.usage.cost_usd - cost_before, 4),
        "providers": dict(hosted.usage.providers),
        "first_pass": fp,
        "step": t,
        "step_calls_per_claim": round(t["tries"] / worked_on, 2) if worked_on else None,
        "step_seconds_per_claim": round(t["seconds"] / worked_on, 1) if worked_on else None,
        # Claims that end with core assumptions after both passes, and the step's conversion as
        # the go/no-go counts it (only with at least TESTABILITY_MIN_TESTABLE testable claims).
        "with_assumptions_after_both": fp["kept_core_assumptions"] + t["converted_and_accepted"],
        "step_scorable": testable >= rp.TESTABILITY_MIN_TESTABLE,
    }
    with (out / "served.jsonl").open("w", encoding="utf-8") as f:
        for row in hosted.served[calls_before:]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "bench.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    return res


def summary(results: list[dict[str, Any]], dry: bool) -> str:
    lines = [
        "# Hosted models as filler and testability agent (eval only, development data)",
        "",
        "Spent cases only; never evidence that the step works. Hosted answers do not repeat.",
    ]
    if dry:
        lines.append("DRY RUN: no model answered; every answer was an empty list.")
    lines += [
        "",
        "| model | case | first pass kept (match sheet / wrong entity) | step converted |"
        " wrong-entity tries | invalid | calls/claim | s/claim | after both | cost |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        fp, t = r["first_pass"], r["step"]
        conv = f"{t['converted_and_accepted']} of {t['of_them_the_sheet_makes_testable']}"
        if not r["step_scorable"]:
            conv += " (under 15 testable: not scorable as written)"
        lines.append(
            f"| {r['model']} | {r['case']} | {fp['kept_core_assumptions']} of {fp['claims']}"
            f" ({fp['of_them_name_only_what_the_sheet_names']} /"
            f" {fp['of_them_name_a_person_phone_or_window_the_sheet_does_not']}) | {conv} |"
            f" {t['mismatch_person_phone_or_window']} | {t['invalid_outputs']} of {t['tries']} |"
            f" {r['step_calls_per_claim']} | {r['step_seconds_per_claim']} |"
            f" {r['with_assumptions_after_both']} of {fp['claims']} | ${r['cost_usd']} |"
        )
    for case, ref in REFERENCE_14B.items():
        if any(r["case"] == case for r in results):
            kept = ref["first_pass_kept"]
            lines += [
                "",
                f"14B run of record on {case} (Mac, 2026-11-03, {ref['note']}): first pass kept"
                f" {kept} of {ref['claims']} ({ref['first_pass_match_sheet']} /"
                f" {ref['first_pass_wrong_entity']}); step converted"
                f" {ref['converted_and_accepted']} of {ref['of_them_the_sheet_makes_testable']};"
                f" {ref['mismatch_person_phone_or_window']} wrong-entity tries;"
                f" {ref['invalid_outputs']} invalid of {ref['tries']};"
                f" {ref['seconds_per_claim_the_step_worked_on']} s per claim; after both"
                f" {kept + ref['converted_and_accepted']} of {ref['claims']}.",
            ]
    return "\n".join(lines) + "\n"


def estimate(results: list[dict[str, Any]], specs: list[OpenModel]) -> str:
    """Price a dry run's calls per model: its prompt tokens at list price, plus an assumed
    OUTPUT_TOKENS_PER_CALL. The dry run tries every claim twice, so this is an upper bound on
    calls; the output allowance is a guess."""
    calls = sum(r["calls"] for r in results)
    tokens = sum(r["input_tokens"] for r in results)
    lines = [f"dry run: {calls} calls, about {tokens} prompt tokens (characters / 4)"]
    for m in specs:
        inp, outp = m.usd_per_mtok
        usd = (tokens * inp + calls * OUTPUT_TOKENS_PER_CALL * outp) / 1_000_000
        lines.append(f"- {m.name}: about ${usd:.2f} at most (list price ${inp}/${outp} per M)")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--cases", default=",".join(DEFAULT_CASES))
    ap.add_argument("--out", type=Path, default=Path("eval/out/agent_bench"))
    ap.add_argument("--reasoning", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--dry-run", action="store_true", help="stand-in answers, no network")
    ap.add_argument("--estimate", action="store_true", help="dry run, then priced per model")
    ap.add_argument("--first-pass", type=Path, default=None, metavar="DB",
                    help="print the first-pass measures of a recorded run's database")  # fmt: skip
    args = ap.parse_args(argv)

    cases = [check_agent_case(c.strip()) for c in args.cases.split(",") if c.strip()]
    specs = [model(n.strip()) for n in args.models.split(",") if n.strip()]
    if args.first_pass is not None:
        for case in cases:
            print(json.dumps(first_pass(args.first_pass, case), indent=2))
        return 0
    dry = args.dry_run or args.estimate
    results = []
    for spec in specs[:1] if args.estimate else specs:
        hosted = HostedModel(spec, args.reasoning, post=dry_post if dry else None)
        for case in cases:
            print(f"{spec.name} {case}", file=sys.stderr, flush=True)
            results.append(run_bench(hosted, case, args.out / spec.name / case))
        print(f"{spec.name}: ${hosted.usage.cost_usd:.2f}", file=sys.stderr, flush=True)
    if args.estimate:
        print(estimate(results, specs))
        return 0
    text = summary(results, dry)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "SUMMARY.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
