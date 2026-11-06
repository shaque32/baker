"""Back up one case folder, so it can be restored whole.

A backup is a new folder holding everything the case needs to open again: its database, its
audit-log anchor file, its settings (case.json), its key file and sealed secrets if it is
encrypted, and every copied input. An encrypted case stays encrypted in the backup, under the
same key, so the same passphrase or recovery key opens it.

Why not copy the folder by hand: a copy taken while Mabillon writes the database may not open,
and the anchor file must not be newer than the database beside it, or the restored case is
blocked (core/review/audit_log.py). So:
1. the anchor file is copied first, so it can only be as new as the database, never newer;
2. the database is copied with SQLite's backup API, a consistent snapshot even if another
   connection writes during the copy;
3. everything else is copied byte for byte and each copy is hashed against its original.
The backup is then opened and its audit log checked against its own anchors before Mabillon
says it is done. A backup that does not verify is deleted and the expert is told why.

Restoring is copying the backup folder back whole (or opening it where it is): nothing here
writes into an existing case folder. The case's audit log records each backup (`case.backup`,
the folder it went to). Nothing here makes a network call.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core import db as casedb
from core import encryption
from core.casework.cases import DB_NAME, UPLOAD_PREFIX, Case, _logged
from core.casework.protect import TMP_SUFFIX
from core.review import audit_log
from core.review.actions import ReviewError, _expert

Clock = Callable[[], datetime]
BACKUPS_FOLDER = "backups"
# The database and the files SQLite keeps beside it while writing: the database is copied with
# the backup API instead, and its journal files must never travel with a snapshot.
_DB_SIDE = ("", "-journal", "-wal", "-shm")


@dataclass(frozen=True)
class BackedUp:
    folder: Path
    files: int  # every file in the backup, the database and anchor file included
    bytes: int


def default_root(case: Case) -> Path:
    """`backups` beside the cases folder: ~/Mabillon/cases/x -> ~/Mabillon/backups."""
    return case.folder.parent.parent / BACKUPS_FOLDER


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _skip(rel: Path, case: Case) -> bool:
    """Files that are not part of the case: the database (copied separately), its journals,
    its anchors (copied first), and half-written uploads or encryption temporaries."""
    name = rel.name
    if len(rel.parts) == 1 and name in {DB_NAME + s for s in _DB_SIDE}:
        return True
    if len(rel.parts) == 1 and name == audit_log.anchors_path(case.db).name:
        return True
    return name.startswith(UPLOAD_PREFIX) or name.endswith(TMP_SUFFIX)


def _connect_like(src: sqlite3.Connection, dest: Path, case: Case) -> sqlite3.Connection:
    """An empty database at `dest` with the same encryption as the case's own."""
    if casedb.is_encrypted(src):
        _key_id, dek = encryption.case_key(case.db)
        return casedb.open_encrypted(dest, dek)
    return sqlite3.connect(dest)


def back_up(
    case: Case,
    actor: str,
    root: Path | None = None,
    clock: Clock | None = None,
) -> BackedUp:
    """Copy `case` into a new folder under `root` (default_root(case) when None), named after
    the case folder and the UTC time. ReviewError when it cannot, with nothing left behind."""
    _expert(actor)
    if case.db.name != DB_NAME:
        raise ReviewError(
            "only a case folder can be backed up (a case opened with --db shares its folder "
            "with other files); copy the database and its files by hand"
        )
    if not case.db.is_file():
        raise ReviewError(f"{case.name} has no database to back up")
    at = (clock or (lambda: datetime.now(UTC)))()
    root = Path(root) if root is not None else default_root(case)
    root = root.expanduser().resolve()
    src_folder = case.folder.resolve()
    if root == src_folder or src_folder in root.parents:
        raise ReviewError("a backup cannot go inside the case folder it copies")
    dest = root / f"{case.folder.name}-backup-{_stamp(at)}"
    if dest.exists():
        raise ReviewError(f"{dest} already exists; wait a second and back up again")

    conn = casedb.connect(case.db)  # CaseLocked for a locked encrypted case
    try:
        try:
            audit_log.require_intact(conn, audit_log.anchors_path(case.db))
        except audit_log.ChainBroken as err:
            raise ReviewError(
                f"this case's audit log does not verify ({err}), so it is not backed up; a "
                "backup of a blocked case would be blocked too"
            ) from err
        try:
            dest.mkdir(parents=True)
            result = _copy(case, conn, dest)
            _verify(case, dest)
        except BaseException:
            _remove(dest)
            raise
        _logged(
            conn,
            at,
            actor,
            "case.backup",
            {"to": str(dest), "files": result.files, "bytes": result.bytes},
        )
    finally:
        conn.close()
    return result


def _remove(folder: Path) -> None:
    """Delete a failed backup, read-only input copies included (Windows refuses those)."""

    def writable_then_retry(func: Callable[[str], object], path: str, _exc: BaseException) -> None:
        try:
            Path(path).chmod(stat.S_IRUSR | stat.S_IWUSR)
            func(path)
        except OSError:
            pass

    shutil.rmtree(folder, onexc=writable_then_retry)


def _copy(case: Case, conn: sqlite3.Connection, dest: Path) -> BackedUp:
    files = 0
    size = 0
    # 1. The anchor file first: it may then be older than the database, never newer.
    anchors = audit_log.anchors_path(case.db)
    if anchors.is_file():
        shutil.copy2(anchors, dest / anchors.name)
        files += 1
        size += anchors.stat().st_size
    # 2. The database, as one consistent snapshot, under the case's own key.
    dest_db = dest / DB_NAME
    out = _connect_like(conn, dest_db, case)
    try:
        conn.backup(out)
    finally:
        out.close()
    files += 1
    size += dest_db.stat().st_size
    # 3. Everything else, hashed against its original.
    for src in sorted(case.folder.rglob("*")):
        rel = src.relative_to(case.folder)
        if src.is_symlink():
            raise ReviewError(f"{rel} is a link; a backup copies only real files")
        if src.is_dir() or _skip(rel, case):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        if _sha256(target) != _sha256(src):
            raise ReviewError(f"the copy of {rel} does not match the original")
        files += 1
        size += target.stat().st_size
    return BackedUp(dest, files, size)


def _verify(case: Case, dest: Path) -> None:
    """The backup opens, and its audit log verifies against its own anchor file."""
    copy = dest / DB_NAME
    conn = casedb.connect(copy)
    try:
        audit_log.require_intact(conn, audit_log.anchors_path(copy))
    except audit_log.ChainBroken as err:
        raise ReviewError(f"the backup did not verify ({err}); nothing was kept") from err
    finally:
        conn.close()
