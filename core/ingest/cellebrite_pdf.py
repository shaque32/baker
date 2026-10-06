"""Cellebrite Physical Analyzer / Reader PDF report importer.

Reads ruled tables with pdfplumber and maps them with the same rules as the Excel importer.
Layout assumptions: docs/ingest/cellebrite_report.md.
"""

from __future__ import annotations

import io
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pdfplumber

from core.contracts import Source, SourceKind
from core.ingest.cellebrite_common import (
    SUMMARY_KEYS,
    Cell,
    Coverage,
    RawTable,
    RecordKind,
    ReportInput,
    find_header,
    kind_for_title,
    norm,
    write_report,
)
from core.ingest.source_file import read_source

# Report sections that are never imported. Timeline repeats messages and calls.
SKIP_SECTIONS = {
    "timeline",
    "locations",
    "device locations",
    "web history",
    "web bookmarks",
    "searched items",
    "installed applications",
    "cell towers",
    "wireless networks",
    "calendar",
    "notes",
    "emails",
    "images",
    "videos",
    "audio",
    "documents",
    "data files",
}
SUMMARY_KEY_NAMES = {n for names in SUMMARY_KEYS.values() for n in names}
PDF_NOTE = (
    "Text comes from PDF layout: line breaks inside cells follow the page width, not the "
    "original message, so a quote spanning a line break can fail verbatim verification and be "
    "dropped. Hidden columns and truncated cells in the PDF cannot be detected."
)


class CellebritePdfImporter:
    """Implements core.contracts.EvidenceImporter."""

    name = "cellebrite_pdf"

    def __init__(self, source_id: str | None = None, now: datetime | None = None) -> None:
        self.source_id = source_id
        self.now = now

    def import_source(self, path: Path, conn: sqlite3.Connection) -> Source:
        sf = read_source(path)
        report = read_pdf(sf.data)
        return write_report(
            conn,
            sf,
            SourceKind.CELLEBRITE_PDF,
            self.name,
            self.source_id,
            self.now or datetime.now(UTC),
            report,
        )


def _section_title(line: str) -> tuple[str, RecordKind | None] | None:
    t = re.sub(r"\s*\(\d+\)$", "", norm(line))
    if t in SKIP_SECTIONS:
        return t, None
    kind = kind_for_title(line)
    return (t, kind) if kind else None


def _inside(top: float, bboxes: list[tuple[float, float, float, float]]) -> bool:
    return any(b[1] - 1 <= top <= b[3] + 1 for b in bboxes)


def read_pdf(data: bytes) -> ReportInput:
    cov = Coverage(notes=[PDF_NOTE])
    summary: list[tuple[str, str]] = []
    tables: list[RawTable] = []
    section: tuple[str, RecordKind | None] | None = None
    prev: RawTable | None = None  # last imported table, for continuation across pages
    pages_without_tables: list[int] = []

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            found = page.find_tables()
            bboxes = [t.bbox for t in found]
            lines = page.extract_text_lines()
            for ln in lines:
                if _inside(ln["top"], bboxes):
                    continue
                key, sep, value = ln["text"].partition(":")
                if sep and norm(key) in SUMMARY_KEY_NAMES and value.strip():
                    summary.append((key, value.strip()))
            if not found:
                pages_without_tables.append(pno)
            # Tables in reading order, each with the section title above it.
            events: list[tuple[float, str, object]] = [
                (ln["top"], "line", ln["text"]) for ln in lines if not _inside(ln["top"], bboxes)
            ]
            events += [(t.bbox[1], "table", t) for t in found]
            events.sort(key=lambda e: (e[0], e[1] == "table"))
            tidx = 0
            for _top, what, obj in events:
                if what == "line":
                    s = _section_title(str(obj))
                    if s is not None:
                        section = s
                        prev = None
                    continue
                tidx += 1
                name = f"p{pno}:t{tidx}"
                raw_rows = obj.extract()  # type: ignore[attr-defined]
                rows: list[tuple[str, list[Cell]]] = [
                    (f"{name}:r{i}", list(r)) for i, r in enumerate(raw_rows, start=1)
                ]
                if not rows:
                    continue
                if section is not None and section[1] is None:
                    cov.not_imported.append({"name": name, "reason": f"section '{section[0]}'"})
                    continue
                hint = section[1] if section else None
                table = RawTable(name=name, kind_hint=hint, rows=rows, reflowed=True)
                if find_header(table) is None:
                    width = len(rows[0][1])
                    if prev is not None and len(prev.rows[0][1]) == width:
                        header = _header_of(prev)
                        table = RawTable(
                            name=name, kind_hint=prev.kind_hint, rows=[header, *rows], reflowed=True
                        )
                        cov.counters["pdf_tables_continued_from_previous_page"] += 1
                    elif _is_summary_table(rows):
                        pairs = [r for _l, r in rows if len(r) >= 2 and r[0] and r[1]]
                        summary.extend((str(r[0]), str(r[1])) for r in pairs)
                        continue
                has_header = find_header(table) is not None
                if hint is None and has_header:
                    cov.counters["pdf_tables_kind_from_columns"] += 1
                tables.append(table)
                prev = table if has_header else None
    if pages_without_tables:
        cov.notes.append(
            "Pages with no ruled table (not parsed; may hold chat-bubble layouts): "
            + ", ".join(str(p) for p in pages_without_tables[:50])
        )
    return ReportInput(summary=summary, tables=tables, coverage=cov)


def _header_of(table: RawTable) -> tuple[str, list[Cell]]:
    found = find_header(table)
    assert found is not None  # noqa: S101 - prev tables always have a header
    return table.rows[found[1]]


def _is_summary_table(rows: list[tuple[str, list[Cell]]]) -> bool:
    keys = {norm(r[0]).rstrip(":") for _l, r in rows if r and r[0]}
    return bool(keys & SUMMARY_KEY_NAMES)
