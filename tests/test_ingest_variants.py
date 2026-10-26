"""Every synthetic report layout variant (eval/synthetic/variants/) imports correctly, or its
coverage record says exactly what was not read. All data is synthetic."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit.invariants import FORBIDDEN_WORDS
from core.db import apply_schema
from core.ingest.cellebrite_common import TimeProblem, parse_time
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.coverage import format_text, load, summaries, summarize
from eval.synthetic.variants import excel as xl
from eval.synthetic.variants.catalog import VARIANTS
from eval.synthetic.variants.check import run_variant


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("variants")


@pytest.mark.parametrize("variant", VARIANTS, ids=[v.name for v in VARIANTS])
def test_variant_reads_correctly_or_reports_what_it_skipped(variant, out):
    res = run_variant(variant, out)
    assert res.ok, "\n".join(res.problems)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


def test_every_import_writes_one_source_coverage_row_matching_the_audit_log(tmp_path):
    path = tmp_path / "r.xlsx"
    xl.write(path, xl.sheets())
    conn = _db()
    CellebriteExcelImporter(source_id="s1").import_source(path, conn)
    rows = conn.execute(
        "SELECT source_id, importer, importer_version, payload_json FROM source_coverage"
    ).fetchall()
    assert len(rows) == 1 and rows[0][:3] == ("s1", "cellebrite_excel", "0.3.1")
    (logged,) = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'import'"
    ).fetchone()
    assert json.loads(rows[0][3]) == json.loads(logged)


def test_coverage_of_an_older_import_is_read_from_the_audit_log(tmp_path):
    path = tmp_path / "r.xlsx"
    xl.write(path, xl.sheets())
    conn = _db()
    CellebriteExcelImporter(source_id="s1").import_source(path, conn)
    conn.execute("DELETE FROM source_coverage")  # as before importer 0.2.0
    cov = load(conn, "s1")
    assert cov is not None and cov.importer == "cellebrite_excel"
    assert summarize(cov).status == "complete"


def test_report_text_in_coverage_is_quoted_so_the_word_check_can_tell(tmp_path):
    """A sheet the examiner named 'Deleted Messages' is the report's words, never Baker's."""
    specs = xl.sheets()
    specs.append(xl.SheetSpec("Deleted Messages", [["#", "Body"], [1, "x"]]))
    path = tmp_path / "r.xlsx"
    xl.write(path, specs)
    conn = _db()
    CellebriteExcelImporter(source_id="s1").import_source(path, conn)
    (s,) = summaries(conn)
    flagged = [i for i in s.attention if i.code == "not_imported"]
    assert flagged and "Deleted Messages" in flagged[0].plain
    for item in s.items:
        own = "".join(t for t, quoted in item.parts if not quoted)
        assert not FORBIDDEN_WORDS.search(own), item.plain
    assert "Deleted Messages" in format_text(s)


def test_cli_text_leads_with_what_needs_review(tmp_path):
    specs = xl.sheets(ts=lambda u, o: "N/A")
    path = tmp_path / "r.xlsx"
    xl.write(path, specs)
    conn = _db()
    CellebriteExcelImporter(source_id="s1").import_source(path, conn)
    text = format_text(summaries(conn)[0])
    first, second = text.splitlines()[:2]
    assert "to review" in first and second.startswith("  ! ")
    assert "see Chats!3" in text  # the rows to open are named


def test_stated_date_order_must_be_mdy_or_dmy(tmp_path):
    path = tmp_path / "r.xlsx"
    xl.write(path, xl.sheets())
    with pytest.raises(ValueError, match="date_order"):
        CellebriteExcelImporter(source_id="s1", date_order="ymd").import_source(path, _db())


@pytest.mark.parametrize(
    ("raw", "utc", "offset"),
    [
        ("13-Mar-2026 18:05:00 GMT-4", datetime(2026, 3, 13, 22, 5, tzinfo=UTC), -240),
        ("Fri, Mar 13, 2026 6:05 PM (UTC-04:00)", datetime(2026, 3, 13, 22, 5, tzinfo=UTC), -240),
        ("3/13/2026 6:05:00 PM -0400", datetime(2026, 3, 13, 22, 5, tzinfo=UTC), -240),
        ("2026-03-13 18:05:00 +03:00", datetime(2026, 3, 13, 15, 5, tzinfo=UTC), 180),
        ("13.03.2026 18:05 [UTC+3]", datetime(2026, 3, 13, 15, 5, tzinfo=UTC), 180),
        ("5 March 2026 07:00:00 utc", datetime(2026, 3, 5, 7, 0, tzinfo=UTC), 0),
    ],
)  # fmt: skip
def test_more_written_offsets_and_month_names(raw, utc, offset):
    from core.ingest.cellebrite_common import DateOrder

    ts = parse_time(raw, DateOrder(), None).ts
    assert (ts.utc, ts.offset_min, ts.raw) == (utc, offset, raw)


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ("3/13/2026 6:05:00 PM EDT", TimeProblem.NAMED_ZONE),
        ("13/03/2026 18:05 (Moscow Standard Time)", TimeProblem.NAMED_ZONE),
        (46095.4, TimeProblem.NUMERIC),
        ("46095.4", TimeProblem.NUMERIC),
        ("3/13/26 6:05 PM", TimeProblem.TWO_DIGIT_YEAR),
        ("3/13/2026", TimeProblem.DATE_ONLY),
        ("N/A", TimeProblem.UNPARSED),
        ("3/4/2026 6:05 PM(UTC-4)", TimeProblem.AMBIGUOUS_DAY_MONTH),
        ("3/13/2026 6:05 PM", TimeProblem.NO_OFFSET),
    ],
)
def test_times_that_cannot_be_read_with_confidence_get_no_utc(value, problem):
    from core.ingest.cellebrite_common import DateOrder

    res = parse_time(value, DateOrder(), None)
    assert res.ts.utc is None and res.problem is problem


def test_excel_escapes_are_read_as_excel_means_them():
    """_x000D_ is a carriage return; _x005F_ is a literal underscore, so _x005F_x000D_ is the
    text '_x000D_'. Text with no escape is left as it is."""
    from core.ingest.cellebrite_common import Coverage
    from core.ingest.cellebrite_excel import _unescape

    cov = Coverage()
    assert _unescape("a_x000D_\nb", cov) == "a\r\nb"
    assert _unescape("_x005F_x000D_", cov) == "_x000D_"
    assert _unescape("box_x1", cov) == "box_x1" and _unescape(7, cov) == 7
    assert cov.counters["cells_with_excel_escapes_decoded"] == 2
