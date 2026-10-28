"""Where case03's planted records sit relative to the fixed retrieval and explain.py. SYNTHETIC.

A builder's report, not a test and not a gate: it prints, claim by claim, whether the fixed
retrieval (core/audit/retrieval.py, k = 20 per assumption, on the draft assumption sheet) returns
each counter-record and decoy, and which explain.py directions list it. It reads no
challenge-step code. Use it after editing case03_story.py or case03_key.py to see that every
group 1 counter-record is still out of the retrieval's reach and found by its direction, and
that every group 2 counter-record is found by neither.

Usage: python -m eval.synthetic.case03_reach [--db eval/out/case03/reach/case03.db] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from core.audit.assumptions import instantiate
from core.audit.retrieval import SqlRetriever
from core.hypotheses import explain
from eval.run_pipeline import build_case, spec_filler
from eval.synthetic import case03_key as key

SHEET = Path("eval/synthetic/case03/draft_assumptions.jsonl")
K = 20  # core.pipeline.Components.k


def reach(conn) -> list[dict]:  # noqa: ANN001 - sqlite3.Connection
    meta = json.loads(Path("eval/synthetic/case03/case.json").read_text(encoding="utf-8"))
    filler = spec_filler(SHEET, conn)
    retriever = SqlRetriever()
    case = explain.load(conn)
    out = []
    for c in key.CLAIMS:
        props = filler(SimpleNamespace(id=c.claim_id), [])
        assumptions = [instantiate(c.claim_id, p.template_id, p.params, p.is_core) for p in props]
        retrieved: set[str] = set()
        for a in assumptions:
            retrieved |= {cand.record_id for cand in retriever.retrieve(a, conn, K)}
        found: dict[str, list[str]] = {}
        kinds = []
        for alt in explain.alternatives(case, assumptions):
            kinds.append(alt.kind)
            for f in alt.fits:
                found.setdefault(f.record_id, []).append(alt.kind)
        plant = meta["plants"][c.claim_id]
        out.append(
            {
                "claim_id": c.claim_id,
                "group": c.group,
                "direction": c.direction,
                "directions_fired": kinds,
                "counter": {
                    rid: {"retrieved": rid in retrieved, "explain": found.get(rid, [])}
                    for rid in plant["counter_records"]
                },
                "decoys": {
                    rid: {"retrieved": rid in retrieved, "explain": found.get(rid, [])}
                    for rid in plant["decoy_records"]
                },
            }
        )
    return out


def problems(rows: list[dict]) -> list[str]:
    """What breaks the design: a counter-record the retrieval returns, a group 1 counter its
    direction misses, or a group 2 counter any direction lists."""
    out = []
    for r in rows:
        for rid, s in r["counter"].items():
            if s["retrieved"]:
                out.append(f"{r['claim_id']}: counter {rid} is retrieved")
            if r["group"] == 1 and r["direction"] not in s["explain"]:
                out.append(f"{r['claim_id']}: {r['direction']} does not list counter {rid}")
            if r["group"] == 2 and s["explain"]:
                out.append(f"{r['claim_id']}: counter {rid} listed by {s['explain']}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path("eval/out/case03/reach/case03.db"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    conn = build_case("case03", args.db)
    try:
        rows = reach(conn)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            fired = ", ".join(r["directions_fired"]) or "none"
            print(f"{r['claim_id']} group {r['group']}: directions fired: {fired}")
            for field, label in (("counter", "counter"), ("decoys", "decoy")):
                for rid, s in r[field].items():
                    where = "RETRIEVED" if s["retrieved"] else "not retrieved"
                    lists = ", ".join(s["explain"]) or "no direction"
                    print(f"    {label} {rid}: {where}; {lists}")
    issues = problems(rows)
    for line in issues:
        print(f"PROBLEM {line}")
    print(f"case03 reach: {len(issues)} problem(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
