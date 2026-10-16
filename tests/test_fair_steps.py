"""The 14B-vs-Opus test's own scoring (eval/bench/fair_steps.py): the split-aware claim matcher
and the replay of a first audit's fills. No model is called."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.contracts import ClaimType, GoldClaim, Verdict
from core.db import apply_schema, connect
from eval.bench.fair_steps import Proposal, ReplayModel, main, pick_entry, split_match


def gold(cid: str, para: int, text: str) -> GoldClaim:
    return GoldClaim(
        claim_id=cid, page=1, para_no=para, text=text, claim_type=ClaimType.COMMUNICATION,
        cross_device=False, gold_verdict=Verdict.SUPPORTED, core_assumptions=(),
        key_evidence=(), trap=None, rationale="test", labeled_by="test",
        labeled_at=datetime(2026, 10, 16, tzinfo=UTC),
    )  # fmt: skip


G1 = gold("C01", 4, "PETROV sent 3 Telegram messages to REYES on March 6, 2026")
G2 = gold("C02", 4, "REYES replied the next morning asking about the tickets")


def found(rows: list[dict]) -> dict[str, bool]:
    return {r["claim_id"]: r["found"] for r in rows}


def test_a_claim_split_into_several_proposals_is_found() -> None:
    props = [
        Proposal("p1", "4", "PETROV sent 3 Telegram messages to REYES."),
        Proposal("p2", "4", "PETROV's messages to REYES were sent on March 6, 2026."),
    ]
    rows = split_match([G1], props)
    assert found(rows) == {"C01": True}
    assert rows[0]["proposals"] == ["p1", "p2"]


def test_one_proposal_counts_toward_one_gold_claim_only() -> None:
    whole = Proposal("p1", "4", f"{G1.text}. {G2.text}.")
    assert sum(found(split_match([G1, G2], [whole])).values()) == 1


def test_every_number_must_be_kept_and_the_paragraph_must_match() -> None:
    no_date = Proposal("p1", "4", "PETROV sent 3 Telegram messages to REYES on March")
    assert found(split_match([G1], [no_date])) == {"C01": False}
    elsewhere = Proposal("p1", "5", G1.text)
    assert found(split_match([G1], [elsewhere])) == {"C01": False}


def _db_with_call(path: Path, prompt: str, raw: str, outcome: str = "ok") -> None:
    conn = connect(path)
    apply_schema(conn)
    conn.execute(
        "INSERT INTO model_runs (id, purpose, model_name, model_sha256, prompt_version,"
        " params_json, started_at_utc) VALUES ('mr:1', 'assumptions', 'm', 'abc', 'v', '{}',"
        " '2026-10-16T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt, raw_output,"
        " outcome, at_utc) VALUES ('mc:mr:1#1', 'mr:1', 1, '[]', ?, ?, ?,"
        " '2026-10-16T00:00:01Z')",
        (prompt, raw, outcome),
    )
    conn.commit()
    conn.close()


def test_the_replay_answers_only_prompts_the_first_audit_sent(tmp_path: Path) -> None:
    db = tmp_path / "case01.db"
    _db_with_call(db, "fill C01", '{"assumptions": []}')
    replay = ReplayModel(db, "assumptions")
    assert replay.sha256 == "abc"
    assert replay.generate_json("fill C01", {}).raw_text == '{"assumptions": []}'
    with pytest.raises(LookupError):
        replay.generate_json("fill C02", {})


def test_the_replay_skips_failed_calls(tmp_path: Path) -> None:
    db = tmp_path / "case01.db"
    _db_with_call(db, "fill C01", "", outcome="error")
    with pytest.raises(LookupError):
        ReplayModel(db, "assumptions").generate_json("fill C01", {})
    with pytest.raises(LookupError):
        ReplayModel(db, "stance")
    assert sqlite3.connect(db).execute("SELECT count(*) FROM model_calls").fetchone() == (1,)


def test_the_local_arm_and_the_mac_probe_pick_the_same_one_model() -> None:
    two = [{"name": "qwen3-8b-q4_k_m"}, {"name": "qwen3-14b-q4_k_m"}]
    assert pick_entry(two, None)["name"] == "qwen3-14b-q4_k_m"
    assert pick_entry(two, "qwen3-8b-q4_k_m")["name"] == "qwen3-8b-q4_k_m"
    assert pick_entry([{"name": "other"}], None)["name"] == "other"
    with pytest.raises(SystemExit):
        pick_entry([{"name": "a"}, {"name": "b"}], None)
    with pytest.raises(SystemExit):
        pick_entry(two, "missing")


def test_an_unknown_effort_is_refused_before_any_call() -> None:
    with pytest.raises(SystemExit):
        main(["--arm", "opus", "--effort", "medum"])
