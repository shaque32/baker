"""Take a wrongly imported file back out of a case, before the case's first audit.

The 2026-11-04 walkthrough found three dead ends with no way out but a new case: the affidavit
dropped in the phone slot, a report imported with the wrong date order, and a wrong file. A
file can be removed only while no audit has run on the case: after that, its records may be
cited, and everything the audit read stays part of the record.

Removing deletes the file's rows (its source, device, accounts, threads, messages, calls,
contacts, locations, attachments and coverage, or for a government document its paragraphs)
and Mabillon's copy in the case folder. The original file is never touched. The audit log
keeps a `case.remove_file` entry with the file's name, SHA-256 and the expert's reason, so the
removal itself is on the record. It is refused while anything the expert entered still points
at the file: a stipulation or name for its device, an account link, a claim or event on the
document's paragraphs, or an exhibit.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from core.casework.cases import Case, _logged, _now, discard
from core.review.actions import ReviewError, _expert

Clock = Callable[[], datetime]
ACTION = "case.remove_file"


def _ids(conn: sqlite3.Connection, sql: str, *args: object) -> list[str]:
    return [r[0] for r in conn.execute(sql, args)]


def _in(ids: list[str]) -> str:
    return ",".join("?" * len(ids))


def _blockers(conn: sqlite3.Connection, source_id: str) -> list[str]:
    """What the expert entered that still points at this file, in words."""
    out: list[str] = []
    devices = _ids(conn, "SELECT id FROM devices WHERE source_id = ?", source_id)
    accounts = _ids(conn, "SELECT id FROM accounts WHERE source_id = ?", source_id)
    if (
        devices
        and conn.execute(
            f"SELECT 1 FROM stipulations WHERE subject_id IN ({_in(devices)})",  # noqa: S608
            devices,
        ).fetchone()
    ):
        out.append("a stipulated user for its phone (withdraw it under Who used each phone)")
    if (
        accounts
        and conn.execute(
            f"SELECT 1 FROM identity_links WHERE account_id IN ({_in(accounts)})",  # noqa: S608
            accounts,
        ).fetchone()
    ):
        out.append("an account link to a person (remove it on Identities)")
    paragraphs = _ids(
        conn,
        "SELECT p.id FROM govdoc_paragraphs p JOIN govdocs g ON g.id = p.govdoc_id"
        " WHERE g.source_id = ?",
        source_id,
    )
    if paragraphs:
        n = conn.execute(
            f"SELECT COUNT(*) FROM claims WHERE paragraph_id IN ({_in(paragraphs)})"  # noqa: S608
            " AND status IN ('accepted', 'edited')",
            paragraphs,
        ).fetchone()[0]
        if n:
            out.append(f"{n} accepted claim(s) on its paragraphs (remove them first)")
        if conn.execute(
            f"SELECT 1 FROM case_events WHERE paragraph_id IN ({_in(paragraphs)})",  # noqa: S608
            paragraphs,
        ).fetchone():
            out.append("an event defined in it (remove it under Events the document defines)")
        if conn.execute(
            f"SELECT 1 FROM exhibits WHERE paragraph_id IN ({_in(paragraphs)})",  # noqa: S608
            paragraphs,
        ).fetchone():
            out.append("an exhibit tied to one of its paragraphs")
    if (
        conn.execute("SELECT 1 FROM exhibit_matches WHERE source_id = ?", (source_id,)).fetchone()
        or conn.execute("SELECT 1 FROM evidence_items WHERE source_id = ?", (source_id,)).fetchone()
    ):
        out.append("records an exhibit or the audit cites")
    return out


def delete_rows(conn: sqlite3.Connection, source_id: str) -> None:
    """Delete every row the importer stored for this source (inside the caller's transaction)."""
    messages = _ids(conn, "SELECT id FROM messages WHERE source_id = ?", source_id)
    accounts = _ids(conn, "SELECT id FROM accounts WHERE source_id = ?", source_id)
    for chunk in range(0, len(messages), 500):
        part = messages[chunk : chunk + 500]
        for table in ("message_recipients", "translations"):
            conn.execute(
                f"DELETE FROM {table} WHERE message_id IN ({_in(part)})",  # noqa: S608
                part,
            )
    for chunk in range(0, len(accounts), 500):
        part = accounts[chunk : chunk + 500]
        conn.execute(
            f"DELETE FROM message_recipients WHERE account_id IN ({_in(part)})",  # noqa: S608
            part,
        )
    # Claims still only proposed (or removed) on the document's paragraphs go with it: they are
    # the model's proposals, not the expert's work (an accepted claim blocks the removal).
    conn.execute(
        "DELETE FROM claims WHERE status IN ('proposed', 'removed') AND paragraph_id IN"
        " (SELECT p.id FROM govdoc_paragraphs p JOIN govdocs g ON g.id = p.govdoc_id"
        " WHERE g.source_id = ?)",
        (source_id,),
    )
    conn.execute(
        "DELETE FROM govdoc_paragraphs WHERE govdoc_id IN"
        " (SELECT id FROM govdocs WHERE source_id = ?)",
        (source_id,),
    )
    # Children first, then the tables they point at. Any other table that carries a source_id
    # (a newer importer's) goes too, before the source itself.
    ordered = [
        "attachments",
        "messages",
        "threads",
        "calls",
        "contacts",
        "locations",
        "accounts",
        "devices",
        "govdocs",
        "source_coverage",
    ]
    others = [
        name
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if name not in ordered
        and name not in ("sources", "evidence_items", "exhibit_matches")
        and any(c[1] == "source_id" for c in conn.execute(f"PRAGMA table_info({name})"))
    ]
    for table in [*ordered, *others]:
        conn.execute(f"DELETE FROM {table} WHERE source_id = ?", (source_id,))  # noqa: S608
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


def remove_file(
    case: Case,
    conn: sqlite3.Connection,
    source_id: str,
    actor: str,
    reason: str,
    clock: Clock | None = None,
) -> str:
    """Remove one imported file before the first audit. Returns its file name."""
    _expert(actor)
    if not reason.strip():
        raise ReviewError("say why the file is removed, in one sentence")
    if conn.execute("SELECT 1 FROM pipeline_runs LIMIT 1").fetchone():
        raise ReviewError(
            "an audit has run on this case, so its files stay: they are part of the record. "
            "Make a new case to start over"
        )
    row = conn.execute(
        "SELECT file_name, sha256, kind FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    if row is None:
        raise ReviewError("no such file in this case")
    file_name, sha256, kind = row
    blockers = _blockers(conn, source_id)
    if blockers:
        raise ReviewError(f"{file_name} is still used by " + "; ".join(blockers))
    copy = _copy_path(case, conn, source_id, file_name)
    with conn:
        delete_rows(conn, source_id)
    _logged(
        conn,
        _now(clock),
        actor,
        ACTION,
        {
            "source_id": source_id,
            "file_name": file_name,
            "kind": kind,
            "sha256": sha256,
            "copied_to": None if copy is None else str(copy.relative_to(case.folder)),
            "reason": reason.strip()[:500],
        },
    )
    if copy is not None:
        discard(copy)
    return file_name


def _copy_path(case: Case, conn: sqlite3.Connection, source_id: str, file_name: str) -> Path | None:
    """Mabillon's copy of the file, from the import's own audit-log entry."""
    import json

    for (payload,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'case.import' ORDER BY seq DESC"
    ):
        p = json.loads(payload)
        if p.get("source_id") == source_id and isinstance(p.get("copied_to"), str):
            path = case.folder / p["copied_to"]
            return path if path.is_file() else None
    path = case.inputs / file_name
    return path if path.is_file() else None
