"""The bug report holds no case data, and the Help page shows it before it is saved.

A synthetic case01 is made on the screen with marked ("canary") values everywhere case data can
live: the case name, the expert's name, the uploaded file names, a claim's text, a background
job's message and an error message. The report must carry none of them, none of the inputs'
SHA-256 values (or a prefix), no long hex run and no folder path, while still saying what a
developer needs: versions, counts and states, and where an error happened in Baker's code.
"""

from __future__ import annotations

import ast
import http.client
import json
import re
import shutil
import threading
from pathlib import Path

import pytest

from core.casework import cases, jobs
from core.db import connect
from core.support import bug_report, errors
from core.support.contact import SUPPORT_EMAIL
from eval import run_pipeline
from tests.test_start_case import (
    GOLD,
    PORT,
    Supports,
    _add_gold_claims,
    components_for,
    extractor_for,
    get,
    inputs,  # noqa: F401 - the module fixture
    post,
    send_file,
    wait,
)
from ui.app import App

ROOT = Path(__file__).resolve().parents[1]
CASE_NAME = "United States v. Quokkaline (synthetic)"
EXPERT = "Examiner Zebrafinch"
CLAIM_TEXT = "PETROV texted the word marmalade-canary to REYES."
JOB_MESSAGE = "Stopped while reading /Users/someone/cases/Quokkaline/phone-canary.xlsx"
ERROR_TEXT = "cannot parse row 7 of tangerine-canary.ufdr: 'meet at the pier'"
CANARIES = (
    "quokkaline",
    "zebrafinch",
    "marmalade",
    "tangerine",
    "phone-canary",
    "pier",
    "petrov",
    "reyes",
    "/users/",
)


def _raise_in_baker() -> None:
    """An error raised inside Baker's own code, with case text in its message."""
    try:
        cases.check_case_name("")
    except Exception as err:
        raise RuntimeError(ERROR_TEXT) from err


@pytest.fixture
def audited(tmp_path: Path, inputs: dict[str, Path]) -> App:  # noqa: F811
    app = App(
        home=tmp_path / "cases",
        port=PORT,
        components_for=components_for(Supports()),
        extractor_for=extractor_for,
        model_check=None,
    )
    post(app, "/expert", name=EXPERT)
    post(app, "/case/new", name=CASE_NAME)
    assert app.case is not None
    named = tmp_path / "named"
    named.mkdir()
    for sid, kind, name in (
        ("affidavit", "govdoc", "Quokkaline-affidavit-canary.pdf"),
        ("item1", "report", "Quokkaline-phone-canary-1.xlsx"),
        ("item2", "report", "Quokkaline-phone-canary-2.xlsx"),
    ):
        copy = named / name
        shutil.copy(inputs[sid], copy)
        assert send_file(app, copy, kind).status == 303
    conn = connect(app.case.db)
    try:
        _add_gold_claims(app, conn)
        para = conn.execute("SELECT paragraph_id FROM claims WHERE id = 'C05'").fetchone()[0]
    finally:
        conn.close()
    post(app, "/claim/add", id="C21", paragraph=para, type="event", text=CLAIM_TEXT)
    meta = json.loads((run_pipeline.synthetic_dir("case01") / "case.json").read_text())
    for d in meta["devices"]:
        device = f"dev:Quokkaline-phone-canary-{d['source_id'][-1]}"
        post(app, "/stipulate", device=device, person=d["owner"], next="/setup")
    post(app, "/audit/start", next="/run")
    job = app.jobs.current
    assert job is not None, app.flash
    wait(job)
    assert job.state == "done", job.message
    job.message = JOB_MESSAGE  # a finished job's message can name a file
    errors.clear()
    try:
        _raise_in_baker()
    except RuntimeError as err:
        errors.note("audit", err)
    return app


def _source_hashes(app: App) -> list[str]:
    conn = connect(app.case.db)  # type: ignore[union-attr]
    try:
        return [r[0] for r in conn.execute("SELECT sha256 FROM sources")]
    finally:
        conn.close()


def test_bug_report_holds_no_case_text_names_paths_or_hashes(audited: App, tmp_path: Path):
    r = get(audited, "/help/bug-report.json")
    assert r.status == 200
    assert r.header("Content-Type").startswith("application/json")
    assert "attachment" in r.header("Content-Disposition")
    text = r.text
    low = text.lower()
    for canary in CANARIES:
        assert canary not in low, canary
    assert EXPERT.lower() not in low and CASE_NAME.lower() not in low
    assert str(tmp_path).lower() not in low and "cases" + "/" not in low
    hashes = _source_hashes(audited)
    assert len(hashes) == 3
    for h in hashes:
        assert h[:12] not in low, "an input's SHA-256 leaked"
    assert not re.search(r"[0-9a-fA-F]{32,}", text)

    report = json.loads(text)
    case = report["open_case"]
    assert case["readable"] and case["audit_log_intact"] is True
    assert case["counts"]["claims"] == len(GOLD) + 1
    assert case["counts"]["sources"] == 3
    assert {s["kind"] for s in case["sources"]} >= {"govdoc"}
    assert case["recent_runs"][0]["status"] == "completed"
    assert sum(case["latest_run_verdicts"].values()) == len(GOLD) + 1
    assert report["last_job"]["kind"] == "audit" and report["last_job"]["state"] == "done"
    err = report["recent_errors"][-1]
    assert err["where"] == "audit"
    assert err["types"][:2] == ["RuntimeError", "core.review.actions.ReviewError"]
    assert any(f.startswith("core/casework/cases.py:") for f in err["frames"])
    assert report["support"] == SUPPORT_EMAIL
    assert report["baker"]["rules"]


def test_help_page_shows_contact_and_the_same_report_without_a_case(tmp_path: Path):
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    r = get(app, "/help")
    assert r.status == 200, "Help opens with no case open"
    page = r.text
    assert SUPPORT_EMAIL in page and "the Baker team sets the real address" not in page
    assert "/help/bug-report.json" in page and "Never send case content" in page
    assert "takes the scrolling, not the judgment" in page
    low = page.lower()
    assert "<script" not in low and " src=" not in low
    assert r.header("Referrer-Policy") == "same-origin"
    assert json.loads(get(app, "/help/bug-report.json").text)["open_case"] is None
    assert "<a href='/help'" in get(app, "/cases").text


def test_help_page_with_a_case_has_no_case_text(audited: App):
    page = get(audited, "/help").text.lower()
    for canary in ("marmalade", "tangerine", "pier", "phone-canary"):
        assert canary not in page, canary


def test_a_report_that_looks_like_case_data_is_withheld(audited: App, monkeypatch):
    sha = _source_hashes(audited)[0]
    real = bug_report.build

    def leaky(**kw):  # noqa: ANN003, ANN202
        out = real(**kw)
        out["oops"] = sha
        return out

    monkeypatch.setattr(bug_report, "build", leaky)
    r = get(audited, "/help/bug-report.json")
    assert r.status == 500 and sha not in r.text
    page = get(audited, "/help").text
    assert "withheld" in page and sha not in page
    with pytest.raises(bug_report.NotClean):
        bug_report.check_clean('{"x": "Quokkaline matter"}', {"Quokkaline matter"})


def test_cli_bug_report_on_a_case_is_clean(audited: App, tmp_path: Path, capsys):
    from cli.main import main

    out = tmp_path / "report.json"
    assert main(["bug-report", "--db", str(audited.case.db), "--out", str(out)]) == 0  # type: ignore[union-attr]
    text = out.read_text(encoding="utf-8").lower()
    for canary in CANARIES:
        assert canary not in text, canary
    assert json.loads(text)["open_case"]["counts"]["claims"] == len(GOLD) + 1


def test_an_unexpected_screen_error_is_kept_without_its_message(tmp_path: Path, monkeypatch):
    from ui.server import make_server

    errors.clear()
    server = make_server(home=tmp_path / "cases", port=0)

    def boom(req):  # noqa: ANN001, ANN202
        raise ValueError(ERROR_TEXT)

    monkeypatch.setattr(server.app, "handle", boom)  # type: ignore[attr-defined]
    try:
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request)
        t.start()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/claims")
        r = c.getresponse()
        body = r.read().decode()
        t.join(10)
    finally:
        server.server_close()
    assert r.status == 500 and "/help" in body and "tangerine" not in body
    assert r.getheader("Referrer-Policy") == "same-origin"
    kept = errors.recent()[-1]
    assert kept.where == "screen" and kept.types == ("ValueError",)
    assert "tangerine" not in json.dumps(kept.record())


def test_error_labels_are_fixed_and_frames_outside_baker_collapse():
    with pytest.raises(ValueError):
        errors.note("free text from a case", RuntimeError("x"))
    try:
        json.loads("{not json")
    except ValueError as err:
        event = errors.note("cli", err)
    assert "(outside Baker)" in event.frames
    assert not any("site-packages" in f or f.startswith("/") for f in event.frames)


def test_job_failure_is_kept_for_the_bug_report(tmp_path: Path):
    errors.clear()
    js = jobs.Jobs()

    def fail(job: jobs.Job) -> None:
        raise KeyError("tangerine-canary")

    job = js.start(jobs.Job("propose", tmp_path / "case.db"), fail)
    wait(job)
    kept = errors.recent()[-1]
    assert kept.where == "propose" and kept.types == ("KeyError",)


def test_support_code_imports_no_network_client():
    bad = {"socket", "urllib.request", "http.client", "requests", "httpx", "ssl", "smtplib",
           "webbrowser"}  # fmt: skip
    for py in [*(ROOT / "core/support").rglob("*.py"), ROOT / "ui/help_pages.py"]:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not set(names) & bad, f"{py}: imports {names}"


def test_download_saves_the_report_the_help_page_showed(audited: App, monkeypatch):
    shown = get(audited, "/help").text
    real = bug_report.build

    def changed(**kw):
        out = real(**kw)
        out["made_at_utc"] = "2099-01-01T00:00:00Z"
        return out

    monkeypatch.setattr(bug_report, "build", changed)
    saved = get(audited, "/help/bug-report.json").text
    assert "2099-01-01" not in saved
    assert json.loads(saved)["made_at_utc"] in shown


def test_unreadable_verdicts_still_give_a_report(audited: App):
    conn = connect(audited.case.db)
    try:
        conn.execute("DROP TABLE verdicts")
        out = bug_report.case_section(audited.case, conn)
    finally:
        conn.close()
    assert out["latest_run_verdicts"] == {}


def test_build_identity_comes_from_core_build(monkeypatch):
    from core import build as baker_build

    monkeypatch.setattr(baker_build, "commit", lambda root=None: ("a" * 40, None))
    monkeypatch.setattr(baker_build, "release", lambda root=None: "9.9.9")
    got = bug_report.baker_section()
    assert got["commit"] == "a" * 12 and got["package"] == "9.9.9"


def test_an_unreadable_model_file_reads_as_not_available(monkeypatch, tmp_path: Path):
    from core.audit import _local_model

    class Boom(type(tmp_path)):
        def is_file(self):
            raise PermissionError("denied")

    class Cfg:
        name = "synthetic-model"
        path = Boom(tmp_path / "m.gguf")

    monkeypatch.setattr(_local_model, "load_config", lambda: Cfg())
    out = bug_report.model_section(None)
    assert out["file_found"] is False and out["file_gb"] is None


def test_a_browser_that_goes_away_is_not_kept_as_an_error(monkeypatch):
    from ui import server

    noted = []
    monkeypatch.setattr(server.support_errors, "note", lambda *a: noted.append(a))

    def gone():
        raise BrokenPipeError

    handler = object.__new__(server._Handler)
    handler._guarded(gone, "screen")
    assert noted == []


def test_only_known_baker_settings_are_named(monkeypatch):
    monkeypatch.setenv("BAKER_CLIENT_SYNTHETICNAME", "1")
    monkeypatch.setenv("BAKER_DEMO", "1")
    got = bug_report.settings_section(None, None)["baker_env_set"]
    assert "BAKER_DEMO" in got and not any("SYNTHETICNAME" in k for k in got)


def test_an_unreadable_model_config_reads_as_not_found(monkeypatch):
    from core.audit import _local_model

    def boom():
        raise PermissionError("denied")

    monkeypatch.setattr(_local_model, "load_config", boom)
    assert bug_report.model_section(None)["config_found"] is False


def test_unreadable_inputs_give_an_unavailable_encryption_state(audited: App, monkeypatch):
    from core.casework import protect

    def boom(case):
        raise PermissionError("denied")

    monkeypatch.setattr(protect, "state", boom)
    assert bug_report.case_section(audited.case, None)["encryption"] == "unavailable"


def test_help_never_creates_a_missing_case_database(audited: App):
    db = audited.case.db
    db.unlink()
    get(audited, "/help/bug-report.json")
    assert not db.exists()


def test_no_evidence_text_or_names_from_the_case_reach_the_report(audited: App, monkeypatch):
    """Every message body, contact name, account identifier and thread title in the synthetic
    case, and a canary in an unknown BAKER_ setting, is absent from the saved report."""
    monkeypatch.setenv("BAKER_QUOKKALINE_CANARY", "Quokkaline-env-canary")
    conn = connect(audited.case.db)  # type: ignore[union-attr]
    try:
        seen = [
            v
            for sql in (
                "SELECT body FROM messages",
                "SELECT name FROM contacts",
                "SELECT identifier FROM accounts",
                "SELECT display_name FROM accounts",
                "SELECT title FROM threads",
                "SELECT text FROM claims",
            )
            for (v,) in conn.execute(sql)
            if isinstance(v, str) and len(v.strip()) >= 8
        ]
    finally:
        conn.close()
    assert len(seen) > 20
    low = get(audited, "/help/bug-report.json").text.lower()
    assert "quokkaline" not in low
    leaked = [v for v in seen if v.strip().lower() in low]
    assert leaked == []
