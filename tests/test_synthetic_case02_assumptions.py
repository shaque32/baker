"""HIDDEN case02 assumption sheet: committed files match the build, every entry fits its
template, and each deterministic check finds what the sheet expects on case02.

Builder threads must not read this file, eval/synthetic/case02* or eval/out/case02/.
"""

import json
import sqlite3

import pytest

from core.audit.assumptions import (
    TEMPLATES,
    TEMPLATES_VERSION,
    instantiate,
    parse_params,
    templates_for,
)
from core.audit.checks import CHECKS
from core.contracts import ClaimType
from eval import run_pipeline
from eval.synthetic import case02_assumptions as spec
from eval.synthetic.case02_generate import generate
from tests.checks import helpers

ROWS = [json.loads(line) for line in spec.JSONL.read_text(encoding="utf-8").splitlines()]


def test_committed_files_match_the_build():
    recs = spec.records()
    assert spec.JSONL.read_text(encoding="utf-8") == spec.render_jsonl(recs)
    assert spec.SHEET.read_text(encoding="utf-8") == spec.render_sheet(recs)


def test_every_draft_gold_claim_has_a_core_assumption():
    assert [c.claim_id for c in spec.SPEC] == sorted(spec.gold_by_id())
    for c in spec.SPEC:
        assert any(a.is_core for a in c.assumptions), c.claim_id


def test_known_misses_are_named_in_their_gaps():
    by_id = {c.claim_id: c for c in spec.SPEC}
    for claim_id in spec.KNOWN_MISSES:
        assert any(g.startswith("KNOWN MISS") for g in by_id[claim_id].gaps), claim_id


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"{r['claim_id']}-{r['template_id']}")
def test_entry_fits_its_template(row):
    assert row["template_version"] == TEMPLATES_VERSION
    assert row["labeled_by"] == spec.DRAFT_LABEL
    parse_params(row["template_id"], row["params"])
    claim_type = ClaimType(spec.gold_by_id()[row["claim_id"]]["claim_type"])
    assert row["template_id"] in {t.id for t in templates_for(claim_type)}


@pytest.fixture(scope="module")
def case02(tmp_path_factory):
    out = tmp_path_factory.mktemp("case02")
    generate(out, out / "case02.db")
    conn = sqlite3.connect(out / "case02.db")
    helpers.stipulate(conn, spec.BRANDT, "Nolan Brandt", spec.ITEM1)
    helpers.stipulate(conn, spec.QUINTERO, "Rafael Quintero", spec.ITEM2)
    yield conn
    conn.close()


@pytest.mark.parametrize(
    "row",
    [r for r in ROWS if r["expected_check"]],
    ids=lambda r: f"{r['claim_id']}-{r['template_id']}",
)
def test_check_finds_what_the_sheet_expects(case02, row):
    a = instantiate(row["claim_id"], row["template_id"], row["params"], row["is_core"])
    (name,) = TEMPLATES[row["template_id"]].checks
    result = CHECKS[name].run(a, case02)
    assert result.outcome.value == row["expected_check"], result.detail


def test_eval_uses_the_drafts_until_signed_and_says_so():
    signed = run_pipeline.Path("eval/gold/case02/gold.jsonl")
    if signed.exists():
        pytest.skip("case02 is signed; tests/test_gold_case02.py covers it")
    assert run_pipeline.gold_path("case02") == spec.GOLD_DRAFT.relative_to(spec.HERE.parents[2])
    assert run_pipeline.key_status(run_pipeline.gold_path("case02")).startswith("draft")
    sheet = run_pipeline.assumption_sheet("case02")
    assert sheet is not None and run_pipeline.sheet_status(sheet).startswith("draft")
    assert run_pipeline.is_hidden("case02") and not run_pipeline.is_hidden("case01")
