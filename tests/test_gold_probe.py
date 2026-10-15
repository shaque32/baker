"""Signed probe set in eval/gold/probe/: only Arsh's signed items, copied byte for byte."""

import json
from pathlib import Path

from core.contracts import Stance
from eval.probe_draft.items import RELABELED, RELABELED_2
from eval.probe_draft.model import RELABEL_LABEL, SIGNED_2_LABEL, SIGNED_LABELS, ProbeItem

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "probe" / "probe.jsonl"
DRAFT = ROOT / "eval" / "probe_draft" / "probe_draft.jsonl"


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_gold_holds_only_signed_items():
    items = [ProbeItem.model_validate_json(line) for line in _lines(GOLD)]
    assert [it.probe_id for it in items] == [f"P{n:03d}" for n in range(1, 106)]
    assert {it.labeled_by for it in items} == SIGNED_LABELS


def test_gold_matches_signed_draft_lines():
    signed = [line for line in _lines(DRAFT) if json.loads(line)["labeled_by"] in SIGNED_LABELS]
    assert _lines(GOLD) == signed


def test_relabeled_items_carry_the_2026_10_14_signature():
    items = [ProbeItem.model_validate_json(line) for line in _lines(GOLD)]
    relabeled = {it.probe_id: it for it in items if it.labeled_by == RELABEL_LABEL}
    assert set(relabeled) == RELABELED == {*(f"P0{n}" for n in range(38, 45)), "P071"}
    assert {it.gold_stance for it in relabeled.values()} == {Stance.COMPLICATES}


def test_the_2026_10_15_signature_relabels_five_and_signs_p089_to_p105():
    items = [ProbeItem.model_validate_json(line) for line in _lines(GOLD)]
    signed = {it.probe_id: it for it in items if it.labeled_by == SIGNED_2_LABEL}
    five = {"P049", "P066", "P067", "P068", "P069"}
    assert RELABELED_2 == five
    assert set(signed) == five | {f"P{n:03d}" for n in range(89, 106)}
    assert {signed[pid].gold_stance for pid in five} == {Stance.COMPLICATES}
    assert signed["P049"].trap == "undated_denial"
    assert {signed[pid].trap for pid in five - {"P049"}} == {"told_frame"}
    gated = [it for it in items if not it.disputed]
    assert len(gated) == 95
    contradicts = [it.probe_id for it in gated if it.gold_stance == Stance.CONTRADICTS]
    assert contradicts == ["P062", "P064", "P065", *(f"P{n:03d}" for n in range(98, 106))]


def test_disputed_flags_carried_over():
    rows = [json.loads(line) for line in _lines(GOLD)]
    assert sum(1 for r in rows if r["disputed"]) == 10
