"""HIDDEN signed case02 gold and assumption sheet: Arsh's signature on every line, and the same
content as the drafts apart from the signature. Builder threads must not read this file."""

import json
from pathlib import Path

from eval import run_pipeline

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "case02"
DRAFTS = ROOT / "eval" / "synthetic" / "case02"
SIGNED_AT = "2026-10-12T04:27:37Z"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _strip(row: dict, *keys: str) -> dict:
    return {k: v for k, v in row.items() if k not in keys}


def test_gold_signed_and_unchanged_from_the_draft():
    gold, draft = _rows(GOLD / "gold.jsonl"), _rows(DRAFTS / "draft_gold.jsonl")
    assert {(r["labeled_by"], r["labeled_at"]) for r in gold} == {("Arsh", SIGNED_AT)}
    assert [_strip(r, "labeled_by", "labeled_at") for r in gold] == [
        _strip(r, "labeled_by", "labeled_at") for r in draft
    ]


def test_assumption_sheet_signed_and_unchanged_from_the_draft():
    sheet, draft = _rows(GOLD / "assumptions.jsonl"), _rows(DRAFTS / "case02_assumptions.jsonl")
    assert {r["labeled_by"] for r in sheet} == {"Arsh, 2026-10-12"}
    assert [_strip(r, "labeled_by") for r in sheet] == [_strip(r, "labeled_by") for r in draft]


def test_eval_reads_both_as_signed():
    assert run_pipeline.gold_path("case02") == Path("eval/gold/case02/gold.jsonl")
    assert run_pipeline.key_status(run_pipeline.gold_path("case02")) == "signed"
    sheet = run_pipeline.assumption_sheet("case02")
    assert sheet == Path("eval/gold/case02/assumptions.jsonl")
    assert run_pipeline.sheet_status(sheet) == "signed"
