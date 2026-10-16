"""The 14B-vs-Opus test's own scoring (eval/bench/fair_steps.py): the split-aware claim matcher,
the replay of a first audit's fills and the cloud retry. No model is called."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.contracts import ClaimType, GoldClaim, Verdict
from core.db import apply_schema, connect
from core.llm.cloud import CloudError
from eval.bench.fair_steps import (
    Proposal,
    ReplayModel,
    Retried,
    main,
    pick_entry,
    sheet_coverage,
    split_match,
    summary,
)


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


def test_strict_matching_stops_unrelated_fragments_pooling_their_words() -> None:
    bits = [
        Proposal("p1", "4", "PETROV owns a garage in Queens"),
        Proposal("p2", "4", "Telegram was installed on 3 phones"),
        Proposal("p3", "4", "REYES moved house in March 2026 and 6 cats came"),
    ]
    assert found(split_match([G1], bits)) == {"C01": True}  # the registered matcher
    assert found(split_match([G1], bits, strict=True)) == {"C01": False}
    real = [
        Proposal("p1", "4", "PETROV sent 3 Telegram messages to REYES."),
        Proposal("p2", "4", "PETROV's messages to REYES were sent on March 6, 2026."),
    ]
    assert found(split_match([G1], real, strict=True)) == {"C01": True}


def test_fills_cover_a_claim_only_with_every_signed_core_template() -> None:
    sheet = [
        {"claim_id": "C01", "template_id": "contact_entry", "is_core": True},
        {"claim_id": "C02", "template_id": "same_account", "is_core": True},
        {"claim_id": "C02", "template_id": "record_time", "is_core": True},
        {"claim_id": "C02", "template_id": "record_time", "is_core": True},
        {"claim_id": "C02", "template_id": "meaning", "is_core": False},
    ]
    fills = [("C01", "contact_entry"), ("C01", "event"), ("C02", "event"), ("C02", "record_time")]
    res = sheet_coverage(sheet, fills)
    assert (res["covered"], res["claims"]) == (1, 2)
    c02 = res["rows"][1]
    assert (c02["missing"], c02["extra"]) == (["record_time", "same_account"], ["event"])
    assert res["rows"][0]["extra"] == ["event"]  # listed, not held against the claim


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


class Flaky:
    """A stand-in cloud model that raises the given failures, then answers."""

    name, sha256, params, where = "claude-opus-5-5", "x", None, "cloud"

    def __init__(self, *failures: CloudError) -> None:
        self.failures, self.sent = list(failures), 0

    def generate_json(self, prompt: str, schema: object, params: object = None) -> str:
        self.sent += 1
        if self.failures:
            raise self.failures.pop(0)
        return "ok"

    def usage(self) -> dict[str, int]:
        return {"calls": self.sent}


def timeout() -> CloudError:
    return CloudError("APITimeoutError", sticky=True, retryable=True)


def test_a_retryable_failure_is_sent_again_as_the_product_does() -> None:
    m = Retried(Flaky(timeout(), timeout()), sleep=lambda _s: None)
    assert m.generate_json("p", {}) == "ok"
    assert (m.failure, m.usage()) == (None, {"calls": 3})


def test_a_failure_left_after_the_retries_makes_the_run_invalid() -> None:
    inner = Flaky(timeout(), timeout(), timeout())
    m = Retried(inner, sleep=lambda _s: None)
    with pytest.raises(CloudError):
        m.generate_json("p", {})
    assert m.failure == "APITimeoutError"
    with pytest.raises(CloudError):  # later calls are not sent at all
        m.generate_json("q", {})
    assert inner.sent == 3
    res = {"arm": "opus", "model": m.name, "invalid": "a cloud call failed"}
    assert "INVALID, do not score" in summary(res)


def test_a_refusal_is_the_models_own_dropped_label_not_an_invalid_run() -> None:
    m = Retried(Flaky(CloudError("declined", sticky=False)), sleep=lambda _s: None)
    with pytest.raises(CloudError):
        m.generate_json("p", {})
    assert m.failure is None
    assert m.generate_json("q", {}) == "ok"
