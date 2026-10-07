"""Look up any evidence record by its stable id: its source_ref, time and citable text.

Record kinds by id prefix: 'msg:' messages, 'call:' calls, 'contact:' contacts, 'att:' attachments.
A message's citable text is its original body. Calls, contacts and attachments have no body, so
their text is a fixed rendering of observed fields; quote checks must verify against this same
text, so this is the single place it is built.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from core.contracts import SourceRef

KIND_BY_PREFIX = {"msg": "message", "call": "call", "contact": "contact", "att": "attachment"}


@dataclass(frozen=True)
class Record:
    id: str
    kind: str
    ref: SourceRef
    text: str
    ts_utc: str | None


def kind_of(record_id: str) -> str | None:
    return KIND_BY_PREFIX.get(record_id.split(":", 1)[0])


def _ident(conn: sqlite3.Connection, account_id: str | None) -> str:
    if account_id is None:
        return "unknown"
    row = conn.execute("SELECT identifier FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return row[0] if row else account_id


def call_text(
    conn: sqlite3.Connection,
    app: str,
    direction: str,
    from_id: str | None,
    to_id: str | None,
    duration_s: int | None,
) -> str:
    dur = "unknown" if duration_s is None else f"{duration_s} s"
    return (
        f"{direction} {app} call from {_ident(conn, from_id)} to {_ident(conn, to_id)},"
        f" duration {dur}"
    )


def get_record(conn: sqlite3.Connection, record_id: str) -> Record | None:
    kind = kind_of(record_id)
    if kind == "message":
        row = conn.execute(
            "SELECT source_id, locator, body, ts_utc FROM messages WHERE id = ?", (record_id,)
        ).fetchone()
        if row:
            return Record(
                record_id, kind, SourceRef(source_id=row[0], locator=row[1]), row[2], row[3]
            )
    elif kind == "call":
        row = conn.execute(
            "SELECT source_id, locator, app, direction, from_account_id, to_account_id,"
            " duration_s, ts_utc FROM calls WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row:
            text = call_text(conn, row[2], row[3], row[4], row[5], row[6])
            return Record(
                record_id, kind, SourceRef(source_id=row[0], locator=row[1]), text, row[7]
            )
    elif kind == "contact":
        row = conn.execute(
            "SELECT source_id, locator, name, identifier FROM contacts WHERE id = ?", (record_id,)
        ).fetchone()
        if row:
            text = f"{row[2] or '(no name)'}: {row[3]}"
            return Record(record_id, kind, SourceRef(source_id=row[0], locator=row[1]), text, None)
    elif kind == "attachment":
        row = conn.execute(
            "SELECT a.source_id, a.locator, a.file_name, m.ts_utc FROM attachments a"
            " LEFT JOIN messages m ON m.id = a.message_id WHERE a.id = ?",
            (record_id,),
        ).fetchone()
        if row:
            text = row[2] or "(no file name)"
            return Record(
                record_id, kind, SourceRef(source_id=row[0], locator=row[1]), text, row[3]
            )
    return None


def record_text(conn: sqlite3.Connection, record_id: str) -> str | None:
    """The text a quote about this record must appear in verbatim, or None if no such record."""
    rec = get_record(conn, record_id)
    return rec.text if rec else None
