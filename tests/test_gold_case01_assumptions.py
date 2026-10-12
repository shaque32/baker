"""Signed case01 assumption sheet in eval/gold/: Arsh's signature on every row, and the same
rows as the draft build apart from labeled_by."""

import json
from pathlib import Path

from eval import run_pipeline

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "case01" / "assumptions.jsonl"
DRAFT = ROOT / "eval" / "probe_draft" / "case01_assumptions.jsonl"
SIGNED = "Arsh, 2026-10-08"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_every_row_signed():
    assert {r["labeled_by"] for r in _rows(GOLD)} == {SIGNED}


def test_matches_the_draft_apart_from_the_signature():
    strip = lambda r: {k: v for k, v in r.items() if k != "labeled_by"}  # noqa: E731
    assert [strip(r) for r in _rows(GOLD)] == [strip(r) for r in _rows(DRAFT)]


def test_eval_reads_it_as_signed():
    sheet = run_pipeline.assumption_sheet("case01")
    assert sheet == Path("eval/gold/case01/assumptions.jsonl")
    assert run_pipeline.sheet_status(sheet) == "signed"
