"""Signed probe set in eval/gold/probe/: only Arsh's signed items, copied byte for byte."""

import json
from pathlib import Path

from eval.probe_draft.model import SIGNED_LABEL, ProbeItem

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "probe" / "probe.jsonl"
DRAFT = ROOT / "eval" / "probe_draft" / "probe_draft.jsonl"


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_gold_holds_only_signed_items():
    items = [ProbeItem.model_validate_json(line) for line in _lines(GOLD)]
    assert [it.probe_id for it in items] == [f"P{n:03d}" for n in range(1, 89)]
    assert {it.labeled_by for it in items} == {SIGNED_LABEL}


def test_gold_matches_signed_draft_lines():
    signed = [line for line in _lines(DRAFT) if json.loads(line)["labeled_by"] == SIGNED_LABEL]
    assert _lines(GOLD) == signed


def test_disputed_flags_carried_over():
    rows = [json.loads(line) for line in _lines(GOLD)]
    assert sum(1 for r in rows if r["disputed"]) == 10
