"""Helpers for the check tests. Every value is invented."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from core.audit.assumptions import TEMPLATES, instantiate, local_window
from core.audit.checks import CHECKS
from core.contracts import CheckResult

NY = "America/New_York"

# The stipulations table arrives with schema v0.2 (patches/schema-v0.2.patch). Until that patch
# is applied to core/schema.sql, tests create the same table themselves.
STIPULATIONS_DDL = """
CREATE TABLE IF NOT EXISTS stipulations (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL CHECK (kind IN ('device_owner')),
    subject_id     TEXT NOT NULL,
    person_id      TEXT NOT NULL REFERENCES persons(id),
    statement      TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('proposed', 'confirmed', 'rejected')),
    decided_by     TEXT,
    decided_at_utc TEXT
);
"""


def stipulate(conn: sqlite3.Connection, person_id: str, name: str, device_id: str) -> None:
    """The expert's case-level stipulation that a phone is a person's, confirmed."""
    conn.executescript(STIPULATIONS_DDL)
    conn.execute("INSERT OR IGNORE INTO persons VALUES (?, ?, 'expert:test')", (person_id, name))
    conn.execute(
        "INSERT INTO stipulations VALUES (?, 'device_owner', ?, ?, ?, 'confirmed', 'expert:test',"
        " '2026-10-07T00:00:00Z')",
        (f"stip:device_owner:{device_id}", device_id, person_id, f"{device_id} is {name}'s phone"),
    )


def window(start: datetime, end_exclusive: datetime, raw: str = "test window", tz: str = NY):
    return local_window(start, end_exclusive, tz, raw)


def check(conn: sqlite3.Connection, template_id: str, **params: Any) -> CheckResult:
    """Build the assumption from its template and run the one check that template names."""
    assumption = instantiate("CT", template_id, params)
    (name,) = TEMPLATES[template_id].checks
    return CHECKS[name].run(assumption, conn)


def text(r: CheckResult) -> str:
    return f"{r.searched} {r.detail}"
