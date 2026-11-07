"""A case made under schema 0.7.0 can store the 0.8.0 verdict bases (Greptile on #228)."""

from __future__ import annotations

import sqlite3

import pytest

from core import db

OLD_BASIS = "supported_basis TEXT CHECK (supported_basis IN ('ai_reviewed', 'confirmed')),"
NEW_BASIS = (
    "supported_basis TEXT CHECK (supported_basis IN "
    "('ai_reviewed', 'confirmed', 'counsel_reviewed', 'checked')),"
)


def _old_case() -> sqlite3.Connection:
    schema = db.SCHEMA_PATH.read_text(encoding="utf-8")
    assert schema.count(NEW_BASIS) == 1
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema.replace(NEW_BASIS, OLD_BASIS))
    return conn


def _insert(conn, vid, basis):
    conn.execute(
        "INSERT INTO verdicts (id, claim_id, pipeline_run_id, verdict, supported_basis,"
        " rule_version, reasons_json, coverage_json, cited_json, decided_at_utc)"
        " VALUES (?, 'C1', 'run', 'supported', ?, '0.4.0', '[]', '[]', '{}', 't')",
        (vid, basis),
    )


def test_an_old_case_refuses_a_checked_verdict_until_upgraded():
    conn = _old_case()
    conn.execute("PRAGMA foreign_keys = OFF")  # the claim and run rows are not the point here
    _insert(conn, "vd:C1@old", "confirmed")
    with pytest.raises(sqlite3.IntegrityError):
        _insert(conn, "vd:C1@new", "checked")
    assert db.upgrade_verdicts(conn) is True
    _insert(conn, "vd:C1@new", "checked")
    _insert(conn, "vd:C1@cou", "counsel_reviewed")
    rows = conn.execute("SELECT id, supported_basis FROM verdicts ORDER BY id").fetchall()
    assert rows == [
        ("vd:C1@cou", "counsel_reviewed"),
        ("vd:C1@new", "checked"),
        ("vd:C1@old", "confirmed"),
    ]
    index = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'verdicts'"
    ).fetchall()
    assert ("idx_verdicts_run",) in index
    with pytest.raises(sqlite3.IntegrityError):
        _insert(conn, "vd:C1@bad", "guessed")  # the new CHECK still refuses other bases
    assert db.upgrade_verdicts(conn) is False  # once is enough


def test_a_current_case_is_left_alone():
    conn = sqlite3.connect(":memory:")
    db.apply_schema(conn)
    table = "SELECT sql FROM sqlite_master WHERE name = 'verdicts'"
    before = conn.execute(table).fetchone()
    assert db.upgrade_verdicts(conn) is False
    assert conn.execute(table).fetchone() == before


def test_the_upgraded_table_matches_the_schema():
    conn = _old_case()
    db.upgrade_verdicts(conn)
    fresh = sqlite3.connect(":memory:")
    db.apply_schema(fresh)

    def cols(c):
        return c.execute("PRAGMA table_info(verdicts)").fetchall()

    assert cols(conn) == cols(fresh)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
