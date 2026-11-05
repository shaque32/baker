"""Imports that used to leave the expert stuck with no way out but a new case (2026-11-04
walkthrough): a PDF with no report tables in the phone slot, a wrong date order, a UFDR named
like the Excel report of the same phone, and any wrong file before the first audit."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

from core.casework.remove import ACTION
from core.db import connect
from eval import run_pipeline
from eval.synthetic import paired
from ui.app import App, Request

HOST = {"host": "127.0.0.1:8765"}


@pytest.fixture(scope="module")
def inputs(tmp_path_factory) -> dict[str, Path]:
    meta = run_pipeline.ensure_reports("case01")
    folder = tmp_path_factory.mktemp("originals")
    out = {
        s["source_id"]: run_pipeline.synthetic_dir("case01") / s["file"] for s in meta["sources"]
    }
    out["affidavit"] = run_pipeline.render_affidavit_pdf("case01", folder / "affidavit.pdf")
    full = paired.write(folder / "paired")["item1-full.ufdr"]
    out["item1.ufdr"] = shutil.copy(full, folder / "item1.ufdr")
    return out


@pytest.fixture
def app(tmp_path) -> App:
    a = App(home=tmp_path / "cases", port=8765, model_check=None)
    post(a, "/expert", name="Test Expert")
    post(a, "/case/new", name="Imports case")
    return a


def post(app: App, path: str, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def send(app: App, path: Path, kind: str, **fields: str) -> str:
    b = "dead-ends-boundary"
    parts = [
        f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in {"token": app.token, "kind": kind, **fields}.items()
    ]
    parts.append(
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode()
        + path.read_bytes()
        + b"\r\n"
    )
    parts.append(f"--{b}--\r\n".encode())
    body = b"".join(parts)
    req = Request("POST", "/case/import", {}, {**HOST, "content-type":
                  f"multipart/form-data; boundary={b}"})  # fmt: skip
    app.handle_upload(req, io.BytesIO(body), len(body))
    return app.flash[0] if app.flash else ""


def _sources(app: App) -> dict[str, str]:
    conn = connect(app.case.db)
    try:
        return dict(conn.execute("SELECT id, file_name FROM sources"))
    finally:
        conn.close()


def test_a_pdf_with_no_report_tables_is_refused_as_a_phone_and_then_imports_as_the_document(
    app, inputs
):
    msg = send(app, inputs["affidavit"], "report")
    assert "holds no Cellebrite report tables" in msg and "Government document" in msg
    assert _sources(app) == {} and not any(app.case.inputs.glob("*.pdf"))
    assert "Imported affidavit.pdf" in send(app, inputs["affidavit"], "govdoc")


def test_a_wrong_date_order_is_refused_with_the_order_that_fits(app, inputs):
    msg = send(app, inputs["item2"], "report", date_order="dmy")
    assert "can only be read month first" in msg and "nothing was imported" in msg
    assert _sources(app) == {}
    assert "Imported item2.xlsx" in send(app, inputs["item2"], "report", date_order="mdy")


def test_a_ufdr_named_like_the_excel_report_of_the_same_phone_imports_under_its_own_id(app, inputs):
    send(app, inputs["item1"], "report")
    msg = send(app, inputs["item1.ufdr"], "report")
    assert "already in this case database" not in msg, msg
    assert set(_sources(app)) == {"item1", "item1-2"}


def test_a_file_can_be_removed_before_the_first_audit_and_imported_again(app, inputs):
    send(app, inputs["item1"], "report")
    post(app, "/case/remove_file", source="item1", reason="")
    assert "item1" in _sources(app)  # a reason is required
    post(app, "/case/remove_file", source="item1", reason="Wrong phone.")
    assert "Removed item1.xlsx" in app.flash[0]
    assert _sources(app) == {} and not any(app.case.inputs.glob("*.xlsx"))
    conn = connect(app.case.db)
    try:
        (payload,) = conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ?", (ACTION,)
        ).fetchone()
        assert '"sha256"' in payload and "Wrong phone." in payload
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    finally:
        conn.close()
    assert "Imported item1.xlsx" in send(app, inputs["item1"], "report")


def test_a_file_stays_while_a_stipulation_points_at_it_or_once_an_audit_has_run(app, inputs):
    send(app, inputs["item1"], "report")
    post(app, "/stipulate", device="dev:item1", person="Daniel Petrov")
    post(app, "/case/remove_file", source="item1", reason="Wrong phone.")
    assert "still used by" in app.flash[0] and "item1" in _sources(app)
    send(app, inputs["item2"], "report")
    conn = connect(app.case.db)
    try:
        with conn:
            conn.execute(
                "INSERT INTO pipeline_runs (id, started_at_utc, status, baker_version,"
                " contracts_version, rule_version, config_json) VALUES"
                " ('run:x', '2026-11-05T00:00:00Z', 'completed', '0', '0', '0', '{}')"
            )
    finally:
        conn.close()
    post(app, "/case/remove_file", source="item2", reason="Wrong phone.")
    assert "an audit has run" in app.flash[0] and "item2" in _sources(app)
