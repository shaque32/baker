"""Starting a case in the browser: new case, file import, claims, owners, background audit.

Synthetic case01 end to end on the screen, with stand-ins for the local model: a claim
extractor on core.llm.runtime.FakeModel, and the audit with the signed assumption sheet, real
retrieval, checks and rules, and a labeler that calls every record support. Under rules 0.2.0
that must leave every claim unproven until an expert accepts evidence.
"""

from __future__ import annotations

import ast
import hashlib
import html
import io
import json
import os
import stat
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core import pipeline
from core.casework import cases, jobs
from core.casework.model_check import check_model
from core.claims import extract
from core.contracts import (
    GoldClaim,
    ModelRun,
    Stance,
    StanceLabel,
    Verdict,
)
from core.db import connect
from core.llm.runtime import FakeModel
from core.report.html import render_report
from core.review import audit_log, status
from core.review.status import LABELING_INCOMPLETE, claim_state
from eval import run_pipeline
from eval.run_eval import load_jsonl
from ui import upload
from ui.app import App, Request

ROOT = Path(__file__).resolve().parents[1]
GOLD = load_jsonl(ROOT / "eval/gold/case01/gold.jsonl", GoldClaim)
PORT = 8765
HOST = {"host": f"127.0.0.1:{PORT}"}
NOW = datetime(2026, 10, 12, tzinfo=UTC)


def _spec() -> Path:
    signed = ROOT / "eval/gold/case01/assumptions.jsonl"
    return signed if signed.exists() else ROOT / "eval/probe_draft/case01_assumptions.jsonl"


# ---------------------------------------------------------------- stand-ins for the model


class Supports:
    """Labels every candidate support, quoting the whole record. `gate` lets a test hold the
    labeler inside a claim (the audit is then mid-claim, doing model work)."""

    def __init__(self, gate: threading.Event | None = None, hold_on: str | None = None):
        self.gate, self.hold_on = gate, hold_on
        self.waiting = threading.Event()

    def label(self, assumption, candidate):  # noqa: ANN001, ANN201
        if self.gate is not None and assumption.claim_id == self.hold_on:
            self.waiting.set()
            assert self.gate.wait(30)
        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance.SUPPORTS,
            quote=candidate.text,
            rationale="test: always supports",
            model_run_id="mr:test-stance",
        )


def components_for(labeler: Supports):  # noqa: ANN201
    def build(conn, ai_review):  # noqa: ANN001, ANN202
        comps = pipeline.real_components(
            conn,
            replace={"labeler": labeler},
            filler=run_pipeline.spec_filler(_spec(), conn),
        )
        comps.model_runs = (
            *comps.model_runs,
            ModelRun(
                id="mr:test-stance",
                purpose="stance",
                model_name="test-stance",
                model_sha256="0" * 64,
                prompt_version="none",
                params={},
                seed=0,
                started_at_utc=NOW,
            ),
        )
        return comps

    return build


def proposes(prompt: str) -> str:
    if "Marc Garage" in prompt:
        return json.dumps(
            {
                "claims": [
                    {
                        "text": 'Item 1 contains a contact named "Marc Garage".',
                        "claim_type": "identity",
                        "span": "Marc Garage",
                    }
                ]
            }
        )
    return json.dumps({"claims": []})


def extractor_for(conn):  # noqa: ANN001, ANN201
    return extract.create(conn, model=FakeModel(name="fake-claims", respond=proposes))


# ---------------------------------------------------------------- helpers


def get(app: App, path: str, **query: str):  # noqa: ANN201
    return app.handle(Request("GET", path, dict(query), dict(HOST)))


def post(app: App, path: str, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def multipart(fields: dict[str, str], name: str, data: bytes) -> tuple[bytes, str]:
    b = "baker-test-boundary-7d1"
    parts = [
        f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in fields.items()
    ]
    parts.append(
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def send_file(app: App, path: Path, kind: str, token: str | None = None, name: str = ""):  # noqa: ANN201
    body, ctype = multipart(
        {"token": token or app.token, "kind": kind}, name or path.name, path.read_bytes()
    )
    req = Request("POST", "/case/import", {}, {**HOST, "content-type": ctype})
    return app.handle_upload(req, io.BytesIO(body), len(body))


def flash(app: App) -> str:
    return get(app, "/setup").text


def wait(job: jobs.Job, timeout: float = 60) -> None:
    end = time.monotonic() + timeout
    while job.running and time.monotonic() < end:
        time.sleep(0.02)
    assert not job.running, f"{job.kind} still running: {job.message}"


@pytest.fixture(scope="module")
def inputs(tmp_path_factory) -> dict[str, Path]:
    meta = run_pipeline.ensure_reports("case01")
    folder = tmp_path_factory.mktemp("originals")
    out = {s["source_id"]: run_pipeline.synthetic_dir("case01") / s["file"] for s in
           meta["sources"]}  # fmt: skip
    out["affidavit"] = run_pipeline.render_affidavit_pdf("case01", folder / "affidavit.pdf")
    return out


@pytest.fixture
def app(tmp_path) -> App:
    return App(
        home=tmp_path / "cases",
        port=PORT,
        components_for=components_for(Supports()),
        extractor_for=extractor_for,
        model_check=None,
    )


def _make_case(app: App, inputs: dict[str, Path]) -> cases.Case:
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="United States v. Petrov (synthetic)")
    assert app.case is not None
    assert send_file(app, inputs["affidavit"], "govdoc").status == 303
    for sid in ("item1", "item2"):
        assert send_file(app, inputs[sid], "report").status == 303
    return app.case


def _add_gold_claims(app: App, conn) -> None:  # noqa: ANN001
    from core.claims.propose import load_paragraphs

    paras = load_paragraphs(conn)
    for gc in GOLD:
        para = run_pipeline.paragraph_for(paras, gc)
        r = post(app, "/claim/add", id=gc.claim_id, paragraph=para.id, type=gc.claim_type,
                 text=gc.text)  # fmt: skip
        assert r.status == 303


def _stipulate(app: App) -> None:
    meta = json.loads((run_pipeline.synthetic_dir("case01") / "case.json").read_text())
    for d in meta["devices"]:
        post(app, "/stipulate", device=f"dev:{d['source_id']}", person=d["owner"], next="/setup")


# ---------------------------------------------------------------- new case and import


def test_no_case_open_sends_the_expert_to_the_case_list(app):
    r = get(app, "/")
    assert r.status == 303 and r.header("Location") == "/cases"
    assert "New case" in get(app, "/cases").text
    post(app, "/case/new", name="X")  # no name yet: nothing is made
    assert app.case is None and not list((app.home or Path()).glob("*/case.db"))


def test_import_copies_hashes_and_makes_each_file_read_only(app, inputs):
    case = _make_case(app, inputs)
    conn = connect(case.db)
    rows = {
        r[0]: r for r in conn.execute("SELECT id, kind, fidelity, file_name, sha256 FROM sources")
    }
    for sid in ("item1", "item2"):
        assert rows[sid][4] == hashlib.sha256(inputs[sid].read_bytes()).hexdigest()
        assert rows[sid][2] == "curated_report"
    gov = [r for r in rows.values() if r[1] == "govdoc"]
    assert (
        len(gov) == 1 and gov[0][4] == hashlib.sha256(inputs["affidavit"].read_bytes()).hexdigest()
    )
    copies = sorted(p.name for p in case.inputs.iterdir())
    assert copies == sorted([inputs["item1"].name, inputs["item2"].name, "affidavit.pdf"])
    for p in case.inputs.iterdir():
        assert stat.S_IMODE(p.stat().st_mode) & 0o222 == 0, f"{p.name} is writable"
        assert p.read_bytes() == inputs[p.stem if p.suffix == ".xlsx" else "affidavit"].read_bytes()
    page = get(app, "/setup").text
    for sid in ("item1", "item2"):
        assert rows[sid][4] in page
    assert "curated report" in page
    imports = conn.execute("SELECT payload_json FROM audit_log WHERE action = 'case.import'")
    logged = [json.loads(p)["sha256"] for (p,) in imports]
    assert sorted(logged) == sorted(r[4] for r in rows.values())
    assert audit_log.verify_chain(conn)


def test_refused_uploads_store_nothing_and_leave_no_file(app, inputs):
    case = _make_case(app, inputs)
    before = sorted(case.inputs.iterdir())
    assert send_file(app, inputs["item1"], "report").status == 303
    assert "already in the case" in flash(app)
    assert send_file(app, inputs["item1"], "govdoc", name="item1.xlsx").status == 303
    assert "imported from a PDF" in flash(app)
    assert send_file(app, inputs["item1"], "report", token="forged").status == 403
    assert send_file(app, inputs["affidavit"], "report", name="notes.txt").status == 303
    assert "Not imported" in flash(app)
    assert sorted(case.inputs.iterdir()) == before
    conn = connect(case.db)
    assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 3


def test_upload_parser_streams_and_checks_the_token_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "CHUNK", 7)  # boundaries split across reads
    data = os.urandom(5000) + b"\r\n--baker-test-boundar" + os.urandom(300)
    body, ctype = multipart({"token": "t", "kind": "report"}, "a.xlsx", data)
    target = tmp_path / "up"
    up = upload.parse(io.BytesIO(body), len(body), ctype, lambda: target, lambda f: None)
    assert target.read_bytes() == data and up.sha256 == hashlib.sha256(data).hexdigest()
    assert up.fields == {"token": "t", "kind": "report"} and up.file_name == "a.xlsx"

    def refuse(fields: dict[str, str]) -> None:
        raise PermissionError(fields.get("token"))

    with pytest.raises(PermissionError):
        upload.parse(io.BytesIO(body), len(body), ctype, lambda: tmp_path / "never", refuse)
    assert not (tmp_path / "never").exists()
    with pytest.raises(upload.UploadError):
        upload.parse(io.BytesIO(body[:-40]), len(body) - 40, ctype, lambda: tmp_path / "x",
                     lambda f: None)  # fmt: skip
    assert cases.safe_file_name("../../etc/pass wd.XLSX") == "pass wd.xlsx"
    assert cases.safe_file_name(r"C:\Users\x\report<1>.pdf") == "report_1_.pdf"


# ---------------------------------------------------------------- claims and owners


def test_proposed_claims_must_be_decided_and_owners_confirmed_before_the_audit(app, inputs):
    case = _make_case(app, inputs)
    post(app, "/claims/propose", next="/setup")
    wait(app.jobs.current)  # type: ignore[arg-type]
    assert app.jobs.current.state == "done", app.jobs.current.message  # type: ignore[union-attr]
    conn = connect(case.db)
    proposed = [r[0] for r in conn.execute("SELECT id FROM claims WHERE status = 'proposed'")]
    assert proposed  # the paragraphs naming Marc Garage
    ready = {r.text: r.ok for r in cases.readiness(case, conn)}
    assert any("still need your decision" in t and not ok for t, ok in ready.items())
    # A proposed claim is named by its printed paragraph and number, not its long internal id.
    pid = conn.execute("SELECT paragraph_id FROM claims WHERE id = ?", (proposed[0],)).fetchone()[0]
    label = conn.execute("SELECT label FROM govdoc_paragraphs WHERE id = ?", (pid,)).fetchone()[0]
    name = f"¶{label}.{proposed[0].rsplit(':', 1)[1]}"
    assert status.claim_name(conn, proposed[0], pid) == name
    assert status.claim_name(conn, "C05", pid) == "C05"
    for path in ("/setup", "/claims"):
        assert f">{name}</a>" in get(app, path).text
    claim_page = get(app, "/claim", id=proposed[0]).text
    assert f"<h1>{name} " in claim_page and proposed[0] in claim_page  # the id stays findable
    post(app, "/audit/start", next="/run")
    assert "not ready" in get(app, "/").text
    assert app.jobs.current.kind == "propose"  # type: ignore[union-attr]

    for cid in proposed:
        post(app, "/claim/edit", claim=cid, status="removed", next="/setup")
    _add_gold_claims(app, conn)
    page = get(app, "/setup").text
    assert "has no stipulated user" in page
    post(app, "/audit/start", next="/run")
    assert "not ready" in get(app, "/").text  # owners not confirmed, not acknowledged
    _stipulate(app)
    assert all(r.ok for r in cases.readiness(case, conn))

    post(app, "/claims/move", claim="C05", delta="-1", next="/setup")
    post(app, "/claims/move", claim="C05", delta="-1", next="/setup")
    order = cases.claim_order(case, conn)
    assert order.index("C05") == 2 and not set(proposed) & set(order)
    assert json.loads(case.settings_path.read_text())["claim_order"][2] == "C05"


# ---------------------------------------------------------------- the background audit


def test_audit_runs_in_the_background_in_the_experts_order(app, inputs):
    case = _make_case(app, inputs)
    conn = connect(case.db)
    _add_gold_claims(app, conn)
    # A claim the signed sheet has no assumptions for: nothing can be checked for it.
    para = conn.execute("SELECT paragraph_id FROM claims WHERE id = 'C05'").fetchone()[0]
    post(app, "/claim/add", id="C21", paragraph=para, type="event",
         text="PETROV met REYES at the garage.")  # fmt: skip
    _stipulate(app)
    for _ in range(len(GOLD) + 1):  # past the top stays at the top
        post(app, "/claims/move", claim="C09", delta="-1", next="/setup")
    order = cases.claim_order(case, conn)
    assert order[0] == "C09"
    r = post(app, "/audit/start", next="/run")
    assert r.header("Location") == "/run"
    job = app.jobs.current
    assert job is not None and job.kind == "audit"
    wait(job)
    assert job.state == "done", job.message

    run = pipeline.last_run(conn)
    assert run is not None and run["config"]["claim_order"] == order
    rows = list(conn.execute(
        "SELECT claim_id, state, candidates_total, candidates_labeled FROM run_claims"
        " WHERE pipeline_run_id = ? ORDER BY position", (run["run_id"],)))  # fmt: skip
    assert [r[0] for r in rows] == order
    assert all(r[1] == "done" and r[2] == r[3] for r in rows)
    finished = [p["claim_id"] for p in pipeline.finished_claims(conn, run["run_id"])]
    assert finished == order  # one log entry per claim, in the order they ran

    states = {cid: claim_state(conn, cid) for cid in order}
    assert all(st.decision.verdict != Verdict.SUPPORTED for st in states.values())
    page = get(app, "/run").text
    assert "Finished" in page and LABELING_INCOMPLETE not in page
    queue_page = get(app, "/claims").text
    assert "Unproven, awaiting expert review" in queue_page
    # Untested is said, with why, not shown as a plain unproven.
    c21 = states["C21"]
    assert c21.untested and c21.label == status.NOT_TESTED
    assert c21.not_tested.startswith(pipeline.NOT_TESTED)
    assert status.NOT_TESTED in queue_page and "Not tested: Baker could not" in queue_page
    claim_page = get(app, "/claim", id="C21").text
    assert pipeline.NOT_TESTED in claim_page
    # ...next to what the case holds, so a claim about the case's own material can be checked.
    held = status.case_holdings(conn)
    assert len(held) == 2 and any("Apple iPhone 13" in h for h in held), held
    report = render_report(conn)
    for page_html in (claim_page, report):
        assert html.escape(status.HOLDINGS) in page_html
        assert all(html.escape(h) in page_html for h in held)
    assert html.escape(status.HOLDINGS) not in get(app, "/claim", id="C05").text
    assert pipeline.last_run(conn)["not_tested"].keys() == {"C21"}
    assert all(not st.untested for cid, st in states.items() if cid != "C21")
    assert audit_log.verify_chain(conn)


def test_finished_claims_are_reviewable_while_the_audit_runs_then_stop_and_resume(tmp_path, inputs):
    gate = threading.Event()
    labeler = Supports(gate, hold_on="C06")
    app = App(home=tmp_path / "cases", port=PORT, components_for=components_for(labeler),
              extractor_for=extractor_for, model_check=None)  # fmt: skip
    case = _make_case(app, inputs)
    conn = connect(case.db)
    _add_gold_claims(app, conn)
    _stipulate(app)
    case.save_settings(claim_order=["C05", "C06", "C07"])
    post(app, "/audit/start", next="/run")
    job = app.jobs.current
    assert job is not None
    assert labeler.waiting.wait(60), job.message  # C05 is done; C06 is mid-labeling
    try:
        run = pipeline.view_run(conn)
        assert run is not None and run.get("partial") and set(run["manifest"]) == {"C05"}
        st = claim_state(conn, "C05")
        assert st is not None and not st.incomplete and st.decision is not None
        assert claim_state(conn, "C06").label == LABELING_INCOMPLETE  # type: ignore[union-attr]
        report = render_report(conn)
        assert "Labeling incomplete: this audit has not finished" in report
        assert report.count(LABELING_INCOMPLETE) >= 3

        # The model is working on C06, yet the expert's decisions save at once.
        eid = next(e.id for e in st.evidence if e.stance == Stance.SUPPORTS)
        started = time.monotonic()
        post(app, "/evidence/decide", id=eid, status="accepted", reason="Matches.", next="/")
        assert time.monotonic() - started < 5
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind = 'expert'"
            ).fetchone()[0]
            == 1
        )
        post(app, "/verdict", claim="C05", action="confirm", note="")
        assert claim_state(conn, "C05").decision.confirmed_by == "expert:Test Expert"  # type: ignore[union-attr]

        # Nothing that would change the run's inputs is taken while it runs.
        post(app, "/redecide", next="/")
        assert "wait until the audit finishes" in get(app, "/").text
        post(app, "/claim/edit", claim="C07", status="removed", next="/setup")
        assert "wait until the audit finishes" in get(app, "/").text
        assert send_file(app, inputs["affidavit"], "govdoc", name="again.pdf").status == 303
        assert "wait until the audit finishes" in flash(app)
        assert "The audit is running" in get(app, "/claims").text

        post(app, "/audit/stop", next="/run")
    finally:
        gate.set()
    wait(job)
    assert job.state == "stopped", job.message
    stopped = pipeline.latest_attempt(conn)
    assert stopped is not None and stopped["status"] == "stopped"
    assert set(stopped["manifest"]) == {"C05", "C06"}  # C06 finished before the stop applied
    assert pipeline.last_run(conn) is None  # never scored
    assert "Resume" in get(app, "/setup").text
    assert LABELING_INCOMPLETE in get(app, "/claims").text

    labeler.gate = None
    post(app, "/audit/start", next="/run")
    wait(app.jobs.current)  # type: ignore[arg-type]
    assert app.jobs.current.state == "done", app.jobs.current.message  # type: ignore[union-attr]
    done = pipeline.last_run(conn)
    assert done is not None and set(done["manifest"]) == {g.claim_id for g in GOLD}
    assert done["config"]["claim_order"][:3] == ["C05", "C06", "C07"]
    assert LABELING_INCOMPLETE not in get(app, "/claims").text
    assert audit_log.verify_chain(conn)


def test_a_run_left_running_by_a_closed_app_is_marked_stopped_on_open(tmp_path, inputs):
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    case = _make_case(app, inputs)
    conn = connect(case.db)
    conn.execute(
        "INSERT INTO pipeline_runs (id, started_at_utc, status, baker_version, contracts_version,"
        " rule_version, config_json) VALUES ('run:x', '2026-10-12T00:00:00Z', 'running', '0',"
        " '0', '0', '{}')"
    )
    conn.commit()
    App(case.db, port=PORT, model_check=None)
    assert conn.execute("SELECT status FROM pipeline_runs WHERE id = 'run:x'").fetchone()[0] == (
        "stopped"
    )


def test_audit_does_not_start_when_the_model_check_fails(tmp_path, inputs):
    def no_model(progress=None):  # noqa: ANN001, ANN202
        return check_model(config=tmp_path / "missing.json", cache=None)

    app = App(home=tmp_path / "cases", port=PORT, components_for=components_for(Supports()),
              model_check=no_model)  # fmt: skip
    case = _make_case(app, inputs)
    conn = connect(case.db)
    _add_gold_claims(app, conn)
    _stipulate(app)
    post(app, "/audit/start", next="/run")
    wait(app.jobs.current)  # type: ignore[arg-type]
    job = app.jobs.current
    assert job is not None and job.state == "failed" and "No usable model" in job.message
    assert conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0] == 0
    assert "No usable model" in get(app, "/run").text


# ---------------------------------------------------------------- model check


def _config(tmp_path: Path, data: bytes, sha: str | None = None) -> Path:
    model = tmp_path / "model.gguf"
    model.write_bytes(data)
    cfg = tmp_path / "model.json"
    cfg.write_text(json.dumps({"name": "test-14b", "path": str(model),
                               "sha256": sha or hashlib.sha256(data).hexdigest()}))  # fmt: skip
    return cfg


def test_model_check_finds_hashes_and_sizes_the_model(tmp_path):
    cfg = _config(tmp_path, b"weights" * 1000)
    cache = tmp_path / "cache.json"
    seen: list[tuple[int, int]] = []
    ok = check_model(cfg, cache, progress=lambda d, t: seen.append((d, t)),
                     memory=lambda: 32 * 1024**3, runtime_installed=lambda: True)  # fmt: skip
    assert ok.ok and seen and seen[-1][0] == seen[-1][1]
    seen.clear()
    again = check_model(cfg, cache, progress=lambda d, t: seen.append((d, t)),
                        memory=lambda: 32 * 1024**3, runtime_installed=lambda: True)  # fmt: skip
    assert again.ok and not seen  # remembered for the unchanged file

    small = check_model(cfg, cache, memory=lambda: 2 * 1024**3, runtime_installed=lambda: True)
    assert not small.ok and "Not enough memory" in small.summary
    no_rt = check_model(cfg, cache, memory=lambda: 32 * 1024**3, runtime_installed=lambda: False)
    assert not no_rt.ok and "llama-cpp-python" in no_rt.summary

    (tmp_path / "other").mkdir()
    bad = _config(tmp_path / "other", b"w", "0" * 64)
    wrong = check_model(bad, None, memory=lambda: 32 * 1024**3, runtime_installed=lambda: True)
    assert not wrong.ok and "SHA-256" in wrong.summary
    missing = check_model(tmp_path / "nope.json", None)
    assert not missing.ok and "No usable model" in missing.summary


def test_estimates_say_where_the_speed_comes_from(tmp_path):
    spc, source = jobs.seconds_per_call(tmp_path / "none.json")
    assert spc == jobs.DEFAULT_SECONDS_PER_CALL and "not this computer" in source
    (tmp_path / "s.json").write_text(json.dumps({"seconds_per_call": 12.5, "calls": 40}))
    assert jobs.seconds_per_call(tmp_path / "s.json")[0] == 12.5
    assert jobs.duration(jobs.estimate_seconds(20, 43.0)) == "about 5 h 58 min"


# ---------------------------------------------------------------- local only


def test_new_code_imports_no_network_client():
    bad_names = {"socket", "urllib.request", "http.client", "requests", "httpx", "ssl",
                 "ftplib", "smtplib", "webbrowser"}  # fmt: skip
    for py in [*(ROOT / "core/casework").rglob("*.py"), ROOT / "ui/upload.py"]:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not set(names) & bad_names, f"{py}: imports {names}"


def test_setup_and_progress_pages_run_no_script(app, inputs):
    _make_case(app, inputs)
    for path in ("/cases", "/setup", "/run", "/"):
        r = get(app, path)
        assert r.status == 200, path
        page = r.text.lower()
        assert "<script" not in page and " src=" not in page
    assert (
        "<form method='post' action='/case/import' enctype='multipart/form-data'"
        in get(app, "/setup").text
    )


def test_own_forms_carry_a_real_origin(app):
    """Under Referrer-Policy no-referrer a browser sends "Origin: null" on this screen's own
    forms and the Origin check refuses them all (seen in Chromium). same-origin keeps it."""
    r = get(app, "/cases")
    assert r.header("Referrer-Policy") == "same-origin"
    post(app, "/expert", name="Test Expert")
    null = Request("POST", "/case/new", {}, {**HOST, "origin": "null"},
                   {"token": app.token, "name": "x"})  # fmt: skip
    assert app.handle(null).status == 403
