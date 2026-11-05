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


def test_a_refused_import_is_logged_as_taken_back_so_bundles_still_verify(app, inputs):
    from core.bundle import verify

    send(app, inputs["affidavit"], "report")  # refused: no report tables
    conn = connect(app.case.db)
    try:
        out = verify._Out()
        verify._inputs(conn, out, None)
        assert not out.failed(), [f.detail for f in out.items]
        (payload,) = conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ?", (ACTION,)
        ).fetchone()
        assert "refused on import" in payload
    finally:
        conn.close()


def test_a_withdrawn_stipulation_no_longer_blocks_but_document_names_do(app, inputs):
    send(app, inputs["item1"], "report")
    post(app, "/stipulate", device="dev:item1", person="Daniel Petrov")
    conn = connect(app.case.db)
    try:
        (sid,) = conn.execute("SELECT id FROM stipulations").fetchone()
    finally:
        conn.close()
    post(app, "/stipulation/withdraw", id=sid)
    post(app, "/device/names", device="dev:item1", names="TARGET PHONE")
    post(app, "/case/remove_file", source="item1", reason="Wrong phone.")
    assert "document names for its phone" in app.flash[0] and "item1" in _sources(app)
    post(app, "/device/names", device="dev:item1", names="")
    post(app, "/case/remove_file", source="item1", reason="Wrong phone.")
    assert "Removed item1.xlsx" in app.flash[0], app.flash
    conn = connect(app.case.db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM stipulations").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM persons WHERE id = 'person:dev:item1:owner'"
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


def _verify_dependents(conn) -> list[str]:  # noqa: ANN001
    from core.bundle import verify

    out = verify._Out()
    verify._stipulations(conn, out)
    verify._identity(conn, out)
    verify._claims(conn, {}, out)
    verify._inputs(conn, out, None)
    return [f.detail for f in out.items if f.level == verify.FAIL]


def test_a_removed_phones_withdrawn_stipulation_still_verifies(app, inputs):
    send(app, inputs["item1"], "report")
    post(app, "/stipulate", device="dev:item1", person="Daniel Petrov")
    conn = connect(app.case.db)
    try:
        (sid,) = conn.execute("SELECT id FROM stipulations").fetchone()
    finally:
        conn.close()
    post(app, "/stipulation/withdraw", id=sid)
    post(app, "/case/remove_file", source="item1", reason="Wrong phone.")
    assert "Removed item1.xlsx" in app.flash[0], app.flash
    conn = connect(app.case.db)
    try:
        assert not _verify_dependents(conn), _verify_dependents(conn)
        (payload,) = conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq DESC", (ACTION,)
        ).fetchone()
        assert sid in payload
    finally:
        conn.close()


def test_a_rejected_account_link_goes_with_the_file_but_a_confirmed_one_blocks(app, inputs):
    from core.contracts import IdentityLinkStatus
    from core.review import actions

    send(app, inputs["item1"], "report")
    send(app, inputs["item2"], "report")
    post(app, "/stipulate", device="dev:item2", person="Daniel Petrov")
    conn = connect(app.case.db)
    try:
        (account,) = conn.execute(
            "SELECT id FROM accounts WHERE source_id = 'item1' ORDER BY id LIMIT 1"
        ).fetchone()
        link = actions.link_account(
            conn, account, "person:dev:item2:owner", "expert:Test Expert", "Same number."
        )
    finally:
        conn.close()
    post(app, "/case/remove_file", source="item1", reason="Wrong phone.")
    assert "confirmed account link" in app.flash[0] and "item1" in _sources(app)
    conn = connect(app.case.db)
    try:
        actions.decide_identity_link(
            conn, link, IdentityLinkStatus.REJECTED, "expert:Test Expert", "Not the same."
        )
    finally:
        conn.close()
    post(app, "/case/remove_file", source="item1", reason="Wrong phone.")
    assert "Removed item1.xlsx" in app.flash[0], app.flash
    conn = connect(app.case.db)
    try:
        assert not conn.execute("SELECT 1 FROM identity_links WHERE id = ?", (link,)).fetchone()
        assert conn.execute(
            "SELECT 1 FROM persons WHERE id = 'person:dev:item2:owner'"
        ).fetchone()  # the other phone's user stays
        assert not _verify_dependents(conn), _verify_dependents(conn)
    finally:
        conn.close()


def test_a_removed_documents_proposed_claims_still_verify(app, inputs):
    from core.claims.propose import PROPOSE_ACTION
    from core.review import audit_log

    send(app, inputs["affidavit"], "govdoc")
    conn = connect(app.case.db)
    try:
        (source,) = conn.execute("SELECT id FROM sources").fetchone()
        (para,) = conn.execute("SELECT id FROM govdoc_paragraphs LIMIT 1").fetchone()
        with conn:
            conn.execute(
                "INSERT INTO claims (id, paragraph_id, text, claim_type, status) VALUES"
                " ('P01', ?, 'A proposed claim.', 'communication', 'proposed')",
                (para,),
            )
            audit_log.append(conn, app.clock(), "system", PROPOSE_ACTION, {"claims": ["P01"]})
    finally:
        conn.close()
    post(app, "/case/remove_file", source=source, reason="Wrong document.")
    assert "Removed affidavit.pdf" in app.flash[0], app.flash
    conn = connect(app.case.db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
        assert not _verify_dependents(conn), _verify_dependents(conn)
    finally:
        conn.close()
