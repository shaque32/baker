import hashlib
import re
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

from core.contracts import DocKind, GovDocIngester, SourceKind
from core.db import apply_schema
from core.ingest.govdoc import (
    AlreadyImportedError,
    GovDocIngestError,
    OcrUnavailableError,
    PdfGovDocIngester,
)
from eval.synthetic import govdocs as syn

FIXED = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _has_tesseract() -> bool:
    if shutil.which("tesseract") is None:
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)  # noqa: S603, S607
    return "eng" in out.stdout.split()


needs_ocr = pytest.mark.skipif(not _has_tesseract(), reason="Tesseract is not installed")


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("govdoc")
    return {name: make(out / name) for name, make in syn.FIXTURES.items()}


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    apply_schema(c)
    return c


def ingester(**kw) -> PdfGovDocIngester:
    return PdfGovDocIngester(clock=lambda: FIXED, **kw)


def flat(text: str) -> str:
    return " ".join(text.split())


def merged(paragraphs) -> list[str]:
    """Paragraph texts with page-break continuations joined back together."""
    out: dict[int, list[str]] = {}
    for p in paragraphs:
        out.setdefault(p.para_no, []).append(p.text)
    return [flat(" ".join(parts)) for _, parts in sorted(out.items())]


def expected(paras: tuple[syn.Para, ...]) -> list[str]:
    return [flat(f"{p.number}. {p.text}" if p.number else p.text) for p in paras]


def test_satisfies_contract():
    _: GovDocIngester = PdfGovDocIngester()


# ---------------------------------------------------------------- text-layer documents


def test_affidavit_paragraphs_match_source(fixtures):
    r = ingester().parse(fixtures["affidavit.pdf"])
    assert merged(r.paragraphs) == expected(syn.AFFIDAVIT)
    assert r.ocr_pages == ()
    assert r.govdoc.doc_kind == DocKind.AFFIDAVIT
    assert r.govdoc.title == syn.AFFIDAVIT_TITLE


def test_spans_are_exact_slices_of_page_text(fixtures):
    for name in ("affidavit.pdf", "police_report.pdf"):
        r = ingester().parse(fixtures[name])
        pages = {p.page: p.text for p in r.pages}
        for p in r.paragraphs:
            assert pages[p.page][p.char_start : p.char_end] == p.text


def test_paragraph_across_page_break_keeps_one_para_no(fixtures):
    r = ingester().parse(fixtures["affidavit.pdf"])
    seven = [p for p in r.paragraphs if p.text.startswith("7.")][0]
    parts = [p for p in r.paragraphs if p.para_no == seven.para_no]
    assert [p.page for p in parts] == [1, 2]
    assert parts[1].text.startswith("February 20, 2026")
    assert len({(p.page, p.para_no) for p in r.paragraphs}) == len(r.paragraphs)
    assert len({p.id for p in r.paragraphs}) == len(r.paragraphs)


def test_para_no_counts_document_order(fixtures):
    r = ingester().parse(fixtures["affidavit.pdf"])
    nos = [p.para_no for p in r.paragraphs]
    assert nos == sorted(nos)
    assert sorted(set(nos)) == list(range(1, len(set(nos)) + 1))
    # the printed number stays in the text so the expert can cite it as written
    printed = [re.match(r"(\d+)\.", p.text) for p in r.paragraphs]
    assert [int(m.group(1)) for m in printed if m] == list(range(1, 11))


def test_headers_footers_kept_out_of_paragraphs_but_listed(fixtures):
    r = ingester().parse(fixtures["affidavit.pdf"])
    for p in r.paragraphs:
        assert "NOT A REAL CASE" not in p.text
        assert "Page 1 of 2" not in p.text
    assert (1, "Page 1 of 2") in r.furniture
    assert sum(1 for _, t in r.furniture if "NOT A REAL CASE" in t) == 2


def test_police_report_indents_and_mid_sentence_page_break(fixtures):
    r = ingester().parse(fixtures["police_report.pdf"])
    assert merged(r.paragraphs) == expected(syn.POLICE_REPORT)
    assert r.govdoc.doc_kind == DocKind.POLICE_REPORT
    # no metadata title, so the title comes from the first line on the page
    assert r.govdoc.title == syn.POLICE_TITLE
    split = [p for p in r.paragraphs if p.text.startswith("an envelope")]
    assert split and split[0].page == 2


def test_wrapped_line_starting_with_a_number_is_not_a_new_paragraph(fixtures):
    # "...under item numbers 1 and\n2. Neither phone..." in the police report
    r = ingester().parse(fixtures["police_report.pdf"])
    assert not any(p.text.startswith("2. Neither") for p in r.paragraphs)


def test_doc_kind_override(fixtures):
    r = ingester(doc_kind=DocKind.OTHER).parse(fixtures["affidavit.pdf"])
    assert r.govdoc.doc_kind == DocKind.OTHER


# ---------------------------------------------------------------- inputs and storage


def test_input_is_hashed_and_not_modified(fixtures, tmp_path):
    path = tmp_path / "affidavit.pdf"
    shutil.copy(fixtures["affidavit.pdf"], path)
    path.chmod(0o444)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    r = ingester().parse(path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert r.source.sha256 == hashlib.sha256(before[0]).hexdigest()
    assert r.source.kind == SourceKind.GOVDOC
    assert r.source.file_name == "affidavit.pdf"
    assert str(tmp_path) not in r.source.model_dump_json()


def test_ingest_writes_rows(fixtures, conn):
    govdoc, paragraphs = ingester().ingest(fixtures["affidavit.pdf"], conn)
    row = conn.execute("SELECT kind, sha256, imported_at_utc FROM sources").fetchone()
    assert row[0] == "govdoc"
    assert row[2] == "2026-10-06T12:00:00Z"
    assert conn.execute("SELECT id, doc_kind FROM govdocs").fetchone() == (
        govdoc.id,
        "affidavit",
    )
    stored = conn.execute(
        "SELECT id, page, para_no, char_start, char_end, text FROM govdoc_paragraphs"
        " ORDER BY page, para_no"
    ).fetchall()
    assert stored == [
        (p.id, p.page, p.para_no, p.char_start, p.char_end, p.text) for p in paragraphs
    ]


def test_ids_are_stable_across_imports(fixtures, conn):
    a = ingester().parse(fixtures["affidavit.pdf"])
    b = ingester().parse(fixtures["affidavit.pdf"])
    assert [p.id for p in a.paragraphs] == [p.id for p in b.paragraphs]
    assert a.paragraphs[0].id == f"para:{a.source.sha256[:16]}:1:1"


def test_reimport_same_file_is_a_no_op(fixtures, conn):
    first = ingester().ingest(fixtures["affidavit.pdf"], conn)
    again = ingester().ingest(fixtures["affidavit.pdf"], conn)
    assert first == again
    assert conn.execute("SELECT count(*) FROM sources").fetchone() == (1,)


def test_reimport_refuses_to_overwrite_when_parse_differs(fixtures, conn):
    ingester().ingest(fixtures["affidavit.pdf"], conn)
    conn.execute("UPDATE govdoc_paragraphs SET text = 'changed' WHERE para_no = 4")
    with pytest.raises(AlreadyImportedError):
        ingester().ingest(fixtures["affidavit.pdf"], conn)


def test_not_a_pdf(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(GovDocIngestError):
        ingester().parse(bad)


def test_password_protected_pdf(tmp_path):
    path = tmp_path / "locked.pdf"
    c = canvas.Canvas(str(path), encrypt=StandardEncryption("pw", ownerPassword="pw"))
    c.drawString(72, 720, "secret")
    c.save()
    with pytest.raises(GovDocIngestError, match="password"):
        ingester().parse(path)


def test_blank_page_has_no_paragraphs_and_no_ocr(tmp_path):
    path = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(path))
    c.showPage()
    c.save()
    r = ingester().parse(path)
    assert r.paragraphs == [] and r.ocr_pages == ()


# ---------------------------------------------------------------- scanned documents


@needs_ocr
def test_scanned_document_falls_back_to_ocr(fixtures):
    r = ingester().parse(fixtures["scanned_affidavit.pdf"])
    assert r.ocr_pages == (1, 2)
    assert re.search(r"ocr:tesseract-[\d.]+:eng:pages=1,2$", r.source.tool_version or "")
    assert r.govdoc.doc_kind == DocKind.AFFIDAVIT
    # Bates stamps are the only text layer; they are furniture, not paragraphs
    assert {t for _, t in r.furniture} == {"BKR-SYN-000001", "BKR-SYN-000002"}
    # OCR is not verbatim, so compare on words, and require one paragraph per source paragraph
    assert len(merged(r.paragraphs)) == len(syn.SCANNED)
    for got, want in zip(merged(r.paragraphs), expected(syn.SCANNED), strict=True):
        words = lambda s: re.findall(r"[a-z0-9@]+", s.lower())  # noqa: E731
        w, g = words(want), set(words(got))
        assert sum(x in g for x in w) / len(w) >= 0.85, (want, got)
    pages = {p.page: p.text for p in r.pages}
    for p in r.paragraphs:
        assert pages[p.page][p.char_start : p.char_end] == p.text


def test_scan_without_tesseract_fails_loudly(fixtures):
    with pytest.raises(OcrUnavailableError, match="page 1"):
        ingester(tesseract_cmd="no-such-tesseract").parse(fixtures["scanned_affidavit.pdf"])


@needs_ocr
def test_scan_without_language_data_fails_loudly(fixtures, tmp_path):
    missing = tmp_path / "no-tessdata"
    missing.mkdir()
    with pytest.raises(OcrUnavailableError, match="page 1"):
        ingester(tessdata=str(missing)).parse(fixtures["scanned_affidavit.pdf"])


# ---------------------------------------------------------------- safety


NETWORK_MODULES = re.compile(
    r"^\s*(import|from)\s+(socket|ssl|urllib|http|requests|httpx|aiohttp|ftplib|smtplib)\b",
    re.M,
)


def test_core_makes_no_network_imports():
    root = Path(__file__).resolve().parents[1] / "core"
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if NETWORK_MODULES.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
