"""The loss report (eval/loss_report.py): one stage per gold key record, and the dropped-label
split. Synthetic rows only."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.contracts import ClaimType, GoldClaim, Verdict
from core.db import apply_schema, connect
from eval import loss_report

RUN = "mr:stance:test"


def gold(claim_id: str, *key: str) -> GoldClaim:
    return GoldClaim(
        claim_id=claim_id,
        page=1,
        para_no=1,
        text="t",
        claim_type=ClaimType.COMMUNICATION,
        cross_device=False,
        gold_verdict=Verdict.SUPPORTED,
        core_assumptions=(),
        key_evidence=key,
        trap=None,
        rationale="r",
        labeled_by="test",
        labeled_at=datetime(2026, 10, 27, tzinfo=UTC),
    )


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = connect(":memory:")
    apply_schema(conn)
    conn.execute("PRAGMA foreign_keys = OFF")  # only the tables the report reads
    conn.execute(
        "INSERT INTO model_runs (id, purpose, model_name, model_sha256, prompt_version,"
        " params_json, started_at_utc) VALUES (?, 'stance', 'm', 'x', 'v', '{}', 't')",
        (RUN,),
    )
    return conn


def assumption(conn: sqlite3.Connection, aid: str, claim_id: str, is_core: int = 1) -> None:
    conn.execute(
        "INSERT INTO assumptions (id, claim_id, kind, template_id, template_version,"
        " params_json, text, is_core, tier) VALUES (?, ?, 'event', 't', '1', '{}', 'a', ?,"
        " 'inferred')",
        (aid, claim_id, is_core),
    )


_seq = iter(range(1, 10_000))


def call(conn, aid: str, rid: str, outcome: str, stance: str | None, run: str = RUN) -> None:  # noqa: ANN001
    raw = json.dumps({"stance": stance, "quote": "", "rationale": "r"}) if stance else "not json"
    n = next(_seq)
    conn.execute(
        "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt, raw_output,"
        " outcome, at_utc) VALUES (?, ?, ?, ?, 'p', ?, ?, 't')",
        (f"mc:{run}#{n}", run, n, json.dumps([aid, rid]), raw, outcome),
    )


def item(conn, aid: str, rid: str, stance: str, run: str = RUN) -> None:  # noqa: ANN001
    conn.execute(
        "INSERT INTO evidence_items (id, assumption_id, source_id, locator, record_id, stance,"
        " quote, rationale, tier, model_run_id) VALUES (?, ?, 's', 'l', ?, ?, 'q', 'r',"
        " 'observed', ?)",
        (f"ev:{aid}|{rid}|{stance}", aid, rid, stance, run),
    )


def failed_check(conn, aid: str) -> None:  # noqa: ANN001
    conn.execute(
        "INSERT INTO check_results (id, assumption_id, check_name, check_version, outcome,"
        " searched, detail) VALUES (?, ?, 'sender', '1', 'fail', 's', 'd')",
        (f"chk:{aid}", aid),
    )


def stages(report: loss_report.LossReport) -> dict[tuple[str, str], str]:
    return {(k.claim_id, k.record_id): k.stage for k in report.key}


def test_each_key_record_gets_one_stage(db) -> None:
    assumption(db, "a1", "C01")
    assumption(db, "a2", "C02")
    assumption(db, "a4", "C04")
    # C01: one surfaced, one labelled irrelevant, one whose quote failed, one never retrieved
    call(db, "a1", "r1", "ok", "supports")
    item(db, "a1", "r1", "supports")
    call(db, "a1", "r2", "quote_failed", "irrelevant")
    call(db, "a1", "r3", "quote_failed", "complicates")
    call(db, "a1", "r9", "ok", "supports")  # retrieved, not key
    item(db, "a1", "r9", "supports")
    # C02: unusable output
    call(db, "a2", "r5", "invalid_output", None)
    # C04: settled by a failed core check, so never labelled
    failed_check(db, "a4")
    r = loss_report.build(
        db, [gold("C01", "r1", "r2", "r3", "r4"), gold("C02", "r5"), gold("C03", "r6"),
             gold("C04", "r7")],
    )  # fmt: skip
    assert stages(r) == {
        ("C01", "r1"): "surfaced",
        ("C01", "r2"): "labelled_irrelevant",
        ("C01", "r3"): "quote_dropped",
        ("C01", "r4"): "not_retrieved",
        ("C02", "r5"): "invalid_output",
        ("C03", "r6"): "refused",
        ("C04", "r7"): "not_retrieved",
    }
    assert r.not_retrieved_split() == {loss_report.SETTLED: 1, loss_report.MISSED: 1}
    assert dict(r.dropped) == {"irrelevant": 1, "quote_failed": 1, "invalid_output": 1}
    assert r.stored == 2


def test_furthest_stage_across_assumptions_wins(db) -> None:
    assumption(db, "a1", "C01")
    assumption(db, "a2", "C01")
    call(db, "a1", "r1", "quote_failed", "irrelevant")
    call(db, "a2", "r1", "ok", "contradicts")
    item(db, "a2", "r1", "contradicts")
    r = loss_report.build(db, [gold("C01", "r1")])
    assert r.key[0].stage == "surfaced" and r.key[0].stances == ("contradicts",)


def test_last_call_per_pair_counts(db) -> None:
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "error", None)
    call(db, "a1", "r1", "ok", "supports")  # asked again on a re-run
    item(db, "a1", "r1", "supports")
    r = loss_report.build(db, [gold("C01", "r1")])
    assert r.key[0].stage == "surfaced" and sum(r.dropped.values()) == 0


def test_stored_irrelevant_item_is_not_surfaced(db) -> None:
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "ok", "irrelevant")
    item(db, "a1", "r1", "irrelevant")
    r = loss_report.build(db, [gold("C01", "r1")])
    assert r.key[0].stage == "labelled_irrelevant" and r.stored_irrelevant == 1


def test_main_leak_names_the_bigger_loss(db) -> None:
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "quote_failed", "irrelevant")
    call(db, "a1", "r2", "quote_failed", "irrelevant")
    call(db, "a1", "r3", "quote_failed", "supports")
    r = loss_report.build(db, [gold("C01", "r1", "r2", "r3")])
    assert r.main_leak().startswith("stance step (2 key records vs 1")


def test_other_runs_are_ignored_and_two_runs_need_a_choice(db) -> None:
    db.execute(
        "INSERT INTO model_runs (id, purpose, model_name, model_sha256, prompt_version,"
        " params_json, started_at_utc) VALUES ('mr:other', 'stance', 'm', 'x', 'v', '{}', 't')"
    )
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "ok", "supports", run="mr:other")
    item(db, "a1", "r1", "supports", run="mr:other")
    with pytest.raises(SystemExit):
        loss_report.build(db, [gold("C01", "r1")])
    r = loss_report.build(db, [gold("C01", "r1")], model_run_id=RUN)
    assert r.key[0].stage == "not_retrieved"


def test_no_stance_run_is_refused() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    with pytest.raises(SystemExit, match="no stance model run"):
        loss_report.build(conn, [gold("C01", "r1")])


def test_cli_reads_read_only_and_hides_ids_for_a_hidden_case(db, tmp_path: Path) -> None:
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "quote_failed", "irrelevant")
    db.commit()  # a backup waits on an open write transaction
    path = tmp_path / "case.db"
    disk = sqlite3.connect(path)
    db.backup(disk)
    disk.close()
    before = path.read_bytes()
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    (gold_dir / "gold.jsonl").write_text(gold("C01", "r1").model_dump_json() + "\n")
    (gold_dir / "case.json").write_text(json.dumps({"hidden": True}))
    out = tmp_path / "loss.json"
    assert loss_report.main(["--db", str(path), "--gold", str(gold_dir / "gold.jsonl"),
                             "--json", str(out)]) == 0  # fmt: skip
    data = json.loads(out.read_text())
    assert "per_record" not in data and data["stages"]["labelled_irrelevant"] == 1
    assert path.read_bytes() == before
