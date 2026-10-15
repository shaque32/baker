"""Append-only, hash-chained audit log (the `audit_log` table)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

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


ANCHORS_SUFFIX = ".anchors.jsonl"

BLOCKED = (
    "the case database was changed outside Baker, so this case cannot be opened for review or "
    "reported. Nothing was changed. Restore the case from a backup, or make a new case from the "
    'original files (docs/review-screen.md, "When a case is blocked"). The command baker '
    "verify-log still reads it."
)


class ChainBroken(Exception):
    """A case whose audit log no longer verifies, or no longer reaches an entry Baker recorded
    outside the database. Opening or reporting it fails closed."""

    def __init__(self, seq: int, problem: str | None = None) -> None:
        self.seq = seq
        self.problem = problem or f"the audit log's hash chain is broken at entry {seq}"
        super().__init__(f"{self.problem}: {BLOCKED}")


def first_break(conn: sqlite3.Connection) -> int | None:
    """The seq of the first entry that does not match the chain, or None when it verifies."""
    prev = ""
    rows = conn.execute(
        "SELECT seq, at_utc, actor, action, payload_json, prev_hash, hash FROM audit_log"
        " ORDER BY seq"
    )
    for seq, at, actor, action, payload_json, prev_hash, h in rows:
        if prev_hash != prev or entry_hash(prev_hash, at, actor, action, payload_json) != h:
            return seq
        prev = h
    return None


def verify_chain(conn: sqlite3.Connection) -> bool:
    return first_break(conn) is None


def anchors_path(db: Path) -> Path:
    """The case's anchor file beside its database (case.db -> case.anchors.jsonl). It holds
    entry numbers and hashes only, no case content."""
    return Path(db).with_suffix(ANCHORS_SUFFIX)


def require_intact(conn: sqlite3.Connection, anchors: Path | None = None) -> None:
    """Raise ChainBroken unless the audit log verifies and still holds every entry recorded in
    the anchor file. The chain alone cannot tell that entries were cut from its end; the
    anchors, kept outside the database, can (back to the newest anchor). Every path that opens
    or reports a case calls this first (the review screen and the CLI), so it fails closed."""
    seq = first_break(conn)
    if seq is not None:
        raise ChainBroken(seq)
    if anchors is None or not anchors.exists():
        return  # a case made before anchors, or a test database
    try:
        lines = anchors.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise ChainBroken(
            0, f"the audit log's anchor file {anchors.name} cannot be read ({err})"
        ) from err
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            a = json.loads(line)
            seq, want = int(a["seq"]), str(a["hash"])
        except (ValueError, KeyError, TypeError) as err:
            raise ChainBroken(
                0, f"line {n} of the audit log's anchor file {anchors.name} is unreadable"
            ) from err
        row = conn.execute("SELECT hash FROM audit_log WHERE seq = ?", (seq,)).fetchone()
        if row is None:
            raise ChainBroken(
                seq,
                f"the audit log has no entry {seq}, which Baker recorded outside the database, "
                "so entries were removed from the end of the log",
            )
        if row[0] != want:
            raise ChainBroken(
                seq,
                f"entry {seq} of the audit log does not match the hash Baker recorded outside "
                "the database",
            )


def anchor(conn: sqlite3.Connection, anchors: Path) -> None:
    """Record the newest entry's number and hash in the anchor file (append-only), unless the
    newest anchor already names it. Called when a case opens and when a report is built. The
    file holds numbers and hashes only: no times and no reasons, since it stays unencrypted
    beside an encrypted case."""
    last = conn.execute("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    if last is None:
        return
    seq, h = last
    try:
        prev = anchors.read_text(encoding="utf-8").splitlines()
        newest = json.loads(prev[-1]) if prev else {}
        if newest.get("seq") == seq and newest.get("hash") == h:
            return
    except (OSError, ValueError, AttributeError):
        pass  # no file yet; an unreadable one was already refused by require_intact
    line = json.dumps({"seq": seq, "hash": h}, sort_keys=True) + "\n"
    created = not anchors.exists()
    with open(anchors, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    if created and os.name == "posix":  # make the new file's directory entry durable too
        fd = os.open(anchors.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
