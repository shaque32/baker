"""Run the full pipeline on a synthetic case and write predictions and the report.

Usage: python -m eval.run_pipeline [--case case01] [--mode fake|real] [--reviewer accept|none]
                                   [--repeat] [--out DIR]

Steps, all through the product's own code:
1. Rebuild the synthetic reports if they are missing (`make synth` does the same).
2. Import each report with the Cellebrite importer and check its SHA-256 against case.json.
3. Render the mock affidavit to PDF and import it with the govdoc ingester.
4. Enter the gold claims as expert-entered claims (the "gold claims" eval mode: claim
   extraction is scored separately and does not gate the alpha).
5. Record the device-ownership stipulation from case.json.
6. Run the audit, then write predictions.jsonl and report.html.

Modes:
  fake   the eval stand-ins from eval/pipeline_fakes.py; output in eval/out/<case>/fake/.
         Not gated: the numbers only show the wiring works.
  real   the product components (core.pipeline.real_components); output in eval/out/<case>/,
         which is what `make eval` gates on.
  --reviewer none   every supporting item is dismissed, so nothing can be SUPPORTED. Shows what
                    the pipeline does without the AI reviewer.
  --repeat          run twice on fresh databases and fail unless the predictions are identical.

case02 is the hidden test case: this script can run it, but builders never tune against it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from core import pipeline
from core.contracts import ClaimType, DocKind, GoldClaim, GovDocParagraph, Prediction
from core.db import apply_schema, connect
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.govdoc import PdfGovDocIngester
from core.report.html import write_report
from core.review import actions
from eval.run_eval import load_jsonl

EVAL_TIME = datetime(2026, 10, 7, tzinfo=UTC)  # fixed, so runs are byte-for-byte repeatable
GOLD_ACTOR = "expert:eval-gold-claims"
STIPULATION_ACTOR = "expert:eval-case-stipulation"


def _clock() -> datetime:
    return EVAL_TIME


def synthetic_dir(case: str) -> Path:
    return Path("eval/synthetic") / case


def ensure_reports(case: str) -> dict:
    meta = json.loads((synthetic_dir(case) / "case.json").read_text(encoding="utf-8"))
    missing = [s for s in meta["sources"] if not (synthetic_dir(case) / s["file"]).exists()]
    if missing:
        if case != "case01":
            raise SystemExit(f"{case}: reports missing; build them with that case's generator")
        from eval.synthetic.generate import generate

        generate(synthetic_dir(case), None)
    return meta


def render_affidavit_pdf(case: str, path: Path) -> Path:
    """The case's mock affidavit as a PDF, laid out like the govdoc fixtures."""
    if case != "case01":
        raise SystemExit(f"{case}: no affidavit renderer")
    from eval.synthetic import govdocs as g
    from eval.synthetic.generate import affidavit_paragraphs

    pages: list[list[tuple[float, float, str]]] = [[]]
    y = g.TOP
    page_no = 1
    heading = g.Para("AFFIDAVIT (SYNTHETIC CASE01, NOT A REAL CASE)", heading=True)
    for x, text in g._lines(heading):
        pages[-1].append((x, y, text))
        y += g.LEADING
    y += g.PARA_GAP
    for page, no, text in affidavit_paragraphs():
        if page != page_no and pages[-1]:
            pages.append([])
            y = g.TOP
            page_no = page
        for x, line in g._lines(g.Para(text, no)):
            if y > g.BOTTOM:
                pages.append([])
                y = g.TOP
            pages[-1].append((x, y, line))
            y += g.LEADING
        y += g.PARA_GAP
    path.parent.mkdir(parents=True, exist_ok=True)
    g._write(pages, path, "AFFIDAVIT (SYNTHETIC CASE01)")
    return path


def paragraph_for(paragraphs: list[GovDocParagraph], gold: GoldClaim) -> GovDocParagraph:
    """Gold cites the printed paragraph number. Prefer the page gold names."""
    hits = [p for p in paragraphs if p.label == str(gold.para_no)]
    if not hits:
        raise SystemExit(f"{gold.claim_id}: no paragraph printed as {gold.para_no}")
    on_page = [p for p in hits if p.page == gold.page]
    return (on_page or hits)[0]


def build_case(case: str, db_path: Path) -> object:
    meta = ensure_reports(case)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = connect(db_path)
    apply_schema(conn)
    for s in meta["sources"]:
        src = CellebriteExcelImporter(source_id=s["source_id"], now=EVAL_TIME).import_source(
            synthetic_dir(case) / s["file"], conn
        )
        if src.sha256 != s["sha256"]:
            raise SystemExit(f"{s['file']}: SHA-256 {src.sha256} does not match case.json")
    pdf = render_affidavit_pdf(case, db_path.parent / "affidavit.pdf")
    _, paragraphs = PdfGovDocIngester(DocKind.AFFIDAVIT, clock=_clock).ingest(pdf, conn)

    gold = load_jsonl(Path("eval/gold") / case / "gold.jsonl", GoldClaim)
    for gc in gold:
        para = paragraph_for(paragraphs, gc)
        actions.add_claim(
            conn, gc.claim_id, para.id, gc.text, ClaimType(gc.claim_type), GOLD_ACTOR, _clock
        )
    for d in meta["devices"]:
        actions.stipulate_device_owner(
            conn, f"dev:{d['source_id']}", d["owner"], STIPULATION_ACTOR, _clock
        )
    return conn


def run_once(case: str, mode: str, reviewer: str, out: Path) -> list[Prediction]:
    conn = build_case(case, out / f"{case}.db")
    try:
        if mode == "fake":
            from eval.pipeline_fakes import fake_components

            comps = fake_components(accept=reviewer == "accept")
        else:
            comps = pipeline.real_components(conn)
            if reviewer == "none":
                from eval.pipeline_fakes import FakeReviewer

                comps.reviewer = FakeReviewer(accept=False)
        result = pipeline.run_audit(
            conn, comps, clock=_clock, config={"eval_mode": mode, "reviewer": reviewer}
        )
        preds = pipeline.predictions(conn)
        (out / "predictions.jsonl").write_text(
            "".join(p.model_dump_json() + "\n" for p in preds), encoding="utf-8"
        )
        write_report(conn, out / "report.html")
        summary = {
            "case": case,
            "mode": mode,
            "reviewer": reviewer,
            "fake": result.fake,
            "claims": len(result.decisions),
            "stored_items": result.stored_items,
            "dropped_labels": result.dropped_labels,
            "reviewer_failures": result.reviewer_failures,
        }
        (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("pipeline: " + json.dumps(summary))
        return preds
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="case01")
    parser.add_argument("--mode", choices=("fake", "real"), default="fake")
    parser.add_argument("--reviewer", choices=("accept", "none"), default="accept")
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    out = args.out
    if out is None:
        out = Path("eval/out") / args.case
        if args.mode == "fake":
            out = out / "fake"
        if args.reviewer == "none":
            out = out / "no_reviewer"
    try:
        first = run_once(args.case, args.mode, args.reviewer, out)
        if args.repeat:
            second = run_once(args.case, args.mode, args.reviewer, out / "repeat")
            if first != second:
                print("pipeline: FAIL, a repeat run gave different predictions")
                return 1
            print("pipeline: repeat run gave identical predictions")
    except pipeline.ComponentsMissing as e:
        print(f"pipeline: real components {e}")
        return 2
    print(f"pipeline: wrote {out}/predictions.jsonl and {out}/report.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
