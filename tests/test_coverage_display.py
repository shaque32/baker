"""The import coverage summary reaches the expert: `baker import`, the case screen and the
report's limitations. All data is synthetic (eval/synthetic/variants/)."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core.audit.invariants import check_report_text
from core.db import apply_schema
from core.ingest import coverage
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.report.html import render_report
from eval.synthetic.variants import excel as xl
from eval.synthetic.variants.catalog import VARIANTS
from ui.app import App, Request

PORT = 8766
HOST = {"host": f"127.0.0.1:{PORT}"}


@pytest.fixture(scope="module")
def ambiguous(tmp_path_factory) -> Path:
    """Every date has day and month at 12 or below, and nothing in the report decides."""
    (v,) = [v for v in VARIANTS if v.name == "x07_ambiguous_dates"]
    return v.build(tmp_path_factory.mktemp("x07")).path


@pytest.fixture(scope="module")
def odd_sheet(tmp_path_factory) -> Path:
    """A sheet Baker does not recognise, named by the examiner with a word Baker never uses."""
    path = tmp_path_factory.mktemp("odd") / "odd.xlsx"
    specs = xl.sheets()
    specs.append(xl.SheetSpec("Deleted Messages", [["#", "Body"], [1, "x"]]))
    xl.write(path, specs)
    return path


def test_baker_import_prints_coverage_and_takes_the_date_order(ambiguous, tmp_path, capsys):
    db = tmp_path / "a.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    assert cli_main(["import", "--db", str(db), "--report", str(ambiguous)]) == 0
    out = capsys.readouterr().out
    assert "to review" in out and "Re-import with the report's date order stated" in out

    db2 = tmp_path / "b.db"
    cli_main(["init", "--db", str(db2)])
    capsys.readouterr()
    args = ["import", "--db", str(db2), "--report", str(ambiguous), "--date-order", "mdy"]
    assert cli_main(args) == 0
    out = capsys.readouterr().out
    assert "Nothing needs review" in out and "Date order stated at import" in out


def test_baker_import_refuses_an_unknown_date_order(ambiguous, tmp_path):
    db = tmp_path / "a.db"
    cli_main(["init", "--db", str(db)])
    with pytest.raises(SystemExit):
        cli_main(["import", "--db", str(db), "--report", str(ambiguous), "--date-order", "ymd"])


def _multipart(fields: dict[str, str], name: str, data: bytes) -> tuple[bytes, str]:
    b = "baker-coverage-boundary"
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


def _screen(tmp_path: Path) -> App:
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    for path, form in (("/expert", {"name": "Test Expert"}), ("/case/new", {"name": "Synth"})):
        app.handle(Request("POST", path, {}, dict(HOST), {"token": app.token, **form}))
    assert app.case is not None
    return app


def _send(app: App, path: Path, **fields: str):  # noqa: ANN202
    body, ctype = _multipart(
        {"token": app.token, "kind": "report", **fields}, path.name, path.read_bytes()
    )
    req = Request("POST", "/case/import", {}, {**HOST, "content-type": ctype})
    return app.handle_upload(req, io.BytesIO(body), len(body))


def _setup(app: App) -> str:
    return app.handle(Request("GET", "/setup", {}, dict(HOST))).text


def test_case_screen_shows_what_each_import_did_not_read(odd_sheet, tmp_path):
    app = _screen(tmp_path)
    assert _send(app, odd_sheet).status == 303
    page = _setup(app)
    assert "to review" in page
    assert '<span class="q">Deleted Messages</span>' in page  # the report's words, quoted
    check_report_text(page)
    assert "name='date_order'" in page  # the order can be stated on the next import


def test_case_screen_passes_the_stated_date_order_to_the_importer(ambiguous, tmp_path):
    app = _screen(tmp_path)
    assert _send(app, ambiguous, date_order="mdy").status == 303
    page = _setup(app)
    assert "Nothing needs review" in page and "to review" not in page


def test_case_screen_refuses_an_unknown_date_order(ambiguous, tmp_path):
    app = _screen(tmp_path)
    _send(app, ambiguous, date_order="ymd")
    page = _setup(app)
    assert "Not imported: the date order is month first or day first" in page
    assert app.case is not None and not list(app.case.inputs.iterdir())


def test_report_limitations_list_each_source_that_needs_review(odd_sheet, ambiguous):
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    CellebriteExcelImporter(source_id="odd").import_source(odd_sheet, conn)
    CellebriteExcelImporter(source_id="amb", date_order="mdy").import_source(ambiguous, conn)
    html = render_report(conn)
    limits = html.split("<h2>Limitations</h2>", 1)[1].split("<h2>", 1)[0]
    assert f'Baker did not read all of <span class="q">{odd_sheet.name}</span>' in limits
    assert '<span class="q">Deleted Messages</span>' in limits
    # read in full once the order was stated
    assert f'Baker did not read all of <span class="q">{ambiguous.name}' not in limits
    check_report_text(html)


def test_render_quotes_report_text_and_escapes_the_rest():
    item = coverage.CoverageItem(
        "attention", "x", (("Sheet ", False), ("<b>", True), (" & more", False)), ("A!1",)
    )
    got = coverage.render(item, lambda t: f"[{t}]", lambda t: t.replace("&", "&amp;"))
    assert got == "Sheet [<b>] &amp; more (see A!1)"
