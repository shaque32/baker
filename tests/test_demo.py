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
from core.audit import challenge
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
    extra = [*demo.load_demo_claims(), *demo.load_agent_claims()]
    return [*demo.load_gold(), *(d["claim_id"] for d in extra)]


def test_demo_matches_the_answer_key_except_the_claim_left_for_the_demo(root):
    gold = {g.claim_id: g.gold_verdict.value for g in demo.load_gold().values()}
    conn = connect(_case(root).db)
    got = _verdicts(conn)
    extra = {d["claim_id"] for d in [*demo.load_demo_claims(), *demo.load_agent_claims()]}
    assert set(got) == set(gold) | extra and not extra & set(gold)
    # The agent's demo claims: D02's accepted proposal ends supported, D03's waits untested.
    assert (got["D02"], got["D03"]) == ("supported", "unproven")
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


def test_the_live_step_shows_the_challenge_steps_find_on_c16(root):
    """The challenge step runs in the demo as in the product: on C16 it finds a message saying
    someone else used the account, marked as its find on the screen and in the report, and left
    open for the person giving the demo. Accepting the doubt leaves C16 unproven."""
    case = _case(root)
    conn = connect(case.db)
    run = pipeline.last_run(conn)
    audit = conn.execute(
        "SELECT config_json FROM pipeline_runs WHERE id = ?", (run["evidence_from_run"],)
    ).fetchone()[0]
    assert json.loads(audit)["challenge"] == challenge.VERSION
    found = challenge.found_items(conn, run)  # the audit's finds, read through the re-run
    items = pipeline.load_evidence(conn, run["manifest"]["C16"]["evidence"])
    doubt = [e for e in items if e.stance is Stance.COMPLICATES]
    assert {e.record_id for e in doubt} == demo.CHALLENGE_DOUBT["C16"]
    assert all(e.status is EvidenceStatus.OPEN for e in doubt)
    assert found and found <= {e.id for e in doubt}
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    page = app.handle(Request("GET", "/claim", {"id": "C16"}, dict(HOST))).body.decode()
    assert page.count(challenge.FOUND_MARK) == len(found)
    report = render_report(conn)
    assert "Found by the challenge step" in report and f"ran ({challenge.VERSION})" in report
    assert _verdicts(conn)["C16"] == "unproven"
    for e in doubt:
        actions.decide_evidence(conn, e.id, EvidenceStatus.ACCEPTED, EXPERT, "Read it myself.")
    redecide(conn, EXPERT)
    assert _verdicts(conn)["C16"] == "unproven"


def test_the_agents_proposal_on_d02_was_accepted_and_reaches_supported(root):
    """D02's first answer writes the phone as an account; code refuses it. The agent's answer,
    told why, passes code's checks; the scripted examiner accepted it, code's contact check
    passed and the expert accepted the record. The screen and the report say the assumption was
    proposed by the agent and accepted by an examiner."""
    from core.audit import testability

    case = _case(root)
    conn = connect(case.db)
    run = pipeline.last_run(conn)
    audit = json.loads(
        conn.execute(
            "SELECT config_json FROM pipeline_runs WHERE id = ?", (run["evidence_from_run"],)
        ).fetchone()[0]
    )
    assert audit["testability"] == testability.VERSION
    repairs = [
        json.loads(p)
        for (p,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq",
            (testability.REPAIR_ACTION,),
        )
    ]
    assert {r["claim_id"] for r in repairs} == {"D02", "D03"}  # the step ran on these only
    assert all(r["check"] == testability.CLAIM_CHECK and r["sheet"] is None for r in repairs)
    d02 = next(r for r in repairs if r["claim_id"] == "D02")
    assert any("matches no account" in why for why in d02["refused_before"])
    assert d02["outcome"] == "proposed" and d02["assumption_ids"] == sorted(
        run["manifest"]["D02"]["assumptions"]
    )
    assert testability.accepted_repairs(conn) == dict.fromkeys(
        d02["assumption_ids"], demo.AGENT_EXAMINER
    )
    assert _verdicts(conn)["D02"] == "supported"
    mark = "Proposed by agent, accepted by examiner (Demo examiner (scripted from the demo claims))"
    assert mark in render_report(conn)
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    page = app.handle(Request("GET", "/claim", {"id": "D02"}, dict(HOST))).body.decode()
    assert html.escape(mark, quote=True) in page
    assert "<section class='agent'" not in page  # used, so no card


def test_the_presenter_accepts_d03s_proposal_on_its_card_and_the_next_audit_tests_it(root):
    """D03's first answer names a call with no party; code refuses it. The agent's proposal
    waits on D03's page. The presenter accepts it there with a reason, which changes nothing
    until the next audit; that audit tests D03 with it."""
    from core.audit import testability
    from core.review.status import claim_state

    case = _case(root)
    conn = connect(case.db)
    assert _verdicts(conn)["D03"] == "unproven" and claim_state(conn, "D03").untested
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    app.expert = "Test Expert"
    page = app.handle(Request("GET", "/claim", {"id": "D03"}, dict(HOST))).body.decode()
    card = page.split("<section class='agent' id='agent'>", 1)[1].split("</section>", 1)[0]
    assert testability.PROPOSED_MARK in card and "Waiting for you" in card
    assert "A call between" in card and card.count("value='accept'") == 1
    (x,) = [p for c, p in testability.proposals(conn, pipeline.last_run(conn)).items()
            if c == "D03"]  # fmt: skip
    form = {
        "token": app.token,
        "claim": "D03",
        "run": x.run_id,
        "attempt": str(x.attempt),
        "decision": "accept",
        "reason": "The number is the one the claim writes.",
        "next": "/claim?id=D03",
    }
    app.handle(Request("POST", "/testability/decide", {}, dict(HOST), form))
    page = app.handle(Request("GET", "/claim", {"id": "D03"}, dict(HOST))).body.decode()
    assert "Accepted by Test Expert" in page
    assert _verdicts(conn)["D03"] == "unproven"  # nothing changes until the next audit
    pipeline.run_audit(conn, demo._components(conn, demo.load_gold()))
    st = claim_state(conn, "D03")
    assert not st.untested and [a.id for a in st.assumptions] == x.assumption_ids
    assert "Proposed by agent, accepted by examiner (Test Expert)" in render_report(conn)


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
    assert reviewers == {demo.SCRIPTED_EXPERT, demo.AGENT_EXAMINER}
    purposes = dict(conn.execute("SELECT id, model_name FROM model_runs"))
    for mr in (demo.DEMO_RUN, demo.DEMO_FILLER_RUN, demo.DEMO_AGENT_RUN):
        assert mr.id in purposes and "scripted" in purposes[mr.id]
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
    from core.review.status import AGENT_STEP, GAP_TEXT, GAP_TOPICS, claim_states

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
    assert sections == ["next", "you", "con", "unp", "sup"]  # C16's open doubt waits on you
    you = page.split("<section class='group' id='you'>", 1)[1].split("</section>", 1)[0]
    assert "id=C16" in you and "id=C05" in you
    unp = page.split("<section class='group' id='unp'>", 1)[1].split("</section>", 1)[0]
    assert "id=C06" in unp and GAP_TEXT[K.MEANING] in unp
    # Next up: D03, the agent's proposal waiting for the person giving the demo.
    nextup = page.split("<section class='nextup' id='next'>", 1)[1].split("</section>")[0]
    assert "id=D03" in nextup and html.escape(AGENT_STEP, quote=True) in nextup
    assert "Verdict not yet confirmed" not in page
    assert "20 of 23" in page
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
    assert "5 claims need you." in page and "18 of 23" in page  # C05, C16, D03 and these two


def test_gap_lines_follow_the_stored_coverage_until_it_is_stale_and_tiles_have_destinations(root):
    """A part the stored verdict left uncovered is "not established" even while support for it
    waits on the expert; after a later change the line says the verdict is not current instead;
    and each count tile links to a section that exists."""
    import dataclasses

    from core.contracts import AssumptionKind as K
    from core.contracts import EvidenceStatus as S
    from core.review.status import claim_states

    case = _case(root)
    conn = connect(case.db)
    st = next(s for s in claim_states(conn) if s.claim.id == "C06")
    meaning = next(a.id for a in st.assumptions if a.kind == K.MEANING)
    item = next(
        x for x in st.evidence if x.assumption_id == meaning and x.stance == Stance.SUPPORTS
    )
    opened = [
        x.model_copy(update={"status": S.OPEN}) if x.id == item.id else x for x in st.evidence
    ]
    reviewers = {k: v for k, v in st.last_reviewer.items() if k != item.id}
    waiting = dataclasses.replace(st, evidence=opened, last_reviewer=reviewers)
    assert st.gaps() == [K.MEANING] and waiting.gaps() == [K.MEANING]
    from core.review.status import STALE
    from ui import pages

    for flag in ("decided_after_run", "edited_after_run", "case_changed_after_run"):
        stale = dataclasses.replace(st, **{flag: True})
        assert stale.gaps() == [] and stale.explain_lines() == [STALE], flag
        assert pages.needs_you(stale), flag
    c01 = next(s for s in claim_states(conn) if s.claim.id == "C01")  # supported by the rules
    c01_stale = dataclasses.replace(c01, case_changed_after_run=True)
    assert pages.needs_you(c01_stale) and c01_stale.explain_lines() == [STALE]
    assert STALE[1] in pages._claim_row(c01_stale, "you")
    assert pages._group(c01_stale) == "you"
    # every core assumption covered, yet unproven by another rule: one line points to the rule
    from core.review.status import OTHER_RULE

    covered = tuple(cv.model_copy(update={"covered": True}) for cv in st.decision.coverage)
    full = dataclasses.replace(st, decision=st.decision.model_copy(update={"coverage": covered}))
    assert full.gaps() == [] and full.explain_lines() == [OTHER_RULE]
    # a claim that also waits on the expert still says what else leaves it unproven
    from core.review.status import GAP_TEXT
    from ui import pages

    row = pages._claim_row(dataclasses.replace(st, ai_dismissed=1), "you")
    assert html.escape(GAP_TEXT[K.MEANING], quote=True) in row

    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    page = app.handle(Request("GET", "/claims", {}, dict(HOST))).body.decode()
    hrefs = re.findall(r"<a class='tile [^']*' href='#([a-z]+)'>", page)
    assert hrefs == ["next", "con", "unp", "sup"]
    for h in hrefs:
        assert f"id='{h}'>" in page
    # the claim page shows the same lines, including "Not current" after an identity change
    c06 = app.handle(Request("GET", "/claim", {"id": "C06"}, dict(HOST))).body.decode()
    assert html.escape(GAP_TEXT[K.MEANING], quote=True) in c06
    from datetime import UTC, datetime

    from core.review import audit_log

    with conn:
        audit_log.append(conn, datetime.now(UTC), EXPERT, "identity.confirm", {})
    c01_page = app.handle(Request("GET", "/claim", {"id": "C01"}, dict(HOST))).body.decode()
    assert html.escape(STALE[1], quote=True) in c01_page
    # a run without verdict rules decided nothing: not audited, not a gap in the data
    pending = dataclasses.replace(
        st,
        decision=st.decision.model_copy(
            update={"reasons": (*st.decision.reasons, pipeline.RULES_PENDING_REASON)}
        ),
    )
    assert pages._group(pending) == "not"
    assert not pages.needs_you(dataclasses.replace(pending, ai_dismissed=1))
    assert dataclasses.replace(pending, case_changed_after_run=True).explain_lines() == []


def test_an_identity_change_stays_not_current_through_a_rules_only_rerun(root):
    """A rules-only re-run reuses the full audit's checks and searches, so an identity or person
    change after that audit keeps the verdicts not current; a stipulation it reloads does not."""
    from datetime import UTC, datetime, timedelta

    from core.review import audit_log
    from core.review.status import case_changed_after

    conn = connect(_case(root).db)
    now = datetime.now(UTC)
    with conn:
        audit_log.append(conn, now, EXPERT, "stipulation.set", {"test": True})
    assert case_changed_after(conn, pipeline.view_run(conn))
    redecide(conn, EXPERT, clock=lambda: now + timedelta(minutes=1))
    assert not case_changed_after(conn, pipeline.view_run(conn))
    with conn:  # a proposed link confirms nothing but widens what the audit searches
        audit_log.append(conn, now + timedelta(minutes=2), "system", "identity.propose", {})
    redecide(conn, EXPERT, clock=lambda: now + timedelta(minutes=3))
    run = pipeline.view_run(conn)
    assert run["evidence_from_run"] != run["run_id"]
    assert case_changed_after(conn, run)


def test_the_claim_page_leads_with_what_has_to_be_true_and_shows_records_in_conversation(root):
    """The checklist reads the stored coverage, records show among their neighbours with the
    verified quote, and the rules' tables stay on the page, folded."""
    case = _case(root)
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    c06 = app.handle(Request("GET", "/claim", {"id": "C06"}, dict(HOST))).body.decode()
    truths = c06.split("<section class='truths'>", 1)[1].split("</section>", 1)[0]
    assert "What has to be true" in truths and "<li class='no'>" in truths
    assert "Meaning of words" in truths and "Not established" in truths
    assert c06.index("<section class='truths'>") < c06.index("<h2 id='evidence'>")
    working = c06.split("<details class='working'>", 1)[1].split("</details>", 1)[0]
    assert "Covered (computed by the rules)" in working and "What was searched" in working
    c05 = app.handle(Request("GET", "/claim", {"id": "C05"}, dict(HOST))).body.decode()
    assert "<div class='thread mini'>" in c05 and "UNDER REVIEW" in c05
    assert "Records found (derived)" in c05 and "Quoted:" in c05
    for page in (c05, c06):  # Baker's own words in the checklist
        truths = page.split("<section class='truths'>", 1)[1].split("</section>", 1)[0]
        text = re.sub(r"<[^>]+>", " ", truths).lower()
        for word in ("guilty", "innocent", "leader", "deleted"):
            assert word not in text, word


def test_the_checklist_leads_the_alternatives_and_cards_share_one_read_per_thread(root):
    from core.audit.context import build_context

    case = _case(root)
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    c16 = app.handle(Request("GET", "/claim", {"id": "C16"}, dict(HOST))).body.decode()
    assert "Other explanations" in c16
    assert c16.index("<section class='truths'>") < c16.index("Other explanations")
    conn = connect(case.db)
    rid = conn.execute("SELECT id FROM messages ORDER BY id LIMIT 1").fetchone()[0]
    threads: dict[str, list[str]] = {}
    assert build_context(conn, rid, 1, threads=threads) == build_context(conn, rid, 1)
    assert len(threads) == 1


def test_tabs_come_in_three_groups_and_the_case_page_leads_with_the_audit(root):
    """The review tabs first, then tools to look closer, then set-up; the case page opens on
    what waits on the expert, with the custody hashes one click away."""
    from ui import pages

    case = _case(root)
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(case)
    home = app.handle(Request("GET", "/", {}, dict(HOST))).body.decode()
    nav = home.split("<nav class='tabs'>", 1)[1].split("</nav>", 1)[0]
    hrefs = re.findall(r"<a href='([^']*)'", nav)
    tabs = [h for g in pages.TAB_GROUPS for h, _ in g] + ["/help"]
    assert hrefs[-len(tabs) :] == tabs
    assert nav.count("class='sep'") >= 2 and "class=on>Case</a>" in nav
    assert home.index("<div class='casestatus'>") < home.index("<details class='custody'>")
    custody = home.split("<details class='custody'>", 1)[1].split("</details>", 1)[0]
    assert "<h2>Sources</h2>" in custody and "SHA-256" in custody
    assert "claim(s) need you</a>" in home
    from core.review.status import claim_states

    status = home.split("<div class='casestatus'>", 1)[1].split("</div>", 1)[0]
    for st in claim_states(connect(case.db)):  # the same pill styles as everywhere else
        pill = f"<span class='verdict {pages._vcls(st)}'>{html.escape(st.label, quote=True)}"
        assert pill in status, st.claim.id
