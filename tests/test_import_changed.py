"""An upload whose bytes are not the bytes the importer parses stores nothing. SYNTHETIC only.

The screen hashes an upload while writing it into inputs/; the importer hashes what it parses.
If the two differ (the copy changed in between), import_upload used to report a failed import
while the importer had already committed every record parsed from the altered copy. Each
importer now refuses other bytes before its one write transaction.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.casework import cases
from core.db import apply_schema, connect
from core.ingest.axiom import AxiomImporter
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.govdoc import PdfGovDocIngester
from core.ingest.source_file import InputChanged
from core.ingest.ufdr import UfdrImporter
from core.review.actions import ReviewError
from eval import run_pipeline
from eval.synthetic import axiom as synth_axiom
from eval.synthetic import ufdr as synth_ufdr

EXPERT = "expert:Test Expert"
NOW = datetime(2026, 10, 16, tzinfo=UTC)
OTHER = hashlib.sha256(b"the bytes the screen received").hexdigest()
RECORD_TABLES = ("sources", "devices", "accounts", "messages", "calls", "contacts", "govdocs")


@pytest.fixture(scope="module")
def files(tmp_path_factory) -> dict[str, Path]:
    meta = run_pipeline.ensure_reports("case01")
    out = tmp_path_factory.mktemp("originals")
    item1 = next(s for s in meta["sources"] if s["source_id"] == "item1")
    axiom_xml, axiom_xlsx = synth_axiom.write_case01(out)[:2]
    return {
        "excel": run_pipeline.synthetic_dir("case01") / item1["file"],
        "govdoc": run_pipeline.render_affidavit_pdf("case01", out / "affidavit.pdf"),
        "ufdr": synth_ufdr.write_case01(out)[0],
        "axiom_xml": axiom_xml,
        "axiom_xlsx": axiom_xlsx,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in RECORD_TABLES}  # noqa: S608


def _upload(case: cases.Case, src: Path) -> Path:
    """What the screen does: the upload written into inputs/ (encrypted when the case is)."""
    up = cases.upload_path(case)
    wrap = cases.input_writer(case)
    with up.open("xb") as f:
        w = wrap(f) if wrap else f
        w.write(src.read_bytes())
        if w is not f:
            w.close()
    return up


KINDS = [
    ("excel", "report"),
    ("govdoc", "govdoc"),
    ("ufdr", "report"),
    ("axiom_xml", "report"),
    ("axiom_xlsx", "report"),
]


@pytest.mark.parametrize(("key", "kind"), KINDS)
def test_a_changed_upload_stores_nothing_and_says_so(tmp_path, files, key, kind):
    src = files[key]
    case = cases.create_case(tmp_path, "Synthetic changed copy", EXPERT, clock=lambda: NOW)
    conn = connect(case.db)
    try:
        log_before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        with pytest.raises(
            ReviewError,
            match=r"changed between upload and import \(SHA-256 [0-9a-f]{64} then [0-9a-f]{64}\);"
            r" nothing was stored",
        ):
            cases.import_upload(
                case, conn, _upload(case, src), OTHER, src.name, kind, EXPERT, clock=lambda: NOW
            )
        assert set(_counts(conn).values()) == {0}
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == log_before
        assert list(case.inputs.iterdir()) == []
        # The same file then imports as usual: nothing half-stored blocks it as a duplicate.
        got = cases.import_upload(
            case, conn, _upload(case, src), _sha(src), src.name, kind, EXPERT, clock=lambda: NOW
        )
        assert got.sha256 == _sha(src)
        assert _counts(conn)["sources"] == 1
    finally:
        conn.close()


def _importer(key: str, expected: str):  # noqa: ANN202
    if key == "excel":
        return CellebriteExcelImporter(source_id="s1", expected_sha256=expected).import_source
    if key == "ufdr":
        return UfdrImporter(source_id="s1", expected_sha256=expected).import_source
    if key.startswith("axiom"):
        return AxiomImporter(source_id="s1", expected_sha256=expected).import_source
    return PdfGovDocIngester(expected_sha256=expected).ingest_full


@pytest.mark.parametrize("key", [k for k, _ in KINDS])
def test_each_importer_refuses_other_bytes_before_writing(files, key):
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    with pytest.raises(InputChanged, match="nothing was stored"):
        _importer(key, OTHER)(files[key], conn)
    assert set(_counts(conn).values()) == {0}
    assert not conn.in_transaction
    _importer(key, _sha(files[key]))(files[key], conn)
    assert _counts(conn)["sources"] == 1
