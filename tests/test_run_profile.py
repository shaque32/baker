"""The run profiler (eval/run_profile.py): time per model job from call timestamps, stance
answers split by the checks on their assumption, and prompt reuse. Synthetic rows only."""

from __future__ import annotations

import json
import sqlite3

import pytest

from core.db import apply_schema, connect
from eval import run_profile

STANCE = "mr:stance:test"
FILLER = "mr:assumptions:test"


def open_db(path: str = ":memory:") -> sqlite3.Connection:
    conn = connect(path)
    apply_schema(conn)
    conn.execute("PRAGMA foreign_keys = OFF")  # only the tables the profiler reads
    for run, purpose in ((STANCE, "stance"), (FILLER, "assumptions")):
        conn.execute(
            "INSERT INTO model_runs (id, pipeline_run_id, purpose, model_name, model_sha256,"
            " prompt_version, params_json, started_at_utc) VALUES (?, 'pr:test', ?, 'm', 'x',"
            " 'v', '{}', 't')",
            (run, purpose),
        )
    return conn


@pytest.fixture
def db() -> sqlite3.Connection:
    return open_db()


def assumption(conn: sqlite3.Connection, aid: str, template: str) -> None:
    conn.execute(
        "INSERT INTO assumptions (id, claim_id, kind, template_id, template_version,"
        " params_json, text, is_core, tier) VALUES (?, 'C01', 'event', ?, '1', '{}', 'a', 1,"
        " 'inferred')",
        (aid, template),
    )


def check(conn: sqlite3.Connection, aid: str, outcome: str, *records: str) -> None:
    n = conn.execute("SELECT count(*) FROM check_results").fetchone()[0]
    conn.execute(
        "INSERT INTO check_results (id, assumption_id, check_name, check_version, outcome,"
        " searched, record_ids_json, detail) VALUES (?, ?, 'sender', '1', ?, 's', ?, 'd')",
        (f"chk:{n}", aid, outcome, json.dumps(list(records))),
    )


_seq = iter(range(1, 10_000))


def call(  # noqa: PLR0913
    conn: sqlite3.Connection,
    run: str,
    at: str,
    prompt: str,
    subject: list[str],
    stance: str | None = None,
) -> None:
    raw = json.dumps({"stance": stance, "quote": "", "rationale": "r"}) if stance else "x"
    n = next(_seq)
    conn.execute(
        "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt, raw_output,"
        " outcome, at_utc) VALUES (?, ?, ?, ?, ?, ?, 'ok', ?)",
        (f"mc:{run}#{n}", run, n, json.dumps(subject), prompt, raw, at),
    )


def t(seconds: int) -> str:
    return f"2026-10-29T22:{seconds // 60:02d}:{seconds % 60:02d}.000000Z"


def test_time_goes_to_the_later_call_and_long_gaps_are_not_counted(db) -> None:  # noqa: ANN001
    call(db, FILLER, t(0), "fill", ["C01"])
    call(db, STANCE, t(40), "a", ["asm:1", "r1"], "irrelevant")
    call(db, STANCE, t(70), "b", ["asm:1", "r2"], "supports")
    call(db, STANCE, t(70 + 700), "c", ["asm:1", "r3"], "supports")  # over the 600 s limit
    prof = run_profile.build(db)
    stance = prof.jobs["stance"]
    assert stance.calls == 3
    assert stance.seconds == [40.0, 30.0]
    assert prof.jobs["assumptions"].seconds == []  # first call: no gap before it
    assert prof.untimed_gaps == 1
    assert round(prof.total_s()) == 70


def test_stance_answers_are_split_by_the_checks_on_their_assumption(db) -> None:  # noqa: ANN001
    assumption(db, "asm:pass", "sender")
    assumption(db, "asm:fail", "sender")
    assumption(db, "asm:open", "no_contact")
    assumption(db, "asm:none", "meaning")
    check(db, "asm:pass", "pass", "r1")
    check(db, "asm:fail", "pass")
    check(db, "asm:fail", "fail")
    check(db, "asm:open", "inconclusive")
    call(db, STANCE, t(0), "p", ["asm:pass", "r1"], "supports")  # the check's own record
    call(db, STANCE, t(10), "p", ["asm:pass", "r2"], "irrelevant")
    call(db, STANCE, t(20), "p", ["asm:fail", "r3"], "contradicts")
    call(db, STANCE, t(30), "p", ["asm:open", "r4"], "irrelevant")
    call(db, STANCE, t(40), "p", ["asm:none", "r5"])  # unparsed answer
    d = run_profile.build(db).as_dict()
    assert d["stance_checks"] == {
        "all passed": 2,
        "a check failed": 1,
        "inconclusive": 1,
        "no check": 1,
    }
    assert d["stance_answers"]["irrelevant"] == 2
    assert d["stance_answers"]["unparsed"] == 1
    assert d["stance_by_check"]["all passed"]["supports"] == 1
    assert d["passed_check_cited_record"] == 1
    assert d["passed_check_cited_record_answers"]["supports"] == 1
    assert d["stance_by_template"] == {"meaning": 1, "no_contact": 1, "sender": 3}


def test_prompt_reuse_counts_the_shared_start_and_the_fixed_end(db) -> None:  # noqa: ANN001
    tail = "INSTRUCTIONS"
    call(db, STANCE, t(0), "HEAD-one-" + tail, ["a", "r1"], "irrelevant")
    call(db, STANCE, t(10), "HEAD-two-" + tail, ["a", "r2"], "irrelevant")
    job = run_profile.build(db).jobs["stance"]
    assert job.prompt_chars == 2 * len("HEAD-one-" + tail)
    assert job.shared_prefix_chars == len("HEAD-")  # only the second call reuses
    # "-INSTRUCTIONS" ends both prompts: counted once per call
    assert job.fixed_tail_chars == 2 * len("-" + tail)


def test_a_single_prompt_has_no_fixed_tail(db) -> None:  # noqa: ANN001
    call(db, FILLER, t(0), "only prompt", ["C01"])
    assert run_profile.build(db).jobs["assumptions"].fixed_tail_chars == 0


def test_render_and_json_print_aggregates_only(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "case.db"
    db = open_db(str(path))
    assumption(db, "asm:secret-claim", "sender")
    call(db, STANCE, t(0), "prompt text", ["asm:secret-claim", "msg:secret"], "supports")
    call(db, STANCE, t(5), "prompt text", ["asm:secret-claim", "msg:secret2"], "irrelevant")
    db.commit()
    text = run_profile.render(run_profile.build(db))
    db.close()
    assert "Stance calls: 2" in text
    assert "secret" not in text and "prompt text" not in text
    out = tmp_path / "profile.json"
    assert run_profile.main(["--db", str(path), "--json", str(out)]) == 0
    saved = out.read_text(encoding="utf-8")
    assert "secret" not in saved and json.loads(saved)["stance_calls"] == 2


def test_refuses_the_hidden_case(tmp_path) -> None:  # noqa: ANN001
    assert run_profile.main(["--db", str(tmp_path / "case02" / "case.db")]) == 2
