"""Look up any evidence record by its stable id: its source_ref, time and citable text.

Record kinds by id prefix: 'msg:' messages, 'call:' calls, 'contact:' contacts, 'att:' attachments.
A message's citable text is its original body. Calls, contacts and attachments have no body, so
their text is a fixed rendering of observed fields; quote checks must verify against this same
text, so this is the single place it is built.

A rendering mixes the record's own fields with Baker's words (" call from ", ": ") and
placeholders for a missing field ("(no name)", "unknown"). Record.own marks the spans that are
the record's own fields; a quote must reach into one of them to cite the record
(core.audit.quotes.cites_record), so text Baker wrote cannot verify a quote by itself.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from core.contracts import SourceRef

KIND_BY_PREFIX = {"msg": "message", "call": "call", "contact": "contact", "att": "attachment"}
NO_NAME = "(no name)"
NO_FILE_NAME = "(no file name)"
UNKNOWN = "unknown"

Span = tuple[int, int]
# A piece of a rendered line: its text, and whether it is the record's own field (True) or
# Baker's words or a placeholder (False).
Part = tuple[str, bool]


@dataclass(frozen=True)
class Record:
    id: str
    kind: str
    ref: SourceRef
    text: str
    ts_utc: str | None
    own: tuple[Span, ...]  # (start, end) of each of the record's own fields in text


def join_parts(parts: list[Part]) -> tuple[str, tuple[Span, ...]]:
    """A rendered line and the spans of the record's own fields in it."""
    text, own = "", []
    for piece, is_own in parts:
        if is_own and piece:
            own.append((len(text), len(text) + len(piece)))
        text += piece
    return text, tuple(own)


def kind_of(record_id: str) -> str | None:
    return KIND_BY_PREFIX.get(record_id.split(":", 1)[0])


def _ident_part(conn: sqlite3.Connection, account_id: str | None) -> Part:
    if account_id is None:
        return UNKNOWN, False
    row = conn.execute("SELECT identifier FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return (row[0], True) if row else (account_id, False)  # Baker's own account id


def call_parts(
    conn: sqlite3.Connection,
    app: str,
    direction: str,
    from_id: str | None,
    to_id: str | None,
    duration_s: int | None,
) -> list[Part]:
    """A call as the labeler is shown it, in pieces; its time is on its context line."""
    return [
        (direction, direction != UNKNOWN),  # 'unknown': the source gave no direction
        (" ", False),
        (app, True),
        (" call from ", False),
        _ident_part(conn, from_id),
        (" to ", False),
        _ident_part(conn, to_id),
        (", duration ", False),
        (UNKNOWN, False) if duration_s is None else (str(duration_s), True),
        ("", False) if duration_s is None else (" s", False),
    ]


def call_text(
    conn: sqlite3.Connection,
    app: str,
    direction: str,
    from_id: str | None,
    to_id: str | None,
    duration_s: int | None,
) -> str:
    """A call as the labeler is shown it; its time is on its context line. A quote about a call
    is checked against this same text (core.audit.invariants.record_text), so a quote copied from
    what the labeler saw can pass."""
    return join_parts(call_parts(conn, app, direction, from_id, to_id, duration_s))[0]


def contact_parts(name: str | None, identifier: str) -> list[Part]:
    """A contact as the labeler is shown it, in pieces."""
    return [(name, True) if name else (NO_NAME, False), (": ", False), (identifier, True)]


def contact_text(name: str | None, identifier: str) -> str:
    """A contact as the labeler is shown it. A quote about a contact is checked against this same
    text (core.audit.invariants.record_text, core.audit.quotes.record_text), so a quote copied
    from what the labeler saw can pass, unless it quotes only the "(no name)" placeholder."""
    return join_parts(contact_parts(name, identifier))[0]


def get_record(conn: sqlite3.Connection, record_id: str) -> Record | None:
    kind = kind_of(record_id)
    if kind == "message":
        row = conn.execute(
            "SELECT source_id, locator, body, ts_utc FROM messages WHERE id = ?", (record_id,)
        ).fetchone()
        if row:
            own = ((0, len(row[2])),) if row[2] else ()
            return Record(
                record_id, kind, SourceRef(source_id=row[0], locator=row[1]), row[2], row[3], own
            )
    elif kind == "call":
        row = conn.execute(
            "SELECT source_id, locator, app, direction, from_account_id, to_account_id,"
            " duration_s, ts_utc FROM calls WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row:
            text, own = join_parts(call_parts(conn, row[2], row[3], row[4], row[5], row[6]))
            return Record(
                record_id, kind, SourceRef(source_id=row[0], locator=row[1]), text, row[7], own
            )
    elif kind == "contact":
        row = conn.execute(
            "SELECT source_id, locator, name, identifier FROM contacts WHERE id = ?", (record_id,)
        ).fetchone()
        if row:
            text, own = join_parts(contact_parts(row[2], row[3]))
            ref = SourceRef(source_id=row[0], locator=row[1])
            return Record(record_id, kind, ref, text, None, own)
    elif kind == "attachment":
        row = conn.execute(
            "SELECT a.source_id, a.locator, a.file_name, m.ts_utc FROM attachments a"
            " LEFT JOIN messages m ON m.id = a.message_id WHERE a.id = ?",
            (record_id,),
        ).fetchone()
        if row:
            text, own = join_parts([(row[2], True) if row[2] else (NO_FILE_NAME, False)])
            return Record(
                record_id, kind, SourceRef(source_id=row[0], locator=row[1]), text, row[3], own
            )
    return None


def record_text(conn: sqlite3.Connection, record_id: str) -> str | None:
    """The text a quote about this record must appear in verbatim, or None if no such record."""
    rec = get_record(conn, record_id)
    return rec.text if rec else None
