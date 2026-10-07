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
  hostile the product's structure (assumptions, checks, retrieval, rules) with the red-team
         worst-case model from eval/adversarial/hostile_model.py: every record is labeled
         support and every item is accepted. Fails if any claim the structure must block
         (eval/adversarial/structural_blocks.STRUCTURAL) comes out SUPPORTED. Claims only the
         real reviewer can stop (MODEL_ONLY) are counted and reported, not gated.
  --reviewer none   every supporting item is dismissed, so nothing can be SUPPORTED. Shows what
                    the pipeline does without the AI reviewer.
  --assumption-spec PATH   fill assumptions from a signed spec instead of the model: JSONL,
                    one {"claim_id", "template_id", "params", "is_core"} per line. The
                    template builder (core/audit/assumptions.py) validates every entry.
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


def spec_filler(path: Path):  # noqa: ANN201 - core.audit.assumptions.Filler
    """A filler that proposes exactly the assumptions a signed spec lists for each claim."""
    from core.audit.assumptions import Proposal

    by_claim: dict[str, list] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            by_claim.setdefault(row["claim_id"], []).append(
                Proposal(row["template_id"], row["params"], row.get("is_core", True))
            )

    def filler(claim, allowed):  # noqa: ANN001, ANN202
        return by_claim.get(claim.id, [])

    return filler


def hostile_components(conn, filler=None) -> pipeline.Components:  # noqa: ANN001
    """Real structure, worst-case model. Adapts the red-team reviewer to contracts v0.2."""
    from core.contracts import ModelRun, ReviewDecision, ReviewerKind, review_id

    try:
        from eval.adversarial.hostile_model import (
            HOSTILE_RUN_ID,
            HostileLabeler,
            HostileReviewer,
        )
    except ModuleNotFoundError as e:
        raise pipeline.ComponentsMissing(f"red-team model not merged yet ({e.name})") from e

    run = ModelRun(
        id=HOSTILE_RUN_ID,
        purpose="stance",
        model_name="hostile",
        model_sha256="0" * 64,
        prompt_version="none",
        params={"red_team": True},
        seed=0,
        started_at_utc=EVAL_TIME,
    )

    class Reviewer:
        model_run_id = HOSTILE_RUN_ID

        def review(self, assumption, item, context):  # noqa: ANN001, ANN201
            out = HostileReviewer().review(assumption, item, context)
            if isinstance(out, ReviewDecision):
                return out
            return ReviewDecision(
                id=review_id(item.id, 1),
                evidence_id=item.id,
                seq=1,
                reviewer_kind=ReviewerKind.AI,
                reviewer="ai:hostile",
                status=out,
                reason="Red-team reviewer: accepts everything.",
                model_run_id=HOSTILE_RUN_ID,
                decided_at_utc=EVAL_TIME,
            )

    comps = pipeline.real_components(
        conn, replace={"labeler": HostileLabeler(), "reviewer": Reviewer()}, filler=filler
    )
    comps.model_runs = (*comps.model_runs, run)
    return comps


def hostile_gate(preds: list[Prediction]) -> int:
    from eval.adversarial.structural_blocks import MODEL_ONLY, STRUCTURAL

    supported = {p.claim_id for p in preds if p.verdict.value == "supported"}
    breached = sorted(supported & set(STRUCTURAL))
    exposed = sorted(supported & set(MODEL_ONLY))
    print(
        f"hostile: {len(exposed)}/{len(MODEL_ONLY)} model-only claims went supported "
        f"(reported, not gated): {exposed}"
    )
    if breached:
        print(f"hostile: FAIL, the structure let these through as supported: {breached}")
        return 1
    print(f"hostile: PASS, none of the {len(STRUCTURAL)} structural claims went supported")
    return 0


def run_once(
    case: str, mode: str, reviewer: str, out: Path, spec: Path | None = None
) -> list[Prediction]:
    conn = build_case(case, out / f"{case}.db")
    try:
        if mode == "fake":
            from eval.pipeline_fakes import fake_components

            comps = fake_components(accept=reviewer == "accept")
        elif mode == "hostile":
            comps = hostile_components(conn, spec_filler(spec) if spec else None)
        else:
            comps = pipeline.real_components(conn, filler=spec_filler(spec) if spec else None)
            if reviewer == "none":
                from eval.pipeline_fakes import FakeReviewer

                comps.reviewer = FakeReviewer(accept=False)
        result = pipeline.run_audit(
            conn,
            comps,
            clock=_clock,
            config={"eval_mode": mode, "reviewer": reviewer, "assumption_spec": str(spec)},
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
    parser.add_argument("--mode", choices=("fake", "real", "hostile"), default="fake")
    parser.add_argument("--reviewer", choices=("accept", "none"), default="accept")
    parser.add_argument("--assumption-spec", type=Path, default=None)
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    out = args.out
    if out is None:
        out = Path("eval/out") / args.case
        if args.mode in ("fake", "hostile"):
            out = out / args.mode
        if args.reviewer == "none":
            out = out / "no_reviewer"
    try:
        first = run_once(args.case, args.mode, args.reviewer, out, args.assumption_spec)
        if args.repeat:
            second = run_once(
                args.case, args.mode, args.reviewer, out / "repeat", args.assumption_spec
            )
            if first != second:
                print("pipeline: FAIL, a repeat run gave different predictions")
                return 1
            print("pipeline: repeat run gave identical predictions")
        if args.mode == "hostile":
            return hostile_gate(first)
    except pipeline.ComponentsMissing as e:
        print(f"pipeline: real components {e}")
        return 2
    print(f"pipeline: wrote {out}/predictions.jsonl and {out}/report.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
