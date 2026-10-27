"""The tested-format notice (core/ingest/tested.py): one tested set (a UFDR stating report version
7.48), the version each import states recorded as written, and the same notice on the case
screen, the claim page and the report. All data is synthetic."""

from __future__ import annotations

import html
import json
import re
import sqlite3
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core import pipeline
from core.audit.invariants import check_report_text
from core.db import apply_schema, connect
from core.ingest import coverage, tested
from core.ingest.axiom import AxiomImporter
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.cellebrite_pdf import CellebritePdfImporter
from core.ingest.ufdr import UfdrImporter
from core.report.html import render_report
from eval import run_pipeline
from eval.pipeline_fakes import fake_components
from eval.synthetic.axiom import write_case01 as write_axiom
from eval.synthetic.generate import generate
from eval.synthetic.ufdr import report_xml, write_package
from eval.synthetic.variants.catalog import VARIANTS
from tests.test_coverage_display import _screen, _send, _setup
from tests.test_ufdr import _chat, _msg
from ui.app import Request

TESTED = (
    "Imported without errors from three public test-phone packages (UFDR report version 7.48). "
    "Counts not yet compared with Cellebrite Reader. Not tested on your case data."
)
CHECK = "Check results against the source tool."
NOTICE_RE = re.compile(r"<p class='format-notice[^']*' data-source='([^']*)'>(.*?)</p>", re.S)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


def _ufdr(tmp: Path, version: str | None, name: str = "phone.ufdr") -> Path:
    xml = report_xml(
        {"Chat": [_chat("c1", _msg("see you at noon", "2026-03-04T10:00:00.000+00:00"))]},
        project={"reportVersion": version},
    )
    return write_package(tmp / name, xml)


def _notices(page: str) -> list[tuple[str, str]]:
    """(source id, the notice as plain text) for each format notice on a page."""
    return [
        (sid, html.unescape(re.sub(r"<[^>]+>", "", body)).strip())
        for sid, body in NOTICE_RE.findall(page)
    ]


@pytest.fixture(scope="module")
def case01(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("case01")
    generate(out)
    write_axiom(out)
    return out


# ---------------------------------------------------------------- the tested set


def test_the_tested_set_is_ufdr_report_version_7_48_only():
    assert tested.TESTED == {("ufdr", "7.48")}
    assert tested.at_import("ufdr", "s", "f", "7.48").tested
    for v in ("7.50", "7.48.0", "7.480", "7.4", " 7.48", "7.48 ", "", None):  # exact, as written
        assert not tested.at_import("ufdr", "s", "f", v).tested, v
    for importer in ("cellebrite_excel", "cellebrite_pdf", "axiom"):
        assert not tested.at_import(importer, "s", "f", "7.48").tested


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("7.48", TESTED),
        ("7.50", f"Not tested: Cellebrite UFDR report version 7.50 has not been tested with "
         f"Mabillon. {CHECK}"),
        (None, f"Not tested: Cellebrite UFDR (no report version stated) has not been tested "
         f"with Mabillon. {CHECK}"),
    ],
)  # fmt: skip
def test_a_ufdr_import_records_its_report_version_and_gets_its_notice(tmp_path, version, expected):
    conn = _db()
    UfdrImporter(source_id="u1").import_source(_ufdr(tmp_path, version), conn)
    check = tested.for_source(conn, "u1")
    assert check is not None and check.notice == expected
    assert check.tested == (version == "7.48")
    cov = coverage.load(conn, "u1")
    assert cov is not None and cov.importer_version == "0.3.2"
    recorded = cov.payload["format_check"]
    assert recorded["stated_version"] == version and recorded["tested"] == check.tested
    assert recorded["format"] == "Cellebrite UFDR" and recorded["notice"] == expected
    (logged,) = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ?", (tested.ACTION,)
    ).fetchall()
    assert json.loads(logged[0]) == recorded
    # every UFDR import needs review, 7.48 included, until its counts are compared with
    # Cellebrite Reader's (gate 5a): the notice informs and never relaxes review. The old
    # "synthetic packages only" wording, wrong since #117, is gone.
    s = coverage.summary(conn, "u1")
    assert s is not None and s.format_unverified and s.status == "needs_review"
    assert s.items[0].plain == coverage.FORMAT_UNVERIFIED
    assert s.headline.startswith("Unverified format. ")
    assert not any("synthetic packages" in i.plain for i in s.items)


def _excel(tmp: Path) -> Path:
    (v,) = [v for v in VARIANTS if v.name == "x01_baseline"]
    return v.build(tmp).path


def _pdf(tmp: Path) -> Path:
    (v,) = [v for v in VARIANTS if v.name == "p01_baseline"]
    return v.build(tmp).path


@pytest.mark.parametrize(
    ("make", "importer", "expected"),
    [
        (lambda tmp, c: _excel(tmp), CellebriteExcelImporter,
         "Not tested: Cellebrite Excel export version 7.70.0.1 has not been tested with Mabillon."),
        (lambda tmp, c: _pdf(tmp), CellebritePdfImporter,
         "Not tested: Cellebrite PDF report version 7.70.0.1 has not been tested with Mabillon."),
        (lambda tmp, c: c / "item1-axiom.xml", AxiomImporter,
         # the synthetic XML report states no AXIOM version
         "Not tested: Magnet AXIOM XML report (no version stated) has not been tested with "
         "Mabillon."),
        (lambda tmp, c: c / "item1-axiom.xlsx", AxiomImporter,
         "Not tested: Magnet AXIOM Excel report version SYNTHETIC has not been tested with "
         "Mabillon."),
    ],
)  # fmt: skip
def test_every_other_format_is_not_tested_with_its_version_as_written(
    tmp_path, case01, make, importer, expected
):
    conn = _db()
    importer(source_id="s1").import_source(make(tmp_path, case01), conn)
    check = tested.for_source(conn, "s1")
    assert check is not None and not check.tested
    assert check.notice == f"{expected} {CHECK}"
    assert conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = ?", (tested.ACTION,)
    ).fetchone() == (1,)


def test_a_source_imported_before_the_check_was_recorded_still_gets_its_notice(tmp_path):
    conn = _db()
    UfdrImporter(source_id="u1").import_source(_ufdr(tmp_path, "7.50"), conn)
    (raw,) = conn.execute("SELECT payload_json FROM source_coverage").fetchone()
    p = json.loads(raw)
    del p["format_check"]  # as an import before importer 0.3.2 wrote it
    conn.execute("UPDATE source_coverage SET payload_json = ?", (json.dumps(p),))
    check = tested.for_source(conn, "u1")
    assert check is not None and check.stated_version == "7.50" and not check.tested


def test_a_stated_version_is_cited_text_never_bakers_words(tmp_path):
    conn = _db()
    UfdrImporter(source_id="u1").import_source(_ufdr(tmp_path, "Deleted build"), conn)
    page = render_report(conn)
    check_report_text(page)  # the export's own words are quoted, so the report renders
    assert '<span class="q">Deleted build</span>' in page


def test_cli_import_prints_the_notice(tmp_path, capsys):
    db = tmp_path / "a.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    assert cli_main(["import", "--db", str(db), "--report", str(_ufdr(tmp_path, "7.48"))]) == 0
    assert TESTED in capsys.readouterr().out


# ---------------------------------------------------------------- screen and report match


def _overview(app) -> str:  # noqa: ANN001
    return app.handle(Request("GET", "/", {}, {"host": "127.0.0.1:8766"})).text


def test_case_screen_and_report_show_the_same_notices(tmp_path):
    app = _screen(tmp_path)
    for version, name in (("7.48", "a.ufdr"), ("7.50", "b.ufdr"), (None, "c.ufdr")):
        assert _send(app, _ufdr(tmp_path, version, name)).status == 303
    overview, setup = _overview(app), _setup(app)
    assert app.case is not None
    conn = connect(app.case.db)
    report = render_report(conn)
    conn.close()
    limits = report.split("<h2>Limitations</h2>", 1)[1].split("<h2>", 1)[0]
    shown = _notices(overview)
    assert len(shown) == 3
    assert sorted(shown) == sorted(_notices(limits)) == sorted(_notices(setup))
    texts = [t for _sid, t in shown]
    assert sum(t.startswith(TESTED) for t in texts) == 1
    assert sum(t.startswith("Not tested: ") for t in texts) == 2
    assert "synthetic packages only" not in report and "tested only on synthetic" not in setup
    for page in (overview, setup, report):
        check_report_text(page)


@pytest.fixture
def audited(tmp_path) -> sqlite3.Connection:
    path = tmp_path / "case.db"
    run_pipeline.build_case("case01", path).close()  # type: ignore[attr-defined]
    conn = connect(path)
    pipeline.run_audit(conn, fake_components(accept=True))
    conn.commit()
    yield conn
    conn.close()


def test_each_claim_page_shows_the_notices_its_report_claim_shows(audited, tmp_path):
    from ui.app import App

    report = render_report(audited)
    app = App(tmp_path / "case.db", expert="Test Expert", port=8765)
    run = pipeline.view_run(audited)
    assert run is not None
    seen = 0
    for cid in run["manifest"]:
        block = report.split(f'<div class="claim" id="{cid}">', 1)[1].split('<div class="claim"')[0]
        page = app.handle(Request("GET", "/claim", {"id": cid}, {"host": "127.0.0.1:8765"})).text
        assert _notices(page) == _notices(block), cid
        seen += len(_notices(block))
    assert seen  # the case01 claims rest on its Excel reports, which are not tested
    assert all(t.startswith("Not tested: Cellebrite Excel export") for _s, t in _notices(report))


def test_a_claim_shows_only_the_sources_it_rests_on(audited):
    from core.report.html import claim_format_notices
    from core.review.status import claim_states

    states = claim_states(audited, run=pipeline.view_run(audited))
    for st in states:
        rests = {x.ref.source_id for x in st.evidence} | {
            s for c in st.checks for s in c.source_ids
        }
        named = {sid for sid, _t in _notices(claim_format_notices(audited, st))}
        assert rests <= named, st.claim.id
        if not st.evidence and not st.checks:
            assert named == set(), st.claim.id


def test_the_notice_changes_no_verdict(audited, monkeypatch):
    """Marking every source tested and auditing again gives the same verdicts: nothing in the
    audit reads the tested set."""
    before = [(p.claim_id, p.verdict) for p in pipeline.predictions(audited)]
    stated = {(c.importer, c.stated_version) for c in tested.all_sources(audited)}
    assert stated and not any(tested.at_import(i, "s", "f", v).tested for i, v in stated)
    monkeypatch.setattr(tested, "TESTED", frozenset(stated) | tested.TESTED)
    assert all(c.tested for c in tested.all_sources(audited))
    pipeline.run_audit(audited, fake_components(accept=True))
    assert [(p.claim_id, p.verdict) for p in pipeline.predictions(audited)] == before
