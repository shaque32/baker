"""Validation card: a scored run's error rates, each with its Wilson 95% interval.

Usage: python -m eval.validation.card --gold <gold.jsonl> --predictions <predictions.jsonl>
           [--db <case.db> [--run <pipeline_run_id>]] [--run-json <run.json>] [--out <dir>]

The merge gate (eval/run_eval.py) asks "did this run pass?". The card asks "how far can these
numbers be trusted?": every rate comes with its count, its denominator and its interval, so 0
false supported out of 12 reads as "up to 24%", not as "0%".

- False supported: predicted SUPPORTED where gold is not SUPPORTED.
- False contradicted: predicted CONTRADICTED where gold is not CONTRADICTED.
- With --db, each false contradicted is attributed to what decided it (a failed check, by check
  name, or expert-accepted evidence), and each check type gets an outcome table. Gold is signed
  per claim, not per assumption, so the check table is a claim-level attribution: "failed on a
  claim gold does not call contradicted" is a lead to inspect, not a counted check error.

Report only: the card never gates and never changes a threshold.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.contracts import GoldClaim, Prediction, Verdict
from eval.run_eval import load_jsonl

Z95 = 1.96


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k/n; None when there is nothing to divide by."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def rate(k: int, n: int) -> dict[str, Any]:
    ci = wilson(k, n)
    return {
        "k": k,
        "n": n,
        "rate": k / n if n else None,
        "ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
    }


def claims_for_upper_bound(target: float, z: float = Z95) -> int:
    """Fewest claims with zero errors whose Wilson upper bound is at or under target."""
    # With k = 0 the upper bound is z^2 / (n + z^2).
    n = 1
    while z * z / (n + z * z) > target:
        n += 1
    return n


@dataclass(frozen=True)
class RunVerdict:
    """What decided one claim's verdict in a stored run (from the verdicts table)."""

    claim_id: str
    verdict: str
    checks: tuple[str, ...]  # names of the checks the verdict cites, e.g. ("absence",)
    evidence: int  # cited evidence items
    overridden: bool  # the expert set the verdict directly


def check_name(check_id: str) -> str:
    """'chk:<assumption_id>|<check_name>@<check_version>' -> check_name."""
    return check_id.rsplit("|", 1)[-1].split("@", 1)[0]


def contradicted_basis(v: RunVerdict) -> str:
    if v.overridden:
        return "expert override"
    if v.checks:
        return "failed check: " + "+".join(sorted(set(v.checks)))
    if v.evidence:
        return "expert-accepted evidence"
    return "unknown"


def _open_ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)


def _verdicts(conn: sqlite3.Connection, run_id: str) -> dict[str, RunVerdict]:
    out: dict[str, RunVerdict] = {}
    rows = conn.execute(
        "SELECT claim_id, verdict, cited_json, override_note FROM verdicts"
        " WHERE pipeline_run_id = ?",
        (run_id,),
    )
    for claim_id, verdict, cited_json, override_note in rows:
        cited = json.loads(cited_json)
        out[claim_id] = RunVerdict(
            claim_id=claim_id,
            verdict=verdict,
            checks=tuple(check_name(c) for c in cited.get("checks", [])),
            evidence=len(cited.get("evidence", [])),
            overridden=override_note is not None,
        )
    return out


def pick_run(conn: sqlite3.Connection, predictions: list[Prediction]) -> str:
    """The newest run whose verdicts equal the predictions on every predicted claim."""
    want = {p.claim_id: p.verdict.value for p in predictions}
    runs = conn.execute("SELECT id FROM pipeline_runs ORDER BY started_at_utc DESC, id DESC")
    for (run_id,) in runs.fetchall():
        got = _verdicts(conn, run_id)
        if want and all(c in got and got[c].verdict == v for c, v in want.items()):
            return run_id
    raise SystemExit("card: no run in the database matches the predictions; pass --run")


def load_run(db: Path, predictions: list[Prediction], run_id: str | None) -> tuple[str, dict]:
    with _open_ro(db) as conn:
        rid = run_id or pick_run(conn, predictions)
        return rid, _verdicts(conn, rid)


def load_checks(db: Path, claim_ids: Iterable[str]) -> list[tuple[str, str, str]]:
    """(claim_id, check_name, outcome) for every check on a core assumption of these claims."""
    wanted = set(claim_ids)
    with _open_ro(db) as conn:
        rows = conn.execute(
            "SELECT a.claim_id, r.check_name, r.outcome FROM check_results r"
            " JOIN assumptions a ON a.id = r.assumption_id WHERE a.is_core = 1"
            " ORDER BY a.claim_id, r.id"
        ).fetchall()
    return [(c, n, o) for c, n, o in rows if c in wanted]


def build_card(
    gold: list[GoldClaim],
    predictions: list[Prediction],
    run: dict[str, RunVerdict] | None = None,
    checks: list[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    ids = [g.claim_id for g in gold]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate claim_id in gold")
    by_id = {p.claim_id: p for p in predictions}
    gold_by_id = {g.claim_id: g for g in gold}

    correct = not_supported = fs = not_contradicted = fc = 0
    gold_contra = missed_contra = gold_supported = missed_supported = 0
    fs_basis: Counter[str] = Counter()
    fc_basis: Counter[str] = Counter()
    per_type: dict[str, Counter[str]] = {}
    for g in gold:
        pred = by_id.get(g.claim_id)
        got = pred.verdict if pred else None
        t = per_type.setdefault(g.claim_type.value, Counter())
        t["n"] += 1
        if got == g.gold_verdict:
            correct += 1
            t["correct"] += 1
        if g.gold_verdict != Verdict.SUPPORTED:
            not_supported += 1
            t["not_supported"] += 1
            if got == Verdict.SUPPORTED:
                fs += 1
                t["false_supported"] += 1
                basis = pred.supported_basis.value if pred and pred.supported_basis else "unknown"
                fs_basis[basis] += 1
        else:
            gold_supported += 1
            if got != Verdict.SUPPORTED:
                missed_supported += 1
        if g.gold_verdict != Verdict.CONTRADICTED:
            not_contradicted += 1
            t["not_contradicted"] += 1
            if got == Verdict.CONTRADICTED:
                fc += 1
                t["false_contradicted"] += 1
                rv = run.get(g.claim_id) if run is not None else None
                fc_basis[contradicted_basis(rv) if rv else "unknown"] += 1
        else:
            gold_contra += 1
            if got != Verdict.CONTRADICTED:
                missed_contra += 1

    check_table: dict[str, Counter[str]] = {}
    for claim_id, name, outcome in checks or []:
        g = gold_by_id.get(claim_id)
        if g is None:
            continue
        row = check_table.setdefault(name, Counter())
        row[outcome] += 1
        if outcome == "fail" and g.gold_verdict != Verdict.CONTRADICTED:
            row["fail_on_claim_gold_not_contradicted"] += 1
        if outcome == "pass" and g.gold_verdict == Verdict.CONTRADICTED:
            row["pass_on_claim_gold_contradicted"] += 1

    return {
        "claims": len(gold),
        "predicted": sum(1 for g in gold if g.claim_id in by_id),
        "accuracy": rate(correct, len(gold)),
        "false_supported": rate(fs, not_supported) | {"by_basis": dict(fs_basis)},
        "false_contradicted": rate(fc, not_contradicted) | {"by_basis": dict(fc_basis)},
        "missed_contradicted": rate(missed_contra, gold_contra),
        "missed_supported": rate(missed_supported, gold_supported),
        "by_claim_type": {
            name: {
                "n": c["n"],
                "accuracy": rate(c["correct"], c["n"]),
                "false_supported": rate(c["false_supported"], c["not_supported"]),
                "false_contradicted": rate(c["false_contradicted"], c["not_contradicted"]),
            }
            for name, c in sorted(per_type.items())
        },
        "checks": {name: dict(sorted(c.items())) for name, c in sorted(check_table.items())}
        if checks is not None
        else None,
        "claims_for_zero_error_upper_bound": {
            "5%": claims_for_upper_bound(0.05),
            "2%": claims_for_upper_bound(0.02),
            "1%": claims_for_upper_bound(0.01),
        },
    }


def _fmt(r: dict[str, Any]) -> str:
    """'0 of 12 (0%) [0-24%]'."""
    if r["rate"] is None:
        return f"{r['k']} of {r['n']}"
    lo, hi = r["ci95"]
    return f"{r['k']} of {r['n']} ({r['rate']:.0%}) [{lo:.0%}-{hi:.0%}]"


def render_markdown(card: dict[str, Any]) -> str:
    inputs = card.get("inputs", {})
    lines = ["# Validation card", ""]
    for key in ("gold", "gold_status", "predictions", "db", "run", "versions"):
        if key in inputs:
            value = inputs[key]
            if isinstance(value, dict):
                value = json.dumps(value, sort_keys=True)
            lines.append(f"- {key.replace('_', ' ').capitalize()}: `{value}`")
    lines += [
        "",
        "Rates are k of n (rate) [Wilson 95% interval]. Report only: nothing here gates.",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Verdict accuracy | {_fmt(card['accuracy'])} |",
        f"| False supported (gold not supported) | {_fmt(card['false_supported'])} |",
        f"| False contradicted (gold not contradicted) | {_fmt(card['false_contradicted'])} |",
        f"| Missed contradiction (gold contradicted) | {_fmt(card['missed_contradicted'])} |",
        f"| Missed support (gold supported) | {_fmt(card['missed_supported'])} |",
    ]
    for label, key in (
        ("False supported", "false_supported"),
        ("False contradicted", "false_contradicted"),
    ):
        basis = card[key]["by_basis"]
        if basis:
            parts = ", ".join(f"{b}: {n}" for b, n in sorted(basis.items()))
            lines += ["", f"{label} by what decided it: {parts}."]
    need = card["claims_for_zero_error_upper_bound"]
    lines += [
        "",
        "Claims needed, with zero errors, for the upper bound to reach 5% / 2% / 1%: "
        f"{need['5%']} / {need['2%']} / {need['1%']}.",
        "",
        "## By claim type",
        "",
        "| Claim type | n | Accuracy | False supported | False contradicted |",
        "|---|---|---|---|---|",
    ]
    for name, row in card["by_claim_type"].items():
        lines.append(
            f"| {name} | {row['n']} | {_fmt(row['accuracy'])} | "
            f"{_fmt(row['false_supported'])} | {_fmt(row['false_contradicted'])} |"
        )
    if card["checks"] is not None:
        lines += [
            "",
            "## Checks on core assumptions",
            "",
            "Claim-level attribution: gold is signed per claim, so a check that failed on a claim"
            " gold does not call contradicted is a lead to inspect, not a counted error.",
            "",
            "| Check | pass | fail | inconclusive | fail, claim not contradicted |"
            " pass, claim contradicted |",
            "|---|---|---|---|---|---|",
        ]
        for name, row in card["checks"].items():
            lines.append(
                f"| {name} | {row.get('pass', 0)} | {row.get('fail', 0)} | "
                f"{row.get('inconclusive', 0)} | "
                f"{row.get('fail_on_claim_gold_not_contradicted', 0)} | "
                f"{row.get('pass_on_claim_gold_contradicted', 0)} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--run", default=None, help="pipeline run id (default: matched)")
    parser.add_argument("--run-json", type=Path, default=None, help="the eval's run.json")
    parser.add_argument("--out", type=Path, default=None, help="write card.json and card.md")
    args = parser.parse_args(argv)

    gold = load_jsonl(args.gold, GoldClaim)
    predictions = load_jsonl(args.predictions, Prediction)
    if not gold:
        print(f"card: {args.gold} holds no gold claims")
        return 1
    drafts = sum(1 for g in gold if g.labeled_by.upper().startswith("DRAFT"))

    run = checks = None
    run_id = None
    if args.db is not None:
        run_id, run = load_run(args.db, predictions, args.run)
        checks = load_checks(args.db, (g.claim_id for g in gold))
    card = build_card(gold, predictions, run, checks)
    card["inputs"] = {
        "gold": str(args.gold),
        "gold_status": f"DRAFT ({drafts} of {len(gold)} unsigned)" if drafts else "signed",
        "predictions": str(args.predictions),
    }
    if args.db is not None:
        card["inputs"] |= {"db": str(args.db), "run": run_id}
    if args.run_json is not None:
        card["inputs"]["versions"] = json.loads(args.run_json.read_text("utf-8")).get("versions")

    md = render_markdown(card)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "card.json").write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
        (args.out / "card.md").write_text(md, encoding="utf-8")
    print(md, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
