"""Cellebrite-style PDF report layouts for the variant set. All synthetic.

A report is a list of blocks (title, summary lines, section headings, tables). Text is ASCII
only, because the built-in PDF fonts have no Cyrillic or emoji glyphs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

STYLES = getSampleStyleSheet()
SUBHEADING = ParagraphStyle("Sub", parent=STYLES["BodyText"], fontName="Helvetica-Bold")
GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)])
NO_GRID = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])


@dataclass
class TableBlock:
    rows: list[list[object]]
    widths: list[int]
    wrap: tuple[int, ...] = ()  # columns whose text wraps inside the cell
    grid: bool = True
    repeat_header: bool = False


@dataclass
class Report:
    blocks: list[object] = field(default_factory=list)

    def title(self, text: str) -> Report:
        self.blocks.append(Paragraph(text, STYLES["Title"]))
        return self

    def line(self, text: str) -> Report:
        self.blocks.append(Paragraph(text, STYLES["BodyText"]))
        return self

    def heading(self, text: str) -> Report:
        self.blocks.append(Paragraph(text, STYLES["Heading2"]))
        return self

    def subheading(self, text: str) -> Report:
        self.blocks.append(Paragraph(text, SUBHEADING))
        return self

    def table(self, tb: TableBlock) -> Report:
        cells = [tb.rows[0]] + [
            [
                Paragraph(str(v).replace("\n", "<br/>"), STYLES["BodyText"])
                if i in tb.wrap and v not in (None, "")
                else ("" if v is None else v)
                for i, v in enumerate(r)
            ]
            for r in tb.rows[1:]
        ]
        self.blocks.append(
            Table(
                cells,
                colWidths=tb.widths,
                style=GRID if tb.grid else NO_GRID,
                repeatRows=1 if tb.repeat_header else 0,
            )
        )
        self.blocks.append(Spacer(1, 12))
        return self

    def page_break(self) -> Report:
        self.blocks.append(PageBreak())
        return self

    def write(self, path: Path) -> Path:
        SimpleDocTemplate(str(path), pagesize=letter, invariant=1).build(list(self.blocks))
        return path
