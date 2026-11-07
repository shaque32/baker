"""An expert's override of a verdict the code checks supported stays readable (Greptile on #228).

A confirmed basis must cite evidence (core/contracts.py), and a checked verdict cites none, so an
override to Supported keeps the checked basis there; the screen still says expert override."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core import pipeline
from core.bundle import export
from core.bundle.verify import FAIL, verify_bundle
from core.casework import cases
from core.contracts import SupportedBasis, Verdict
from core.db import connect
from core.review import actions
from core.review.redecide import redecide
from core.review.status import verdict_label
from eval import demo

EXPERT = "expert:Test Expert"
CHECKED = demo.LEFT_OPEN[0]  # C05: rules 0.5.0 support it by its code checks alone


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("demo-override")
    demo.reset(root)
    return root


@pytest.fixture
def conn(built, tmp_path):  # noqa: ANN201
    out = tmp_path / "demo"
    shutil.copytree(built, out)
    (case,) = cases.list_cases(demo.cases_dir(out))
    c = connect(case.db)
    yield c
    c.close()


def _current(conn):  # noqa: ANN001, ANN202
    return pipeline.load_verdict(conn, CHECKED, pipeline.last_run(conn)["run_id"])


def test_the_demo_claim_starts_checked(conn):
    d = _current(conn)
    assert d.verdict is Verdict.SUPPORTED and d.supported_basis is SupportedBasis.CHECKED


def test_an_override_to_supported_keeps_the_checked_basis_and_reads_back(conn):
    actions.override_verdict(conn, CHECKED, Verdict.SUPPORTED, EXPERT, "The records show it.")
    d = _current(conn)
    assert d.supported_basis is SupportedBasis.CHECKED and d.cited_evidence_ids == ()
    assert d.confirmed_by == EXPERT
    assert verdict_label(d)[0] == "Supported (expert override)"


def test_unproven_then_supported_again_reads_back_and_survives_a_rerun(conn, tmp_path):
    actions.override_verdict(conn, CHECKED, Verdict.UNPROVEN, EXPERT, "Not sure yet.")
    assert _current(conn).supported_basis is None
    actions.override_verdict(conn, CHECKED, Verdict.SUPPORTED, EXPERT, "Checked it myself.")
    assert _current(conn).supported_basis is SupportedBasis.CHECKED
    redecide(conn, EXPERT)
    d = _current(conn)  # the re-run carried the override
    assert d.verdict is Verdict.SUPPORTED and d.override_note == "Checked it myself."
    path = export.export_bundle(
        conn,
        tmp_path / "b.zip",
        EXPERT,
        counsel_confirmed=True,
        clock=lambda: datetime(2026, 11, 7, tzinfo=UTC),
        include="all",
    ).path
    fails = [f"{f.check}: {f.detail}" for f in verify_bundle(path) if f.level == FAIL]
    assert fails == []
