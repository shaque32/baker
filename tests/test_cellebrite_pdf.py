import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.contracts import Fidelity, SourceKind
from core.ingest.cellebrite_pdf import CellebritePdfImporter

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
STYLES = getSampleStyleSheet()
GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])
LONG = "this message is long enough that the report wraps it onto a second line in the cell"


def grid(rows: list[list[object]], widths: list[int], wrap: tuple[int, ...] = ()) -> Table:
    cells = [rows[0]] + [
        [Paragraph(str(v), STYLES["BodyText"]) if i in wrap and v else v for i, v in enumerate(r)]
        for r in rows[1:]
    ]
    return Table(cells, colWidths=widths, style=GRID, repeatRows=0)


def build_pdf(path: Path) -> Path:
    chat_header = ["#", "Chat #", "Source", "From", "Body", "Timestamp", "Deleted"]
    chat_rows = [
        [1, "c1", "WhatsApp", "+15550000002 Alex", LONG, "3/5/2026 9:31:00 PM(UTC-5)", "Intact"],
        *[
            [n, "c1", "WhatsApp", "+15550000001 Dana (owner)", f"msg {n}",
             f"3/6/2026 {n % 12 + 1}:00:00 AM(UTC-5)", ""]
            for n in range(2, 46)
        ],
    ]  # fmt: skip
    story = [
        Paragraph("Extraction Report", STYLES["Title"]),
        Paragraph("Extraction type: File System", STYLES["BodyText"]),
        Paragraph("UFED Physical Analyzer version: 7.70.0.1", STYLES["BodyText"]),
        Paragraph("Time zone: UTC-5", STYLES["BodyText"]),
        Paragraph("Chats (45)", STYLES["Heading2"]),
        grid([chat_header, *chat_rows], [20, 35, 55, 95, 120, 100, 45], wrap=(3, 4, 5)),
        Spacer(1, 12),
        Paragraph("Timeline", STYLES["Heading2"]),
        grid(
            [["#", "From", "Body", "Timestamp"], [1, "+15550000002", "msg 2", "x"]],
            [30, 90, 90, 90],
        ),
        PageBreak(),
        Paragraph("Call Log (1)", STYLES["Heading2"]),
        grid(
            [
                ["#", "Type", "Parties", "Timestamp", "Duration"],
                [1, "Incoming", "+15550000002 Alex", "3/7/2026 8:00:00 PM", "00:02:00"],
            ],
            [25, 60, 120, 140, 60],
            wrap=(2, 3),
        ),
    ]
    SimpleDocTemplate(str(path), pagesize=letter).build(story)
    return path


def test_pdf_import(tmp_path: Path, case_db: sqlite3.Connection):
    path = build_pdf(tmp_path / "report.pdf")
    src = CellebritePdfImporter(source_id="srcp", now=NOW).import_source(path, case_db)
    assert src.kind is SourceKind.CELLEBRITE_PDF
    assert src.fidelity is Fidelity.CURATED_REPORT
    assert src.tool_version == "7.70.0.1"

    n_msgs = case_db.execute("SELECT count(*) FROM messages").fetchone()[0]
    assert n_msgs == 45  # table split across pages; timeline table not imported
    first = case_db.execute(
        "SELECT id, body, ts_utc, deleted_flag, direction FROM messages WHERE locator = 'p1:t1:r2'"
    ).fetchone()
    assert first[0] == "msg:srcp:p1:t1:r2"
    assert first[1].replace("\n", " ") == LONG  # PDF reflow adds line breaks
    assert first[2:] == ("2026-03-06T02:31:00Z", 0, "unknown")

    owner_msg = case_db.execute(
        "SELECT direction, deleted_flag FROM messages WHERE body = 'msg 2'"
    ).fetchone()
    assert owner_msg == ("outgoing", None)

    # report time zone UTC-5 is a fixed offset, so it applies to the call's offset-less time
    call = case_db.execute(
        "SELECT direction, ts_utc, ts_offset_min, duration_s FROM calls"
    ).fetchone()
    assert call == ("incoming", "2026-03-08T01:00:00Z", -300, 120)

    cov = json.loads(
        case_db.execute("SELECT payload_json FROM audit_log WHERE action='import'").fetchone()[0]
    )
    assert cov["importer"] == "cellebrite_pdf"
    assert any(n["reason"] == "section 'timeline'" for n in cov["not_imported"])
    assert cov["counts"]["pdf_tables_continued_from_previous_page"] >= 1
    assert cov["counts"]["times_offset_from_report_settings"] == 1
    assert any("line breaks" in n for n in cov["notes"])
