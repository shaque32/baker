"""Cloud Claude benchmark: the trap tests and synthetic case01, scored like the local model.

EVAL ONLY: core/ never imports this. It answers one question for Arsh: can cloud Claude be
offered as a per-case opt-in? Only synthetic data goes to the API: the signed probe set
(eval/gold/probe/probe.jsonl) and synthetic case01. Any other input file, and case02 (the
hidden held-out case), is refused before a client is made. Agreeing with Claude is not the same
as being right; only the signed labels score.

Usage:
  python -m eval.bench.claude_bench [--models claude-sonnet-5-5,claude-haiku-5-5]
      [--effort medium] [--probe-set eval/gold/probe/probe.jsonl] [--repeat 2]
      [--skip-case] [--claims C02,C05] [--out eval/out/bench]
  python -m eval.bench.claude_bench --dry-run
      No network: a stand-in client answers every call, to check the plumbing.

Needs `pip install -e ".[bench]"` and Anthropic credentials (ANTHROPIC_API_KEY, or an
`ant auth login` profile).

For each model:
1. Probe: every signed probe item through the signed reviewer and stance prompts, the same
   scoring as eval/probe/run_probe.py (gated items only toward a bar; disputed items reported).
2. Case: synthetic case01 through the real pipeline with this model as the stance labeler, the
   simulated expert, then the merge-gate scoring (verdict accuracy, false supported). Times and
   costs the whole case.
Then writes <out>/RESULTS.md beside the local Qwen3-14B's signed results.

Decision rule, fixed 2026-10-13 before any cloud run. A model is a candidate for a per-case
cloud opt-in only when, on the signed undisputed probe items and case01, it:
  a. meets all four Expert-confirms bars (supports recall >= 90%, contradicts precision >= 90%,
     zero contradicting items shown as support, valid output 100%), and
  b. has zero false supported on case01 after the simulated expert, with verdict accuracy
     >= 0.80 (the merge gate).
Among candidates, prefer the cheaper per case. Reviewer overreach false accepts and repeat
identity are reported, not gated: under rules 0.2.0 the AI reviewer decides nothing and is off
by default, and stored outputs make an expert's rerun reuse the first answer. Passing this rule
does not change the product; the cloud rule in CLAUDE.md is Arsh's to change.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.llm.runtime import ModelOutput, parse_json_output

ROOT = Path(__file__).resolve().parents[2]
SIGNED_PROBE = ROOT / "eval" / "gold" / "probe" / "probe.jsonl"
DEFAULT_MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5")
DEFAULT_CASE = "case01"

# Only these synthetic files and cases may reach the API.
ALLOWED_PROBE_DIRS = (ROOT / "eval" / "gold" / "probe", ROOT / "eval" / "probe_draft")
ALLOWED_PROBE_FILES = (ROOT / "eval" / "probe" / "smoke_stance.jsonl",
                       ROOT / "eval" / "probe" / "smoke_reviewer.jsonl")  # fmt: skip
ALLOWED_CASES = ("case01",)

# USD per million tokens (input, output), Anthropic first-party rates as of 2026-10-06.
# Haiku 5.5 is priced for prompts up to 100K tokens; every prompt here is far shorter.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
CACHE_READ_FACTOR = 0.1  # cache reads bill at a tenth of input
CACHE_WRITE_FACTOR = 1.25  # 5-minute cache writes bill at 1.25x input

# JSON Schema keywords the API's structured outputs do not take. They are dropped from the
# schema sent to the API; the full schema is still checked here on the answer.
UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {"minLength", "maxLength", "pattern", "minimum", "maximum", "multipleOf", "format"}
)

# The local Qwen3-14B Q4_K_M, as measured on Arsh's Mac (eval/probe/README.md, results of
# 2026-10-09 and 2026-10-12, signed stance prompt v1.0). Copied, not re-measured here.
LOCAL_14B: dict[str, Any] = {
    "model": "Qwen3-14B Q4_K_M (local, Mac)",
    "supports_recall": 1.0,
    "contradicts_precision": 1.0,
    "contradicts_shown_as_supports": 5,
    "stance_valid_output": 1.0,
    "contradicts_recall": 0.50,
    "expert_load_supports_shown": 49,
    "expert_load_precision": 0.55,
    "probe_seconds_per_stance_call": 22.5,
    "case_seconds_per_stance_call": 56.0,
    "case_hours": "7.75 h measured (plain), about 6.2 h estimated (flash)",
    "case_cost_usd": "0 (runs on the expert's machine)",
    "case_accuracy": "pending (the Mac run of 2026-10-13)",
}


class DataSafetyError(ValueError):
    """An input that is not one of the synthetic files or cases allowed to reach the API."""


def check_probe_path(path: Path) -> Path:
    p = path.resolve()
    if p in ALLOWED_PROBE_FILES or any(p.is_relative_to(d) for d in ALLOWED_PROBE_DIRS):
        return p
    raise DataSafetyError(
        f"{path}: only the synthetic probe files may go to a cloud model "
        f"(eval/gold/probe/, eval/probe_draft/, eval/probe/smoke_*.jsonl)"
    )


def check_case(case: str) -> str:
    if case not in ALLOWED_CASES:
        raise DataSafetyError(f"{case}: only {', '.join(ALLOWED_CASES)} may go to a cloud model")
    return case


def api_schema(schema: Any) -> Any:
    """The schema without keywords the API rejects, recursively. Never edits the input."""
    if isinstance(schema, dict):
        return {k: api_schema(v) for k, v in schema.items() if k not in UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(schema, list):
        return [api_schema(v) for v in schema]
    return schema


@dataclass(frozen=True)
class ApiParams:
    """What a call log and a model run record for a cloud call, in place of local settings."""

    model: str
    effort: str
    max_tokens: int = 16000
    seed: int | None = None  # the API takes no seed

    def as_record(self) -> dict[str, str | int | float | bool]:
        return {"api_model": self.model, "effort": self.effort, "max_tokens": self.max_tokens,
                "grammar": "json_schema"}  # fmt: skip


@dataclass
class Usage:
    calls: int = 0
    refusals: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    seconds: float = 0.0

    def add(self, other: Usage) -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def copy(self) -> Usage:
        return Usage(**{k: getattr(self, k) for k in self.__dataclass_fields__})

    def since(self, before: Usage) -> Usage:
        return Usage(
            **{k: getattr(self, k) - getattr(before, k) for k in self.__dataclass_fields__}
        )

    def cost_usd(self, model: str) -> float | None:
        price = PRICES_PER_MTOK.get(model)
        if price is None:
            return None
        inp, out = price
        total = (
            self.input_tokens * inp
            + self.cache_read_tokens * inp * CACHE_READ_FACTOR
            + self.cache_write_tokens * inp * CACHE_WRITE_FACTOR
            + self.output_tokens * out
        )
        return round(total / 1_000_000, 4)

    def as_dict(self, model: str) -> dict[str, Any]:
        d: dict[str, Any] = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["seconds"] = round(self.seconds, 1)
        d["cost_usd"] = self.cost_usd(model)
        d["mean_seconds_per_call"] = round(self.seconds / self.calls, 2) if self.calls else None
        return d


@dataclass
class ClaudeModel:
    """Same `generate_json` surface as the local runtime, backed by the Claude API.

    No refusal fallbacks: a silent switch to another model would corrupt the benchmark, so a
    refusal is scored as an invalid output instead. Thinking runs at the model's adaptive
    default; effort is fixed per run and recorded.
    """

    name: str
    effort: str = "medium"
    client: Any = None
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic(max_retries=8)
        self.sha256 = f"api:{self.name}"
        self.params = ApiParams(self.name, self.effort)

    def generate_json(self, prompt: str, schema: dict[str, Any], params: Any = None) -> ModelOutput:
        start = time.perf_counter()
        resp = self.client.messages.create(
            model=self.name,
            max_tokens=self.params.max_tokens,
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": api_schema(schema)},
            },
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.perf_counter() - start
        u = resp.usage
        self.usage.add(
            Usage(
                calls=1,
                refusals=int(resp.stop_reason == "refusal"),
                input_tokens=u.input_tokens or 0,
                output_tokens=u.output_tokens or 0,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
                seconds=elapsed,
            )
        )
        if resp.stop_reason == "refusal":
            return ModelOutput("", None, "refusal", u.input_tokens, u.output_tokens, elapsed)
        if resp.stop_reason == "max_tokens":
            return ModelOutput("", None, "max_tokens", u.input_tokens, u.output_tokens, elapsed)
        text = "".join(b.text for b in resp.content if b.type == "text")
        parsed, error = parse_json_output(text, schema)
        return ModelOutput(
            raw_text=text,
            parsed=parsed,
            error=error,
            prompt_tokens=u.input_tokens,
            completion_tokens=u.output_tokens,
            seconds=elapsed,
        )


# ---------------------------------------------------------------- stand-in client (--dry-run)


class _Obj:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class DryRunClient:
    """Answers like the API with no network: dismiss every review, 'irrelevant' every stance."""

    def __init__(self) -> None:
        self.messages = self
        self.requests: list[dict[str, Any]] = []

    def create(self, **kw: Any) -> Any:
        self.requests.append(kw)
        props = kw["output_config"]["format"]["schema"]["properties"]
        if "decision" in props:
            body = {"decision": "dismiss", "reason": "dry run"}
        else:
            body = {"stance": "irrelevant", "quote": "", "rationale": "dry run"}
        text = json.dumps(body)
        usage = _Obj(input_tokens=len(kw["messages"][0]["content"]) // 4, output_tokens=20,
                     cache_read_input_tokens=0, cache_creation_input_tokens=0)  # fmt: skip
        return _Obj(stop_reason="end_turn", content=[_Obj(type="text", text=text)], usage=usage)


# ---------------------------------------------------------------- the two runs


def probe_items(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from eval.probe.from_draft import convert
    from eval.probe.run_probe import load_items

    pairs = [convert(row) for row in load_items(check_probe_path(path))]
    return [r for r, _ in pairs], [s for _, s in pairs]


def run_probe(model: ClaudeModel, probe: Path, repeat: int, out: Path) -> dict[str, Any]:
    from eval.probe.run_probe import run_model

    reviewer, stance = probe_items(probe)
    before = model.usage.copy()
    res = run_model(model, reviewer, stance, model.params, repeat, out)  # type: ignore[arg-type]
    res["usage"] = model.usage.since(before).as_dict(model.name)
    res["effort"] = model.effort
    return res


def run_case(model: ClaudeModel, case: str, out: Path, claims: list[str] | None) -> dict[str, Any]:
    """The real pipeline on a synthetic case with this model as the stance labeler, then the
    simulated expert and the merge-gate scoring, as `make eval-real` does for the local model."""
    from core.contracts import GoldClaim
    from core.db import connect
    from eval import run_pipeline as rp
    from eval.probe.time_case import surfacing
    from eval.run_eval import load_jsonl, score

    check_case(case)
    spec = rp.assumption_sheet(case)
    before = model.usage.copy()
    start = time.perf_counter()
    preds = rp.run_once(case, "real", "accept", out, spec, "simulated", labeler_model=model,
                        claim_ids=claims)  # fmt: skip
    wall = time.perf_counter() - start
    spent = model.usage.since(before)
    gold = load_jsonl(rp.gold_path(case), GoldClaim)
    if claims:
        gold = [g for g in gold if g.claim_id in claims]
    s = score(gold, preds)
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    conn = connect(out / f"{case}.db")
    try:
        surfaced = surfacing(conn, gold)
    finally:
        conn.close()
    return {
        "case": case,
        "claims_run": claims or "all",
        "wall_seconds": round(wall, 1),
        "verdict_accuracy": round(s.verdict_accuracy, 3),
        "n_false_supported": s.n_false_supported,
        "false_supported_rate": round(s.false_supported_rate, 3),
        "confusion": s.confusion,
        "verdicts": run.get("verdicts"),
        "unreviewed_verdicts": run.get("unreviewed_verdicts"),
        "dropped_labels": run.get("dropped_labels"),
        "key_evidence_recall": surfaced["key_evidence_recall"],
        "key_evidence_retrieved": surfaced["key_evidence_retrieved"],
        "key_evidence_wrong_direction": surfaced["key_evidence_wrong_direction"],
        "claims_ready_for_expert": surfaced["claims_ready_for_expert"],
        "claims_needing_key_evidence": surfaced["claims_needing_key_evidence"],
        "supporting_items_for_expert": surfaced["supporting_items_for_expert"],
        "usage": spent.as_dict(model.name),
    }


def decide(res: dict[str, Any]) -> dict[str, Any]:
    """The decision rule in the module docstring, applied to one model's results."""
    ec = res.get("probe", {}).get("expert_confirms", {})
    case = res.get("case")
    probe_ok = bool(ec.get("passes_all"))
    if case is None:
        return {"candidate": None, "probe_bars_met": probe_ok, "why": "case01 not run"}
    case_ok = case["n_false_supported"] == 0 and case["verdict_accuracy"] >= 0.80
    if case["claims_run"] != "all":
        return {"candidate": None, "probe_bars_met": probe_ok,
                "why": "case01 run on a subset of claims"}  # fmt: skip
    why = []
    if not probe_ok:
        missed = [k for k, v in ec.get("bars", {}).items() if not v]
        why.append("misses probe bars: " + ", ".join(missed))
    if not case_ok:
        why.append(
            f"case01: {case['n_false_supported']} false supported, "
            f"accuracy {case['verdict_accuracy']:.0%}"
        )
    return {"candidate": probe_ok and case_ok, "probe_bars_met": probe_ok,
            "case_gate_met": case_ok, "why": "; ".join(why) or "meets every bar"}  # fmt: skip


# ---------------------------------------------------------------- report


def _pct(v: object) -> str:
    return f"{v:.0%}" if isinstance(v, float) else ("n/a" if v is None else str(v))


def _money(v: object) -> str:
    return f"${v:.2f}" if isinstance(v, float | int) and not isinstance(v, bool) else str(v)


def results_markdown(results: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    lines = [
        "# Cloud Claude benchmark",
        "",
        f"Run {meta['at_utc']}. Probe set: {meta['probe_set']}. Effort: {meta['effort']}. "
        f"Repeat: {meta['repeat']}.{' DRY RUN (stand-in client, no API calls).' if meta['dry_run'] else ''}",  # noqa: E501
        "Synthetic data only. Signed, undisputed items count toward a bar.",
        "",
        "## Trap tests: stance, Expert-confirms bars (signed undisputed items)",
        "",
        "| model | supports recall (>=90%) | contradicts precision (>=90%) "
        "| contradicting shown as support (0) | valid output (100%) | contradicts recall "
        "| supports shown (precision) | s/stance call |",
        "|---|---|---|---|---|---|---|---|",
    ]
    loc = LOCAL_14B
    lines.append(
        f"| {loc['model']} | {_pct(loc['supports_recall'])} | {_pct(loc['contradicts_precision'])}"
        f" | {loc['contradicts_shown_as_supports']} | {_pct(loc['stance_valid_output'])}"
        f" | {_pct(loc['contradicts_recall'])} | {loc['expert_load_supports_shown']}"
        f" ({_pct(loc['expert_load_precision'])}) | {loc['probe_seconds_per_stance_call']} |"
    )
    for r in results:
        ec = r["probe"]["expert_confirms"]
        lines.append(
            f"| {r['model']} | {_pct(ec['supports_recall'])} | {_pct(ec['contradicts_precision'])}"
            f" | {ec['contradicts_shown_as_supports']} | {_pct(ec['stance_valid_output'])}"
            f" | {_pct(ec['contradicts_recall'])} | {ec['expert_load_supports_shown']}"
            f" ({_pct(ec['expert_load_precision'])})"
            f" | {r['probe'].get('mean_seconds_per_stance_call')} |"
        )
    lines += [
        "",
        "## Trap tests: AI reviewer (reported, not gated under rules 0.2.0)",
        "",
        "| model | overreach false accepts (0) | false accept rate | clear accept rate "
        "| accuracy | valid output | repeat identical (stance / reviewer) | refusals "
        "| probe cost |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        p = r["probe"]
        lines.append(
            f"| {r['model']} | {p['overreach_false_accepts']} of {p['overreach_items']}"
            f" | {_pct(p['reviewer_false_accept_rate'])} | {_pct(p['reviewer_clear_accept_rate'])}"
            f" | {_pct(p['reviewer_accuracy'])} | {_pct(p['reviewer_valid_output'])}"
            f" | {_pct(p['stance_repeat_identical'])} / {_pct(p['reviewer_repeat_identical'])}"
            f" | {p['usage']['refusals']} | {_money(p['usage']['cost_usd'])} |"
        )
    lines += [
        "",
        "## Synthetic case01: full pipeline, simulated expert, merge-gate scoring",
        "",
        "A labeler that finds nothing scores 55% here: the five claims a failed check decides,"
        " plus the unproven ones.",
        "",
        "| model | claims | verdict accuracy (>=80%) | false supported (0) "
        "| key evidence surfaced (retrieved) | key evidence in the wrong direction "
        "| claims ready for the expert | stance calls | s/call | time for the case "
        "| cost for the case |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        f"| {loc['model']} | all | {loc['case_accuracy']} | {loc['case_accuracy']} | | | "
        f"| 498 | {loc['case_seconds_per_stance_call']} | {loc['case_hours']}"
        f" | {loc['case_cost_usd']} |",
    ]
    for r in results:
        c = r.get("case")
        if c is None:
            lines.append(f"| {r['model']} | not run |" + " |" * 9)
            continue
        u = c["usage"]
        n = "all" if c["claims_run"] == "all" else ",".join(c["claims_run"])
        lines.append(
            f"| {r['model']} | {n} | {_pct(c['verdict_accuracy'])} | {c['n_false_supported']}"
            f" | {_pct(c['key_evidence_recall'])} ({_pct(c['key_evidence_retrieved'])})"
            f" | {len(c['key_evidence_wrong_direction'])}"
            f" | {c['claims_ready_for_expert']} of {c['claims_needing_key_evidence']}"
            f" | {u['calls']} | {u['mean_seconds_per_call']} | {c['wall_seconds'] / 60:.0f} min"
            f" | {_money(u['cost_usd'])} |"
        )
    lines += ["", "## Decision rule (fixed before the run; see eval/bench/claude_bench.py)", ""]
    for r in results:
        d = r["decision"]
        verdict = {True: "candidate", False: "not a candidate", None: "undecided"}[d["candidate"]]
        lines.append(f"- {r['model']}: **{verdict}**. {d['why']}.")
    lines += [
        "",
        "Refusals are scored as invalid output. Costs use first-party list prices "
        "(eval/bench/claude_bench.py PRICES_PER_MTOK) on the tokens the API reported.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--probe-set", type=Path, default=SIGNED_PROBE)
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--skip-case", action="store_true", help="probe only, no case01 run")
    ap.add_argument("--claims", default=None, help="case01 claims to run, e.g. C02,C05")
    ap.add_argument("--dry-run", action="store_true", help="stand-in client, no network")
    ap.add_argument("--out", type=Path, default=Path("eval/out/bench"))
    args = ap.parse_args(argv)

    probe = check_probe_path(args.probe_set)
    check_case(DEFAULT_CASE)
    claims = [c.strip() for c in args.claims.split(",")] if args.claims else None
    results = []
    for name in [m.strip() for m in args.models.split(",") if m.strip()]:
        client = DryRunClient() if args.dry_run else None
        model = ClaudeModel(name, args.effort, client=client)
        out = args.out / name
        out.mkdir(parents=True, exist_ok=True)
        print(f"{name}: probe ({probe.name})", file=sys.stderr, flush=True)
        probe_res = run_probe(model, probe, args.repeat, out / "probe")
        res: dict[str, Any] = {"model": name, "effort": args.effort, "probe": probe_res}
        if not args.skip_case:
            print(f"{name}: {DEFAULT_CASE} audit", file=sys.stderr, flush=True)
            res["case"] = run_case(model, DEFAULT_CASE, out / DEFAULT_CASE, claims)
        res["usage_total"] = model.usage.as_dict(name)
        res["decision"] = decide(res)
        results.append(res)
        (out / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    meta = {
        "at_utc": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()),
        "probe_set": str(probe.relative_to(ROOT)),
        "effort": args.effort,
        "repeat": args.repeat,
        "dry_run": args.dry_run,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps({"meta": meta, "local_14b": LOCAL_14B, "results": results}, indent=2,
                   ensure_ascii=False) + "\n", encoding="utf-8")  # fmt: skip
    md = results_markdown(results, meta)
    (args.out / "RESULTS.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
