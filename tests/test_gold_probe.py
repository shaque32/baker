"""Signed probe set in eval/gold/probe/: only Arsh's signed items, copied byte for byte."""

import json
from pathlib import Path

from core.contracts import Stance
from eval.probe_draft.items import RELABELED
from eval.probe_draft.model import RELABEL_LABEL, SIGNED_LABELS, ProbeItem

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "probe" / "probe.jsonl"
DRAFT = ROOT / "eval" / "probe_draft" / "probe_draft.jsonl"


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_gold_holds_only_signed_items():
    items = [ProbeItem.model_validate_json(line) for line in _lines(GOLD)]
    assert [it.probe_id for it in items] == [f"P{n:03d}" for n in range(1, 89)]
    assert {it.labeled_by for it in items} == SIGNED_LABELS


def test_gold_matches_signed_draft_lines():
    signed = [line for line in _lines(DRAFT) if json.loads(line)["labeled_by"] in SIGNED_LABELS]
    assert _lines(GOLD) == signed


def test_relabeled_items_carry_the_2026_10_14_signature():
    items = [ProbeItem.model_validate_json(line) for line in _lines(GOLD)]
    relabeled = {it.probe_id: it for it in items if it.labeled_by == RELABEL_LABEL}
    assert set(relabeled) == RELABELED == {*(f"P0{n}" for n in range(38, 45)), "P071"}
    assert {it.gold_stance for it in relabeled.values()} == {Stance.COMPLICATES}
    gated = [it for it in items if not it.disputed]
    assert sum(1 for it in gated if it.gold_stance == Stance.CONTRADICTS) == 8


def test_disputed_flags_carried_over():
    rows = [json.loads(line) for line in _lines(GOLD)]
    assert sum(1 for r in rows if r["disputed"]) == 10
