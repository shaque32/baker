"""Small bugs from the 2026-11-04 walkthrough: the redacted summary before any audit, a claim
id already in use, a change of examiner name, claim order, outgoing messages' recipients, the
Run page during and after a failed start, and verify-bundle on screen imports."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.audit.context import build_context, render_context
from core.bundle import verify
from core.db import apply_schema, connect
from core.review import audit_log
from core.review.status import claim_sort_key
from eval import run_pipeline
from ui import pages
from ui.app import App, Request

HOST = {"host": "127.0.0.1:8765"}


def get(app: App, path: str, **query: str):  # noqa: ANN201
    return app.handle(Request("GET", path, dict(query), dict(HOST)))


def post(app: App, path: str, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


@pytest.fixture
def app(tmp_path) -> App:
    a = App(home=tmp_path / "cases", port=8765, model_check=None, name_file=tmp_path / "me.json")
    post(a, "/expert", name="Dana Reyes")
    post(a, "/case/new", name="Small fixes case")
    return a


def test_the_redacted_summary_downloads_before_the_first_audit(app):
    r = get(app, "/flags/summary.json")
    assert r.status == 200, r.body[:200]
    assert json.loads(r.body)["denominators"]["claims_with_verdict"] == 0


def _paragraph(app: App, tmp_path: Path) -> str:
    pdf = run_pipeline.render_affidavit_pdf("case01", tmp_path / "affidavit.pdf")
    from tests.test_start_case import send_file

    assert send_file(app, pdf, "govdoc").status == 303
    conn = connect(app.case.db)  # type: ignore[union-attr]
    return conn.execute("SELECT id FROM govdoc_paragraphs ORDER BY para_no LIMIT 1").fetchone()[0]


def test_a_used_claim_id_is_refused_plainly_and_the_text_kept(app, tmp_path):
    para = _paragraph(app, tmp_path)
    post(app, "/claim/add", id="C01", paragraph=para, type="event", text="First claim.")
    r = post(app, "/claim/add", id="C01", paragraph=para, type="event", text="My long text.")
    assert r.status == 303
    form = html.unescape(get(app, "/claim/new").text)
    assert "already has a claim called C01" in form and "UNIQUE" not in form
    assert "My long text.</textarea>" in form and "value='C01'" in form
    # Each paragraph is shown in full to pick from, the one picked still picked.
    assert f"value='{para}' checked" in form
    again = html.unescape(get(app, "/claim/new").text)
    assert "My long text." not in again  # the draft refills once


def test_a_name_change_is_logged_and_the_name_is_remembered(app, tmp_path):
    post(app, "/expert", name="Dana R. Reyes")
    conn = connect(app.case.db)  # type: ignore[union-attr]
    row = conn.execute(
        "SELECT actor, payload_json FROM audit_log WHERE action = 'reviewer.rename'"
    ).fetchone()
    assert row is not None and row[0] == "expert:Dana R. Reyes"
    assert json.loads(row[1])["from"] == "expert:Dana Reyes"
    later = App(home=tmp_path / "cases", port=8765, model_check=None,
                name_file=tmp_path / "me.json")  # fmt: skip
    assert later.expert == "Dana R. Reyes"


def test_claims_sort_by_number_not_by_text():
    ids = ["C10", "C2", "claim:p:1:10", "claim:p:1:7", "C1"]
    assert sorted(ids, key=claim_sort_key) == ["C1", "C2", "C10", "claim:p:1:7", "claim:p:1:10"]


def test_outgoing_messages_say_who_they_went_to_on_screen_only(tmp_path):
    conn = run_pipeline.build_case("case01", tmp_path / "case.db")
    out = conn.execute(
        "SELECT m.id FROM messages m JOIN message_recipients r ON r.message_id = m.id"
        " WHERE m.direction = 'outgoing' LIMIT 1"
    ).fetchone()
    assert out is not None
    lines = build_context(conn, out[0])
    target = next(ln for ln in lines if ln.is_target)
    assert target.to
    # The stance prompt's context text is the same with or without the recipients.
    assert render_context(lines) == render_context([replace(ln, to="") for ln in lines])


def test_the_run_page_never_says_no_audit_under_a_running_one(app):
    conn = connect(app.case.db)  # type: ignore[union-attr]
    page = app._page()
    job = SimpleNamespace(running=True, done=0, total=3, message="", hashed=None, awake="")
    text = pages.run_page(conn, page, run=None, rows=[], job=job, left="")
    assert "No audit has run" not in text
    check = SimpleNamespace(ok=False, lines=[("fail", "No usable model is set up. To fix it.")])
    failed = SimpleNamespace(running=False, state="failed", message="The audit did not start. "
                             "No usable model is set up. To fix it.", check=check)  # fmt: skip
    text = pages.run_page(conn, page, run=None, rows=[], job=failed, left="")
    assert text.count("No usable model is set up") == 1 and "No audit has run" not in text


def _db(tmp_path: Path):  # noqa: ANN202
    conn = connect(tmp_path / "v.db")
    apply_schema(conn)
    return conn


def _source(conn, sid: str, kind: str, sha: str) -> None:  # noqa: ANN001
    conn.execute(
        "INSERT INTO sources (id, kind, fidelity, extraction_type, file_name, sha256,"
        " imported_at_utc) VALUES (?, ?, 'unknown', 'not_applicable', ?, ?, ?)",
        (sid, kind, f"{sid}.pdf", sha, "2026-11-05T00:00:00Z"),
    )


def test_verify_bundle_reads_the_screens_import_and_removal_entries(tmp_path):
    conn = _db(tmp_path)
    original = tmp_path / "in" / "doc.pdf"
    original.parent.mkdir()
    original.write_bytes(b"synthetic affidavit")
    sha = hashlib.sha256(b"synthetic affidavit").hexdigest()
    _source(conn, "doc", "govdoc", sha)
    now = datetime.now(UTC)
    entries = [
        ("case.import", {"kind": "govdoc", "source_id": "doc", "sha256": sha}),
        ("case.import", {"kind": "cellebrite_excel", "source_id": "gone", "sha256": "0" * 64}),
        ("case.remove_file", {"source_id": "gone", "sha256": "0" * 64, "reason": "wrong file"}),
    ]
    with conn:
        for action, payload in entries:
            audit_log.append(conn, now, "expert:D", action, payload)
    out = verify._Out()
    verify._inputs(conn, out, original.parent)
    details = [f.detail for f in out.items]
    assert not out.failed(), details
    assert "1 input hash match the import log" in details
    assert not any("no import entry" in d for d in details)
