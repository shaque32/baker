"""Speed test: a full audit of a synthetic case on a local model, timed, with model calls per claim.

Usage:
  python -m eval.probe.time_case --dry-run
      No model. Counts the calls a real run makes (stance calls do not depend on the model).
  python -m eval.probe.time_case --models eval/probe/models.local.json [--claims C02,C05]
      [--n-ctx 4096] [--ai-review] [--case case01] [--out eval/out/speed]

For each model in the models file (the probe's file; a null sha256 is computed here):
1. Build the case fresh, as the eval does (eval/run_pipeline.build_case), with the case's
   assumption sheet as the filler, so every model sees the same assumptions.
2. Cold run: the product's components on that model. Records model load time, each call's
   seconds and tokens, and wall time. --claims runs a subset and projects the whole case.
3. Warm run: the same audit again on the same database, which is what an expert's rerun after
   accepting evidence costs. Stored outputs are reused (core/audit/_local_model.py).
4. Surfacing: for each gold claim, whether the run put its key evidence in front of the
   expert with a verified quote and the gold direction (supports for a supported claim,
   contradicts for a contradicted one). Under rules 0.2.0 the expert accepts the key evidence
   for every SUPPORTED, so evidence the model never surfaces is a claim the expert cannot
   support from the queue. Reported, not gated; thread 2's eval gates verdicts.

Writes <out>/summary.md (paste this back) and <out>/summary.json. Synthetic data only.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import shutil
import sqlite3
import subprocess  # noqa: S404 - sysctl only, fixed arguments
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core import pipeline
from core.audit import review as review_mod
from core.audit import stance as stance_mod
from core.audit._local_model import LazyModel, ModelConfig, RunPort
from core.contracts import GoldClaim, Stance
from core.llm.runtime import FakeModel, sha256_file
from eval import run_pipeline as rp
from eval.run_eval import load_jsonl

GOLD_SPEC = Path("eval/gold/case01/assumptions.jsonl")  # once Arsh signs the sheet
DRAFT_SPEC = Path("eval/probe_draft/case01_assumptions.jsonl")
K = pipeline.Components.k  # candidates per assumption, as the pipeline asks for
DIRECTION = {"supported": Stance.SUPPORTS, "contradicted": Stance.CONTRADICTS}


def default_spec() -> Path:
    return GOLD_SPEC if GOLD_SPEC.exists() else DRAFT_SPEC


def machine() -> dict[str, Any]:
    info: dict[str, Any] = {"platform": platform.platform(), "cpu": platform.processor()}
    try:
        info["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30)
    except (ValueError, OSError, AttributeError):
        info["ram_gb"] = None
    exe = shutil.which("sysctl")
    if exe and sys.platform == "darwin":
        try:
            out = subprocess.run(  # noqa: S603 - fixed arguments, local binary
                [exe, "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5, check=True,
            )  # fmt: skip
            info["cpu"] = out.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            pass
    return info


# ---------------------------------------------------------------- one run


def _components(conn: sqlite3.Connection, model: Any, spec: Path, ai_review: bool):  # noqa: ANN202
    replace: dict[str, object] = {"labeler": stance_mod.create(conn, model=model)}
    if ai_review:
        replace["reviewer"] = review_mod.create(conn, model=model)
    # real_components collects the model_runs of the passes given in replace.
    return pipeline.real_components(conn, replace=replace, filler=rp.spec_filler(spec))


def _ports(comps: pipeline.Components) -> dict[str, RunPort]:
    out = {}
    for purpose, comp in (("stance", comps.labeler), ("review", comps.reviewer)):
        port = getattr(comp, "model", None)
        if isinstance(port, RunPort):
            out[purpose] = port
    return out


def calls_per_claim(conn: sqlite3.Connection, run_ids: set[str]) -> dict[str, Counter]:
    """Model calls per claim and purpose, from model_calls (subject ids name the assumption
    for stance calls and the evidence item for review calls)."""
    asm_claim = dict(conn.execute("SELECT id, claim_id FROM assumptions"))
    ev_asm = dict(conn.execute("SELECT id, assumption_id FROM evidence_items"))
    purpose = dict(conn.execute("SELECT id, purpose FROM model_runs"))
    out: dict[str, Counter] = defaultdict(Counter)
    for run_id, subject_json in conn.execute("SELECT model_run_id, subject_json FROM model_calls"):
        if run_id not in run_ids:
            continue
        first = json.loads(subject_json)[0]
        claim = asm_claim.get(first) or asm_claim.get(ev_asm.get(first, ""), "?")
        out[claim][purpose.get(run_id, "?")] += 1
    return out


def retrieved_keys(conn: sqlite3.Connection, assumption_ids: list[str], keys: set[str]) -> set[str]:
    """Key evidence retrieval hands the labeler at all (the ceiling for any model)."""
    from core.audit import retrieval

    r = retrieval.create(conn)
    found: set[str] = set()
    for a in pipeline.load_assumptions(conn, assumption_ids):
        found |= {c.record_id for c in r.retrieve(a, conn, K)} & keys
    return found


def surfacing(conn: sqlite3.Connection, gold: list[GoldClaim]) -> dict[str, Any]:
    """Key evidence surfaced in the gold direction, in the latest completed run, next to the
    key evidence retrieval reached at all, so a model miss and a retrieval miss stay apart."""
    run = pipeline.last_run(conn)
    manifest = run["manifest"] if run else {}
    claims: dict[str, Any] = {}
    key_total = key_found = key_retrieved = ready = needs = 0
    wrong_direction: list[str] = []
    support_items = 0
    for g in gold:
        items = pipeline.load_evidence(conn, manifest.get(g.claim_id, {}).get("evidence", []))
        support_items += sum(e.stance == Stance.SUPPORTS for e in items)
        want = DIRECTION.get(g.gold_verdict.value)
        if want is None:
            continue
        needs += 1
        keys = set(g.key_evidence)
        found = sorted({e.record_id for e in items if e.record_id in keys and e.stance == want})
        flipped = sorted(
            {
                e.record_id
                for e in items
                if e.record_id in keys and e.stance in DIRECTION.values() and e.stance != want
            }
        )
        wrong_direction += [f"{g.claim_id}:{r}" for r in flipped]
        reached = retrieved_keys(conn, manifest.get(g.claim_id, {}).get("assumptions", []), keys)
        key_total += len(keys)
        key_found += len(found)
        key_retrieved += len(reached)
        ready += bool(found)
        claims[g.claim_id] = {
            "gold": g.gold_verdict.value,
            "key_evidence": len(keys),
            "surfaced": found,
            "retrieved": sorted(reached),
            "wrong_direction": flipped,
        }
    return {
        "claims_ready_for_expert": ready,
        "claims_needing_key_evidence": needs,
        "key_evidence_recall": round(key_found / key_total, 3) if key_total else None,
        "key_evidence_retrieved": round(key_retrieved / key_total, 3) if key_total else None,
        "key_evidence_wrong_direction": wrong_direction,
        "supporting_items_for_expert": support_items,
        "per_claim": claims,
    }


def _stats(ports: dict[str, RunPort]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for purpose, port in ports.items():
        fresh = [s for s in port.stats if not s.reused]
        secs = sum(s.seconds for s in fresh)
        toks = sum(s.completion_tokens for s in fresh)
        out[purpose] = {
            "calls": len(port.stats),
            "reused": port.reused,
            "seconds": round(secs, 1),
            "mean_seconds_per_call": round(secs / len(fresh), 2) if fresh else None,
            "mean_prompt_tokens": round(sum(s.prompt_tokens for s in fresh) / len(fresh))
            if fresh
            else None,
            "mean_completion_tokens": round(toks / len(fresh)) if fresh else None,
            "tokens_per_second": round(toks / secs, 1) if secs else None,
        }
    return out


def audit_once(
    conn: sqlite3.Connection, model: Any, spec: Path, ai_review: bool, claims: list[str] | None
) -> dict[str, Any]:
    comps = _components(conn, model, spec, ai_review)
    start = time.perf_counter()
    result = pipeline.run_audit(conn, comps, clock=rp._clock, claim_ids=claims)
    wall = time.perf_counter() - start
    ports = _ports(comps)
    run_ids = {p.run_id for p in ports.values()}
    return {
        "wall_seconds": round(wall, 1),
        "claims": len(result.decisions),
        "verdicts": dict(Counter(d.verdict.value for d in result.decisions)),
        "stored_items": result.stored_items,
        "dropped_labels": result.dropped_labels,
        "outputs_reused": result.model_outputs_reused,
        "passes": _stats(ports),
        "calls_per_claim": {k: dict(v) for k, v in sorted(calls_per_claim(conn, run_ids).items())},
    }


def time_model(
    entry: dict[str, Any],
    *,
    case: str,
    spec: Path,
    out: Path,
    n_ctx: int | None,
    ai_review: bool,
    claims: list[str] | None,
    full_stance_calls: int | None,
) -> dict[str, Any]:
    name = entry["name"]
    path = Path(entry["path"]).expanduser()
    sha = entry.get("sha256")
    if not sha:
        print(f"{name}: computing SHA-256 of {path} (one pass over the file)", file=sys.stderr)
        sha = sha256_file(path)
    model = LazyModel(ModelConfig(name=name, path=path, sha256=sha, n_ctx=n_ctx))
    conn = rp.build_case(case, out / name / f"{case}.db")
    gold = load_jsonl(Path("eval/gold") / case / "gold.jsonl", GoldClaim)
    try:
        print(f"{name}: cold run", file=sys.stderr, flush=True)
        cold = audit_once(conn, model, spec, ai_review, claims)
        cold["model_load_seconds"] = round(model.load_seconds or 0.0, 1)
        cold["surfacing"] = surfacing(conn, [g for g in gold if not claims or g.claim_id in claims])
        print(f"{name}: warm run (rerun after expert decisions)", file=sys.stderr, flush=True)
        warm = audit_once(conn, model, spec, ai_review, claims)
    finally:
        conn.close()
    res: dict[str, Any] = {
        "model": name,
        "sha256": sha,
        "n_ctx": model.params.n_ctx,
        "ai_review": ai_review,
        "claims_run": claims or "all",
        "cold": cold,
        "warm": {k: warm[k] for k in ("wall_seconds", "outputs_reused", "passes")},
    }
    stance = cold["passes"].get("stance", {})
    per_call = stance.get("mean_seconds_per_call")
    if per_call and full_stance_calls:
        res["projected_full_case_stance_hours"] = round(per_call * full_stance_calls / 3600, 2)
    return res


# ---------------------------------------------------------------- dry run


def dry_run(case: str, spec: Path, out: Path) -> dict[str, Any]:
    """Every stance call a real run makes, with no model: the fake answers 'irrelevant'."""
    fake = FakeModel(
        name="dry-run",
        respond=lambda _p: '{"stance": "irrelevant", "quote": "", "rationale": "dry run"}',
    )
    conn = rp.build_case(case, out / "dry_run" / f"{case}.db")
    try:
        comps = _components(conn, fake, spec, ai_review=False)
        pipeline.run_audit(conn, comps, clock=rp._clock)
        port = _ports(comps)["stance"]
        run_ids = {port.run_id}
        per_claim = calls_per_claim(conn, run_ids)
        kinds = Counter(
            k
            for (k,) in conn.execute(
                "SELECT a.kind FROM model_calls mc JOIN assumptions a"
                " ON a.id = json_extract(mc.subject_json, '$[0]') WHERE mc.model_run_id = ?",
                (port.run_id,),
            )
        )
        chars = [
            len(p)
            for (p,) in conn.execute(
                "SELECT prompt FROM model_calls WHERE model_run_id = ?", (port.run_id,)
            )
        ]
    finally:
        conn.close()
    return {
        "stance_calls": len(chars),
        "stance_calls_by_assumption_kind": dict(kinds.most_common()),
        "mean_prompt_chars": round(sum(chars) / len(chars)) if chars else 0,
        "max_prompt_chars": max(chars, default=0),
        "calls_per_claim": {k: v["stance"] for k, v in sorted(per_claim.items())},
    }


# ---------------------------------------------------------------- output


def _f(v: object) -> str:
    return "n/a" if v is None else str(v)


def markdown(summary: dict[str, Any]) -> str:
    m = summary["machine"]
    lines = [
        f"# Speed test, {summary['case']}",
        "",
        f"Machine: {m.get('cpu')}, {m.get('ram_gb')} GB, {m.get('platform')}",
        f"Assumptions: {summary['assumption_spec']}",
    ]
    d = summary["dry_run"]
    lines += [
        "",
        f"Calls a full run makes: {d['stance_calls']} stance calls "
        f"(by assumption kind: {d['stance_calls_by_assumption_kind']}), prompts about "
        f"{d['mean_prompt_chars']} characters (max {d['max_prompt_chars']}).",
        "Stance calls per claim: " + ", ".join(f"{k} {v}" for k, v in d["calls_per_claim"].items()),
    ]
    rows = summary.get("models", [])
    if rows:
        lines += [
            "",
            "| model | n_ctx | claims | cold wall s | load s | stance calls | s/call "
            "| prompt tok | output tok | tok/s | full case h (projected) | warm wall s "
            "| reused | key evidence surfaced (retrieved) | claims ready | support items |",
            "|" + "---|" * 16,
        ]
        for r in rows:
            if "error" in r:
                lines.append(f"| {r['model']} | error: {r['error']} |" + " |" * 14)
                continue
            c, st = r["cold"], r["cold"]["passes"].get("stance", {})
            s = c["surfacing"]
            lines.append(
                "| "
                + " | ".join(
                    _f(x)
                    for x in (
                        r["model"],
                        r["n_ctx"],
                        c["claims"],
                        c["wall_seconds"],
                        c["model_load_seconds"],
                        st.get("calls"),
                        st.get("mean_seconds_per_call"),
                        st.get("mean_prompt_tokens"),
                        st.get("mean_completion_tokens"),
                        st.get("tokens_per_second"),
                        r.get("projected_full_case_stance_hours"),
                        r["warm"]["wall_seconds"],
                        r["warm"]["outputs_reused"],
                        f"{s['key_evidence_recall']} ({s['key_evidence_retrieved']})",
                        f"{s['claims_ready_for_expert']}/{s['claims_needing_key_evidence']}",
                        s["supporting_items_for_expert"],
                    )
                )
                + " |"
            )
        for r in rows:
            if "error" in r:
                continue
            s = r["cold"]["surfacing"]
            missed = [k for k, v in s["per_claim"].items() if not v["surfaced"]]
            lines += [
                "",
                f"{r['model']}: verdicts {r['cold']['verdicts']}; dropped labels "
                f"{r['cold']['dropped_labels']}; claims with no key evidence surfaced: "
                f"{', '.join(missed) or 'none'}; key evidence in the wrong direction: "
                f"{', '.join(s['key_evidence_wrong_direction']) or 'none'}.",
            ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", type=Path, help="the probe's models.local.json")
    ap.add_argument("--dry-run", action="store_true", help="count calls only, no model")
    ap.add_argument("--case", default="case01")
    ap.add_argument("--assumption-spec", type=Path, default=None)
    ap.add_argument("--claims", default=None, help="comma-separated claim ids (a subset)")
    ap.add_argument("--n-ctx", type=int, default=None, help="4096 for a 14B model on 16 GB")
    ap.add_argument("--ai-review", action="store_true", help="also time the AI reviewer pass")
    ap.add_argument("--out", type=Path, default=Path("eval/out/speed"))
    args = ap.parse_args(argv)
    if not args.dry_run and args.models is None:
        ap.error("pass --models (or --dry-run)")

    spec = args.assumption_spec or default_spec()
    claims = [c.strip() for c in args.claims.split(",")] if args.claims else None
    args.out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "case": args.case,
        "machine": machine(),
        "assumption_spec": str(spec),
        "dry_run": dry_run(args.case, spec, args.out),
    }
    full = summary["dry_run"]["stance_calls"]
    if not args.dry_run:
        summary["models"] = []
        for entry in json.loads(args.models.read_text(encoding="utf-8")):
            try:
                res = time_model(
                    entry,
                    case=args.case,
                    spec=spec,
                    out=args.out,
                    n_ctx=args.n_ctx,
                    ai_review=args.ai_review,
                    claims=claims,
                    full_stance_calls=full,
                )
            except Exception as e:  # noqa: BLE001 - report and move on to the next model
                res = {"model": entry.get("name"), "error": f"{type(e).__name__}: {e}"}
            summary["models"].append(res)
            gc.collect()  # free one model's weights before the next loads
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md = markdown(summary)
    (args.out / "summary.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
