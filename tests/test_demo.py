"""The demo case (eval/demo.py, `baker demo`): synthetic case01, built in seconds through the
product's own code, scripted labels said plainly on every page, verdicts that match the signed
answer key once the person giving the demo does the one step left open, and a reset that never
touches anything but a demo case."""

from __future__ import annotations

import html
import json
import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from core import pipeline
from core.casework import cases
from core.contracts import EvidenceStatus, Stance, Verdict
from core.db import connect
from core.report.html import render_report
from core.review import actions, audit_log
from core.review.redecide import redecide
from eval import demo
from ui.app import App, Request

PORT = 8766
HOST = {"host": f"127.0.0.1:{PORT}"}
EXPERT = "expert:Test Expert"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("demo")
    demo.reset(root)
    return root


@pytest.fixture
def root(built, tmp_path) -> Path:
    """A private copy of the built demo, so each test may change it."""
    out = tmp_path / "demo"
    shutil.copytree(built, out)
    return out


def _case(root: Path) -> cases.Case:
    (case,) = cases.list_cases(demo.cases_dir(root))
    return case


def _verdicts(conn: sqlite3.Connection) -> dict[str, str]:
    run = pipeline.last_run(conn)
    return dict(
        conn.execute(
            "SELECT claim_id, verdict FROM verdicts WHERE pipeline_run_id = ?", (run["run_id"],)
        )
    )


def _claim_ids() -> list[str]:
    return [*demo.load_gold(), *(d["claim_id"] for d in demo.load_demo_claims())]


def test_demo_matches_the_answer_key_except_the_claim_left_for_the_demo(root):
    gold = {g.claim_id: g.gold_verdict.value for g in demo.load_gold().values()}
    conn = connect(_case(root).db)
    got = _verdicts(conn)
    extra = {d["claim_id"] for d in demo.load_demo_claims()}
    assert set(got) == set(gold) | extra and not extra & set(gold)
    for claim_id in extra:
        del got[claim_id]
    for claim_id in demo.LEFT_OPEN:
        assert got[claim_id] == "unproven"
    assert {c: v for c, v in got.items() if c not in demo.LEFT_OPEN} == {
        c: v for c, v in gold.items() if c not in demo.LEFT_OPEN
    }


def test_the_live_step_makes_c05_supported_only_after_the_expert_accepts(root):
    conn = connect(_case(root).db)
    run = pipeline.last_run(conn)
    items = [
        e
        for e in pipeline.load_evidence(conn, run["manifest"]["C05"]["evidence"])
        if e.stance is Stance.SUPPORTS
    ]
    assert items and all(e.status is EvidenceStatus.OPEN for e in items)
    for e in items:
        actions.decide_evidence(conn, e.id, EvidenceStatus.ACCEPTED, EXPERT, "Read it myself.")
    redecide(conn, EXPERT)
    assert _verdicts(conn)["C05"] == "supported"
    basis = conn.execute(
        "SELECT supported_basis FROM verdicts WHERE claim_id = 'C05' AND pipeline_run_id = ?",
        (pipeline.last_run(conn)["run_id"],),
    ).fetchone()[0]
    assert basis == "confirmed"


def test_scripted_parts_are_named_on_the_screen_and_in_the_report(root):
    case = _case(root)
    conn = connect(case.db)
    run = pipeline.last_run(conn)
    assert run["fake"] and pipeline.scripted_demo(run)
    assert "Demo case: synthetic data, scripted labels." in render_report(conn)
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    page = app.handle(Request("GET", "/claims", {}, dict(HOST))).body.decode()
    assert "Demo case: synthetic data, scripted labels." in page
    reviewers = {r for (r,) in conn.execute("SELECT DISTINCT reviewer FROM evidence_reviews")}
    assert reviewers == {demo.SCRIPTED_EXPERT}
    labels = {r for (r,) in conn.execute("SELECT DISTINCT model_run_id FROM evidence_items")}
    assert labels == {demo.DEMO_RUN.id}


def test_every_claim_page_and_the_report_render(root):
    case = _case(root)
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    for claim_id in _claim_ids():
        resp = app.handle(Request("GET", "/claim", {"id": claim_id}, dict(HOST)))
        assert resp.status == 200, (claim_id, resp.body[:200])
    assert app.handle(Request("GET", "/report", {}, dict(HOST))).status == 200


def test_overview_groups_claims_and_says_why_each_unproven_claim_is_unproven(root):
    """The claims overview puts what waits on the expert first, then the findings, and gives each
    unproven claim a plain gap line read from the stored coverage. The report prints the same
    lines; no verdict changes."""
    from core.contracts import AssumptionKind as K
    from core.review.status import GAP_TEXT, GAP_TOPICS, claim_states

    case = _case(root)
    conn = connect(case.db)
    states = {st.claim.id: st for st in claim_states(conn)}
    assert states["C06"].gaps() == [K.MEANING]
    assert states["C18"].gaps() == [K.IDENTITY]
    assert states["D01"].gaps() == [K.COMPLETENESS]
    assert states["C05"].gaps() == []  # waits on the expert; every core assumption is covered
    assert all(not st.gaps() for st in states.values() if st.decision.verdict != Verdict.UNPROVEN)
    before = _verdicts(conn)

    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    page = app.handle(Request("GET", "/claims", {}, dict(HOST))).body.decode()
    sections = re.findall(r"<section class='(?:group|nextup)' id='([a-z]+)'>", page)
    assert sections == ["next", "con", "unp", "sup"]
    unp = page.split("<section class='group' id='unp'>", 1)[1].split("</section>", 1)[0]
    assert "id=C06" in unp and GAP_TEXT[K.MEANING] in unp
    assert "id=C05" in page.split("<section class='nextup' id='next'>", 1)[1].split("</section>")[0]
    assert "Verdict not yet confirmed" not in page
    assert "20 of 21" in page
    own = " ".join([*GAP_TEXT.values(), *GAP_TOPICS.values()]).lower()  # Baker's words, not claims'
    assert not any(w in own for w in ("guilty", "innocent", "leader", "deleted"))
    report = render_report(conn)
    assert html.escape(GAP_TEXT[K.COMPLETENESS], quote=True) in report
    assert _verdicts(conn) == before


def test_an_experts_own_reason_with_a_blocked_word_shows_as_written(root):
    """Guilty, innocent, leader and deleted are words Baker never uses. An expert may: their
    reasons and override notes show as typed, and the page and report still render."""
    case = _case(root)
    conn = connect(case.db)
    reason = "Nothing shows these messages were deleted."
    first, second = [
        r[0] for r in conn.execute("SELECT id FROM evidence_items WHERE stance = 'supports'")
    ][:2]
    actions.decide_evidence(conn, first, EvidenceStatus.ACCEPTED, EXPERT, reason)
    actions.decide_evidence(conn, second, EvidenceStatus.DISMISSED, EXPERT, reason)
    redecide(conn, EXPERT)
    actions.override_verdict(conn, "C03", Verdict.UNPROVEN, EXPERT, "Not the leader; " + reason)
    conn.close()
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    pages = [("/claim", {"id": c}) for c in _claim_ids()]
    pages += [("/evidence", {"id": first}), ("/evidence", {"id": second}), ("/report", {})]
    shown = ""
    for path, query in pages:
        resp = app.handle(Request("GET", path, query, dict(HOST)))
        assert resp.status == 200, (path, query, resp.body[:200])
        shown += resp.body.decode()
    assert f'<span class="said">{reason}</span>' in shown
    assert "Not the leader;" in shown


def test_the_demo_absence_claim_stays_unproven_because_a_curated_report_cannot_show_absence(
    root,
):
    """D01 (demo only): no WhatsApp record falls in the window, yet the check is inconclusive and
    the verdict unproven, because the searched reports are curated and cannot show absence."""
    conn = connect(_case(root).db)
    assert _verdicts(conn)["D01"] == "unproven"
    outcome, detail = conn.execute(
        "SELECT c.outcome, c.detail FROM check_results c JOIN assumptions a"
        " ON a.id = c.assumption_id WHERE a.claim_id = 'D01' AND c.check_name = 'absence'"
    ).fetchone()
    assert outcome == "inconclusive"
    assert detail.startswith("Found none.")
    assert "curated report, which cannot show that something is absent" in detail
    assert "Not found does not mean there was no contact" in detail
    reasons = conn.execute(
        "SELECT reasons_json FROM verdicts WHERE claim_id = 'D01' AND pipeline_run_id = ?",
        (pipeline.last_run(conn)["run_id"],),
    ).fetchone()[0]
    assert "is not covered" in reasons


def test_paired_demo_shows_what_the_curated_report_left_out_and_keeps_the_verdicts(root, tmp_path):
    conn = connect(_case(root).db)
    plain = _verdicts(conn)
    conn.close()  # Windows cannot delete an open database
    case, kind = demo.reset(root, paired=True)
    assert kind == "scripted-paired" and case.settings["paired"] is True
    conn = connect(case.db)
    assert _verdicts(conn) == plain
    files = {f for (f,) in conn.execute("SELECT file_name FROM sources WHERE kind != 'govdoc'")}
    conn.close()
    assert files == {"item1.xlsx", "item2.xlsx", "item1-full.ufdr"}
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    page = app.handle(Request("GET", "/selection", {}, dict(HOST))).body.decode()
    assert "Curated report against a larger source of the same phone" in page
    assert "or sunday works too" in page  # planted in the UFDR, left out of the curated report
    claim = app.handle(Request("GET", "/claim", {"id": "C05"}, dict(HOST))).body.decode()
    assert "within an hour of this claim" in claim
    _, kind = demo.reset(root)
    assert kind == "scripted"
    assert not _case(root).settings.get("paired")


def test_inputs_are_read_only_hashed_copies_and_the_log_verifies(root):
    case = _case(root)
    conn = connect(case.db)
    assert audit_log.verify_chain(conn)
    meta = json.loads(demo.CASE_META.read_text(encoding="utf-8"))
    shas = {s for (s,) in conn.execute("SELECT sha256 FROM sources WHERE kind != 'govdoc'")}
    assert shas == {s["sha256"] for s in meta["sources"]}
    files = list(case.inputs.iterdir())
    assert len(files) == 3
    assert all(not (f.stat().st_mode & 0o222) for f in files)


def test_reset_rebuilds_a_clean_demo(root):
    case = _case(root)
    conn = connect(case.db)
    e = conn.execute("SELECT id FROM evidence_items WHERE stance = 'supports' LIMIT 1").fetchone()
    actions.decide_evidence(conn, e[0], EvidenceStatus.ACCEPTED, EXPERT, "Demo click.")
    conn.close()
    demo.reset(root)
    conn = connect(_case(root).db)
    experts = conn.execute(
        "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer = ?", (EXPERT,)
    ).fetchone()[0]
    assert experts == 0


def test_reset_never_deletes_a_case_that_is_not_a_demo(root):
    real = cases.create_case(demo.cases_dir(root), "Somebody's case", EXPERT)
    with pytest.raises(SystemExit, match="not demo cases"):
        demo.reset(root)
    assert real.db.is_file()
    assert len(cases.list_cases(demo.cases_dir(root))) == 2


def test_a_saved_audit_becomes_the_demo_and_scripted_brings_the_script_back(root, tmp_path):
    source = tmp_path / "finished"
    shutil.copytree(_case(root).folder, source)
    demo.save_snapshot(root, source)
    case, kind = demo.reset(root)
    assert kind == "snapshot" and case.settings["demo"] == "snapshot"
    assert case.folder.name == demo.DEMO_FOLDER
    demo.drop_snapshot(root)
    _, kind = demo.reset(root)
    assert kind == "scripted"


def test_only_synthetic_case01_can_become_the_demo(root, tmp_path):
    source = tmp_path / "other"
    shutil.copytree(_case(root).folder, source)
    conn = connect(source / cases.DB_NAME)
    conn.execute("UPDATE sources SET sha256 = ? WHERE id = 'item1'", ("1" * 64,))
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit, match="not one of synthetic case01"):
        demo.save_snapshot(root, source)
    assert not demo.snapshot_dir(root).exists()


def test_cli_demo_build_only(tmp_path, monkeypatch, capsys):
    from cli.main import main

    monkeypatch.setenv(demo.DEMO_ROOT_ENV, str(tmp_path / "demo"))
    assert main(["demo", "--build-only"]) == 0
    out = capsys.readouterr().out
    assert "demo case ready" in out and "scripted labels" in out
    assert len(cases.list_cases(tmp_path / "demo" / "cases")) == 1


def test_cli_demo_paired_build_only(tmp_path, monkeypatch, capsys):
    from cli.main import main

    monkeypatch.setenv(demo.DEMO_ROOT_ENV, str(tmp_path / "demo"))
    assert main(["demo", "--build-only", "--paired"]) == 0
    assert "paired audit" in capsys.readouterr().out
    (case,) = cases.list_cases(tmp_path / "demo" / "cases")
    assert case.settings["paired"] is True


def test_a_claim_supported_on_ai_review_or_with_ai_dismissed_support_waits_on_the_expert(
    root, monkeypatch
):
    """Rules 0.3.0 never store an AI-reviewed supported verdict, but if a later rule version does,
    the overview must not file it under "An expert accepted the evidence" or count it as done.
    Support the AI reviewer dismissed, unseen by an expert, waits on the expert too."""
    import dataclasses

    from core.contracts import SupportedBasis
    from core.review.status import SUPPORTED_AI, claim_states
    from ui import pages

    case = _case(root)
    conn = connect(case.db)
    states = claim_states(conn)
    i = next(i for i, st in enumerate(states) if st.claim.id == "C01")
    ai = states[i].decision.model_copy(update={"supported_basis": SupportedBasis.AI_REVIEWED})
    states[i] = dataclasses.replace(states[i], decision=ai)
    j = next(i for i, st in enumerate(states) if st.claim.id == "C02")
    states[j] = dataclasses.replace(states[j], ai_dismissed=1)
    assert states[i].label == SUPPORTED_AI
    assert pages.needs_you(states[i]) and pages.needs_you(states[j])
    monkeypatch.setattr(pages, "queue", lambda conn: sorted(states, key=lambda s: s.priority))

    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    page = app.handle(Request("GET", "/claims", {}, dict(HOST))).body.decode()
    sup = page.split("<section class='group' id='sup'>", 1)[1].split("</section>", 1)[0]
    assert "id=C01" not in sup and "id=C02" not in sup
    assert html.escape(SUPPORTED_AI) not in sup
    assert "3 claims need you." in page and "18 of 21" in page
