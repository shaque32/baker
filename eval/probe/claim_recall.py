"""Claim proposal recall: does `baker claims propose` find the claims gold lists?

Usage:
  python -m eval.probe.claim_recall --models eval/probe/models.local.json [--n-ctx 4096]
      [--case case01] [--out eval/out/claims]

For each model: a fresh case database holding only the mock affidavit (rendered and ingested
as the eval does), then the product's claim proposal (core/claims/propose.py) on every
paragraph. Each gold claim is matched to at most one proposal from the paragraph gold cites:
the proposal holding the largest share of the gold claim's content words, counted a match
when that share is at least MATCH_AT and every number in the gold text appears in it. Target
90% recall, not gating (Wave 3 plan). The side-by-side table in summary.md is there for a
person to check the matching; a proposal no gold claim matches is listed too (the expert
keeps or removes it).
"""

from __future__ import annotations

import argparse
import gc
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from core.audit._local_model import LazyModel, ModelConfig
from core.claims import extract
from core.claims.propose import load_paragraphs, propose_claims
from core.contracts import Claim, DocKind, GoldClaim, GovDocParagraph
from core.db import apply_schema, connect
from core.ingest.govdoc import PdfGovDocIngester
from core.llm.runtime import sha256_file
from eval import run_pipeline as rp
from eval.run_eval import load_jsonl

MATCH_AT = 0.6
TARGET = 0.90
_WORD = re.compile(r"[a-z0-9@#'+]+")
_DIGITS = re.compile(r"\d+")
STOP = frozenset(
    "a an and are as at be by for from had has he his in is it its of on or that the this "
    "to was were which with".split()
)


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower().replace("’", "'")) if w not in STOP}


def overlap(gold: str, proposed: str) -> float:
    g = words(gold)
    return len(g & words(proposed)) / len(g) if g else 0.0


def numbers_kept(gold: str, proposed: str) -> bool:
    return set(_DIGITS.findall(gold)) <= set(_DIGITS.findall(proposed))


def match(
    gold: list[GoldClaim], proposed: list[Claim], paragraphs: list[GovDocParagraph]
) -> list[dict[str, Any]]:
    """One row per gold claim. Greedy one-to-one: best-scoring pairs are taken first."""
    label = {p.id: (p.page, p.label) for p in paragraphs}
    pairs = []
    for g in gold:
        for i, c in enumerate(proposed):
            page, printed = label.get(c.paragraph_id, (None, None))
            if printed != str(g.para_no):
                continue
            score = overlap(g.text, c.text)
            pairs.append((score, numbers_kept(g.text, c.text), g.claim_id, i))
    pairs.sort(key=lambda t: (-t[0], t[2], t[3]))
    taken_gold: dict[str, tuple[float, bool, int]] = {}
    taken_prop: set[int] = set()
    for score, nums, gid, i in pairs:
        if gid in taken_gold or i in taken_prop:
            continue
        if score >= MATCH_AT and nums:
            taken_gold[gid] = (score, nums, i)
            taken_prop.add(i)
    best_any: dict[str, tuple[float, bool, int]] = {}
    for score, nums, gid, i in pairs:
        best_any.setdefault(gid, (score, nums, i))
    rows = []
    for g in gold:
        hit = taken_gold.get(g.claim_id)
        near = hit or best_any.get(g.claim_id)
        c = proposed[near[2]] if near else None
        rows.append(
            {
                "claim_id": g.claim_id,
                "para_no": g.para_no,
                "gold_text": g.text,
                "gold_type": g.claim_type.value,
                "matched": hit is not None,
                "score": round(near[0], 2) if near else 0.0,
                "numbers_kept": near[1] if near else False,
                "proposal_id": c.id if c else None,
                "proposal_text": c.text if c else None,
                "proposal_type": c.claim_type.value if c else None,
            }
        )
    return rows


def build_doc(case: str, db_path: Path):  # noqa: ANN201 - sqlite3.Connection
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = connect(db_path)
    apply_schema(conn)
    pdf = rp.render_affidavit_pdf(case, db_path.parent / "affidavit.pdf")
    PdfGovDocIngester(DocKind.AFFIDAVIT, clock=rp._clock).ingest(pdf, conn)
    return conn


def recall_for(model: Any, case: str, out: Path) -> dict[str, Any]:
    gold = load_jsonl(Path("eval/gold") / case / "gold.jsonl", GoldClaim)
    conn = build_doc(case, out / f"{case}.db")
    try:
        paragraphs = load_paragraphs(conn)
        extractor = extract.create(conn, model=model)
        start = time.perf_counter()
        result = propose_claims(conn, extractor, paragraphs, clock=rp._clock)
        wall = time.perf_counter() - start
    finally:
        conn.close()
    rows = match(gold, result.claims, paragraphs)
    matched = [r for r in rows if r["matched"]]
    used = {r["proposal_id"] for r in matched}
    return {
        "gold_claims": len(gold),
        "proposed": len(result.claims),
        "dropped": len(result.drops),
        "drop_reasons": [f"{d.paragraph_id}: {d.reason}" for d in result.drops],
        "matched": len(matched),
        "recall": round(len(matched) / len(gold), 3) if gold else None,
        "meets_target": bool(gold) and len(matched) / len(gold) >= TARGET,
        "type_agrees": sum(r["gold_type"] == r["proposal_type"] for r in matched),
        "wall_seconds": round(wall, 1),
        "model_calls": len(extractor.recorder.calls),
        "rows": rows,
        "unmatched_proposals": [
            {"id": c.id, "type": c.claim_type.value, "text": c.text}
            for c in result.claims
            if c.id not in used
        ],
    }


def _cell(text: object) -> str:
    return str(text if text is not None else "").replace("|", "/").replace("\n", " ")


def markdown(case: str, results: list[dict[str, Any]]) -> str:
    lines = [f"# Claim proposal recall, {case} (target {TARGET:.0%}, not gating)", ""]
    lines += [
        "| model | recall | matched | proposed | dropped | type agrees | calls | wall s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['model']} | error: {_cell(r['error'])} | | | | | | |")
            continue
        lines.append(
            f"| {r['model']} | {r['recall']:.0%} | {r['matched']}/{r['gold_claims']} "
            f"| {r['proposed']} | {r['dropped']} | {r['type_agrees']}/{r['matched']} "
            f"| {r['model_calls']} | {r['wall_seconds']} |"
        )
    for r in results:
        if "error" in r:
            continue
        lines += ["", f"## {r['model']}", "", "| gold | match | score | gold text | proposal |"]
        lines += ["|---|---|---|---|---|"]
        for row in r["rows"]:
            lines.append(
                f"| {row['claim_id']} ({row['gold_type']}) | {'yes' if row['matched'] else 'NO'} "
                f"| {row['score']} | {_cell(row['gold_text'])} "
                f"| {_cell(row['proposal_text'])} ({_cell(row['proposal_type'])}) |"
            )
        if r["unmatched_proposals"]:
            lines += ["", "Proposals no gold claim matched:"]
            lines += [f"- {u['id']} ({u['type']}): {u['text']}" for u in r["unmatched_proposals"]]
        if r["drop_reasons"]:
            lines += ["", "Dropped proposals:"] + [f"- {d}" for d in r["drop_reasons"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", type=Path, required=True, help="the probe's models.local.json")
    ap.add_argument("--case", default="case01")
    ap.add_argument("--n-ctx", type=int, default=None)
    ap.add_argument("--out", type=Path, default=Path("eval/out/claims"))
    args = ap.parse_args(argv)

    results = []
    for entry in json.loads(args.models.read_text(encoding="utf-8")):
        name = entry["name"]
        try:
            path = Path(entry["path"]).expanduser()
            sha = entry.get("sha256") or sha256_file(path)
            model = LazyModel(ModelConfig(name=name, path=path, sha256=sha, n_ctx=args.n_ctx))
            res = {"model": name, **recall_for(model, args.case, args.out / name)}
        except Exception as e:  # noqa: BLE001 - report and move on to the next model
            res = {"model": name, "error": f"{type(e).__name__}: {e}"}
        results.append(res)
        gc.collect()  # free one model's weights before the next loads
        print(f"{name}: recall {res.get('recall')}", file=sys.stderr)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md = markdown(args.case, results)
    (args.out / "summary.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
