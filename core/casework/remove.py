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
at the file: a confirmed stipulation or a name for its device, a confirmed account link, an
accepted claim or an event on the document's paragraphs, or an exhibit. What is left that
the expert withdrew or rejected, and the model's proposals, go with the file; the entry lists
their ids, and verify-bundle replays them.
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


def _select(table: str, where: str) -> str:
    return f"SELECT id FROM {table} WHERE {where} ORDER BY id"  # noqa: S608


def _has(conn: sqlite3.Connection, table: str) -> bool:
    """A case made before a table existed (person_aliases, schema 0.6.0) reads as empty."""
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def _blockers(conn: sqlite3.Connection, source_id: str) -> list[str]:
    """What the expert entered that still points at this file, in words."""
    out: list[str] = []
    devices = _ids(conn, "SELECT id FROM devices WHERE source_id = ?", source_id)
    accounts = _ids(conn, "SELECT id FROM accounts WHERE source_id = ?", source_id)
    if (
        devices
        and conn.execute(
            f"SELECT 1 FROM stipulations WHERE subject_id IN ({_in(devices)})"  # noqa: S608
            " AND status = 'confirmed'",
            devices,
        ).fetchone()
    ):
        out.append("a stipulated user for its phone (withdraw it under Who used each phone)")
    # Names the expert gave the phone, or other names for its owner, are kept by device id: a
    # later report with the same file name gets the same id and would inherit them.
    from core.review.device_names import logged_names

    named = logged_names(conn)
    if any(named.get(d) for d in devices):
        out.append("document names for its phone (clear them under Who used each phone)")
    owners = [f"person:{d}:owner" for d in devices]
    if (
        owners
        and _has(conn, "person_aliases")
        and conn.execute(
            f"SELECT 1 FROM person_aliases WHERE person_id IN ({_in(owners)})",  # noqa: S608
            owners,
        ).fetchone()
    ):
        out.append("other names for its phone's user (clear them on Identities)")
    if (
        accounts
        and conn.execute(
            f"SELECT 1 FROM identity_links WHERE account_id IN ({_in(accounts)})"  # noqa: S608
            " AND status = 'confirmed'",
            accounts,
        ).fetchone()
    ):
        out.append("a confirmed account link to a person (reject it on Identities)")
    # A confirmed link from another file's account to this phone's user: the user's person row
    # is kept by device id, so a later report with the same file name would take it over.
    if (
        owners
        and conn.execute(
            f"SELECT 1 FROM identity_links WHERE person_id IN ({_in(owners)})"  # noqa: S608
            " AND status = 'confirmed'",
            owners,
        ).fetchone()
    ):
        out.append("a confirmed link from an account to its phone's user (reject it on Identities)")
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


def delete_rows(conn: sqlite3.Connection, source_id: str) -> dict[str, list[str]]:
    """Delete every row the importer stored for this source (inside the caller's transaction).

    Returns the ids of the dependent rows that went with it (stipulations, identity links,
    persons, claims), for the `case.remove_file` entry: the bundle verifier replays them, so a
    row the log recorded and the removal took is not reported missing."""
    messages = _ids(conn, "SELECT id FROM messages WHERE source_id = ?", source_id)
    accounts = _ids(conn, "SELECT id FROM accounts WHERE source_id = ?", source_id)
    devices = _ids(conn, "SELECT id FROM devices WHERE source_id = ?", source_id)
    gone: dict[str, list[str]] = {
        "stipulations_removed": [],
        "links_removed": [],
        "persons_removed": [],
        "claims_removed": [],
    }
    for chunk in range(0, len(accounts), 500):
        # Only links not confirmed can be left (a confirmed one blocks the removal): proposed,
        # rejected or unresolved. They go with the accounts; the log keeps each decision.
        part = accounts[chunk : chunk + 500]
        where = f"account_id IN ({_in(part)}) AND status != 'confirmed'"
        gone["links_removed"] += _ids(conn, _select("identity_links", where), *part)
        conn.execute(f"DELETE FROM identity_links WHERE {where}", part)  # noqa: S608
    if devices:
        # Only withdrawn stipulations can be left (a confirmed one blocks the removal); they go
        # with the phone, and so does its owner's person row when nothing else uses it. The
        # audit log keeps both decisions.
        where = f"subject_id IN ({_in(devices)}) AND status != 'confirmed'"
        gone["stipulations_removed"] = _ids(conn, _select("stipulations", where), *devices)
        conn.execute(f"DELETE FROM stipulations WHERE {where}", devices)  # noqa: S608
        # Links not confirmed from any account to this phone's user go too (a confirmed one
        # blocks the removal), so no later phone with the same id inherits them.
        owners = [f"person:{d}:owner" for d in devices]
        where = f"person_id IN ({_in(owners)}) AND status != 'confirmed'"
        gone["links_removed"] += _ids(conn, _select("identity_links", where), *owners)
        conn.execute(f"DELETE FROM identity_links WHERE {where}", owners)  # noqa: S608
        for d in devices:
            owner = f"person:{d}:owner"
            used = any(
                conn.execute(
                    f"SELECT 1 FROM {t} WHERE person_id = ?",  # noqa: S608
                    (owner,),
                ).fetchone()
                for t in ("stipulations", "identity_links", "person_aliases")
                if _has(conn, t)
            )
            if not used and conn.execute("DELETE FROM persons WHERE id = ?", (owner,)).rowcount:
                gone["persons_removed"].append(owner)
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
    where = (
        "status IN ('proposed', 'removed') AND paragraph_id IN"
        " (SELECT p.id FROM govdoc_paragraphs p JOIN govdocs g ON g.id = p.govdoc_id"
        " WHERE g.source_id = ?)"
    )
    gone["claims_removed"] = _ids(conn, _select("claims", where), source_id)
    conn.execute(f"DELETE FROM claims WHERE {where}", (source_id,))  # noqa: S608
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
    return gone


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
        gone = delete_rows(conn, source_id)
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
            **gone,
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
            if path.is_file():
                return path
            break
    path = case.inputs / file_name
    if path.is_file():
        return path
    return _copy_by_hash(case, conn, source_id)


def _copy_by_hash(case: Case, conn: sqlite3.Connection, source_id: str) -> Path | None:
    """The copy whose plain bytes hash to the source's SHA-256: found when the import stopped
    after an encrypted case's copy was renamed (core/casework/cases.py _hide_name) but before
    its log entry recorded the new name."""
    from core import encryption

    row = conn.execute("SELECT sha256 FROM sources WHERE id = ?", (source_id,)).fetchone()
    if row is None or not case.inputs.is_dir():
        return None
    for f in sorted(case.inputs.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        try:
            if encryption.plain_sha256(f) == row[0]:
                return f
        except (OSError, encryption.EncryptionError, encryption.CaseLocked):
            continue
    return None
