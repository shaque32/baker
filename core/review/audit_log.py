"""Append-only, hash-chained audit log (the `audit_log` table)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from core.contracts import AuditLogEntry


def entry_hash(prev_hash: str, at_utc: str, actor: str, action: str, payload_json: str) -> str:
    """sha256 over prev_hash, at_utc, actor, action, payload_json (as a JSON array, so field
    boundaries are unambiguous)."""
    material = json.dumps([prev_hash, at_utc, actor, action, payload_json], ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def append(
    conn: sqlite3.Connection, at_utc: datetime, actor: str, action: str, payload: object
) -> AuditLogEntry:
    row = conn.execute("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    seq, prev_hash = (row[0] + 1, row[1]) if row else (1, "")
    at = at_utc.isoformat().replace("+00:00", "Z")
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    h = entry_hash(prev_hash, at, actor, action, payload_json)
    conn.execute(
        "INSERT INTO audit_log (seq, at_utc, actor, action, payload_json, prev_hash, hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (seq, at, actor, action, payload_json, prev_hash, h),
    )
    return AuditLogEntry(
        seq=seq,
        at_utc=at_utc,
        actor=actor,
        action=action,
        payload_json=payload_json,
        prev_hash=prev_hash,
        hash=h,
    )


def verify_chain(conn: sqlite3.Connection) -> bool:
    prev = ""
    rows = conn.execute(
        "SELECT seq, at_utc, actor, action, payload_json, prev_hash, hash FROM audit_log"
        " ORDER BY seq"
    )
    for _seq, at, actor, action, payload_json, prev_hash, h in rows:
        if prev_hash != prev or entry_hash(prev_hash, at, actor, action, payload_json) != h:
            return False
        prev = h
    return True
