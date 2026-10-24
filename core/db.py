"""Open a case database and apply the canonical schema.

A plain case database (every case made before encryption at rest, and `--db` files made by
`baker init`) opens with the standard library's sqlite3, exactly as before. An encrypted one
(core/encryption.py) opens with SQLCipher, keyed from the case key this process unlocked; a
locked one raises CaseLocked. Code that catches database errors uses the tuples below, not
sqlite3's own classes, because SQLCipher raises its own classes of the same names.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core import encryption
from core.encryption import CaseLocked

try:  # imported only to name its error classes; an encrypted case needs it to open
    import sqlcipher3.dbapi2 as _cipher
except ImportError:  # pragma: no cover - a computer that only opens plain cases
    _cipher = None

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

__all__ = [
    "CaseLocked",
    "Error",
    "IntegrityError",
    "OperationalError",
    "apply_schema",
    "connect",
    "is_encrypted",
]


def _both(name: str) -> tuple[type[Exception], ...]:
    std: type[Exception] = getattr(sqlite3, name)
    return (std, getattr(_cipher, name)) if _cipher is not None else (std,)


Error = _both("Error")
OperationalError = _both("OperationalError")
IntegrityError = _both("IntegrityError")
DatabaseError = _both("DatabaseError")


def _special(path: Path | str) -> bool:
    s = str(path)
    return s == "" or s.startswith(":memory:") or s.startswith("file:")


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (or create) a case database with foreign keys on.

    A new database is created encrypted when its key file (case.key beside case.db) is
    already there and unlocked, which is how an encrypted case is made."""
    if _special(path) or not encryption.database_needs_key(Path(path)):
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    _key_id, dek = encryption.case_key(Path(path))
    return open_encrypted(Path(path), dek)


def open_encrypted(path: Path, dek: bytes) -> sqlite3.Connection:
    if _cipher is None:
        raise CaseLocked(
            "this case is encrypted and this install of Mabillon cannot open encrypted cases "
            "(the sqlcipher3 package is missing); run Mabillon's installer again"
        )
    conn = _cipher.connect(str(path))
    try:
        conn.execute("PRAGMA cipher_log_level = NONE")
        conn.execute(f'PRAGMA key = "{encryption.sqlcipher_key(dek)}"')
        conn.execute("PRAGMA temp_store = MEMORY")  # sorts and temp tables never spill to disk
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except _cipher.DatabaseError as err:
            raise CaseLocked(
                f"{path.name} does not open with this case's key; its key file may belong to "
                "another case"
            ) from err
        conn.execute("PRAGMA foreign_keys = ON")
    except BaseException:
        conn.close()
        raise
    return conn  # type: ignore[return-value]  # the same DB-API as sqlite3.Connection


def is_encrypted(conn: sqlite3.Connection) -> bool:
    return _cipher is not None and isinstance(conn, _cipher.Connection)


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
