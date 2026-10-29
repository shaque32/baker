"""Run the full pipeline on a synthetic case and write predictions and the report.

Usage: python -m eval.run_pipeline [--case case01] [--mode model-free|real|fake|hostile]
                                   [--expert simulated|rubber-stamp|fallible|none]
                                   [--error-rate RATE] [--expert-seed N]
                                   [--reviewer accept|none] [--no-challenge]
                                   [--testability CAP [--testability-prompt PATH]]
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
  --expert rubber-stamp   the two passes, with the rubber-stamp expert in place of the simulated
                    one: it accepts every labeled item (eval/simulated_expert.py). Not a gate;
                    it shows what gets through when the expert accepts everything. Output in
                    <out>/rubber_stamp/.
  --expert fallible --error-rate RATE   the two passes, with the fallible expert: it decides as
                    the simulated one but gets each item wrong at RATE (0 to 1, no default: the
                    rate is Arsh's to set), drawn per item from --expert-seed (default 0). Not a
                    gate; its summary gives the dismissal rate and items decided per claim.
                    Output in <out>/fallible/.
  --no-challenge    skip the challenge step (core/audit/challenge.py), which runs by default as
                    it does in the product: code's counter-searches on claims close to
                    supported, storing only doubt. Output in <out>/no_challenge/.
  --testability CAP the testability step (core/audit/testability.py, eval only, off by
                    default), real mode only: the model fills the assumptions, and on a claim it
                    leaves untested the step makes up to CAP more calls (CAP: Arsh sets it; no
                    default). The case's signed sheet is used only to check each repair and to
                    score. The run's expert accepts every repair that passed code's checks, as
                    the examiner (eval/simulated_expert.py). --testability-prompt names the
                    prompt; the default is the signed core/audit/prompts/agent_testability.md,
                    and any other (the draft in docs/prompts/) is reported as a draft with no
                    go/no-go. Output in <out>/testability/. The go/no-go (testability_go_no_go)
                    is printed after the run and written to <out>/go_no_go.json; a decision
                    needs Arsh's X, Y, cap and least denominator, a held-out case, --expert
                    rubber-stamp and --repeat.
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
For a case whose case.json says "hidden", the printed summary is aggregate only (no claim ids,
no record ids); the details stay in <out>/run.json, which builders do not read. Until Arsh signs
case02's key and assumption sheet, the drafts under eval/synthetic/case02/ stand in, and every
run says so.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from core import pipeline
from core.contracts import ClaimType, DocKind, GoldClaim, GovDocParagraph, Prediction
from core.db import apply_schema, connect
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.govdoc import PdfGovDocIngester
from core.report.html import quote_check_label, write_report
from core.review import actions
from eval.run_eval import load_jsonl, score

EVAL_TIME = datetime(2026, 10, 7, tzinfo=UTC)  # fixed, so runs are byte-for-byte repeatable
GOLD_ACTOR = "expert:eval-gold-claims"
STIPULATION_ACTOR = "expert:eval-case-stipulation"


def _clock() -> datetime:
    return EVAL_TIME


def synthetic_dir(case: str) -> Path:
    return Path("eval/synthetic") / case


# Draft keys, used only until Arsh signs the case's gold (eval/gold/<case>/gold.jsonl).
DRAFT_GOLD = {
    "case02": Path("eval/synthetic/case02/draft_gold.jsonl"),
    "case03": Path("eval/synthetic/case03/draft_gold.jsonl"),  # challenge-step case, ungated
}


def gold_path(case: str) -> Path:
    """The case's signed gold if there is one, else its draft key (case02, case03)."""
    signed = Path("eval/gold") / case / "gold.jsonl"
    if signed.exists() and signed.read_text(encoding="utf-8").strip():
        return signed
    return DRAFT_GOLD.get(case, signed)


def key_status(path: Path) -> str:
    """'signed' only for gold under eval/gold/ with no line still marked DRAFT."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    drafts = sum(1 for r in rows if str(r.get("labeled_by", "")).upper().startswith("DRAFT"))
    if Path("eval/gold") in path.parents and not drafts:
        return "signed"
    return f"draft, not signed by Arsh ({drafts}/{len(rows)} claims marked DRAFT)"


def is_hidden(case: str) -> bool:
    meta = json.loads((synthetic_dir(case) / "case.json").read_text(encoding="utf-8"))
    return bool(meta.get("hidden"))


def ensure_reports(case: str) -> dict:
    meta = json.loads((synthetic_dir(case) / "case.json").read_text(encoding="utf-8"))
    missing = [s for s in meta["sources"] if not (synthetic_dir(case) / s["file"]).exists()]
    if missing:
        if case == "case01":
            from eval.synthetic.generate import generate
        elif case == "case02":
            from eval.synthetic.case02_generate import generate
        elif case == "case03":
            from eval.synthetic.case03_generate import generate
        else:
            raise SystemExit(f"{case}: reports missing; build them with that case's generator")
        generate(synthetic_dir(case), None)
    return meta


def render_affidavit_pdf(case: str, path: Path) -> Path:
    """The case's mock affidavit as a PDF, laid out like the govdoc fixtures."""
    if case == "case02":
        from eval.synthetic.case02_generate import write_affidavit_pdf

        path.parent.mkdir(parents=True, exist_ok=True)
        return write_affidavit_pdf(path)
    if case == "case03":
        from eval.synthetic.case03_generate import write_affidavit_pdf as write_case03

        return write_case03(path)
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
    """Gold cites the printed paragraph number. Prefer the page gold names.

    If the ingester gave no paragraph that label (it labels a numbered run only when the run
    starts at 1, so an excerpt that starts at paragraph 21 gets no labels), fall back to the
    paragraph whose text starts with the printed number, and say so: the eval still runs, and
    the gap stays visible until the ingester reads such excerpts."""
    hits = [p for p in paragraphs if p.label == str(gold.para_no)]
    if not hits:
        hits = [p for p in paragraphs if re.match(rf"{gold.para_no}\.\s", p.text)]
        if hits and gold.para_no not in _UNLABELED_SEEN:
            _UNLABELED_SEEN.add(gold.para_no)
            print(
                f"pipeline: NOTE the govdoc ingester did not label printed paragraph "
                f"{gold.para_no}; matched it by the number at the start of its text"
            )
    if not hits:
        raise SystemExit(f"{gold.claim_id}: no paragraph printed as {gold.para_no}")
    on_page = [p for p in hits if p.page == gold.page]
    return (on_page or hits)[0]


_UNLABELED_SEEN: set[int] = set()


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

    gold = load_jsonl(gold_path(case), GoldClaim)
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


DRAFT_SHEETS = {
    "case01": Path("eval/probe_draft/case01_assumptions.jsonl"),
    "case02": Path("eval/synthetic/case02/case02_assumptions.jsonl"),
}


def assumption_sheet(case: str) -> Path | None:
    """The case's assumption sheet: the signed copy under eval/gold/ if there is one, else the
    draft (eval/probe_draft/ for case01, the hidden eval/synthetic/case02/ for case02)."""
    signed = Path("eval/gold") / case / "assumptions.jsonl"
    if signed.exists():
        return signed
    draft = DRAFT_SHEETS.get(case)
    return draft if draft is not None and draft.exists() else None


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


def run_versions(conn) -> dict:  # noqa: ANN001
    """What a result depends on, as the report stamps it: the latest run's Baker release and git
    commit, pipeline, rule and quote-check versions and every model run's file SHA-256 and seed."""
    run = pipeline.last_run(conn) or {}
    return {
        "build": (run.get("config") or {}).get("build"),
        "evidence_build": (run.get("config") or {}).get("evidence_build"),
        "pipeline": run.get("baker_version"),
        "rules": run.get("rule_version"),
        "quote_check": quote_check_label(run),
        "models": [
            {"purpose": r[0], "model": r[1], "sha256": r[2], "prompt": r[3], "seed": r[4]}
            for r in conn.execute(
                "SELECT purpose, model_name, model_sha256, prompt_version, seed FROM model_runs"
                " ORDER BY purpose, id"
            )
        ],
    }


def write_outputs(conn, out: Path, summary: dict) -> list[Prediction]:  # noqa: ANN001
    out.mkdir(parents=True, exist_ok=True)
    summary["versions"] = run_versions(conn)
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


class _ReplayableFiller:
    """A model filler for a two-pass eval run: the first pass asks the model, the replay pass
    (after the simulated expert) gets the same proposals back with no model call, so both
    passes test the same assumptions."""

    def __init__(self, filler: object) -> None:
        self.filler = filler
        self.recorder = getattr(filler, "recorder", None)
        self.model_runs = getattr(filler, "model_runs", ())
        self.replaying = False
        self._seen: dict[str, object] = {}

    def __getattr__(self, name: str) -> object:
        return getattr(self.filler, name)

    def __call__(self, claim, allowed):  # noqa: ANN001, ANN204
        if self.replaying and claim.id in self._seen:
            return self._seen[claim.id]
        out = self.filler(claim, allowed)  # type: ignore[operator]
        self._seen[claim.id] = out
        return out


# The testability step's go/no-go (plans/agentic.md), fixed before the run. Arsh sets X, Y, the
# per-claim cap and the least denominator; until then each prints as not set and no go/no-go is
# given (testability_go_no_go).
TESTABILITY_X_PERCENT: float | None = None  # least share of sheet-testable refusals converted
TESTABILITY_Y_BUDGET: dict[str, float] | None = None  # most "calls" and "seconds", per claim
TESTABILITY_CAP: int | None = None  # the per-claim cap the go/no-go runs with
TESTABILITY_MIN_TESTABLE: int | None = None  # fewest sheet-testable refusals for a decision
TESTABILITY_SIGNED_PROMPT = Path("core/audit/prompts/agent_testability.md")
# Cases whose claims and signed sheets were written by someone other than the prompt's author,
# held out for the go/no-go. None yet: case01 and case03 are development cases.
TESTABILITY_GO_NO_GO_CASES: frozenset[str] = frozenset()


def sim_examiner(actor: str):  # noqa: ANN201 - core.audit.testability.Examiner
    """The eval's examiner for the testability step: it accepts every repair that reached it,
    which is every repair that passed code's checks against the signed sheet, under the run's
    expert's actor. No UI; a real examiner's step is a later, signed change."""

    def examiner(claim, assumptions):  # noqa: ANN001, ANN202
        return actor

    return examiner


def testability_step(
    conn,  # noqa: ANN001
    case: str,
    filler: object,
    cap: int,
    prompt: Path | None,
    expert: str,
    model: object | None = None,
):  # noqa: ANN201 - core.audit.testability.Testability
    """The step for an eval run, checked against the case's signed sheet."""
    from core.audit import testability
    from core.audit._llm_json import prompt_body
    from eval.simulated_expert import FALLIBLE, RUBBER_STAMP, SIM_EXPERT

    if case == "case02" or is_hidden(case):  # held-out scores never hold gold-filtered repairs
        raise SystemExit(f"{case}: the testability step never runs on a hidden case")
    sheet = assumption_sheet(case)
    if sheet is None or sheet_status(sheet) != "signed":
        raise SystemExit(f"{case}: the testability step needs a signed assumption sheet")
    rows = [json.loads(line) for line in sheet.read_text(encoding="utf-8").splitlines() if line]
    path = prompt or TESTABILITY_SIGNED_PROMPT
    if not path.exists():
        raise SystemExit(f"testability: no prompt at {path}; Arsh signs it (docs/prompts/ draft)")
    actor = {"rubber-stamp": RUBBER_STAMP, "fallible": FALLIBLE}.get(expert, SIM_EXPERT)
    # With no expert (--expert none) nobody accepts: repairs stay logged proposals, never used.
    examiner = sim_examiner(actor) if expert != "none" else None
    step = testability.create(
        conn,
        filler,  # type: ignore[arg-type]
        testability.sheet_named(rows, sheet_people(conn)),
        cap,
        model=model,
        template=prompt_body(path.read_text(encoding="utf-8")),
        examiner=examiner,
    )
    return step


def testability_summary(
    result: pipeline.RunResult,
    step,  # noqa: ANN001
    case: str,
    prompt: Path | None,
) -> dict[str, object]:
    """What the step did on the first pass, with the go/no-go measures (plans/agentic.md).
    Counts only, so a hidden case prints nothing claim by claim."""
    from core.audit import testability

    reps = list(result.testability.values())
    tries = [a for r in reps for a in r.attempts]
    # Tries that passed the filler's checks and the claim-only check (the product's gate); the
    # sheet then rejects some of them: how often the claim's own words let a wrong one through.
    checked = [a for a in tries if a.outcome in ("mismatch", "proposed")]
    # #159's rate on the same tries, reported beside it until the go/no-go fixes one: of the
    # tries that passed the filler's checks, the share the sheet check rejects, with an
    # "outside" try counted by what the sheet says of the names it gave.
    passed = [
        (r, a) for r in reps for a in r.attempts if a.outcome in ("mismatch", "proposed", "outside")
    ]
    sheet_rejects = sum(
        a.outcome == "mismatch"
        or (
            a.outcome == "outside"
            and (r.sheet is None or bool(testability.mismatch(a.named, r.sheet)))
        )
        for r, a in passed
    )
    testable = [r for r in reps if r.sheet is not None]
    converted = [r for r in reps if r.assumptions]
    signed = prompt is None or prompt == TESTABILITY_SIGNED_PROMPT
    out: dict[str, object] = {
        "prompt": "signed" if signed else "DRAFT, not signed by Arsh",
        "cap": step.cap,
        "claims_the_filler_left_untested": len(reps),
        "of_them_the_sheet_makes_testable": len(testable),
        # An upper bound filtered by gold: the signed sheet rejects whatever it does not name.
        "converted_and_accepted": len(converted),
        "conversion_rate": (len(converted) / len(testable)) if testable else None,
        # Of the tries that passed the filler's checks and the claim-only check, the share the
        # sheet check rejected.
        "wrong_entity_rate": (sum(a.outcome == "mismatch" for a in checked) / len(checked))
        if checked
        else None,
        "wrong_entity_rate_without_the_claim_check": (sheet_rejects / len(passed))
        if passed
        else None,
        "tries": len(tries),
        "invalid_outputs": sum(a.outcome == "invalid" for a in tries),
        "valid_output_rate": (1 - sum(a.outcome == "invalid" for a in tries) / len(tries))
        if tries
        else None,
        "refused_by_code": sum(a.outcome == "refused" for a in tries),
        "outside_the_claims_words": sum(a.outcome == "outside" for a in tries),
        "mismatch_person_phone_or_window": sum(a.no_go for a in tries),
        "mismatch_other_only": sum(
            a.outcome == "mismatch" and not a.no_go and r.sheet is not None
            for r in reps
            for a in r.attempts
        ),
        "repairs_on_claims_the_sheet_leaves_untested": sum(
            a.outcome == "mismatch" and r.sheet is None for r in reps for a in r.attempts
        ),
        "seconds": round(step.seconds, 1),
        "x_percent": TESTABILITY_X_PERCENT,
        "y_budget": TESTABILITY_Y_BUDGET,
        "cap_set": TESTABILITY_CAP,
        "min_testable": TESTABILITY_MIN_TESTABLE,
        "go_no_go_case": case in TESTABILITY_GO_NO_GO_CASES,
    }
    return out


def run_once(
    case: str,
    mode: str,
    reviewer: str,
    out: Path,
    spec: Path | None = None,
    expert: str = "none",
    labeler_model: object | None = None,
    claim_ids: list[str] | None = None,
    filler_model: object | None = None,
    challenge: bool = True,
    error_rate: float | None = None,
    expert_seed: int = 0,
    testability_cap: int | None = None,
    testability_prompt: Path | None = None,
    testability_model: object | None = None,
) -> list[Prediction]:
    """One audit of a case. labeler_model (real mode only) is the stance labeler's model in
    place of the configured local one: the cloud benchmark (eval/bench) passes Claude here.
    filler_model (real mode, no assumption sheet) is the assumption filler's model the same
    way. claim_ids audits just those claims. testability_cap (real mode, no assumption sheet)
    turns the testability step on, with testability_model in place of the configured model."""
    from eval.simulated_expert import (
        GoldKey,
        RecordingRetriever,
        ReplayLabeler,
        fallible_review,
        rubber_stamp_review,
    )
    from eval.simulated_expert import readiness as key_readiness
    from eval.simulated_expert import review as expert_review

    conn = build_case(case, out / f"{case}.db")
    gold = GoldKey(load_jsonl(gold_path(case), GoldClaim))
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
            replace: dict[str, object] = {}
            if labeler_model is not None:
                from core.audit import stance as stance_mod

                replace["labeler"] = stance_mod.create(conn, model=labeler_model)  # type: ignore[arg-type]
            filler = spec_filler(spec, conn) if spec else None
            if filler is None and (filler_model is not None or testability_cap is not None):
                from core.audit import assumption_filler

                filler = _ReplayableFiller(assumption_filler.create(conn, model=filler_model))  # type: ignore[arg-type]
            comps = pipeline.real_components(conn, replace=replace, filler=filler)
            if testability_cap is not None:
                if spec is not None:
                    raise SystemExit("testability: the model fills; the sheet is only checked")
                step = testability_step(
                    conn, case, filler, testability_cap, testability_prompt, expert,
                    model=testability_model,
                )  # fmt: skip
                comps.testability = step
                comps.recorders = (*comps.recorders, step)
                comps.model_runs = (*comps.model_runs, *step.model_runs)
            if reviewer == "none":
                from eval.pipeline_fakes import FakeReviewer

                comps.reviewer = FakeReviewer(accept=False)
        recorder = RecordingRetriever(comps.retriever)
        comps.retriever = recorder
        comps.challenge = challenge
        config = {
            "eval_mode": mode,
            "reviewer": reviewer,
            "expert": expert,
            "assumption_spec": str(spec),
        }
        result = pipeline.run_audit(conn, comps, clock=_clock, claim_ids=claim_ids, config=config)
        summary: dict = {
            "case": case,
            "mode": mode,
            "reviewer": reviewer,
            "expert": expert,
            "assumption_sheet": {"path": str(spec), "status": sheet_status(spec)},
            "gold": {"path": str(gold_path(case)), "status": key_status(gold_path(case))},
            "fake": result.fake,
            "claims": len(result.decisions),
            "stored_items": result.stored_items,
            "dropped_labels": result.dropped_labels,
            "reviewer_failures": result.reviewer_failures,
        }
        if comps.testability is not None:
            summary["testability"] = testability_summary(
                result, comps.testability, case, testability_prompt
            )
        if expert not in ("simulated", "rubber-stamp", "fallible"):
            preds = write_outputs(conn, out, summary)
            print("pipeline: " + json.dumps(summary))
            return preds

        unreviewed = write_outputs(conn, out / "unreviewed", summary)
        ready = key_readiness(gold, recorder.retrieved, conn, result.manifest)
        ready["not_labeled"] = not_labeled(conn, gold, result)
        if expert == "rubber-stamp":
            decided = rubber_stamp_review(conn, result.manifest, _clock)
        elif expert == "fallible":
            if error_rate is None:
                raise SystemExit("pipeline: the fallible expert needs an error rate")
            decided = fallible_review(
                conn, gold, result.manifest, _clock, error_rate, seed=expert_seed
            )
        else:
            decided = expert_review(conn, gold, result.manifest, _clock)
        # Second pass: the same retrieval, checks and assumptions, the first pass's stored
        # labels (no model call), and the rules on the expert's decisions.
        comps.labeler = ReplayLabeler(conn)
        for f in comps.recorders:  # a model filler answers the replay from its first answers
            if isinstance(f, _ReplayableFiller):
                f.replaying = True
        if comps.testability is not None:  # and so does the testability step
            comps.testability.replaying = True
        comps.recorders = ()  # the first pass stored every call already
        second = pipeline.run_audit(
            conn,
            comps,
            clock=_clock,
            claim_ids=claim_ids,
            config={**config, "pass": f"after {expert} expert"},
        )
        if second.manifest != result.manifest:
            raise SystemExit("pipeline: the replay pass considered different evidence")
        summary["unreviewed_verdicts"] = _verdict_counts(unreviewed)
        summary["simulated_expert"] = decided.summary()
        if challenge:
            summary["challenge"] = challenge_summary(result)
        summary["readiness"] = ready
        summary["contradicted_by_failed_check"] = sorted(
            d.claim_id
            for d in second.decisions
            if d.verdict.value == "contradicted" and d.cited_check_ids
        )
        preds = write_outputs(conn, out, summary)
        summary["verdicts"] = _verdict_counts(preds)
        (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        if is_hidden(case):
            print_hidden_summary(summary)
        else:
            print_summary(summary)
        return preds
    finally:
        conn.close()


def challenge_summary(result: pipeline.RunResult) -> dict[str, object]:
    """What the challenge step searched and stored on the first pass (the replay pass asks the
    same searches and stores the same items)."""
    entries = [e for es in result.challenge.values() for e in es]
    return {
        "claims_challenged": sorted(result.challenge),
        "searches": len(entries),
        "records_found": sum(len(e["record_ids"]) for e in entries),  # type: ignore[arg-type]
        "stored": sum(len(e["stored"]) for e in entries),  # type: ignore[arg-type]
        "discarded_not_doubt": sum(e["discarded"] for e in entries),  # type: ignore[misc]
        "dropped": sum(e["dropped"] for e in entries),  # type: ignore[misc]
    }


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


def print_hidden_summary(s: dict) -> None:
    """Aggregate numbers only, so builders who run make eval learn nothing claim by claim."""
    r = s["readiness"]
    print(f"pipeline: {s['case']} {s['mode']} (hidden case, aggregate only): {s['claims']} claims")
    print(f"pipeline: gold {s['gold']['status']}")
    print(f"pipeline: assumption sheet {s['assumption_sheet']['status']}")
    print(f"pipeline: unreviewed run verdicts {s['unreviewed_verdicts']} (0 supported by design)")
    print(
        f"pipeline: key evidence {r['key_evidence']} records; retrieved "
        f"{r['key_evidence_recall_retrieved']:.0%}, surfaced to the expert "
        f"{r['key_evidence_recall_surfaced']:.0%}"
    )
    print(
        f"pipeline: claims ready for the expert {len(r['claims_ready_for_expert'])}/{s['claims']}"
    )
    print(f"pipeline: verdicts after the simulated expert {s['verdicts']}")
    if "testability" in s:
        print_testability(s["testability"])


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
    if "error_rate" in e:
        print(
            f"pipeline: fallible expert at error rate {e['error_rate']}: {e['wrong_accepts']} "
            f"wrong accepts, {e['wrong_dismissals']} wrong dismissals; dismissal rate "
            f"{e['dismissal_rate']:.0%}, {e['items_per_claim_decided']} items decided per claim"
        )
    print(f"pipeline: verdicts after the simulated expert {s['verdicts']}")
    print(f"pipeline: contradicted with a failed check cited: {s['contradicted_by_failed_check']}")
    if "testability" in s:
        print_testability(s["testability"])


def print_testability(t: dict) -> None:
    """The testability step's measures. The go/no-go is read from them after the run
    (report_go_no_go), since it also needs the repeat and the false-supported count."""
    rate = t["conversion_rate"]
    print(
        f"pipeline: testability ({t['prompt']} prompt, cap {t['cap']}): the filler left "
        f"{t['claims_the_filler_left_untested']} claims untested, the sheet makes "
        f"{t['of_them_the_sheet_makes_testable']} of them testable; "
        f"{t['converted_and_accepted']} converted and accepted"
        + (f" ({rate:.0%})" if rate is not None else "")
        + ", an upper bound: the signed sheet filters every try"
    )
    wrong = t["wrong_entity_rate"]
    print(
        "pipeline: testability: of the tries that passed the filler's checks and the claim-only "
        "check, the sheet check " + (f"rejected {wrong:.0%}" if wrong is not None else "saw none")
    )
    before = t["wrong_entity_rate_without_the_claim_check"]
    print(
        "pipeline: testability: of the tries that passed the filler's checks (#159's measure, "
        "the claim-only check aside), the sheet check "
        + (f"rejects {before:.0%}" if before is not None else "saw none")
    )
    print(
        f"pipeline: testability: {t['tries']} calls, {t['invalid_outputs']} invalid outputs, "
        f"{t['refused_by_code']} refused by code, {t['outside_the_claims_words']} naming what "
        "the claim's own words do not; mismatches with the sheet: "
        f"{t['mismatch_person_phone_or_window']} on a person, phone or window, "
        f"{t['mismatch_other_only']} on an account, handle, app, template or quote only, "
        f"{t['repairs_on_claims_the_sheet_leaves_untested']} on claims the sheet leaves untested;"
        f" {t['seconds']} s"
    )


# The go/no-go's settings: what Arsh sets, in the order the reasons name them.
GO_NO_GO_SETTINGS = ("x_percent", "y_budget", "cap_set", "min_testable")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson 95% interval of k in n (n > 0)."""
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def testability_go_no_go(
    t: dict,
    *,
    expert: str,
    false_supported: int | None,
    repeat: dict | None,
    gold: str | None,
) -> dict[str, object]:
    """The testability step's go/no-go (plans/agentic.md, approved 2026-10-27) on one run's
    measures `t` (testability_summary), against Arsh's X, Y, cap and least denominator.

    A decision needs all four set, the signed prompt, a held-out case, the rubber-stamp expert
    (the false-supported bar), --repeat (the byte-identical repeat) and Arsh's signed key
    (`gold`, its key_status); otherwise none is given, with the reasons. With fewer
    sheet-testable refusals than the least denominator the result is "insufficient", not a
    decision. Then GO only if every bar holds: conversion at least X%, no try naming a different
    person, phone or window than the sheet, 0 false supported, every output valid, the repeat
    identical, and calls and seconds per claim within Y."""
    why: list[str] = []
    unset = [k for k in GO_NO_GO_SETTINGS if t.get(k) is None]
    why += [f"{', '.join(unset)} not set by Arsh"] if unset else []
    why += ["the prompt is a draft"] if t["prompt"] != "signed" else []
    why += ["this is not a held-out go/no-go case"] if not t["go_no_go_case"] else []
    if t.get("cap_set") is not None and t["cap"] != t["cap_set"]:
        why.append(f"the run's cap is {t['cap']}, not Arsh's {t['cap_set']}")
    if expert != "rubber-stamp":
        why.append("the false-supported bar needs --expert rubber-stamp")
    if repeat is None:
        why.append("the byte-identical repeat needs --repeat")
    if false_supported is None:
        why.append("no gold key to score false supported")
    elif gold != "signed":
        why.append("the gold key is a draft, not signed by Arsh")
    if why:
        return {"decision": "none given", "why": why, "checks": []}
    testable = int(t["of_them_the_sheet_makes_testable"])
    if testable < max(1, int(t["min_testable"])):
        return {
            "decision": "insufficient",
            "why": [
                f"{testable} refusals the sheet makes testable, fewer than the "
                f"{t['min_testable']} a decision needs"
            ],
            "checks": [],
        }
    converted = int(t["converted_and_accepted"])
    low, high = wilson(converted, testable)
    worked = int(t["claims_the_filler_left_untested"])  # >= testable > 0
    y = t["y_budget"]
    calls, seconds = t["tries"] / worked, t["seconds"] / worked
    invalid = int(t["invalid_outputs"])
    differ = [k for k in ("predictions", "model_calls") if not repeat[k]]  # type: ignore[index]
    checks = [
        {
            "bar": f"conversion at least {t['x_percent']:g}%",
            "value": f"{converted} of {testable} ({converted / testable:.0%}, "
            f"Wilson 95% {low:.0%} to {high:.0%})",
            "ok": converted / testable * 100 >= t["x_percent"],
        },
        {
            "bar": "no try names a different person, phone or window than the sheet",
            "value": f"{t['mismatch_person_phone_or_window']} such tries",
            "ok": t["mismatch_person_phone_or_window"] == 0,
        },
        {
            "bar": "0 false supported under the rubber-stamp expert",
            "value": f"{false_supported} false supported",
            "ok": false_supported == 0,
        },
        {
            "bar": "100% valid outputs",
            "value": f"{invalid} invalid of {t['tries']} calls",
            "ok": invalid == 0,
        },
        {
            "bar": "a byte-identical repeat",
            "value": (f"different ({', '.join(differ)})" if differ else "identical")
            + f", {repeat['calls_compared']} filler and step calls compared",  # type: ignore[index]
            "ok": not differ,
        },
        {
            "bar": f"at most {y['calls']:g} calls per claim",
            "value": f"{calls:.2f} per claim the step worked on ({worked})",
            "ok": calls <= y["calls"],
        },
        {
            "bar": f"at most {y['seconds']:g} s per claim",
            "value": f"{seconds:.1f} s per claim the step worked on ({worked})",
            "ok": seconds <= y["seconds"],
        },
    ]  # fmt: skip
    failed = [c["bar"] for c in checks if not c["ok"]]
    return {"decision": "NO-GO" if failed else "GO", "why": failed, "checks": checks}


def model_outputs(db: Path) -> list[tuple[str, str, str, str]]:
    """The filler's and the testability step's model calls in a run's database, sorted: what a
    byte-identical repeat must give again (the stance calls are compared through the
    predictions)."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT r.purpose, c.prompt, c.raw_output, c.outcome FROM model_calls c "
            "JOIN model_runs r ON r.id = c.model_run_id "
            "WHERE r.purpose IN ('assumptions', 'testability')"
        ).fetchall()
    finally:
        conn.close()
    return sorted(tuple(r) for r in rows)


def repeat_result(
    first: list[Prediction], second: list[Prediction], first_db: Path, second_db: Path
) -> dict[str, object]:
    """Whether the repeat gave the same predictions and the same filler and step model calls,
    byte for byte."""
    a, b = model_outputs(first_db), model_outputs(second_db)
    return {
        "identical": first == second and a == b,
        "predictions": first == second,
        "model_calls": a == b,
        "calls_compared": len(a),
    }


def hardware() -> dict[str, object]:
    """What a go/no-go's calls and seconds were measured on, and when (wall-clock time, not the
    eval's fixed clock)."""
    memory = None
    try:
        memory = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (AttributeError, ValueError, OSError):
        pass
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpus": os.cpu_count(),
        "memory_gb": memory,
        "python": platform.python_version(),
        "measured_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def report_go_no_go(
    case: str,
    out: Path,
    expert: str,
    first: list[Prediction],
    second: list[Prediction] | None,
) -> dict[str, object]:
    """Read the run's testability measures, score its false supported, compare the repeat, and
    write and print the go/no-go (<out>/go_no_go.json)."""
    t = json.loads((out / "run.json").read_text(encoding="utf-8"))["testability"]
    gold = load_jsonl(gold_path(case), GoldClaim)
    false_supported = score(gold, first).n_false_supported if gold else None
    status = key_status(gold_path(case)) if gold else None
    repeat = None
    if second is not None:
        repeat = repeat_result(first, second, out / f"{case}.db", out / "repeat" / f"{case}.db")
    result = testability_go_no_go(
        t, expert=expert, false_supported=false_supported, repeat=repeat, gold=status
    )
    record = {
        **result,
        "case": case,
        "gold": {"path": str(gold_path(case)), "status": status},
        "testability": t,
        "repeat": repeat,
        "hardware": hardware(),
    }
    (out / "go_no_go.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    why = "; ".join(result["why"])  # type: ignore[arg-type]
    print(f"pipeline: testability go/no-go: {result['decision']}" + (f" ({why})" if why else ""))
    for c in result["checks"]:  # type: ignore[attr-defined]
        mark = "pass" if c["ok"] else "FAIL"
        print(f"pipeline: testability go/no-go: {mark}: {c['bar']}: {c['value']}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="case01")
    parser.add_argument(
        "--mode", choices=("model-free", "real", "fake", "hostile"), default="model-free"
    )
    parser.add_argument(
        "--expert", choices=("simulated", "rubber-stamp", "fallible", "none"), default=None
    )
    parser.add_argument("--error-rate", type=float, default=None)
    parser.add_argument("--expert-seed", type=int, default=0)
    parser.add_argument("--reviewer", choices=("accept", "none"), default="accept")
    parser.add_argument("--assumption-spec", type=Path, default=None)
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--challenge", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--testability", type=int, default=None, metavar="CAP")
    parser.add_argument("--testability-prompt", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    expert = args.expert
    if expert is None:
        expert = "simulated" if args.mode in ("model-free", "real") else "none"
    if expert in ("simulated", "rubber-stamp", "fallible") and args.mode not in (
        "model-free",
        "real",
    ):
        parser.error(f"the {expert} expert runs in model-free and real modes only")
    if (expert == "fallible") != (args.error_rate is not None):
        parser.error("--error-rate goes with --expert fallible, and it needs one")
    if args.error_rate is not None and not 0.0 <= args.error_rate <= 1.0:
        parser.error("--error-rate is between 0 and 1")
    if args.testability is not None and (args.mode != "real" or args.assumption_spec):
        parser.error(
            "--testability runs in real mode, with the model filling (no --assumption-spec)"
        )
    if args.testability_prompt is not None and args.testability is None:
        parser.error("--testability-prompt goes with --testability CAP")
    if args.testability is not None and (
        args.case == "case02"
        or ((synthetic_dir(args.case) / "case.json").exists() and is_hidden(args.case))
    ):
        parser.error("--testability never runs on a hidden case")
    if args.mode == "hostile" and args.case != "case01":
        parser.error("the red-team gate lists case01's structural claims; run it on case01")
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
        if expert == "rubber-stamp":
            out = out / "rubber_stamp"
        if expert == "fallible":
            out = out / "fallible"
        if not args.challenge:
            out = out / "no_challenge"
        if args.testability is not None:
            out = out / "testability"
    try:
        first = run_once(
            args.case,
            args.mode,
            args.reviewer,
            out,
            spec,
            expert,
            challenge=args.challenge,
            error_rate=args.error_rate,
            expert_seed=args.expert_seed,
            testability_cap=args.testability,
            testability_prompt=args.testability_prompt,
        )
        second = None
        if args.repeat:
            second = run_once(
                args.case,
                args.mode,
                args.reviewer,
                out / "repeat",
                spec,
                expert,
                challenge=args.challenge,
                error_rate=args.error_rate,
                expert_seed=args.expert_seed,
                testability_cap=args.testability,
                testability_prompt=args.testability_prompt,
            )
        if args.testability is not None:
            report_go_no_go(args.case, out, expert, first, second)
        if second is not None:
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
