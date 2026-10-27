"""Where a run loses each claim's signed key evidence. Eval only, no model, read-only.

Usage: python -m eval.loss_report --db <case.db> [--gold eval/gold/case01/gold.jsonl]
                                  [--model-run <model_runs.id>] [--json <out.json>]

Reads a finished run's case database (opened read-only) and the signed gold key, and puts
every gold key record at exactly one stage, the furthest it reached on any assumption of its
claim:

  refused              the claim has no assumptions, so nothing about it was tested
  not_retrieved        no assumption of the claim sent the record to the stance step. Split
                       into "settled by a failed core check" (retrieval is skipped for such a
                       claim by design, core/pipeline.py) and "retrieval missed"
  labelled_irrelevant  the stance step labelled it irrelevant on every assumption it saw
  invalid_output       the stance step's output was unusable (wrong shape, or an error)
  quote_dropped        the stance step gave a real label but the quote check dropped it
  surfaced             it became an evidence item the expert can accept

It also splits the run's dropped labels by reason, from the stored model calls
(model_calls.outcome plus the stance in raw_output). An irrelevant label carries no quote, so
the pipeline drops it at the quote check and stores the call as quote_failed: that is a stance
outcome, not a quote failure, and it is counted as "irrelevant" here. "quote_failed" counts
only real labels (supports, contradicts, complicates) whose quote did not verify.

The stance step is one model run. Every retrieved candidate is labelled (core/pipeline.py), so
the call subjects (assumption id, record id) are what retrieval returned for the claims the run
labelled. A database with more than one stance model run needs --model-run.

For a hidden case (case.json beside the gold says "hidden"), only aggregate counts are printed
and written: no claim or record ids.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from core.contracts import GoldClaim
from eval.run_eval import load_jsonl

VERSION = "1.0.0"

STAGES = (
    "refused",
    "not_retrieved",
    "labelled_irrelevant",
    "invalid_output",
    "quote_dropped",
    "surfaced",
)
# How far a record got on one assumption, for picking its furthest stage across assumptions.
_RANK = {"labelled_irrelevant": 0, "invalid_output": 1, "quote_dropped": 2, "surfaced": 3}
DROP_REASONS = ("irrelevant", "quote_failed", "invalid_output", "error")
SETTLED = "settled by a failed core check"
MISSED = "retrieval missed"


@dataclass
class KeyRecord:
    claim_id: str
    record_id: str
    stage: str
    detail: str = ""
    stances: tuple[str, ...] = ()  # labels of surfaced items, for a wrong-direction check


@dataclass
class LossReport:
    model_run_id: str
    key: list[KeyRecord] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)
    stored_irrelevant: int = 0
    stored: int = 0

    def stage_counts(self) -> dict[str, int]:
        c = Counter(k.stage for k in self.key)
        return {s: c.get(s, 0) for s in STAGES}

    def not_retrieved_split(self) -> dict[str, int]:
        c = Counter(k.detail for k in self.key if k.stage == "not_retrieved")
        return {SETTLED: c.get(SETTLED, 0), MISSED: c.get(MISSED, 0)}

    def main_leak(self) -> str:
        """Which of the two later steps loses more key records the stance step saw."""
        s = self.stage_counts()
        stance_loss = s["labelled_irrelevant"] + s["invalid_output"]
        quote_loss = s["quote_dropped"]
        if stance_loss == quote_loss == 0:
            return "neither: every key record the stance step saw was surfaced"
        if stance_loss > quote_loss:
            return f"stance step ({stance_loss} key records vs {quote_loss} at the quote check)"
        if quote_loss > stance_loss:
            return f"quote check ({quote_loss} key records vs {stance_loss} at the stance step)"
        return f"tied ({stance_loss} at the stance step, {quote_loss} at the quote check)"

    def as_dict(self, hidden: bool) -> dict[str, object]:
        out: dict[str, object] = {
            "loss_report": VERSION,
            "model_run_id": self.model_run_id,
            "key_records": len(self.key),
            "stages": self.stage_counts(),
            "not_retrieved": self.not_retrieved_split(),
            "main_leak": self.main_leak(),
            "dropped_labels": sum(self.dropped.values()),
            "dropped_by_reason": {r: self.dropped.get(r, 0) for r in DROP_REASONS},
            "stored_items": self.stored,
            "stored_irrelevant": self.stored_irrelevant,
        }
        if not hidden:
            out["per_record"] = [
                {
                    "claim_id": k.claim_id,
                    "record_id": k.record_id,
                    "stage": k.stage,
                    "detail": k.detail,
                    "stances": list(k.stances),
                }
                for k in self.key
            ]
        return out


def open_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(path)
    return sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)


def stance_run(conn: sqlite3.Connection, model_run_id: str | None = None) -> str:
    runs = [r[0] for r in conn.execute("SELECT id FROM model_runs WHERE purpose = 'stance'")]
    if model_run_id is not None:
        if model_run_id not in runs:
            raise SystemExit(f"no stance model run {model_run_id!r}; stance runs: {runs}")
        return model_run_id
    if not runs:
        raise SystemExit("no stance model run in this database (a model-free run records none)")
    if len(runs) > 1:
        raise SystemExit(f"{len(runs)} stance model runs; pick one with --model-run: {runs}")
    return runs[0]


def _raw_stance(raw: str) -> str | None:
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return None
    s = obj.get("stance") if isinstance(obj, dict) else None
    return s if isinstance(s, str) else None


def _pair_outcome(outcome: str, stance: str | None) -> str:
    """One labelled pair's outcome: 'stored' or a DROP_REASONS entry."""
    if outcome == "ok":
        return "stored"
    if outcome == "quote_failed":
        return "irrelevant" if stance == "irrelevant" else "quote_failed"
    return "invalid_output" if outcome == "invalid_output" else "error"


def build(
    conn: sqlite3.Connection, gold: list[GoldClaim], model_run_id: str | None = None
) -> LossReport:
    run = stance_run(conn, model_run_id)
    report = LossReport(model_run_id=run)

    claim_of: dict[str, str] = {}
    assumptions: dict[str, list[str]] = defaultdict(list)
    for aid, cid in conn.execute("SELECT id, claim_id FROM assumptions"):
        claim_of[aid] = cid
        assumptions[cid].append(aid)
    failed_core = {
        claim_of[aid]
        for (aid,) in conn.execute(
            "SELECT c.assumption_id FROM check_results c JOIN assumptions a"
            " ON a.id = c.assumption_id WHERE c.outcome = 'fail' AND a.is_core = 1"
        )
    }

    # The last call per (assumption, record) is the label the pipeline kept or dropped.
    last: dict[tuple[str, str], tuple[str, str | None]] = {}
    for subject, raw, outcome in conn.execute(
        "SELECT subject_json, raw_output, outcome FROM model_calls WHERE model_run_id = ?"
        " ORDER BY seq",
        (run,),
    ):
        ids = json.loads(subject)
        if len(ids) < 2:
            continue
        last[(ids[0], ids[1])] = (outcome, _raw_stance(raw))

    pair: dict[tuple[str, str], str] = {}
    for (aid, rid), (outcome, stance) in last.items():
        result = _pair_outcome(outcome, stance)
        pair[(aid, rid)] = result
        if result != "stored":
            report.dropped[result] += 1

    shown: dict[tuple[str, str], list[str]] = defaultdict(list)
    for aid, rid, stance in conn.execute(
        "SELECT assumption_id, record_id, stance FROM evidence_items WHERE model_run_id = ?",
        (run,),
    ):
        report.stored += 1
        if stance == "irrelevant":
            report.stored_irrelevant += 1
        else:
            shown[(aid, rid)].append(stance)

    labelled_claims = {claim_of.get(aid) for aid, _ in pair}
    for g in sorted(gold, key=lambda g: g.claim_id):
        for rid in sorted(set(g.key_evidence)):
            report.key.append(
                _stage(g.claim_id, rid, assumptions[g.claim_id], pair, shown,
                       labelled=g.claim_id in labelled_claims,
                       settled=g.claim_id in failed_core)
            )  # fmt: skip
    return report


def _stage(
    claim_id: str,
    rid: str,
    aids: list[str],
    pair: dict[tuple[str, str], str],
    shown: dict[tuple[str, str], list[str]],
    *,
    labelled: bool,
    settled: bool,
) -> KeyRecord:
    if not aids:
        return KeyRecord(claim_id, rid, "refused", "no assumptions")
    best: str | None = None
    stances: list[str] = []
    for aid in aids:
        if shown.get((aid, rid)):
            stances.extend(shown[(aid, rid)])
            here = "surfaced"
        elif (aid, rid) in pair:
            here = {
                "irrelevant": "labelled_irrelevant",
                "quote_failed": "quote_dropped",
                "invalid_output": "invalid_output",
                "error": "invalid_output",
                "stored": "labelled_irrelevant",  # stored, but as an irrelevant item
            }[pair[(aid, rid)]]
        else:
            continue
        if best is None or _RANK[here] > _RANK[best]:
            best = here
    if best is None:
        detail = SETTLED if settled and not labelled else MISSED
        return KeyRecord(claim_id, rid, "not_retrieved", detail)
    return KeyRecord(claim_id, rid, best, stances=tuple(sorted(set(stances))))


def is_hidden(gold_path: Path) -> bool:
    meta = gold_path.parent / "case.json"
    if not meta.exists():
        return False
    return bool(json.loads(meta.read_text(encoding="utf-8")).get("hidden"))


def render(report: LossReport, hidden: bool) -> str:
    s = report.stage_counts()
    n = len(report.key)
    split = report.not_retrieved_split()
    lines = [
        f"Loss report {VERSION}, stance model run {report.model_run_id}",
        f"Main leak: {report.main_leak()}",
        "",
        "| stage | key records |",
        "|---|---|",
    ]
    for stage in STAGES:
        extra = ""
        if stage == "not_retrieved" and s[stage]:
            extra = f" ({split[SETTLED]} {SETTLED}, {split[MISSED]} {MISSED})"
        lines.append(f"| {stage} | {s[stage]} of {n}{extra} |")
    d = report.dropped
    lines += [
        "",
        f"Dropped labels: {sum(d.values())}: "
        + ", ".join(f"{r} {d.get(r, 0)}" for r in DROP_REASONS),
        f"Stored items: {report.stored} ({report.stored_irrelevant} labelled irrelevant)",
    ]
    if not hidden:
        lost = [k for k in report.key if k.stage != "surfaced"]
        if lost:
            lines += ["", "| claim | key record | stage | detail |", "|---|---|---|---|"]
            lines += [f"| {k.claim_id} | {k.record_id} | {k.stage} | {k.detail} |" for k in lost]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--gold", type=Path, default=Path("eval/gold/case01/gold.jsonl"))
    p.add_argument("--model-run")
    p.add_argument("--json", type=Path)
    args = p.parse_args(argv)
    gold = load_jsonl(args.gold, GoldClaim)
    if not gold:
        print(f"no gold rows in {args.gold}", file=sys.stderr)
        return 2
    hidden = is_hidden(args.gold)
    conn = open_readonly(args.db)
    try:
        report = build(conn, gold, args.model_run)
    finally:
        conn.close()
    print(render(report, hidden))
    if args.json:
        args.json.write_text(json.dumps(report.as_dict(hidden), indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
