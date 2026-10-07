"""Government document ingest: PDF -> paragraphs with page, paragraph number and char span.

Implements GovDocIngester from core/contracts.py.

The definitions below are what an expert would need to reproduce a citation by hand.

- Page text. The text segments of one page in PDFium content order (one per line in
  ordinary documents), joined with "\\n". Fragments that sit on the same baseline (OCR often splits
  a paragraph number from its text) are joined into one line with a single space.
  OCR pages use the same rule on the OCR text layer.
- Span. char_start and char_end are offsets into that page text, and
  paragraph.text == page_text[char_start:char_end] exactly. Nothing is cleaned or rewritten.
- Paragraph number. para_no is the paragraph's position in the document, counting from 1.
  The number printed in the document goes in label ("7"), and stays inside the text too.
  A paragraph that runs across a page break is stored once per page under the same para_no
  and label.
- Page furniture. Lines in the top or bottom margin that are page numbers, or that repeat on
  most pages once digits are ignored (running headers, Bates stamps), are left out of
  paragraphs. They are listed in GovDocIngestResult.furniture so nothing is dropped silently.
- OCR. A page is OCR'd only when its text layer is nearly empty and an image covers most of
  it (a scan, possibly with a Bates stamp on top). OCR text is not verbatim source text; its
  paragraphs carry ocr=True, and the pages are listed in GovDocIngestResult.ocr_pages and in
  the source's tool_version. If OCR
  is needed but Tesseract is not installed, ingest fails instead of returning empty pages.

The input is opened read-only, hashed with SHA-256 and parsed from the bytes in memory.
No network access: OCR runs the local Tesseract binary with local language data.
Libraries are permissively licensed (pypdfium2: Apache-2.0/BSD-3; Pillow: MIT-CMU).
"""

from __future__ import annotations

import hashlib
import io
import math
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pypdfium2.version import PDFIUM_INFO

from core.contracts import (
    DocKind,
    ExtractionType,
    Fidelity,
    GovDoc,
    GovDocParagraph,
    Source,
    SourceKind,
)

PARSER_VERSION = "govdoc-pdf/3"

OCR_MAX_TEXT_CHARS = 50  # a page with fewer text-layer characters than this may be a scan
OCR_MIN_IMAGE_COVER = 0.5  # ...if images cover at least this share of the page
OCR_DPI = 300
MARGIN_FRAC = 0.08  # top and bottom band where headers, footers and Bates stamps live
REPEAT_FRAC = 0.6  # a margin line on at least this share of pages is furniture
PARA_GAP_RATIO = 1.35  # line pitch above this multiple of the page's usual pitch
INDENT_PT = 12.0  # a first-line indent at least this deep starts a paragraph

_MARKER = re.compile(r"^\s*(\d{1,3})[.)]\s")
_PAGE_NUMBER = re.compile(
    r"^\s*(page\s+\d+(\s+of\s+\d+)?|-?\s*\d{1,4}\s*-?|\d+\s*/\s*\d+)\s*$", re.IGNORECASE
)
_TERMINAL = re.compile(r"[.!?:;\"'”’)\]]\s*$")


class GovDocIngestError(Exception):
    pass


class OcrUnavailableError(GovDocIngestError):
    """A page needs OCR and Tesseract (or its language data) is not available locally."""


class AlreadyImportedError(GovDocIngestError):
    """The same file was imported before and today's parse differs from what is stored."""


@dataclass(frozen=True)
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    start: int  # offset of the line in the page text
    end: int

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


@dataclass(frozen=True)
class PageText:
    page: int  # 1-based
    text: str
    lines: tuple[Line, ...]
    height: float
    ocr: bool


@dataclass(frozen=True)
class GovDocIngestResult:
    source: Source
    govdoc: GovDoc
    paragraphs: list[GovDocParagraph]
    pages: tuple[PageText, ...]
    ocr_pages: tuple[int, ...]
    furniture: tuple[tuple[int, str], ...]  # (page, line text) left out as header/footer


# ---------------------------------------------------------------- reading


def read_input(path: Path) -> tuple[bytes, str]:
    """Read the file once, read-only, and return its bytes and SHA-256."""
    with path.open("rb") as f:
        data = f.read()
    return data, hashlib.sha256(data).hexdigest()


def _raw_lines(page: pdfium.PdfPage) -> list[list]:
    """[x0, y0, x1, y1, text] per text segment, top-down coordinates, content order."""
    height = page.get_height()
    tp = page.get_textpage()
    out: list[list] = []
    try:
        for i in range(tp.count_rects()):
            left, bottom, right, top = tp.get_rect(i)
            text = tp.get_text_bounded(left, bottom, right, top)
            text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
            if text.strip():
                out.append([left, height - top, right, height - bottom, text])
    finally:
        tp.close()
    return out


def _same_baseline(a: list, b: list) -> bool:
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    return overlap > 0.5 * min(a[3] - a[1], b[3] - b[1])


def _merge_baselines(raw: list[list]) -> list[list]:
    merged: list[list] = []
    for r in raw:
        prev = merged[-1] if merged else None
        if prev is not None and _same_baseline(prev, r) and r[0] >= prev[2] - 1:
            prev[4] = f"{prev[4]} {r[4]}"
            prev[2] = max(prev[2], r[2])
            prev[1] = min(prev[1], r[1])
            prev[3] = max(prev[3], r[3])
        else:
            merged.append(list(r))
    return merged


def _build_page(number: int, height: float, raw: list[list], ocr: bool) -> PageText:
    lines: list[Line] = []
    parts: list[str] = []
    pos = 0
    for x0, y0, x1, y1, text in _merge_baselines(raw):
        if parts:
            pos += 1  # the "\n" joining this line to the previous one
        lines.append(Line(text, x0, y0, x1, y1, pos, pos + len(text)))
        parts.append(text)
        pos += len(text)
    return PageText(number, "\n".join(parts), tuple(lines), height, ocr)


def _needs_ocr(page: pdfium.PdfPage, raw: list[list]) -> bool:
    chars = sum(len(r[4].strip()) for r in raw)
    if chars >= OCR_MAX_TEXT_CHARS:
        return False
    w, h = page.get_size()
    if w <= 0 or h <= 0:
        return False
    covered = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
        left, bottom, right, top = obj.get_bounds()
        cw = min(right, w) - max(left, 0.0)
        ch = min(top, h) - max(bottom, 0.0)
        if cw > 0 and ch > 0:
            covered += cw * ch
    return covered / (w * h) >= OCR_MIN_IMAGE_COVER


class Tesseract:
    """Runs the locally installed Tesseract binary. No network, no Python bindings."""

    def __init__(self, cmd: str = "tesseract", tessdata: str | None = None, language: str = "eng"):
        self.cmd = cmd
        self.tessdata = tessdata
        self.language = language

    def version(self) -> str:
        exe = self._exe()
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [exe, "--version"], capture_output=True, text=True, check=False, timeout=30
        )
        first = (out.stdout or out.stderr).splitlines()
        return first[0].split()[-1] if first else "unknown"

    def _exe(self) -> str:
        exe = shutil.which(self.cmd)
        if exe is None:
            raise OcrUnavailableError(f"Tesseract not found ({self.cmd!r} is not on PATH)")
        return exe

    def lines(self, page: pdfium.PdfPage) -> list[list]:
        """OCR one page. [x0, y0, x1, y1, text] per OCR line, in PDF points, top-down."""
        scale = OCR_DPI / 72
        image = page.render(scale=scale, grayscale=True).to_pil()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        argv = [self._exe(), "stdin", "stdout", "-l", self.language, "--dpi", str(OCR_DPI)]
        if self.tessdata:
            argv += ["--tessdata-dir", self.tessdata]
        argv.append("tsv")
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, input=buf.getvalue(), capture_output=True, check=False, timeout=300
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            raise OcrUnavailableError(f"Tesseract failed: {err[-1] if err else proc.returncode}")
        grouped: dict[tuple[str, str, str], list] = {}
        for row in proc.stdout.decode("utf-8").splitlines()[1:]:
            cols = row.split("\t")
            if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
                continue
            x, y, w, h = (int(c) / scale for c in cols[6:10])
            key = (cols[2], cols[3], cols[4])  # block, paragraph, line
            if key not in grouped:
                grouped[key] = [x, y, x + w, y + h, cols[11]]
            else:
                g = grouped[key]
                g[0], g[1] = min(g[0], x), min(g[1], y)
                g[2], g[3] = max(g[2], x + w), max(g[3], y + h)
                g[4] = f"{g[4]} {cols[11]}"
        return list(grouped.values())


def extract_pages(pdf: pdfium.PdfDocument, ocr: Tesseract) -> tuple[PageText, ...]:
    pages: list[PageText] = []
    for i in range(len(pdf)):
        page = pdf[i]
        try:
            raw = _raw_lines(page)
            scanned = _needs_ocr(page, raw)
            if scanned:
                try:
                    raw = ocr.lines(page)
                except OcrUnavailableError as e:
                    raise OcrUnavailableError(
                        f"page {i + 1} has no usable text layer and OCR is unavailable: {e}. "
                        "Install Tesseract with its language data, or pass tessdata=<path>."
                    ) from e
            pages.append(_build_page(i + 1, page.get_height(), raw, scanned))
        finally:
            page.close()
    return tuple(pages)


# ---------------------------------------------------------------- page furniture


def _in_margin(line: Line, height: float) -> bool:
    return line.y1 <= height * MARGIN_FRAC or line.y0 >= height * (1 - MARGIN_FRAC)


def _shape(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.split())).lower()


def find_furniture(pages: tuple[PageText, ...]) -> set[tuple[int, int]]:
    """(page, line index) of headers, footers, page numbers and Bates stamps."""
    seen: dict[str, set[int]] = {}
    for p in pages:
        for line in p.lines:
            if _in_margin(line, p.height):
                seen.setdefault(_shape(line.text), set()).add(p.page)
    need = max(2, math.ceil(REPEAT_FRAC * len(pages)))
    out: set[tuple[int, int]] = set()
    for p in pages:
        for k, line in enumerate(p.lines):
            if not _in_margin(line, p.height):
                continue
            if _PAGE_NUMBER.match(line.text) or len(seen[_shape(line.text)]) >= need:
                out.add((p.page, k))
    return out


# ---------------------------------------------------------------- paragraphs


def _is_heading(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and len(text) < 120 and all(c.isupper() for c in letters)


def _terminal(text: str) -> bool:
    return bool(_TERMINAL.search(text))


@dataclass
class _Para:
    page: int
    lines: list[Line]
    continues_previous: bool = False


def _split_page(
    page: PageText, body: list[Line], last_marker: int | None
) -> tuple[list[_Para], int | None]:
    """Group body lines into paragraphs. Returns the paragraphs and the last printed
    paragraph number seen, so numbering can carry across pages."""
    paras: list[_Para] = []
    pitches = sorted(b.y0 - a.y0 for a, b in zip(body, body[1:], strict=False) if b.y0 > a.y0)
    usual = pitches[len(pitches) // 4] if pitches else 0.0  # lower quartile: plain line pitch
    for line in body:
        cur = paras[-1] if paras else None
        new = cur is None
        if cur is not None:
            prev = cur.lines[-1]
            pitch = line.y0 - prev.y0
            m = _MARKER.match(line.text)
            expected = 1 if last_marker is None else last_marker + 1
            if pitch > PARA_GAP_RATIO * usual or pitch < 0:
                new = True  # blank space before the line, or a jump back up (new column)
            elif m and int(m.group(1)) == expected and _terminal(prev.text):
                new = True  # next printed paragraph number after a finished sentence
            elif (
                len(cur.lines) >= 2
                and line.x0 >= cur.lines[1].x0 + INDENT_PT
                and _terminal(prev.text)
            ):
                new = True  # first-line indent
            elif _is_heading(prev.text) != _is_heading(line.text):
                new = True
        if new:
            paras.append(_Para(page.page, [line]))
        else:
            paras[-1].lines.append(line)
        m = _MARKER.match(line.text)
        if m and new:
            n = int(m.group(1))
            if n == (1 if last_marker is None else last_marker + 1):
                last_marker = n
    return paras, last_marker


@dataclass(frozen=True)
class _Row:
    page: int
    para_no: int
    label: str | None
    start: int
    end: int
    text: str
    ocr: bool


def segment(pages: tuple[PageText, ...], furniture: set[tuple[int, int]]) -> list[_Row]:
    """Every paragraph, in reading order."""
    out: list[_Row] = []
    para_no = 0
    label: str | None = None
    last_marker: int | None = None
    prev_text: str | None = None
    for p in pages:
        body = [ln for k, ln in enumerate(p.lines) if (p.page, k) not in furniture]
        paras, marker_after = _split_page(p, body, last_marker)
        for i, para in enumerate(paras):
            first = para.lines[0].text
            m = _MARKER.match(first)
            starts_numbered = bool(m) and int(m.group(1)) == (
                1 if last_marker is None else last_marker + 1
            )
            continues = (
                i == 0
                and prev_text is not None
                and not _terminal(prev_text)
                and not _is_heading(prev_text)
                and not _is_heading(first)
                and not starts_numbered
            )
            if not continues:
                para_no += 1
                label = m.group(1) if m and starts_numbered else None
            start, end = para.lines[0].start, para.lines[-1].end
            text = p.text[start:end]
            out.append(_Row(p.page, para_no, label, start, end, text, p.ocr))
            prev_text = text
            if m and starts_numbered:
                last_marker = int(m.group(1))
        last_marker = marker_after if marker_after is not None else last_marker
    return out


# ---------------------------------------------------------------- document kind


_KIND_WORDS: tuple[tuple[DocKind, tuple[str, ...]], ...] = (
    (DocKind.AFFIDAVIT, ("AFFIDAVIT", "SWORN STATEMENT")),
    (DocKind.FORENSIC_REPORT, ("FORENSIC", "EXTRACTION REPORT", "EXAMINATION REPORT")),
    (DocKind.POLICE_REPORT, ("INCIDENT REPORT", "POLICE", "OFFENSE REPORT", "ARREST REPORT")),
)


def classify(title: str, opening: str) -> DocKind:
    """Keyword match on the title, then on the opening text. OTHER when nothing matches."""
    for text in (title.upper(), opening.upper()):
        for kind, words in _KIND_WORDS:
            if any(w in text for w in words):
                return kind
    return DocKind.OTHER


# ---------------------------------------------------------------- ingester


class PdfGovDocIngester:
    """GovDocIngester for PDF affidavits, police reports and forensic reports."""

    def __init__(
        self,
        doc_kind: DocKind | None = None,
        *,
        tessdata: str | None = None,
        ocr_language: str = "eng",
        tesseract_cmd: str = "tesseract",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.doc_kind = doc_kind  # None: classify from the title and opening text
        self.ocr = Tesseract(tesseract_cmd, tessdata, ocr_language)  # None: Tesseract's default
        self.clock = clock

    def ingest(self, path: Path, conn: sqlite3.Connection) -> tuple[GovDoc, list[GovDocParagraph]]:
        result = self.ingest_full(path, conn)
        return result.govdoc, result.paragraphs

    def parse(self, path: Path) -> GovDocIngestResult:
        """Parse without touching a database."""
        data, sha = read_input(path)
        try:
            pdf = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as e:
            if "password" in str(e).lower():
                raise GovDocIngestError(f"{path.name} is password protected") from e
            raise GovDocIngestError(f"{path.name} is not a readable PDF: {e}") from e
        try:
            pages = extract_pages(pdf, self.ocr)
            meta_title = pdf.get_metadata_dict().get("Title") or ""
        finally:
            pdf.close()

        furniture = find_furniture(pages)
        rows = segment(pages, furniture)
        ocr_pages = tuple(p.page for p in pages if p.ocr)

        key = sha[:16]
        version = f"{PARSER_VERSION} pdfium-{PDFIUM_INFO}"
        if ocr_pages:
            version += f" ocr:tesseract-{self.ocr.version()}:{self.ocr.language}:pages=" + ",".join(
                str(n) for n in ocr_pages
            )
        source = Source(
            id=f"src:{key}",
            kind=SourceKind.GOVDOC,
            fidelity=Fidelity.UNKNOWN,
            extraction_type=ExtractionType.NOT_APPLICABLE,
            file_name=path.name,
            sha256=sha,
            tool_name="baker-govdoc",
            tool_version=version,
            imported_at_utc=self.clock(),
        )
        first_line = rows[0].text.split("\n", 1)[0].strip() if rows else ""
        title = " ".join(meta_title.split()) or first_line or path.stem
        opening = " ".join(r.text for r in rows[:3])
        govdoc = GovDoc(
            id=f"govdoc:{key}",
            source_id=source.id,
            title=title,
            doc_kind=self.doc_kind or classify(title, opening),
        )
        paragraphs = [
            GovDocParagraph(
                id=f"para:{key}:{r.page}:{r.para_no}",
                govdoc_id=govdoc.id,
                page=r.page,
                para_no=r.para_no,
                label=r.label,
                char_start=r.start,
                char_end=r.end,
                text=r.text,
                ocr=r.ocr,
            )
            for r in rows
        ]
        dropped = tuple(
            (p.page, p.lines[k].text)
            for p in pages
            for k in range(len(p.lines))
            if (p.page, k) in furniture
        )
        return GovDocIngestResult(source, govdoc, paragraphs, pages, ocr_pages, dropped)

    def ingest_full(self, path: Path, conn: sqlite3.Connection) -> GovDocIngestResult:
        """Parse and write sources, govdocs and govdoc_paragraphs in one transaction.

        Re-importing the same file returns what is stored if today's parse matches it,
        and raises AlreadyImportedError if it does not (the parser changed).
        """
        result = self.parse(path)
        stored = load(conn, result.govdoc.id)
        if stored is not None:
            govdoc, paragraphs = stored
            if govdoc != result.govdoc or paragraphs != result.paragraphs:
                raise AlreadyImportedError(
                    f"{path.name} was imported before as {govdoc.id} and parses differently "
                    f"now ({PARSER_VERSION}); refusing to overwrite stored paragraphs"
                )
            return GovDocIngestResult(
                result.source,
                govdoc,
                paragraphs,
                result.pages,
                result.ocr_pages,
                result.furniture,
            )
        s = result.source
        with conn:
            conn.execute(
                "INSERT INTO sources (id, kind, fidelity, extraction_type, file_name, sha256,"
                " tool_name, tool_version, extracted_at_utc, imported_at_utc)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    s.id,
                    s.kind.value,
                    s.fidelity.value,
                    s.extraction_type.value,
                    s.file_name,
                    s.sha256,
                    s.tool_name,
                    s.tool_version,
                    None,
                    s.imported_at_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                ),
            )
            g = result.govdoc
            conn.execute(
                "INSERT INTO govdocs (id, source_id, title, doc_kind) VALUES (?, ?, ?, ?)",
                (g.id, g.source_id, g.title, g.doc_kind.value),
            )
            conn.executemany(
                "INSERT INTO govdoc_paragraphs"
                " (id, govdoc_id, page, para_no, label, char_start, char_end, text, ocr)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        p.id,
                        p.govdoc_id,
                        p.page,
                        p.para_no,
                        p.label,
                        p.char_start,
                        p.char_end,
                        p.text,
                        int(p.ocr),
                    )
                    for p in result.paragraphs
                ],
            )
        return result


def load(conn: sqlite3.Connection, govdoc_id: str) -> tuple[GovDoc, list[GovDocParagraph]] | None:
    row = conn.execute(
        "SELECT id, source_id, title, doc_kind FROM govdocs WHERE id = ?", (govdoc_id,)
    ).fetchone()
    if row is None:
        return None
    govdoc = GovDoc(id=row[0], source_id=row[1], title=row[2], doc_kind=DocKind(row[3]))
    paragraphs = [
        GovDocParagraph(
            id=r[0],
            govdoc_id=r[1],
            page=r[2],
            para_no=r[3],
            label=r[4],
            char_start=r[5],
            char_end=r[6],
            text=r[7],
            ocr=bool(r[8]),
        )
        for r in conn.execute(
            "SELECT id, govdoc_id, page, para_no, label, char_start, char_end, text, ocr"
            " FROM govdoc_paragraphs WHERE govdoc_id = ? ORDER BY page, para_no",
            (govdoc_id,),
        )
    ]
    return govdoc, paragraphs
