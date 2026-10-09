"""Run the full pipeline on a synthetic case and write predictions and the report.

Usage: python -m eval.run_pipeline [--case case01] [--mode model-free|real|fake|hostile]
                                   [--expert simulated|none] [--reviewer accept|none]
                                   [--assumption-spec PATH] [--repeat] [--out DIR]

Steps, all through the product's own code:
1. Rebuild the synthetic reports if they are missing (`make synth` does the same).
2. Import each report with the Cellebrite importer and check its SHA-256 against case.json.
3. Render the mock affidavit to PDF and import it with the govdoc ingester.
4. Enter the gold claims as expert-entered claims (the "gold claims" eval mode: claim
   extraction is scored separately and does not gate the alpha).
5. Record the device-ownership stipulation from case.json.
6. Run the audit, then write predictions.jsonl and report.html.
   With the simulated expert (eval/simulated_expert.py), the first pass is the unreviewed run
   (written to <out>/unreviewed/); the expert then accepts or dismisses every labeled item
   through core/review/actions.py, and a second pass replays the stored labels so the rules
   decide on the expert's decisions. <out>/predictions.jsonl is that second pass.

Modes:
  model-free  the merge gate. Real assumption templates (filled from the case's assumption
         sheet), real retrieval, real checks, quote check and rules; the stance model is the
         gold-direction stand-in and there is no AI reviewer, so no model is needed. Every
         labeled item goes to the simulated expert. Output in eval/out/<case>/model_free/.
  fake   the eval stand-ins from eval/pipeline_fakes.py; output in eval/out/<case>/fake/.
         Not gated: the numbers only show the wiring works.
  real   the product components (core.pipeline.real_components), local model included, then
         the simulated expert; output in eval/out/<case>/. `make eval-real` gates on it on a
         machine with the model installed.
  hostile the product's structure (assumptions, checks, retrieval, rules) with the red-team
         worst-case model from eval/adversarial/hostile_model.py: every record is labeled
         support and every item is accepted. Fails if any claim the structure must block
         (eval/adversarial/structural_blocks.STRUCTURAL) comes out SUPPORTED. Claims only the
         real reviewer can stop (MODEL_ONLY) are counted and reported, not gated.
  --expert none     skip the simulated expert: one pass, no expert decisions (model-free and
                    real only; under rules 0.2.0 nothing can then be SUPPORTED).
  --reviewer none   every supporting item is dismissed, so nothing can be SUPPORTED. Shows what
                    the pipeline does without the AI reviewer.
  --assumption-spec PATH   fill assumptions from a signed spec instead of the model: JSONL,
                    one {"claim_id", "template_id", "params", "is_core"} per line. The
                    template builder (core/audit/assumptions.py) validates every entry.
                    model-free mode needs one; without it, it uses the case's sheet
                    (eval/gold/<case>/assumptions.jsonl once signed, else the draft).
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


def sheet_people(conn) -> dict[str, str]:  # noqa: ANN001
    """The assumption sheet names people by surname ('person:petrov'); the case names each
    phone's owner by the id its device-owner stipulation made ('person:dev:item1:owner').
    Map each sheet id to the one stipulated owner whose surname it is. A sheet person with no
    stipulated owner (a third party such as person:sokolov) keeps its id and stays unresolved,
    as it should: nothing ties that person to an account."""
    by_surname: dict[str, list[str]] = {}
    for pid, name in conn.execute(
        "SELECT p.id, p.name FROM persons p JOIN stipulations s ON s.person_id = p.id"
        " WHERE s.kind = 'device_owner' ORDER BY p.id"
    ):
        if name and name.split():
            by_surname.setdefault(name.split()[-1].lower(), []).append(pid)
    return {f"person:{k}": v[0] for k, v in by_surname.items() if len(v) == 1}


def spec_filler(path: Path, conn=None):  # noqa: ANN001, ANN201 - core.audit.assumptions.Filler
    """A filler that proposes exactly the assumptions a signed spec lists for each claim.
    With conn, the sheet's person ids are mapped to the case's stipulated owners first."""
    from core.audit.assumptions import Proposal

    people = sheet_people(conn) if conn is not None else {}
    by_claim: dict[str, list] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            params = dict(row["params"])
            if "person_ids" in params:
                params["person_ids"] = [people.get(p, p) for p in params["person_ids"]]
            by_claim.setdefault(row["claim_id"], []).append(
                Proposal(row["template_id"], params, row.get("is_core", True))
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


def assumption_sheet(case: str) -> Path | None:
    """The case's assumption sheet: the signed copy under eval/gold/ if there is one, else the
    draft under eval/probe_draft/ (case01 only)."""
    signed = Path("eval/gold") / case / "assumptions.jsonl"
    if signed.exists():
        return signed
    draft = Path("eval/probe_draft") / f"{case}_assumptions.jsonl"
    return draft if draft.exists() else None


def sheet_status(spec: Path | None) -> str:
    """'signed' only for a sheet under eval/gold/ with no row still marked DRAFT."""
    if spec is None:
        return "none (assumptions from the model)"
    rows = [json.loads(line) for line in spec.read_text(encoding="utf-8").splitlines() if line]
    drafts = sum(1 for r in rows if str(r.get("labeled_by", "")).upper().startswith("DRAFT"))
    if Path("eval/gold") in spec.parents and not drafts:
        return "signed"
    return f"draft, not signed by Arsh ({drafts}/{len(rows)} rows marked DRAFT)"


def model_free_components(conn, spec: Path, gold) -> pipeline.Components:  # noqa: ANN001
    """Real structure, no model: the gold-direction stand-in labels and no AI reviewer runs,
    so every labeled item stays open for the simulated expert."""
    from eval.pipeline_fakes import FakeReviewer
    from eval.simulated_expert import GoldDirectionLabeler

    comps = pipeline.real_components(
        conn,
        replace={"labeler": GoldDirectionLabeler(conn, gold), "reviewer": FakeReviewer(False)},
        filler=spec_filler(spec, conn),
    )
    comps.reviewable = lambda item: False  # no AI review: everything waits for the expert
    comps.model_runs = (*comps.model_runs, *GoldDirectionLabeler.model_runs)
    return comps


def write_outputs(conn, out: Path, summary: dict) -> list[Prediction]:  # noqa: ANN001
    out.mkdir(parents=True, exist_ok=True)
    preds = pipeline.predictions(conn)
    (out / "predictions.jsonl").write_text(
        "".join(p.model_dump_json() + "\n" for p in preds), encoding="utf-8"
    )
    write_report(conn, out / "report.html")
    (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return preds


def _verdict_counts(preds: list[Prediction]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in preds:
        counts[p.verdict.value] = counts.get(p.verdict.value, 0) + 1
    return dict(sorted(counts.items()))


def run_once(
    case: str,
    mode: str,
    reviewer: str,
    out: Path,
    spec: Path | None = None,
    expert: str = "none",
) -> list[Prediction]:
    from eval.simulated_expert import GoldKey, RecordingRetriever, ReplayLabeler
    from eval.simulated_expert import readiness as key_readiness
    from eval.simulated_expert import review as expert_review

    conn = build_case(case, out / f"{case}.db")
    gold = GoldKey(load_jsonl(Path("eval/gold") / case / "gold.jsonl", GoldClaim))
    try:
        if mode == "fake":
            from eval.pipeline_fakes import fake_components

            comps = fake_components(accept=reviewer == "accept")
        elif mode == "hostile":
            comps = hostile_components(conn, spec_filler(spec, conn) if spec else None)
        elif mode == "model-free":
            if spec is None:
                raise SystemExit(f"{case}: model-free mode needs an assumption sheet")
            comps = model_free_components(conn, spec, gold)
        else:
            comps = pipeline.real_components(conn, filler=spec_filler(spec, conn) if spec else None)
            if reviewer == "none":
                from eval.pipeline_fakes import FakeReviewer

                comps.reviewer = FakeReviewer(accept=False)
        recorder = RecordingRetriever(comps.retriever)
        comps.retriever = recorder
        config = {
            "eval_mode": mode,
            "reviewer": reviewer,
            "expert": expert,
            "assumption_spec": str(spec),
        }
        result = pipeline.run_audit(conn, comps, clock=_clock, config=config)
        summary: dict = {
            "case": case,
            "mode": mode,
            "reviewer": reviewer,
            "expert": expert,
            "assumption_sheet": {"path": str(spec), "status": sheet_status(spec)},
            "fake": result.fake,
            "claims": len(result.decisions),
            "stored_items": result.stored_items,
            "dropped_labels": result.dropped_labels,
            "reviewer_failures": result.reviewer_failures,
        }
        if expert != "simulated":
            preds = write_outputs(conn, out, summary)
            print("pipeline: " + json.dumps(summary))
            return preds

        unreviewed = write_outputs(conn, out / "unreviewed", summary)
        ready = key_readiness(gold, recorder.retrieved, conn, result.manifest)
        ready["not_labeled"] = not_labeled(conn, gold, result)
        decided = expert_review(conn, gold, result.manifest, _clock)
        # Second pass: the same retrieval, checks and assumptions, the first pass's stored
        # labels (no model call), and the rules on the expert's decisions.
        comps.labeler = ReplayLabeler(conn)
        second = pipeline.run_audit(
            conn, comps, clock=_clock, config={**config, "pass": "after simulated expert"}
        )
        if second.manifest != result.manifest:
            raise SystemExit("pipeline: the replay pass considered different evidence")
        summary["unreviewed_verdicts"] = _verdict_counts(unreviewed)
        summary["simulated_expert"] = decided.summary()
        summary["readiness"] = ready
        summary["contradicted_by_failed_check"] = sorted(
            d.claim_id
            for d in second.decisions
            if d.verdict.value == "contradicted" and d.cited_check_ids
        )
        preds = write_outputs(conn, out, summary)
        summary["verdicts"] = _verdict_counts(preds)
        (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print_summary(summary)
        return preds
    finally:
        conn.close()


def not_labeled(conn, gold, result: pipeline.RunResult) -> dict[str, dict]:  # noqa: ANN001
    """Claims the run did not send to the stance model because a failed core check already
    decides them (core/pipeline.py, settled_by_check). Retrieval does not run for them either,
    so their key evidence counts as not retrieved above. This shows how much of it the failed
    checks cite, which the expert sees on the claim."""
    out: dict[str, dict] = {}
    for claim_id in sorted(result.unlabeled):
        key = gold.key(claim_id)
        cited: set[str] = set()
        for check_id in result.manifest.get(claim_id, {}).get("checks", []):
            (rids,) = conn.execute(
                "SELECT record_ids_json FROM check_results WHERE id = ?", (check_id,)
            ).fetchone()
            cited |= set(json.loads(rids))
        out[claim_id] = {"key": len(key), "cited_by_checks": len(key & cited)}
    return out


def print_summary(s: dict) -> None:
    r = s["readiness"]
    e = s["simulated_expert"]
    print(
        f"pipeline: {s['case']} {s['mode']}: {s['claims']} claims, {s['stored_items']} items "
        f"stored, {s['dropped_labels']} labels dropped"
    )
    print(f"pipeline: assumption sheet {s['assumption_sheet']['status']}")
    print(f"pipeline: unreviewed run verdicts {s['unreviewed_verdicts']} (0 supported by design)")
    print(
        f"pipeline: key evidence {r['key_evidence']} records; retrieved "
        f"{r['key_evidence_recall_retrieved']:.0%}, surfaced to the expert "
        f"{r['key_evidence_recall_surfaced']:.0%}"
    )
    skipped = r.get("not_labeled", {})
    missed = {c: v["missed"] for c, v in r["per_claim"].items() if v["missed"] and c not in skipped}
    print(f"pipeline: key evidence never retrieved: {json.dumps(missed)}")
    if skipped:
        key = sum(v["key"] for v in skipped.values())
        cited = sum(v["cited_by_checks"] for v in skipped.values())
        print(
            f"pipeline: not sent to the model, a failed core check decides them: "
            f"{', '.join(skipped)}; their failed checks cite {cited} of their {key} key records"
        )
    print(
        f"pipeline: claims ready for the expert (key evidence surfaced) "
        f"{len(r['claims_ready_for_expert'])}/{s['claims']}; all key evidence retrieved "
        f"{len(r['claims_all_key_retrieved'])}/{s['claims']}"
    )
    print(f"pipeline: simulated expert accepted {e['accepted']}, dismissed {e['dismissed']}")
    print(f"pipeline: verdicts after the simulated expert {s['verdicts']}")
    print(f"pipeline: contradicted with a failed check cited: {s['contradicted_by_failed_check']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="case01")
    parser.add_argument(
        "--mode", choices=("model-free", "real", "fake", "hostile"), default="model-free"
    )
    parser.add_argument("--expert", choices=("simulated", "none"), default=None)
    parser.add_argument("--reviewer", choices=("accept", "none"), default="accept")
    parser.add_argument("--assumption-spec", type=Path, default=None)
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    expert = args.expert
    if expert is None:
        expert = "simulated" if args.mode in ("model-free", "real") else "none"
    if expert == "simulated" and args.mode not in ("model-free", "real"):
        parser.error("the simulated expert runs in model-free and real modes only")
    spec = args.assumption_spec
    if spec is None and args.mode == "model-free":
        spec = assumption_sheet(args.case)

    out = args.out
    if out is None:
        out = Path("eval/out") / args.case
        if args.mode in ("fake", "hostile"):
            out = out / args.mode
        if args.mode == "model-free":
            out = out / "model_free"
        if args.reviewer == "none":
            out = out / "no_reviewer"
        if expert == "none" and args.mode in ("model-free", "real"):
            out = out / "no_expert"
    try:
        first = run_once(args.case, args.mode, args.reviewer, out, spec, expert)
        if args.repeat:
            second = run_once(args.case, args.mode, args.reviewer, out / "repeat", spec, expert)
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
