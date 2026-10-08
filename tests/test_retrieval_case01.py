"""Retrieval and context on synthetic case01, against Arsh's gold key evidence."""

import json
import sqlite3
from pathlib import Path

import pytest

from core.audit.context import build_context
from core.audit.retrieval import query_for, search
from core.contracts import Assumption, AssumptionKind, AssumptionParams, ProvenanceTier
from eval.synthetic.generate import generate

GOLD = Path(__file__).resolve().parents[1] / "eval/gold/case01/gold.jsonl"
RECALL_FLOOR = 0.60  # recall@50 from claim wording alone, empty params; measured 0.648 (46/71)


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    generate(out, out / "case01.db")
    c = sqlite3.connect(out / "case01.db")
    yield c
    c.close()


@pytest.fixture(scope="module")
def gold() -> list[dict]:
    return [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line]


def _assumption(claim_id: str, **params) -> Assumption:
    return Assumption(
        id=f"{claim_id}-a",
        claim_id=claim_id,
        kind=AssumptionKind.EVENT,
        template_id="test_template",
        template_version="0",
        params=AssumptionParams(**params),
        text="not parsed",
        is_core=True,
        tier=ProvenanceTier.INFERRED,
    )


def _retrieved(conn, g: dict, k: int) -> set[str]:
    """Claim wording only, with empty params: the floor before templates fill accounts and
    windows."""
    q = query_for(_assumption(g["claim_id"]), conn, claim=g["text"])
    return {c.record_id for c in search(conn, q, k)}


def test_recall_of_gold_key_evidence_does_not_regress(conn, gold):
    hit = total = 0
    for g in gold:
        key = set(g["key_evidence"])
        hit += len(key & _retrieved(conn, g, 50))
        total += len(key)
    assert hit / total >= RECALL_FLOOR, f"recall@50 {hit}/{total}"


def test_handle_change_finds_both_handles_by_user_id(conn, gold):
    c02 = next(g for g in gold if g["claim_id"] == "C02")
    assert set(c02["key_evidence"]) <= _retrieved(conn, c02, 50)


def test_second_alex_stays_two_accounts(conn):
    q = query_for(_assumption("x"), conn, claim='"Alex" wrote about the tickets')
    accounts = {a.split(":", 2)[2] for a in q.account_ids}
    assert "SMS:+12125550182" in accounts
    assert not any("5551234" in a for a in accounts)


def test_item1_context_shows_new_york_time_not_the_printed_utc(conn):
    # Printed 3/5/2026 2:31:00 AM(UTC+0) on item1; the phone is in New York (timezone trap).
    lines = build_context(conn, "msg:item1:Chats!1011", window=0)
    assert lines[0].local_time == "2026-03-04 21:31:00 EST (UTC-05:00)"
