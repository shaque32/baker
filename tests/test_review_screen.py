"""The expert review screen, the rules-only re-run and the report, on synthetic case01.

The case is audited with real structure (the case01 assumption spec, real retrieval and checks)
and a worst-case model: a labeler that calls every record support and an AI reviewer that
accepts everything. Under rules 0.2.0 that must leave every claim unproven until an expert
accepts evidence on the screen and re-runs the verdicts.
"""

from __future__ import annotations

import ast
import http.client
import json
import re
import shutil
import socket
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest

from cli.main import main as cli_main
from core import pipeline
from core.contracts import (
    EvidenceStatus,
    GoldClaim,
    ReviewDecision,
    ReviewerKind,
    Stance,
    SupportedBasis,
    Verdict,
    review_id,
)
from core.db import connect
from core.report.html import AWAITING_EXPERT, SUPPORTED_EXPERT, render_report, write_report
from core.review import actions, audit_log
from core.review.actions import ReviewError
from core.review.redecide import redecide
from core.review.status import claim_state, queue
from eval import run_pipeline
from eval.run_eval import load_jsonl
from ui.app import App, Request
from ui.server import make_server

RUN_TIME = datetime(2026, 10, 7, tzinfo=UTC)
EXPERT = "expert:Test Expert"
ROOT = Path(__file__).resolve().parents[1]
GOLD = load_jsonl(ROOT / "eval/gold/case01/gold.jsonl", GoldClaim)


def _spec() -> Path:
    signed = ROOT / "eval/gold/case01/assumptions.jsonl"
    return signed if signed.exists() else ROOT / "eval/probe_draft/case01_assumptions.jsonl"


def _filler(path: Path):  # noqa: ANN202
    from core.audit.assumptions import Proposal

    by_claim: dict[str, list] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            by_claim.setdefault(row["claim_id"], []).append(
                Proposal(row["template_id"], row["params"], row.get("is_core", True))
            )
    return lambda claim, allowed: by_claim.get(claim.id, [])


class EverythingSupports:
    """Worst-case labeler: every retrieved record supports, quoting the whole record."""

    def label(self, assumption, candidate):  # noqa: ANN001, ANN201
        from core.contracts import StanceLabel

        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance.SUPPORTS,
            quote=candidate.text,
            rationale="test: always supports",
            model_run_id="mr:test-stance",
        )


class AcceptsEverything:
    model_run_id = "mr:test-review"

    def review(self, assumption, item, context):  # noqa: ANN001, ANN201
        return ReviewDecision(
            id=review_id(item.id, 1),
            evidence_id=item.id,
            seq=1,
            reviewer_kind=ReviewerKind.AI,
            reviewer="ai:test-accepts-everything",
            status=EvidenceStatus.AI_ACCEPTED,
            reason="Test reviewer accepts everything.",
            model_run_id="mr:test-review",
            decided_at_utc=RUN_TIME,
        )


@pytest.fixture(scope="module")
def audited_case(tmp_path_factory) -> Path:
    from core.contracts import ModelRun

    path = tmp_path_factory.mktemp("screen") / "case01.db"
    conn = run_pipeline.build_case("case01", path)
    comps = pipeline.real_components(
        conn,
        replace={"labeler": EverythingSupports(), "reviewer": AcceptsEverything()},
        filler=_filler(_spec()),
    )
    comps.model_runs = (
        *comps.model_runs,
        *(
            ModelRun(
                id=f"mr:test-{p}",
                purpose=p,
                model_name=f"test-{p}",
                model_sha256="0" * 64,
                prompt_version="none",
                params={},
                seed=0,
                started_at_utc=RUN_TIME,
            )
            for p in ("stance", "review")
        ),
    )
    pipeline.run_audit(conn, comps, clock=lambda: RUN_TIME)
    conn.close()
    return path


@pytest.fixture
def db(audited_case, tmp_path) -> Path:
    copy = tmp_path / "case.db"
    shutil.copy(audited_case, copy)
    return copy


@pytest.fixture
def conn(db) -> sqlite3.Connection:
    c = connect(db)
    yield c
    c.close()


PORT = 8765
HOST = {"host": f"127.0.0.1:{PORT}"}


def get(app: App, path: str, **query: str):  # noqa: ANN201
    return app.handle(Request("GET", path, dict(query), dict(HOST)))


def post(app: App, path: str, headers: dict | None = None, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, {**HOST, **(headers or {})}, form))


def key_items(conn: sqlite3.Connection, claim_id: str) -> list[str]:
    gold = next(g for g in GOLD if g.claim_id == claim_id)
    st = claim_state(conn, claim_id)
    return [
        e.id
        for e in st.evidence
        if e.record_id in gold.key_evidence and e.stance == Stance.SUPPORTS
    ]


# ---------------------------------------------------------------- the rules decide, not the AI


def test_ai_acceptance_alone_never_makes_a_claim_supported(conn):
    states = queue(conn)
    assert states and all(s.decision.verdict != Verdict.SUPPORTED for s in states)
    awaiting = [s for s in states if s.label == AWAITING_EXPERT]
    assert awaiting, "AI-accepted support must show as awaiting expert review"
    assert all(s.ai_accepted > 0 for s in awaiting)
    result = redecide(conn, EXPERT)  # re-running the rules changes nothing without an expert
    assert all(d.verdict != Verdict.SUPPORTED for d in result.decisions)


def test_screen_never_shows_ai_reviewed_as_confirmed(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    page = get(app, "/claim", id="C05").text
    assert AWAITING_EXPERT in page and SUPPORTED_EXPERT not in page
    assert "ai_reviewed: AI-reviewed, not confirmed" in page
    assert "badge b-conf" not in page and "accepted by an expert</span>" not in page
    for path in ("/", "/claims"):
        assert SUPPORTED_EXPERT not in get(app, path).text

    (first, *rest) = key_items(conn, "C05")
    r = post(app, "/evidence/decide", id=first, status="accepted", reason="Seen in the sheet.")
    assert r.status == 303
    page = get(app, "/claim", id="C05").text
    assert page.count("badge b-conf") == 1  # only the item the expert accepted
    assert "ai_reviewed: AI-reviewed, not confirmed" in page
    # still not supported until the verdicts are re-run, and the screen says so
    assert AWAITING_EXPERT in page and "Verdicts are out of date" in page


def test_expert_flow_on_the_screen_reaches_expert_confirmed_supported(db, conn):
    app = App(db, port=PORT)
    # no reviewer name yet: nothing is recorded
    eid = key_items(conn, "C05")[0]
    post(app, "/evidence/decide", id=eid, status="accepted", reason="ok")
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind='expert'"
        ).fetchone()[0]
        == 0
    )
    assert "enter your name" in get(app, "/").text.lower()

    post(app, "/expert", name="Test Expert")
    for eid in key_items(conn, "C05"):
        post(app, "/evidence/decide", id=eid, status="accepted", reason="Matches the export.")
    assert claim_state(conn, "C05").decision.verdict == Verdict.UNPROVEN  # rules have not run
    r = post(app, "/redecide", next="/claims")
    assert r.status == 303 and r.header("Location") == "/claims"
    st = claim_state(conn, "C05")
    assert st.decision.verdict == Verdict.SUPPORTED
    assert st.decision.supported_basis == SupportedBasis.CONFIRMED
    assert st.label == SUPPORTED_EXPERT
    assert SUPPORTED_EXPERT in get(app, "/claim", id="C05").text

    post(app, "/verdict", claim="C05", action="confirm", note="")
    assert claim_state(conn, "C05").decision.confirmed_by == EXPERT
    post(app, "/verdict", claim="C06", action="override", verdict="contradicted", note="")
    assert "Not recorded" in get(app, "/").text  # an override needs a note
    post(app, "/verdict", claim="C06", action="override", verdict="contradicted", note="Reads x.")
    assert claim_state(conn, "C06").label == "Contradicted (expert override)"

    actions_logged = [
        r[0] for r in conn.execute("SELECT action FROM audit_log WHERE actor = ?", (EXPERT,))
    ]
    assert actions_logged.count("evidence.decide") == len(key_items(conn, "C05"))
    assert "verdict.confirm" in actions_logged and "verdict.override" in actions_logged
    assert audit_log.verify_chain(conn)


def test_claims_and_stipulations_from_the_screen(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    para = conn.execute("SELECT paragraph_id FROM claims WHERE id = 'C01'").fetchone()[0]
    r = post(app, "/claim/add", id="C21", paragraph=para, type="event", text='Sent "ok".')
    assert r.header("Location") == "/claim?id=C21"
    assert "Not audited" in get(app, "/claim", id="C21").text
    post(app, "/claim/edit", claim="C02", status="edited", text="New wording.")
    post(app, "/claim/edit", claim="C03", status="removed")
    result = redecide(conn, EXPERT)
    assert "C21" in result.skipped and "C02" in result.skipped and "C03" not in result.skipped
    assert {d.claim_id for d in result.decisions}.isdisjoint({"C02", "C03", "C21"})

    stip = conn.execute("SELECT id FROM stipulations ORDER BY id").fetchone()[0]
    post(app, "/stipulation/withdraw", id=stip)
    assert (
        conn.execute("SELECT status FROM stipulations WHERE id = ?", (stip,)).fetchone()[0]
        == "rejected"
    )
    assert "Verdicts are out of date" in get(app, "/").text
    dev = conn.execute("SELECT subject_id FROM stipulations WHERE id = ?", (stip,)).fetchone()[0]
    post(app, "/stipulate", device=dev, person="Daniel Petrov")
    assert (
        conn.execute("SELECT status FROM stipulations WHERE id = ?", (stip,)).fetchone()[0]
        == "confirmed"
    )
    assert audit_log.verify_chain(conn)


def test_redecide_keeps_the_trail_and_the_test_run_flag(conn):
    first = pipeline.last_run(conn)
    a = redecide(conn, EXPERT)
    b = redecide(conn, EXPERT)
    run = pipeline.last_run(conn)
    assert run["run_id"] == b.run_id and run["mode"] == "rules_only"
    assert run["from_run"] == a.run_id and run["evidence_from_run"] == first["run_id"]
    assert run["fake"] == first["fake"]
    assert run["manifest"] == first["manifest"]
    assert pipeline.predictions(conn)  # the eval reads a re-decided run like any other
    with pytest.raises(ReviewError):
        redecide(conn, "someone")


def test_redecide_stops_on_a_broken_invariant_and_stores_nothing(conn, monkeypatch):
    from core.audit import rules
    from core.audit.invariants import InvariantViolation

    real = rules.decide_verdict

    def lying(*args, **kw):  # noqa: ANN002, ANN003, ANN202
        d = real(*args, **kw)
        return d.model_copy(update={"rule_version": ""})

    monkeypatch.setattr(rules, "decide_verdict", lying)
    before = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    with pytest.raises(InvariantViolation):
        redecide(conn, EXPERT)
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == before
    assert (
        conn.execute("SELECT status FROM pipeline_runs ORDER BY started_at_utc DESC").fetchone()[0]
        == "failed"
    )


# ---------------------------------------------------------------- local only, offline


def test_requests_from_other_sites_are_refused(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    eid = key_items(conn, "C05")[0]
    form = {"id": eid, "status": "accepted", "reason": "x"}
    assert post(app, "/evidence/decide", token="wrong", **form).status == 403
    evil = {"origin": "http://evil.example"}
    assert post(app, "/evidence/decide", headers=evil, **form).status == 403
    cross = {"sec-fetch-site": "cross-site"}
    assert post(app, "/evidence/decide", headers=cross, **form).status == 403
    rebound = Request("GET", "/", {}, {"host": "evil.example:8765"})
    assert app.handle(rebound).status == 400
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind='expert'"
        ).fetchone()[0]
        == 0
    )
    ok = {"origin": f"http://127.0.0.1:{PORT}", "sec-fetch-site": "same-origin"}
    assert post(app, "/evidence/decide", headers=ok, **form).status == 303
    assert post(app, "/evidence/decide", next="//evil.example", **form).header("Location") == "/"


PAGES = [("/", {}), ("/claims", {}), ("/claim", {"id": "C05"}), ("/claim/new", {}),
         ("/log", {}), ("/report", {})]  # fmt: skip


def test_pages_load_nothing_from_outside_and_run_no_script(db, conn):
    app = App(db, expert="Test Expert", port=PORT)
    eid = key_items(conn, "C05")[0]
    for path, query in [*PAGES, ("/evidence", {"id": eid})]:
        r = get(app, path, **query)
        assert r.status == 200, path
        csp = r.header("Content-Security-Policy")
        assert "default-src 'none'" in csp and "script" not in csp
        assert r.header("Cache-Control") == "no-store"
        page = r.text.lower()
        assert "<script" not in page and " src=" not in page and "@import" not in page
        assert not re.search(r"(href|action)\s*=\s*['\"]?\s*(https?:)?//", page), path
        assert not re.search(r"url\(", page), path


def test_the_whole_flow_makes_no_network_call(db, conn, monkeypatch):
    calls: list[object] = []

    def refuse(*args, **kw):  # noqa: ANN002, ANN003, ANN202
        calls.append(args)
        raise OSError("network call attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    app = App(db, port=PORT)
    post(app, "/expert", name="Test Expert")
    for eid in key_items(conn, "C05"):
        post(app, "/evidence/decide", id=eid, status="accepted", reason="ok")
        get(app, "/evidence", id=eid)
    post(app, "/redecide")
    for path, query in PAGES:
        get(app, path, **query)
    get(app, "/report", download="1")
    assert calls == []


SERVER_FILES = ["ui", "core/review", "core/report"]
NETWORK_MODULES = {"socket", "urllib.request", "http.client", "requests", "httpx", "ssl",
                   "ftplib", "smtplib", "webbrowser"}  # fmt: skip


def test_screen_code_imports_no_network_client():
    for folder in SERVER_FILES:
        for py in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                bad = [n for n in names if n in NETWORK_MODULES]
                assert not bad, f"{py}: imports {bad}"


def test_server_binds_loopback_only_and_answers(db):
    server = make_server(db, port=0, expert="Test Expert")
    try:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"
        t = threading.Thread(target=server.handle_request)
        t.start()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/claims")
        r = c.getresponse()
        body = r.read().decode()
        t.join(10)
        assert r.status == 200 and "Claims queue" in body
        t = threading.Thread(target=server.handle_request)
        t.start()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request(
            "POST",
            "/redecide",
            urlencode({"token": "forged"}),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert c.getresponse().status == 403
        t.join(10)
    finally:
        server.server_close()


# ---------------------------------------------------------------- report


def test_report_has_awaiting_versions_coverage_log_and_print_layout(conn, tmp_path):
    html = render_report(conn)
    assert AWAITING_EXPERT in html and "awaiting expert review.</strong>" in html
    for sha in [r[0] for r in conn.execute("SELECT sha256 FROM sources")]:
        assert sha in html
    assert "<h2>Versions</h2>" in html and "Verdict rules" in html and "test-stance" in html
    assert "<h2>Searches and coverage</h2>" in html and "absence" in html
    assert "Hash chain verified" in html and "Pipeline runs: completed 1" in html
    assert "@media print" in html and "thead { display: table-header-group; }" in html
    write_report(conn, tmp_path / "r.html")  # passes the forbidden-word check


def test_report_after_expert_review_says_expert_confirmed(conn):
    for eid in key_items(conn, "C05"):
        actions.decide_evidence(conn, eid, EvidenceStatus.ACCEPTED, EXPERT, "Matches.")
    assert "expert evidence decisions were made after this run" in render_report(conn)
    redecide(conn, EXPERT)
    html = render_report(conn)
    assert f'"verdict v-sup">{SUPPORTED_EXPERT}' in html
    assert "re-decided the verdicts with the rules only" in html


def test_cli_redecide(db, capsys):
    assert cli_main(["redecide", "--db", str(db), "--by", EXPERT]) == 0
    assert "rules only" in capsys.readouterr().out
    assert cli_main(["redecide", "--db", str(db), "--by", "nobody"]) == 2
