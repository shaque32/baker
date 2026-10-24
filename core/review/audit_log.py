"""Append-only, hash-chained audit log (the `audit_log` table)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from core import db
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


ANCHORS_SUFFIX = ".anchors.jsonl"  # added to the database's full name: case.db.anchors.jsonl

BLOCKED = (
    "the case database was changed outside Mabillon, so this case cannot be opened for review or "
    "reported. Nothing was changed. Restore the case from a backup, or make a new case from the "
    'original files (docs/review-screen.md, "When a case is blocked"). The command baker '
    "verify-log still reads it."
)


class ChainBroken(Exception):
    """A case whose audit log no longer verifies, or no longer reaches an entry Mabillon recorded
    outside the database. Opening or reporting it fails closed."""

    def __init__(self, seq: int, problem: str | None = None) -> None:
        self.seq = seq
        self.problem = problem or f"the audit log's hash chain is broken at entry {seq}"
        super().__init__(f"{self.problem}: {BLOCKED}")


class AnchorUnwritable(ChainBroken):
    """Mabillon cannot record the anchor beside the database (read-only media, permissions). The
    case is not opened or reported, because the next check could not see a cut from here on."""

    def __init__(self, anchors: Path, err: OSError) -> None:
        self.seq = 0
        self.problem = f"Mabillon cannot write {anchors.name} beside the case database ({err})"
        Exception.__init__(
            self,
            f"{self.problem}. Nothing was changed. Copy the case folder somewhere Mabillon can "
            "write, then open the copy.",
        )


def first_break(
    conn: sqlite3.Connection, withheld: Mapping[int, Mapping[str, str]] | None = None
) -> int | None:
    """The seq of the first entry that does not match the chain, or None when it verifies.

    `withheld`: entries a scoped reproducibility bundle left out (core/bundle/export.py), by
    seq, each with its prev_hash and hash. Without its payload a withheld entry's own hash
    cannot be recomputed, so it is taken as given; the entries after it still have to chain
    from it, up to the last hash the report prints."""
    withheld = withheld or {}
    prev = ""
    rows = conn.execute(
        "SELECT seq, at_utc, actor, action, payload_json, prev_hash, hash FROM audit_log"
        " ORDER BY seq"
    )
    entries: list[tuple] = [
        (seq, None, None, None, None, w.get("prev_hash"), w.get("hash"), True)
        for seq, w in withheld.items()
    ]
    entries += [(*r, False) for r in rows]
    entries.sort(key=lambda r: (r[0], r[7]))
    expect = 1
    for seq, at, actor, action, payload_json, prev_hash, h, stub in entries:
        if withheld and seq != expect:  # a seq both withheld and present, or one missing
            return seq if seq > expect else expect - 1
        expect = seq + 1
        try:
            ok = prev_hash == prev and (
                isinstance(h, str)
                if stub
                else entry_hash(prev_hash, at, actor, action, payload_json) == h
            )
        except (TypeError, ValueError):  # a non-text value stored by an edit outside Mabillon
            ok = False
        if not ok:
            return seq
        prev = h
    return None


def decision_problem(conn: sqlite3.Connection) -> tuple[int, str] | None:
    """(seq, why) for the first expert evidence decision that the log and the stored reviews no
    longer agree on, or None. Each evidence.decide entry must have its expert review row, with
    the status (and, from #86 on, the reason) it logged, and each expert review row must have
    its entry. So a row edited, added or removed outside Mabillon is caught. Entries logged before
    #86 carry no reason, so their reasons are not compared. One statement reads both tables,
    so a decision committed meanwhile by another Mabillon process is seen whole or not at all."""
    logged: dict[str, tuple[int, str | None, str | None]] = {}
    stored: dict[str, tuple[str, str]] = {}
    rows = conn.execute(
        "SELECT 'log', seq, payload_json, NULL, NULL FROM audit_log"
        " WHERE action = 'evidence.decide'"
        " UNION ALL SELECT 'review', NULL, id, reason, status FROM evidence_reviews"
        " WHERE reviewer_kind = 'expert'"
    )
    for kind, seq, text, reason, status in rows:
        if kind == "review":
            stored[text] = (reason, status)
            continue
        try:
            p = json.loads(text)
            review, why, was = p.get("review_id"), p.get("reason"), p.get("status")
        except (ValueError, AttributeError, TypeError):
            return seq, f"evidence decision {seq} of the audit log cannot be read"
        if not isinstance(review, str):
            return seq, f"evidence decision {seq} of the audit log names no review"
        logged.setdefault(review, (seq, why, was))
    for review, (seq, why, was) in sorted(logged.items(), key=lambda kv: kv[1][0]):
        if review not in stored:
            return seq, (
                f"evidence decision {seq} of the audit log has no matching expert review in the "
                "case database, so it was removed outside Mabillon"
            )
        reason, status = stored[review]
        if (why is not None and why != reason) or (was is not None and was != status):
            return seq, (
                f"the expert's decision or reason for evidence decision {seq} of the audit log "
                "was changed after it was logged"
            )
    for review in stored:
        if review not in logged:
            return 0, (
                f"the expert review {review} is in the case database but not in the audit log, "
                "so it was added outside Mabillon"
            )
    return None


def verify_chain(
    conn: sqlite3.Connection, withheld: Mapping[int, Mapping[str, str]] | None = None
) -> bool:
    return first_break(conn, withheld) is None


def anchors_path(db: Path) -> Path:
    """The case's anchor file beside its database (case.db -> case.db.anchors.jsonl; the full
    name, so matter.db and matter.sqlite never share one). It holds entry numbers and hashes
    only, no case content."""
    db = Path(db)
    return db.with_name(db.name + ANCHORS_SUFFIX)


def require_intact(conn: sqlite3.Connection, anchors: Path | None = None) -> None:
    """Raise ChainBroken unless the audit log verifies and still holds every entry recorded in
    the anchor file. The chain alone cannot tell that entries were cut from its end; the
    anchors, kept outside the database, can (back to the newest anchor). Every path that opens
    or reports a case calls this first (the review screen and the CLI), so it fails closed."""
    try:
        _require_intact(conn, anchors)
    except db.DatabaseError as err:  # the table or a column was removed, or the file is damaged
        if isinstance(err, db.OperationalError) and "locked" in str(err):
            raise  # another writer holds the database for now; that is not a broken log
        raise ChainBroken(0, f"the audit log cannot be read ({err})") from err


def _require_intact(conn: sqlite3.Connection, anchors: Path | None) -> None:
    seq = first_break(conn)
    if seq is not None:
        raise ChainBroken(seq)
    found = decision_problem(conn)
    if found is not None:
        raise ChainBroken(*found)
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
        except (ValueError, KeyError, TypeError, OverflowError) as err:  # 1e999 -> inf
            raise ChainBroken(
                0, f"line {n} of the audit log's anchor file {anchors.name} is unreadable"
            ) from err
        row = conn.execute("SELECT hash FROM audit_log WHERE seq = ?", (seq,)).fetchone()
        if row is None:
            raise ChainBroken(
                seq,
                f"the audit log has no entry {seq}, which Mabillon recorded outside the database, "
                "so entries were removed from the end of the log",
            )
        if row[0] != want:
            raise ChainBroken(
                seq,
                f"entry {seq} of the audit log does not match the hash Mabillon recorded outside "
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
    try:  # an append cut off before its newline would join two anchors on one line
        if not created and anchors.stat().st_size:
            with open(anchors, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    line = "\n" + line
    except OSError as err:
        raise AnchorUnwritable(anchors, err) from err
    try:
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
    except OSError as err:
        raise AnchorUnwritable(anchors, err) from err
