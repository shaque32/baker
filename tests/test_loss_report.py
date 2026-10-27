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
PRUN = "pr:test"  # the pipeline run RUN belongs to


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
    stance_run(conn, RUN, PRUN)
    return conn


def stance_run(conn: sqlite3.Connection, run: str, prun: str) -> None:
    conn.execute(
        "INSERT INTO model_runs (id, pipeline_run_id, purpose, model_name, model_sha256,"
        " prompt_version, params_json, started_at_utc) VALUES (?, ?, 'stance', 'm', 'x', 'v',"
        " '{}', 't')",
        (run, prun),
    )


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


def finish(
    conn: sqlite3.Connection,
    *claims: str,
    run: str = RUN,
    prun: str = PRUN,
    uses: list[str] | None = None,
) -> None:
    """The entry a pipeline run writes as each claim finishes (core/pipeline.py), with the
    manifest built from the rows: the claim's assumptions (only those in `uses`, if given),
    their checks, and the items and model calls of `run` for them."""
    for cid in claims:
        aids = [r[0] for r in conn.execute("SELECT id FROM assumptions WHERE claim_id = ?",
                                           (cid,)) if uses is None or r[0] in uses]  # fmt: skip

        def of(sql: str, *args: str) -> list[str]:
            return [r[0] for r in conn.execute(sql, args) if r[1] in aids]  # noqa: B023

        manifest = {
            "assumptions": aids,
            "checks": of("SELECT id, assumption_id FROM check_results"),
            "evidence": of(
                "SELECT id, assumption_id FROM evidence_items WHERE model_run_id = ?", run
            ),
        }
        calls = [r[0] for r in conn.execute(
            "SELECT id, subject_json FROM model_calls WHERE model_run_id = ?", (run,))
            if json.loads(r[1])[0] in aids]  # fmt: skip
        n = next(_seq)
        conn.execute(
            "INSERT INTO audit_log (seq, at_utc, actor, action, payload_json, prev_hash, hash)"
            " VALUES (?, 't', 'system', 'pipeline.claim', ?, '', ?)",
            (n, json.dumps({"run_id": prun, "claim_id": cid, "manifest": manifest,
                            "model_calls": {"ids": calls}}), f"h{n}"),
        )  # fmt: skip


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
    finish(db, "C01", "C02", "C03", "C04")
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
    finish(db, "C01")
    r = loss_report.build(db, [gold("C01", "r1")])
    assert r.key[0].stage == "surfaced" and r.key[0].stances == ("contradicts",)


def test_last_call_per_pair_counts(db) -> None:
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "error", None)
    call(db, "a1", "r1", "ok", "supports")  # asked again on a re-run
    item(db, "a1", "r1", "supports")
    finish(db, "C01")
    r = loss_report.build(db, [gold("C01", "r1")])
    assert r.key[0].stage == "surfaced" and sum(r.dropped.values()) == 0


def test_stored_irrelevant_item_is_not_surfaced(db) -> None:
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "ok", "irrelevant")
    item(db, "a1", "r1", "irrelevant")
    finish(db, "C01")
    r = loss_report.build(db, [gold("C01", "r1")])
    assert r.key[0].stage == "labelled_irrelevant" and r.stored_irrelevant == 1


def test_main_leak_names_the_bigger_loss(db) -> None:
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "quote_failed", "irrelevant")
    call(db, "a1", "r2", "quote_failed", "irrelevant")
    call(db, "a1", "r3", "quote_failed", "supports")
    finish(db, "C01")
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
    finish(db, "C01")
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
    finish(db, "C01")
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


def test_an_earlier_runs_items_come_from_its_claim_entries(db) -> None:
    # A later run made the same item and took over its model_run_id; the earlier run's claim
    # entry in the audit log still lists it, so it still counts as surfaced for that run.
    later = "mr:stance:later"
    stance_run(db, later, "pr:later")
    assumption(db, "a1", "C01")
    call(db, "a1", "r1", "ok", "supports")
    item(db, "a1", "r1", "supports")
    finish(db, "C01")
    call(db, "a1", "r1", "ok", "supports", run=later)
    db.execute("UPDATE evidence_items SET model_run_id = ?", (later,))
    finish(db, "C01", run=later, prun="pr:later")
    for run in (RUN, later):
        r = loss_report.build(db, [gold("C01", "r1")], run)
        assert stages(r) == {("C01", "r1"): "surfaced"}, run


def test_rows_an_earlier_audit_left_are_not_counted(db) -> None:
    # An earlier audit gave C01 an assumption and settled C02 with a failed core check. This
    # run's filler refused C01 and gave C02 a new assumption, and it did not finish C03. Each
    # claim is staged by what its own entry lists, so the earlier rows change nothing.
    stance_run(db, "mr:old", "pr:old")
    assumption(db, "a_old1", "C01")
    assumption(db, "a_old2", "C02")
    failed_check(db, "a_old2")
    call(db, "a_old1", "r1", "ok", "supports", run="mr:old")
    item(db, "a_old1", "r1", "supports", run="mr:old")
    finish(db, "C01", "C02", "C03", run="mr:old", prun="pr:old")
    assumption(db, "a2", "C02")
    call(db, "a2", "r9", "ok", "supports")  # retrieved, not key
    item(db, "a2", "r9", "supports")
    finish(db, "C01", uses=[])
    finish(db, "C02", uses=["a2"])
    key = [gold("C01", "r1"), gold("C02", "r2"), gold("C03", "r3")]
    r = loss_report.build(db, key, RUN)
    assert stages(r) == {
        ("C01", "r1"): "refused",
        ("C02", "r2"): "not_retrieved",
        ("C03", "r3"): "not_audited",
    }
    assert r.not_retrieved_split() == {loss_report.SETTLED: 0, loss_report.MISSED: 1}
    assert r.stored == 1
    r = loss_report.build(db, key, "mr:old")
    assert stages(r) == {
        ("C01", "r1"): "surfaced",
        ("C02", "r2"): "not_retrieved",
        ("C03", "r3"): "refused",
    }
    assert r.not_retrieved_split() == {loss_report.SETTLED: 1, loss_report.MISSED: 0}


def test_hidden_is_read_from_the_cases_own_folder(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic"
    (synthetic / "caseX").mkdir(parents=True)
    (synthetic / "caseX" / "case.json").write_text('{"hidden": true}', encoding="utf-8")
    (synthetic / "caseY").mkdir()
    (synthetic / "caseY" / "case.json").write_text('{"hidden": false}', encoding="utf-8")
    signed = tmp_path / "gold"
    for case in ("caseX", "caseY"):
        (signed / case).mkdir(parents=True)
    assert loss_report.is_hidden(signed / "caseX" / "gold.jsonl", synthetic)
    assert not loss_report.is_hidden(signed / "caseY" / "gold.jsonl", synthetic)
    assert loss_report.is_hidden(tmp_path / "case02" / "gold.jsonl", synthetic)  # always
