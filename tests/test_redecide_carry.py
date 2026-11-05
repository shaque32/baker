"""Re-running the verdicts keeps an expert's confirmation or override when the rules decide the
claim exactly as before, and lets it lapse, named, when they do not (2026-11-04 walkthrough:
"Re-run verdicts" dropped every override and confirmation on other claims)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from core import pipeline
from core.bundle import export
from core.bundle.verify import FAIL, verify_bundle
from core.contracts import EvidenceStatus, Stance, Verdict
from core.review import actions, audit_log
from core.review.redecide import CARRY_ACTION, redecide
from core.review.status import claim_state
from tests.test_report_consistency import EXPERT, START, _build


def _stored(conn, claim_id: str):  # noqa: ANN001, ANN202
    run = pipeline.last_run(conn)
    return pipeline.load_verdict(conn, claim_id, run["run_id"])


@pytest.fixture
def reviewed(tmp_path: Path):  # noqa: ANN201
    conn = _build(tmp_path / "case01.db", START)
    yield conn
    conn.close()


def test_unchanged_claims_keep_the_experts_confirmation_and_override(reviewed, tmp_path):
    conn = reviewed
    before = {c: _stored(conn, c) for c in ("C05", "C07")}
    assert before["C05"].confirmed_by == EXPERT and before["C07"].override_note == "Reads x."
    result = redecide(conn, EXPERT, lambda: START + timedelta(hours=5))
    after = {c: _stored(conn, c) for c in ("C05", "C07")}
    for c in ("C05", "C07"):
        if c in result.carried:
            assert after[c].confirmed_by == EXPERT
            assert after[c].verdict == before[c].verdict
            assert after[c].override_note == before[c].override_note
        else:
            assert c in result.lapsed and after[c].confirmed_by is None
    assert set(result.carried) | set(result.lapsed) >= {"C05", "C07"}
    assert "C07" in result.carried  # nothing C07 rests on changed since its override
    (n,) = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = ?", (CARRY_ACTION,)
    ).fetchone()
    assert n == len(result.carried)
    assert audit_log.verify_chain(conn)
    path = export.export_bundle(
        conn, tmp_path / "b.zip", EXPERT, counsel_confirmed=True,
        clock=lambda: START + timedelta(hours=6), include="all",
    ).path  # fmt: skip
    fails = [f.detail for f in verify_bundle(path) if f.level == FAIL]
    assert not fails, fails


def test_a_second_rerun_with_no_change_carries_everything(reviewed):
    conn = reviewed
    redecide(conn, EXPERT, lambda: START + timedelta(hours=5))
    second = redecide(conn, EXPERT, lambda: START + timedelta(hours=6))
    assert not second.lapsed
    assert _stored(conn, "C07").verdict == Verdict.CONTRADICTED
    assert _stored(conn, "C07").override_note == "Reads x."


def test_a_claim_whose_verdict_changed_lapses_and_is_named(reviewed):
    conn = reviewed
    redecide(conn, EXPERT, lambda: START + timedelta(hours=5))
    assert _stored(conn, "C05").confirmed_by == EXPERT
    for item in claim_state(conn, "C05").evidence:  # take back the support the expert accepted
        if item.stance == Stance.SUPPORTS and item.status == EvidenceStatus.ACCEPTED:
            actions.decide_evidence(
                conn, item.id, EvidenceStatus.DISMISSED, EXPERT, "Not it.",
                lambda: START + timedelta(hours=6),
            )  # fmt: skip
    result = redecide(conn, EXPERT, lambda: START + timedelta(hours=7))
    assert "C05" in result.lapsed and "C05" not in result.carried
    assert _stored(conn, "C05").confirmed_by is None
