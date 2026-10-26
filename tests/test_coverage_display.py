"""The import coverage summary reaches the expert: `baker import`, the case screen and the
report's limitations. All data is synthetic (eval/synthetic/variants/)."""

from __future__ import annotations

import html
import io
import sqlite3
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core.audit.invariants import FORBIDDEN_WORDS, check_report_text
from core.contracts import SourceCoverage
from core.db import apply_schema
from core.ingest import coverage
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.ufdr import UfdrImporter
from core.report.html import q, render_report
from eval.synthetic.ufdr import related_package
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
    """A sheet Mabillon does not recognise, named by the examiner with a word Mabillon never
    uses."""
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
    assert f'Mabillon did not read all of <span class="q">{odd_sheet.name}</span>' in limits
    assert '<span class="q">Deleted Messages</span>' in limits
    # read in full once the order was stated
    assert f'Mabillon did not read all of <span class="q">{ambiguous.name}' not in limits
    check_report_text(html)


def test_render_quotes_report_text_and_escapes_the_rest():
    item = coverage.CoverageItem(
        "attention", "x", (("Sheet ", False), ("<b>", True), (" & more", False)), ("A!1",)
    )
    got = coverage.render(item, lambda t: f"[{t}]", lambda t: t.replace("&", "&amp;"))
    assert got == "Sheet [<b>] &amp; more (see A!1)"


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in _strings(k) + _strings(v)]
    if isinstance(value, tuple | list):
        return [s for v in value for s in _strings(v)]
    return []


def test_no_coverage_wording_says_a_forbidden_word():
    """Every line coverage can show is Mabillon's own text, so the report check applies to all
    of it, including lines only a real package reaches (a related copy matching no record)."""
    words = [s for name, v in vars(coverage).items() if name.isupper() or name.startswith("_")
             for s in _strings(v)]  # fmt: skip
    assert len(words) > 50
    assert [s for s in words if FORBIDDEN_WORDS.search(s)] == []


def test_report_on_a_package_with_related_copies_passes_the_word_check(tmp_path):
    """The validation run on a public phone stopped here: a package with related copies, one of
    which matches no record, put "deleted state" in the report's limitations."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    UfdrImporter(source_id="rel").import_source(related_package(tmp_path / "rel.ufdr", True), conn)
    html = render_report(conn)
    limits = html.split("<h2>Limitations</h2>", 1)[1].split("<h2>", 1)[0]
    assert "held only as a related copy" in limits and "record state" in limits
    check_report_text(html)


def _every_branch(importer: str, xml: bool, n: int) -> SourceCoverage:
    """A coverage payload that reaches every line summarize() can write, with count n. Every
    value from the report itself says "Deleted", as an examiner's sheet name may."""
    table = {
        "name": "Deleted Messages",
        "kind": "chats",
        "missing_key_fields": [*coverage._KEY_FIELD_WORDS, "other"],
        "rows_skipped": {r: n for r in [*coverage._SKIP_REASON_WORDS, "other_reason", "empty"]},
        "skipped_locators": {r: ["A!1"] * 6 for r in coverage._SKIP_REASON_WORDS},
        "time_problems": {p: n for p in [*coverage._TIME_PROBLEM_WORDS, "other_problem"]},
        "time_problem_locators": {p: ["A!2"] for p in coverage._TIME_PROBLEM_WORDS},
        "duplicate_columns": [
            {"field": "body", "column": "Deleted", "used": "Body"},
            {"field": "mood", "column": "Deleted", "used": "Mood"},
        ],
        "merged_columns_not_filled": ["Deleted"],
        "flagged_locators": {
            f: ["A!3"] * n
            for f in [*coverage._FLAG_WORDS, "body_at_excel_cell_limit", "no_body_or_attachment"]
        },
        "flag_counts": {f: n for f in coverage._FLAG_WORDS},
        "unknown_columns": ["Deleted"],
        "header_offsets": {"Deleted": -300},
        "header_zone_names": {"Deleted": "EST"},
        "merged_cells_filled": n,
        "header_notes": ["Deleted"],
        "app_from_title": "Deleted",
        "rows_imported": n,
        "rows_read": n + 1,
        "date_order_basis": "other tables in the report",
        "date_order": "dmy",
    }
    payload = {
        "importer": importer,
        "layout": "xml" if xml else "sheets",
        "file_name": "Deleted.ufdr",
        "format_support": "unverified",
        "tables": [table, {**table, "date_order_basis": "field name", "date_order": "mdy"}],
        "not_imported": [
            {"name": "Deleted", "reason": "category not imported", "records": n},
            {"name": "Deleted", "reason": "section 'x'", "rows": n, "section": "Deleted"},
            {"name": "Deleted", "reason": "model type not recognised", "lines": n},
            {"name": "Deleted", "reason": "other", "columns": ["Deleted"]},
        ],
        "counts": {k: n for k in [*coverage._ATTENTION_COUNTERS, *coverage._INFO_COUNTERS]},
        "unmapped_direction_values": {"Deleted": n},
        "categories_not_found": [*coverage.KIND_WORDS, "other"],
        "summary_found": False,
        "date_order_stated_at_import": "mdy",
        "report_time_zone_raw": "Deleted",
        "hidden_sheets": ["Deleted"],
        "accounts_with_multiple_display_names": ["Deleted"],
        "ufdr": {
            "partial_extractions": ["Deleted"],
            "extractions": [{"name": "Deleted"}, {"type": "Deleted"}],
            "namespace": "Deleted",
            "namespace_known": False,
            "package_files": n,
            "package_files_hashed": n,
            "tagged_files": n,
            "deleted_state_values": {"Deleted": n, "Intact": n},
        },
        "notes": [*coverage._OWN_NOTES],
    }
    return SourceCoverage(
        source_id="s", importer=importer, importer_version="0.2.0", payload=payload
    )


@pytest.mark.parametrize("importer", [*coverage.READERS, "cellebrite_excel"])
@pytest.mark.parametrize("xml", [True, False])
@pytest.mark.parametrize("n", [1, 2])
def test_every_rendered_coverage_line_passes_the_word_check(importer, xml, n):
    """Close #137's gap: check the lines as summarize() builds and render() prints them, not only
    the module's constants, so wording put together inside a function cannot slip past."""
    s = coverage.summarize(_every_branch(importer, xml, n))
    codes = {i.code for i in s.items}
    reached = {
        *coverage._FLAG_WORDS,
        *coverage._ATTENTION_COUNTERS,
        *coverage._INFO_COUNTERS,
        *(f"missing_{f}" for f in coverage._KEY_FIELD_WORDS),
        *(f"rows_skipped_{r}" for r in coverage._SKIP_REASON_WORDS),
        *(f"times_{p}" for p in coverage._TIME_PROBLEM_WORDS),
    }
    assert reached <= codes, reached - codes
    assert len(codes) > 70
    own = [s.headline] + [coverage.render(i, lambda _t: "", html.escape) for i in s.items]
    assert [t for t in own if FORBIDDEN_WORDS.search(t)] == []
    # as the report prints them: the report's own words checked, its cited values exempt
    printed = "".join(f"<li>{coverage.render(i, q, html.escape)}</li>" for i in s.items)
    assert "Deleted" in printed
    check_report_text(f"<p>{html.escape(s.headline)}</p><ul>{printed}</ul>")
