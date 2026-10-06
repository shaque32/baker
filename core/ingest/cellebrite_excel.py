"""Cellebrite Physical Analyzer / Reader Excel report (.xlsx) importer.

Layout assumptions: docs/ingest/cellebrite_report.md.
"""

from __future__ import annotations

import io
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import load_workbook

from core.contracts import Source, SourceKind
from core.ingest.cellebrite_common import (
    SUMMARY_SHEETS,
    Coverage,
    RawTable,
    ReportInput,
    kind_for_title,
    norm,
    text,
    write_report,
)
from core.ingest.source_file import read_source


class CellebriteExcelImporter:
    """Implements core.contracts.EvidenceImporter."""

    name = "cellebrite_excel"

    def __init__(self, source_id: str | None = None, now: datetime | None = None) -> None:
        self.source_id = source_id
        self.now = now

    def import_source(self, path: Path, conn: sqlite3.Connection) -> Source:
        sf = read_source(path)
        report = read_workbook(sf.data)
        return write_report(
            conn,
            sf,
            SourceKind.CELLEBRITE_EXCEL,
            self.name,
            self.source_id,
            self.now or datetime.now(UTC),
            report,
        )


def read_workbook(data: bytes) -> ReportInput:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    cov = Coverage()
    summary: list[tuple[str, str]] = []
    tables: list[RawTable] = []
    try:
        for ws in wb.worksheets:
            title = ws.title
            rows = [
                (f"{title}!{i}", list(cells))
                for i, cells in enumerate(ws.iter_rows(values_only=True), start=1)
            ]
            if norm(title) in SUMMARY_SHEETS:
                for _loc, cells in rows:
                    vals = [text(c) for c in cells]
                    present = [v for v in vals if v is not None]
                    if len(present) >= 2:
                        summary.append((present[0], present[1]))
                continue
            kind = kind_for_title(title)
            if kind is None:
                # Never guess a sheet's kind from its columns: a Timeline sheet holds the same
                # messages and calls again and would import them twice.
                cov.not_imported.append({"name": title, "reason": "sheet not recognised"})
                continue
            tables.append(RawTable(name=title, kind_hint=kind, rows=rows))
    finally:
        wb.close()
    return ReportInput(summary=summary, tables=tables, coverage=cov)
