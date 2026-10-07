import re
import sqlite3
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core import contracts as c
from core.db import SCHEMA_PATH, apply_schema

SCHEMA = SCHEMA_PATH.read_text(encoding="utf-8")

# (table, column) -> the contracts enum its CHECK constraint must match
ENUM_COLUMNS = {
    ("sources", "kind"): c.SourceKind,
    ("sources", "fidelity"): c.Fidelity,
    ("sources", "extraction_type"): c.ExtractionType,
    ("identity_links", "status"): c.IdentityLinkStatus,
    ("identity_links", "tier"): c.ProvenanceTier,
    ("messages", "direction"): c.MessageDirection,
    ("calls", "direction"): c.CallDirection,
    ("govdocs", "doc_kind"): c.DocKind,
    ("claims", "claim_type"): c.ClaimType,
    ("claims", "status"): c.ClaimStatus,
    ("assumptions", "kind"): c.AssumptionKind,
    ("assumptions", "tier"): c.ProvenanceTier,
    ("evidence_items", "stance"): c.Stance,
    ("evidence_reviews", "reviewer_kind"): c.ReviewerKind,
    ("evidence_reviews", "status"): c.EvidenceStatus,
    ("check_results", "outcome"): c.CheckOutcome,
    ("stipulations", "kind"): c.StipulationKind,
    ("stipulations", "status"): c.StipulationStatus,
    ("verdicts", "verdict"): c.Verdict,
    ("verdicts", "supported_basis"): c.SupportedBasis,
    ("model_calls", "outcome"): c.ModelCallOutcome,
    ("pipeline_runs", "status"): c.PipelineRunStatus,
}

# (table, column) -> the subset of an enum its CHECK constraint allows
SUBSET_COLUMNS = {
    ("evidence_items", "tier"): {t.value for t in c.RECORD_TIERS},
}


def check_values(table: str, column: str) -> set[str]:
    body = re.search(rf"CREATE TABLE {table} \((.*?)\n\);", SCHEMA, re.S)
    assert body, f"table {table} not found"
    m = re.search(rf"\b{column}\b[^\n]*?CHECK \({column} IN \((.*?)\)\)", body.group(1), re.S)
    assert m, f"no CHECK on {table}.{column}"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_schema_applies_cleanly():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sources", "messages", "claims", "evidence_items", "verdicts", "audit_log"} <= tables


@pytest.mark.parametrize(("table", "column"), sorted(ENUM_COLUMNS))
def test_schema_enums_match_contracts(table, column):
    assert check_values(table, column) == {e.value for e in ENUM_COLUMNS[(table, column)]}


@pytest.mark.parametrize(("table", "column"), sorted(SUBSET_COLUMNS))
def test_schema_subset_enums(table, column):
    assert check_values(table, column) == SUBSET_COLUMNS[(table, column)]


def test_every_evidence_table_has_source_ref():
    for table in [
        "devices",
        "accounts",
        "threads",
        "messages",
        "attachments",
        "calls",
        "contacts",
        "locations",
        "evidence_items",
    ]:
        body = re.search(rf"CREATE TABLE {table} \((.*?)\n\);", SCHEMA, re.S).group(1)
        assert "source_id" in body and "locator" in body, table


def test_models_are_frozen():
    ref = c.SourceRef(source_id="s1", locator="/report/msg[1]")
    with pytest.raises(ValidationError):
        ref.locator = "changed"


def test_timestamp_rejects_naive_utc():
    with pytest.raises(ValidationError):
        c.Timestamp(utc=datetime(2026, 3, 5, 2, 31), offset_min=None, raw=None)
    c.Timestamp(
        utc=datetime(2026, 3, 5, 2, 31, tzinfo=UTC), offset_min=-300, raw="3/4/2026 9:31 PM"
    )


def test_evidence_item_requires_verified_quote():
    fields = dict(
        id="e1",
        assumption_id="a1",
        record_id="msg:s1:1",
        ref=c.SourceRef(source_id="s1", locator="x"),
        stance=c.Stance.SUPPORTS,
        quote="Bring it tomorrow.",
        rationale="r",
        tier=c.ProvenanceTier.OBSERVED,
        status=c.EvidenceStatus.OPEN,
        model_run_id="m1",
    )
    c.EvidenceItem(quote_verified=True, **fields)
    with pytest.raises(ValidationError):
        c.EvidenceItem(quote_verified=False, **fields)


def test_rules_are_a_stub():
    from core.audit import rules

    with pytest.raises(NotImplementedError):
        rules.decide_verdict(None, [], [], [])  # type: ignore[arg-type]
