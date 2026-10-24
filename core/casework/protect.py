"""Encrypting a case that was made before encryption at rest, and changing its passphrase.

Nothing here runs on its own: a plain case stays plain, and opens as before, until the expert
asks for it to be encrypted (the case's setup page, or `mabillon encrypt`). Encrypting:

1. refuses while an audit is recorded as running on the case;
2. takes the database's write lock, so no other writer can change it until the end;
3. writes the key file (case.key, synced to disk) before anything else changes;
4. copies the database into a new encrypted file (SQLCipher's export) and checks the copy:
   integrity, the row count of every table, and the audit log's hash chain and last hash;
5. encrypts each copied input into a new file, reads it back and checks its SHA-256 against
   the plain bytes, then puts it in place of the plain copy;
6. puts the encrypted database in place of the plain one, and logs `case.encrypt`.

A crash or error part way leaves a case that still opens: each input and the database say for
themselves whether they are encrypted, and running the same step again (with the passphrase
just chosen) finishes the rest. It then shows a new recovery key, since the first one may
never have reached the screen.

The plain files are replaced, not wiped. On an SSD their old blocks can stay readable to
forensic tools until reused, so the computer's own disk encryption (FileVault, BitLocker) is
still what protects data written before the case was encrypted.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core import db as casedb
from core import encryption
from core.casework.cases import UPLOAD_PREFIX, Case, _logged, _make_writable, _now, discard
from core.encryption import Kdf
from core.review import audit_log
from core.review.actions import ReviewError, _expert

Clock = Callable[[], datetime]
TMP_SUFFIX = ".encrypting"


@dataclass(frozen=True)
class Encrypted:
    recovery_key: str
    files: int  # inputs encrypted by this call
    database: bool  # the database was encrypted by this call
    resumed: bool  # an earlier, interrupted encryption was finished


def state(case: Case) -> str:
    """'plain', 'encrypted', or 'partial' (a key file, but the database or a copied input is
    still plain: an encryption that did not finish)."""
    if not encryption.is_encrypted_case(case.db):
        return "plain"
    if encryption.database_is_plain(case.db):
        return "partial"
    if case.inputs.is_dir():
        for f in case.inputs.iterdir():
            if _is_input(f) and not encryption.is_encrypted_file(f):
                return "partial"
    return "encrypted"


def _is_input(f: Path) -> bool:
    return f.is_file() and not f.name.startswith(".")


def _tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        )
    ]


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for t in _tables(conn):
        q = '"' + t.replace('"', '""') + '"'
        out[t] = conn.execute(f"SELECT count(*) FROM {q}").fetchone()[0]  # noqa: S608
    return out


def _last_hash(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    return None if row is None else row[0]


def _export(plain: Path, target: Path, dek: bytes) -> None:
    """SQLCipher's own copy of a plain database into a new encrypted one."""
    cipher = casedb._cipher
    if cipher is None:
        raise ReviewError("this install of Mabillon cannot encrypt (sqlcipher3 is missing)")
    src = cipher.connect(str(plain))
    try:
        src.execute("PRAGMA cipher_log_level = NONE")
        src.execute("ATTACH DATABASE ? AS enc KEY ?", (str(target), encryption.sqlcipher_key(dek)))
        src.execute("SELECT sqlcipher_export('enc')")
        version = int(src.execute("PRAGMA main.user_version").fetchone()[0])
        src.execute(f"PRAGMA enc.user_version = {version}")
        src.execute("DETACH DATABASE enc")
    finally:
        src.close()


def _check_copy(plain: sqlite3.Connection, target: Path, dek: bytes) -> None:
    enc = casedb.open_encrypted(target, dek)
    try:
        problems = []
        if enc.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            problems.append("integrity check failed")
        if enc.execute("PRAGMA cipher_integrity_check").fetchall():
            problems.append("page check failed")
        want, got = _counts(plain), _counts(enc)
        if want != got:
            diff = sorted(t for t in set(want) | set(got) if want.get(t) != got.get(t))
            problems.append(f"row counts differ in {', '.join(diff)}")
        if not audit_log.verify_chain(enc) or _last_hash(enc) != _last_hash(plain):
            problems.append("the audit log does not match")
        if problems:
            raise ReviewError("the encrypted copy did not check out: " + "; ".join(problems))
    finally:
        enc.close()


def _replace(src: Path, dst: Path) -> None:
    """os.replace, retried briefly: on Windows a file another program has open cannot be
    replaced until it lets go."""
    for attempt in range(5):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def _encrypt_inputs(case: Case, key_id: str, dek: bytes) -> int:
    if not case.inputs.is_dir():
        return 0
    n = 0
    for f in sorted(case.inputs.iterdir()):
        if not f.is_file():
            continue
        if f.name.startswith(UPLOAD_PREFIX) or f.name.endswith(TMP_SUFFIX):
            discard(f)  # an upload that never finished, or a copy from an interrupted run
            continue
        if f.name.startswith("."):
            continue
        if encryption.is_encrypted_file(f):
            with encryption.open_input(f):  # CaseLocked or EncryptionError if not this case's
                pass
            continue
        tmp = f.with_name(f".{f.name}{TMP_SUFFIX}")
        try:
            sha = encryption.encrypt_file(f, tmp, key_id, dek)
            if encryption.plain_sha256(tmp) != sha:
                raise ReviewError(f"{f.name} did not read back the same after encrypting")
            _make_writable(f)
            _replace(tmp, f)
        except BaseException:
            discard(tmp)
            raise
        f.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        n += 1
    return n


def encrypt_case(
    case: Case,
    passphrase: str,
    actor: str,
    again: str | None = None,
    clock: Clock | None = None,
    kdf: Kdf | None = None,
) -> Encrypted:
    """Encrypt a plain case, or finish an interrupted encryption (then `passphrase` is the one
    chosen when it started, or the recovery key). See the module docstring for the steps."""
    _expert(actor)
    try:
        encryption.require()
    except encryption.EncryptionError as err:
        raise ReviewError(str(err)) from err
    dbp = case.db
    resumed = encryption.is_encrypted_case(dbp)
    plain = encryption.database_is_plain(dbp)
    if plain is None:
        raise ReviewError("this case has no database to encrypt")
    if not plain and not resumed:
        raise ReviewError("the case database is encrypted but its key file is missing")
    if resumed:
        if state(case) == "encrypted":
            raise ReviewError("this case is already encrypted")
        try:
            encryption.unlock(dbp, passphrase)
        except encryption.WrongSecret as err:
            raise ReviewError(
                "this case's encryption did not finish; enter the passphrase chosen then, or "
                "its recovery key, to finish it"
            ) from err
        if not plain:
            _require_intact(casedb.connect(dbp), dbp)
    else:
        try:
            encryption.check_new_passphrase(passphrase, again)
        except ValueError as err:
            raise ReviewError(str(err)) from err

    if plain:
        _require_intact(sqlite3.connect(dbp), dbp)  # a blocked case is not touched
    conn = sqlite3.connect(dbp) if plain else None  # a plain file: the standard module
    try:
        if conn is not None:
            conn.execute("PRAGMA busy_timeout = 10000")
            running = conn.execute(
                "SELECT count(*) FROM pipeline_runs WHERE status = 'running'"
            ).fetchone()[0]
            if running:
                raise ReviewError(
                    "an audit is recorded as running on this case; let it finish or stop it, "
                    "then encrypt (if Mabillon is not running, open the case in Mabillon once "
                    "first)"
                )
            conn.execute("BEGIN IMMEDIATE")  # no other writer until the encrypted copy is in
        if resumed:
            recovery = encryption.new_recovery(dbp, kdf)
        else:
            recovery = encryption.create_key(dbp, passphrase, kdf, _now(clock))
        key_id, dek = encryption.case_key(dbp)

        tmp_db = dbp.with_name(f".{dbp.name}{TMP_SUFFIX}")
        discard(tmp_db)
        if conn is not None:
            try:
                _export(dbp, tmp_db, dek)
                _check_copy(conn, tmp_db, dek)
            except BaseException:
                discard(tmp_db)
                raise
        files = _encrypt_inputs(case, key_id, dek)
        if conn is not None:
            before = os.stat(dbp)
            conn.rollback()
            conn.close()
            conn = None
            after = os.stat(dbp)
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                discard(tmp_db)
                raise ReviewError(
                    "the case database changed while it was being encrypted; nothing was lost. "
                    "Run the encryption again to finish it"
                )
            try:
                _replace(tmp_db, dbp)
            except BaseException:
                discard(tmp_db)
                raise
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()

    enc = casedb.connect(dbp)
    try:
        _logged(
            enc,
            _now(clock),
            actor,
            "case.encrypt",
            {
                "key_id": key_id,
                "database": "encrypted now" if plain else "already encrypted",
                "inputs_encrypted": files,
                "finished_interrupted_run": resumed,
            },
        )
    finally:
        enc.close()
    return Encrypted(recovery_key=recovery, files=files, database=bool(plain), resumed=resumed)


def change_passphrase(
    case: Case,
    current: str,
    new: str,
    again: str,
    actor: str,
    clock: Clock | None = None,
    kdf: Kdf | None = None,
) -> None:
    """`current` is the old passphrase or the recovery key. Only the key file changes."""
    _expert(actor)
    if state(case) == "plain":
        raise ReviewError("this case is not encrypted")
    try:
        encryption.check_new_passphrase(new, again)
        encryption.unlock(case.db, current)  # the log is inside the database: open it first
    except (ValueError, encryption.WrongSecret) as err:
        raise ReviewError(str(err)) from err
    _require_intact(casedb.connect(case.db), case.db)  # a blocked case is not touched
    try:
        encryption.change_passphrase(case.db, current, new, kdf)
    except (ValueError, encryption.WrongSecret) as err:
        raise ReviewError(str(err)) from err
    conn = casedb.connect(case.db)
    try:
        _logged(conn, _now(clock), actor, "case.passphrase", {"changed": "passphrase"})
    finally:
        conn.close()


def _require_intact(conn: sqlite3.Connection, dbp: Path) -> None:
    """The audit-log gate (core/review/audit_log.py); closes the connection either way."""
    try:
        audit_log.require_intact(conn, audit_log.anchors_path(dbp))
    finally:
        conn.close()


def lock(case: Case) -> None:
    """Forget the case key in this process. Open connections keep working until closed."""
    encryption.lock(case.db)


def is_locked(case: Case) -> bool:
    return not encryption.is_unlocked(case.db)
