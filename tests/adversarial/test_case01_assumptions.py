"""case01 assumption spec: committed files match the build, every entry fits its template, and
each deterministic check finds what the spec expects on case01.

The template and check tests skip until core/audit/assumptions.py and core/audit/checks/
(PR #16) are on the branch.
"""

import importlib
import json
import sqlite3

import pytest

from eval.probe_draft import case01_assumptions as spec

ROWS = [json.loads(line) for line in spec.JSONL.read_text(encoding="utf-8").splitlines()]


def _need(module: str):
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError:
        pytest.skip(f"{module} is not on this branch yet")


def test_committed_files_match_the_build():
    recs = spec.records()
    assert spec.JSONL.read_text(encoding="utf-8") == spec.render_jsonl(recs)
    assert spec.SHEET.read_text(encoding="utf-8") == spec.render_sheet(recs)


def test_every_gold_claim_has_a_core_assumption():
    gold = spec.gold_by_id()
    assert [c.claim_id for c in spec.SPEC] == sorted(gold)
    for c in spec.SPEC:
        assert any(a.is_core for a in c.assumptions), c.claim_id


def test_rows_have_the_pipeline_keys():
    for row in ROWS:
        assert {"claim_id", "template_id", "params", "is_core"} <= row.keys()
        assert row["labeled_by"] == spec.DRAFT_LABEL


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"{r['claim_id']}-{r['template_id']}")
def test_entry_fits_its_template(row):
    assumptions = _need("core.audit.assumptions")
    from core.contracts import ClaimType

    assert row["template_version"] == assumptions.TEMPLATES_VERSION
    assumptions.parse_params(row["template_id"], row["params"])
    claim_type = ClaimType(spec.gold_by_id()[row["claim_id"]]["claim_type"])
    assert row["template_id"] in {t.id for t in assumptions.templates_for(claim_type)}


@pytest.fixture(scope="module")
def case01(tmp_path_factory):
    _need("core.audit.checks")
    helpers = _need("tests.checks.helpers")
    from eval.synthetic.generate import generate

    out = tmp_path_factory.mktemp("case01")
    generate(out, out / "case01.db")
    conn = sqlite3.connect(out / "case01.db")
    helpers.stipulate(conn, spec.PETROV, "Daniel Petrov", spec.ITEM1)
    helpers.stipulate(conn, spec.REYES, "Marcus Reyes", spec.ITEM2)
    yield conn
    conn.close()


@pytest.mark.parametrize(
    "row",
    [r for r in ROWS if r["expected_check"]],
    ids=lambda r: f"{r['claim_id']}-{r['template_id']}",
)
def test_check_finds_what_the_spec_expects(case01, row):
    from core.audit.assumptions import TEMPLATES, instantiate
    from core.audit.checks import CHECKS

    a = instantiate(row["claim_id"], row["template_id"], row["params"], row["is_core"])
    (name,) = TEMPLATES[row["template_id"]].checks
    result = CHECKS[name].run(a, case01)
    assert result.outcome.value == row["expected_check"], result.detail


def test_supported_claims_carry_the_kind_their_type_needs():
    """Rules 0.1.0 rule 3e: e.g. a communication claim needs a core identity assumption."""
    assumptions = _need("core.audit.assumptions")
    rules = _need("core.audit.rules")
    required = getattr(rules, "_REQUIRED_KIND", None)
    if required is None:
        pytest.skip("rules.py has no rule 3e yet")
    from core.contracts import ClaimType

    gold = spec.gold_by_id()
    for c in spec.SPEC:
        if gold[c.claim_id]["gold_verdict"] != "supported":
            continue
        need = required.get(ClaimType(gold[c.claim_id]["claim_type"]))
        kinds = {assumptions.TEMPLATES[a.template_id].kind for a in c.assumptions if a.is_core}
        assert need is None or need in kinds, f"{c.claim_id} needs a core {need} assumption"
