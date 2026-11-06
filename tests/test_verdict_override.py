"""An expert override to Supported (core/review/actions.py override_verdict) on the demo case.

Supported needs the expert's own acceptance of the claim's support, and the verdict cites it.
Before this, an override to Supported on C05 (unproven, citing nothing) was stored with no cited
evidence, which the VerdictDecision contract refuses to load, so every page of the case failed.
A case that already holds such a row shows a page offering a verdict re-run instead."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core import pipeline
from core.bundle import export
from core.bundle.verify import FAIL, PASS, _override_support, verify_bundle
from core.casework import cases
from core.contracts import EvidenceStatus, Stance, Verdict
from core.db import connect
from core.review import actions
from core.review.actions import ReviewError
from eval import demo
from ui.app import App, Request

PORT = 8767
HOST = {"host": f"127.0.0.1:{PORT}"}
EXPERT = "expert:Test Expert"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("demo-override")
    demo.reset(root)
    return root


@pytest.fixture
def root(built, tmp_path) -> Path:
    out = tmp_path / "demo"
    shutil.copytree(built, out)
    return out


def _case(root: Path) -> cases.Case:
    (case,) = cases.list_cases(demo.cases_dir(root))
    return case


def _app(root: Path) -> App:
    app = App(home=demo.cases_dir(root), port=PORT, model_check=None)
    app.open_case(_case(root))
    app.expert = "Test Expert"
    return app


def _get(app: App, path: str, **query: str):  # noqa: ANN202
    return app.handle(Request("GET", path, query, dict(HOST)))


def _post(app: App, path: str, **form: str):  # noqa: ANN202
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def _row(conn, claim_id: str) -> tuple:  # noqa: ANN001
    run = pipeline.view_run(conn)
    return conn.execute(
        "SELECT verdict, supported_basis, cited_json, confirmed_by, override_note FROM verdicts"
        " WHERE claim_id = ? AND pipeline_run_id = ?",
        (claim_id, run["run_id"]),
    ).fetchone()


def _supports(conn, claim_id: str) -> list:  # noqa: ANN001, ANN202
    run = pipeline.view_run(conn)
    return [
        x
        for x in pipeline.load_evidence(conn, run["manifest"][claim_id]["evidence"])
        if x.stance is Stance.SUPPORTS
    ]


def _overrides(conn) -> int:  # noqa: ANN001
    return conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'verdict.override'"
    ).fetchone()[0]


def test_supported_without_accepted_support_is_refused_and_nothing_is_stored(root):
    conn = connect(_case(root).db)
    before, logged = _row(conn, "C05"), _overrides(conn)
    assert before[0] == "unproven" and json.loads(before[2])["evidence"] == []
    with pytest.raises(ReviewError, match="supporting evidence you accepted"):
        actions.override_verdict(conn, "C05", Verdict.SUPPORTED, EXPERT, "I read it myself.")
    assert _row(conn, "C05") == before and _overrides(conn) == logged


def test_the_screen_says_why_and_the_case_stays_up(root):
    app = _app(root)
    resp = _post(app, "/verdict", claim="C05", action="override", verdict="supported", note="ok")
    assert resp.status == 303
    msg, is_error = app.flash
    assert is_error and "Not recorded" in msg and "supporting evidence you accepted" in msg
    for path, query in (("/claim", {"id": "C05"}), ("/claims", {}), ("/", {}), ("/report", {})):
        assert _get(app, path, **query).status == 200, path


def test_an_open_or_ai_accepted_item_is_not_support_for_an_override(root):
    conn = connect(_case(root).db)
    items = _supports(conn, "C05")
    assert items and all(x.status is EvidenceStatus.OPEN for x in items)
    actions.decide_evidence(conn, items[0].id, EvidenceStatus.DISMISSED, EXPERT, "Not it.")
    with pytest.raises(ReviewError, match="supporting evidence you accepted"):
        actions.override_verdict(conn, "C05", Verdict.SUPPORTED, EXPERT, "I read it myself.")


def test_supported_after_accepting_cites_the_accepted_support(root, tmp_path):
    conn = connect(_case(root).db)
    items = _supports(conn, "C05")
    for x in items:
        actions.decide_evidence(conn, x.id, EvidenceStatus.ACCEPTED, EXPERT, "Read it myself.")
    actions.override_verdict(conn, "C05", Verdict.SUPPORTED, EXPERT, "Sent March 12 local.")
    verdict, basis, cited_json, by, note = _row(conn, "C05")
    cited = sorted(x.id for x in items)
    assert (verdict, basis, by, note) == ("supported", "confirmed", EXPERT, "Sent March 12 local.")
    assert json.loads(cited_json)["evidence"] == cited
    (payload,) = [
        json.loads(p)
        for (p,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = 'verdict.override'"
        )
    ]
    assert payload["cited_evidence_ids"] == cited and payload["was"] == "unproven"
    d = pipeline.load_verdict(conn, "C05", pipeline.view_run(conn)["run_id"])
    assert d is not None and d.cited_evidence_ids == tuple(cited)
    app = _app(root)
    for path, query in (("/claim", {"id": "C05"}), ("/claims", {}), ("/report", {})):
        assert _get(app, path, **query).status == 200, path
    # The bundle replays the override's citations from the log, and passes.
    path = export.export_bundle(conn, tmp_path / "b.zip", EXPERT, counsel_confirmed=True).path
    findings = verify_bundle(path)
    assert not [f for f in findings if f.level == FAIL and f.check == "verdicts"], findings
    assert any(f.level == PASS and "set by the expert" in f.detail for f in findings)
    # Overriding away again keeps the citations, as the bundle replays.
    actions.override_verdict(conn, "C05", Verdict.UNPROVEN, EXPERT, "Second thoughts.")
    assert _row(conn, "C05")[:2] == ("unproven", None)
    path = export.export_bundle(conn, tmp_path / "c.zip", EXPERT, counsel_confirmed=True).path
    findings = verify_bundle(path)
    assert not [f for f in findings if f.level == FAIL and f.check == "verdicts"], findings


def test_the_bundle_refuses_an_override_citing_support_nobody_accepted(root):
    conn = connect(_case(root).db)
    run = pipeline.view_run(conn)
    items = run["manifest"]["C05"]
    open_item = _supports(conn, "C05")[0].id
    log = [
        (s, at, a, act, json.loads(p))
        for s, at, a, act, p in conn.execute(
            "SELECT seq, at_utc, actor, action, payload_json FROM audit_log ORDER BY seq"
        )
    ]
    end = log[-1][0] + 1
    forged = [(EXPERT, "verdict.override", {"cited_evidence_ids": [open_item], "_seq": end})]
    assert "had not accepted" in _override_support(conn, log, items, forged)
    other = [(EXPERT, "verdict.override", {"cited_evidence_ids": ["ev:not-this"], "_seq": end})]
    assert "not the claim's" in _override_support(conn, log, items, other)


def test_an_already_stored_bad_row_shows_a_re_run_page_that_repairs_it(root):
    """A case where the old override stored Supported with nothing cited."""
    conn = connect(_case(root).db)
    run_id = pipeline.view_run(conn)["run_id"]
    with conn:
        conn.execute(
            "UPDATE verdicts SET verdict = 'supported', supported_basis = 'confirmed',"
            " confirmed_by = ?, override_note = 'old' WHERE claim_id = 'C05'"
            " AND pipeline_run_id = ?",
            (EXPERT, run_id),
        )
    with pytest.raises(pipeline.StoredVerdictInvalid, match="Re-run the verdicts"):
        pipeline.load_verdict(conn, "C05", run_id)
    app = _app(root)
    for path, query in (("/claim", {"id": "C05"}), ("/claims", {}), ("/", {})):
        resp = _get(app, path, **query)
        assert resp.status == 409, path
        assert "Re-run the verdicts" in resp.text and 'action="/redecide"' in resp.text
    resp = _post(app, "/redecide", next="/claim?id=C05")
    assert resp.status == 303 and not app.flash[1], app.flash
    assert _get(app, "/claim", id="C05").status == 200
    assert _row(conn, "C05")[0] == "unproven"  # the rules' verdict, in the new run


def test_the_command_line_names_the_repair_for_a_bad_row(root, tmp_path, capsys):
    from cli.main import main

    case = _case(root)
    conn = connect(case.db)
    run_id = pipeline.view_run(conn)["run_id"]
    with conn:
        conn.execute(
            "UPDATE verdicts SET verdict = 'supported', supported_basis = 'confirmed'"
            " WHERE claim_id = 'C05' AND pipeline_run_id = ?",
            (run_id,),
        )
    conn.close()
    assert main(["report", "--db", str(case.db), "--out", str(tmp_path / "r.html")]) == 2
    err = capsys.readouterr().err
    assert "breaks the verdict contract" in err and "mabillon redecide" in err
    assert main(["redecide", "--db", str(case.db), "--by", EXPERT]) == 0
    assert main(["report", "--db", str(case.db), "--out", str(tmp_path / "r.html")]) == 0


def test_a_supported_override_lapses_on_a_verdict_re_run(root):
    """The override cites support accepted on the old run, so a re-run never carries it, even
    when the rules decide the claim exactly as before; the claim waits for the expert again."""
    from core.review.redecide import redecide

    conn = connect(_case(root).db)
    items = _supports(conn, "C05")
    for x in items:
        actions.decide_evidence(conn, x.id, EvidenceStatus.ACCEPTED, EXPERT, "Read it myself.")
    actions.override_verdict(conn, "C05", Verdict.SUPPORTED, EXPERT, "Sent March 12 local.")
    for x in items:  # back to as the rules last saw it
        actions.decide_evidence(conn, x.id, EvidenceStatus.OPEN, EXPERT, "Look again.")
    result = redecide(conn, EXPERT)
    assert "C05" in result.lapsed and "C05" not in result.carried
    verdict, basis, cited_json, by, note = _row(conn, "C05")
    assert (verdict, basis, by, note) == ("unproven", None, None, None)
    assert json.loads(cited_json)["evidence"] == []
    assert _get(_app(root), "/claim", id="C05").status == 200
