"""Cellebrite Physical Analyzer / Reader PDF report importer.

Reads ruled tables with pdfplumber and maps them with the same rules as the Excel importer.
Layout assumptions: docs/ingest/cellebrite_report.md.
"""

from __future__ import annotations

import io
import re
import sqlite3
import statistics
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pdfplumber

from core.contracts import Source, SourceKind
from core.ingest.cellebrite_common import (
    NOT_IMPORTED_CATEGORIES,
    SUMMARY_KEYS,
    Cell,
    Coverage,
    RawTable,
    RecordKind,
    ReportInput,
    app_for_title,
    find_header,
    header_preview,
    kind_for_title,
    norm,
    write_report,
)
from core.ingest.source_file import read_source

SUMMARY_KEY_NAMES = {n for names in SUMMARY_KEYS.values() for n in names}
PDF_NOTE = (
    "Text comes from PDF layout: line breaks inside cells follow the page width, not the "
    "original message, so a quote spanning a line break can fail verbatim verification and be "
    "dropped. Hidden columns and truncated cells in the PDF cannot be detected."
)


class CellebritePdfImporter:
    """Implements core.contracts.EvidenceImporter."""

    name = "cellebrite_pdf"

    def __init__(
        self,
        source_id: str | None = None,
        now: datetime | None = None,
        date_order: str | None = None,
    ) -> None:
        """`date_order` ('mdy' or 'dmy'): the report's day/month order, when a person states
        it from the report's date format. Without it, dates like 3/4/2026 are read only if
        another value in the report decides the order; otherwise they are reported unread."""
        self.source_id = source_id
        self.now = now
        self.date_order = date_order

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
            self.date_order,
        )


# Headings that title the whole report or its summary, not a data section.
REPORT_HEADING_WORDS = ("report", "summary", "extraction", "case information", "device info")
_UNKNOWN = "unrecognised heading"


@dataclass(frozen=True)
class Section:
    title: str
    kind: RecordKind | None  # None: a section Baker does not import
    app: str | None = None
    unrecognised: bool = False  # a heading Baker does not know; its tables are not imported
    size: float = 0.0  # font size of the heading line; a smaller heading is a sub-heading


_COUNT_RE = re.compile(r"\s*\(\s*[\d,]+\s*\)$")


def _section_title(line: str) -> Section | None:
    shown = _COUNT_RE.sub("", " ".join(line.split()))  # as printed, without '(45)'
    if norm(shown) in NOT_IMPORTED_CATEGORIES:
        return Section(shown, None)
    kind = kind_for_title(line)
    return Section(shown, kind, app_for_title(line)) if kind else None


def _line_size(ln: dict) -> float:
    chars = [c for c in ln.get("chars", []) if str(c.get("text", "")).strip()]
    return max((float(c.get("size", 0)) for c in chars), default=0.0)


def _is_heading(ln: dict, body_size: float) -> bool:
    """A line set larger than the page's body text, or all bold and short."""
    chars = [c for c in ln.get("chars", []) if str(c.get("text", "")).strip()]
    if not chars:
        return False
    bold = all("bold" in str(c.get("fontname", "")).lower() for c in chars)
    return _line_size(ln) > body_size * 1.15 or (bold and len(ln["text"]) <= 60)


def _body_size(page: object) -> float:
    sizes = [round(float(c["size"]), 1) for c in page.chars if str(c["text"]).strip()]  # type: ignore[attr-defined]
    return statistics.median(sizes) if sizes else 0.0


def _inside(top: float, bboxes: list[tuple[float, float, float, float]]) -> bool:
    return any(b[1] - 1 <= top <= b[3] + 1 for b in bboxes)


class _PdfReader:
    """Walks the pages in reading order, keeping the current section and, per page and
    section, how many text lines and tables it held: text in a data section with no table
    beside it is reported, never dropped."""

    def __init__(self) -> None:
        self.cov = Coverage(notes=[PDF_NOTE])
        self.summary: list[tuple[str, str, str]] = []
        self.tables: list[RawTable] = []
        self.section: Section | None = None
        self.prev: RawTable | None = None  # last imported table, for continuation across pages
        self.pages_without_tables: list[int] = []
        self.span_lines = 0  # text lines in the current section on this page
        self.span_tables = 0

    def set_section(self, s: Section | None, pno: int) -> None:
        self.flush_span(pno)
        self.section, self.prev = s, None

    def flush_span(self, pno: int) -> None:
        sec = self.section
        if self.span_lines and sec is not None and sec.kind is not None:
            if self.span_tables == 0:
                self.cov.not_imported.append(
                    {
                        "name": f"p{pno}",
                        "reason": "text with no ruled table, so it was not read",
                        "section": sec.title,
                        "lines": self.span_lines,
                    }
                )
            else:
                self.cov.counters["pdf_text_lines_outside_tables_in_data_sections"] += (
                    self.span_lines
                )
        self.span_lines = self.span_tables = 0

    def line(self, ln: dict, body: float, pno: int) -> None:
        s = _section_title(str(ln["text"]))
        size = _line_size(ln)
        if s is not None:
            self.set_section(replace(s, size=size), pno)
        elif _is_heading(ln, body):
            title = _COUNT_RE.sub("", " ".join(str(ln["text"]).split()))
            if self.section is not None and size < self.section.size - 0.5:
                # Smaller than the heading that opened the section: a sub-heading inside it
                # (one chat's title), so the section goes on.
                self.cov.counters["pdf_subheadings_in_sections"] += 1
            elif any(w in norm(title) for w in REPORT_HEADING_WORDS):
                self.set_section(None, pno)  # the report title or its summary
            else:
                self.set_section(Section(title, None, unrecognised=True, size=size), pno)
        elif self.section is not None and self.section.kind is not None:
            if norm(str(ln["text"]).partition(":")[0]) not in SUMMARY_KEY_NAMES:
                self.span_lines += 1

    def table(self, name: str, raw_rows: list[list[Cell]]) -> None:
        cov, section = self.cov, self.section
        rows: list[tuple[str, list[Cell]]] = [
            (f"{name}:r{i}", list(r)) for i, r in enumerate(raw_rows, start=1)
        ]
        if not rows:
            return
        self.span_tables += 1
        if section is not None and section.kind is None and not section.unrecognised:
            cov.not_imported.append(
                {
                    "name": name,
                    "reason": "category not imported",
                    "section": section.title,
                    "rows": len(rows),
                }
            )
            return
        hint = section.kind if section else None
        app = section.app if section else None
        table = RawTable(name=name, kind_hint=hint, rows=rows, reflowed=True, app_hint=app)
        prev = self.prev
        if find_header(table) is None:
            width = len(rows[0][1])
            if prev is not None and len(prev.rows[0][1]) == width:
                table = RawTable(
                    name=name,
                    kind_hint=prev.kind_hint,
                    rows=[_header_of(prev), *rows],
                    reflowed=True,
                    app_hint=prev.app_hint,
                )
                cov.counters["pdf_tables_continued_from_previous_page"] += 1
            elif _is_summary_table(rows):
                self.summary.extend(
                    (str(r[0]), str(r[1]), loc) for loc, r in rows if len(r) >= 2 and r[0] and r[1]
                )
                return
        if section is not None and section.unrecognised:
            # A heading Baker does not know: never read its tables by their columns, since a
            # post or a location list can look like a message table.
            cov.not_imported.append(
                {
                    "name": name,
                    "reason": "under a heading Baker does not recognise",
                    "section": section.title,
                    "rows": len(rows),
                    "columns": header_preview(table),
                }
            )
            return
        has_header = find_header(table) is not None
        if hint is None and has_header:
            cov.counters["pdf_tables_kind_from_columns"] += 1
        self.tables.append(table)
        self.prev = table if has_header else None

    def page(self, pno: int, page: object) -> None:
        found = page.find_tables()  # type: ignore[attr-defined]
        bboxes = [t.bbox for t in found]
        lines = page.extract_text_lines()  # type: ignore[attr-defined]
        body = _body_size(page)
        outside = [ln for ln in lines if not _inside(ln["top"], bboxes)]
        for ln in outside:
            key, sep, value = ln["text"].partition(":")
            if sep and norm(key) in SUMMARY_KEY_NAMES and value.strip():
                self.summary.append((key, value.strip(), f"p{pno}"))
        if not found:
            self.pages_without_tables.append(pno)
        # Lines and tables in reading order, so each table has the section title above it.
        events: list[tuple[float, str, object]] = [(ln["top"], "line", ln) for ln in outside]
        events += [(t.bbox[1], "table", t) for t in found]
        events.sort(key=lambda e: (e[0], e[1] == "table"))
        tidx = 0
        for _top, what, obj in events:
            if what == "line":
                self.line(obj, body, pno)  # type: ignore[arg-type]
            else:
                tidx += 1
                self.table(f"p{pno}:t{tidx}", obj.extract())  # type: ignore[attr-defined]
        self.flush_span(pno)


def read_pdf(data: bytes) -> ReportInput:
    r = _PdfReader()
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            r.page(pno, page)
    cov = r.cov
    if r.pages_without_tables:
        cov.notes.append(
            "Pages with no ruled table (not parsed; may hold chat-bubble layouts): "
            + ", ".join(str(p) for p in r.pages_without_tables[:50])
        )
    cov.summary_found = bool(r.summary)
    return ReportInput(summary=r.summary, tables=r.tables, coverage=cov)


def _header_of(table: RawTable) -> tuple[str, list[Cell]]:
    found = find_header(table)
    assert found is not None  # noqa: S101 - prev tables always have a header
    return table.rows[found[1]]


def _is_summary_table(rows: list[tuple[str, list[Cell]]]) -> bool:
    keys = {norm(r[0]).rstrip(":") for _l, r in rows if r and r[0]}
    return bool(keys & SUMMARY_KEY_NAMES)
