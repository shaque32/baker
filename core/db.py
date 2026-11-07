"""Open a case database and apply the canonical schema.

A plain case database (every case made before encryption at rest, and `--db` files made by
`mabillon init`) opens with the standard library's sqlite3, exactly as before. An encrypted one
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
    "upgrade_verdicts",
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


def _schema_table(name: str) -> str:
    """The CREATE TABLE statement core/schema.sql gives for one table."""
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    start = text.index(f"CREATE TABLE {name} (")
    return text[start : text.index("\n);", start) + 3]


def upgrade_verdicts(conn: sqlite3.Connection) -> bool:
    """Rebuild a verdicts table made under schema 0.7.0 or earlier, whose CHECK refuses the
    bases rules 0.5.0 can store (checked, counsel_reviewed). SQLite cannot change a CHECK in
    place, so the table is copied into the 0.8.0 definition, every row and column as it was,
    and its index made again, inside one savepoint. No other table references verdicts. Returns
    whether it rebuilt the table; a current or missing table is left alone."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'verdicts'"
    ).fetchone()
    if row is None or "'checked'" in row[0]:
        return False
    cols = ", ".join(r[1] for r in conn.execute("PRAGMA table_info(verdicts)"))
    new = _schema_table("verdicts").replace("CREATE TABLE verdicts (", "CREATE TABLE verdicts_08 (")
    conn.execute("SAVEPOINT upgrade_verdicts")
    try:
        conn.execute(new)
        conn.execute(f"INSERT INTO verdicts_08 ({cols}) SELECT {cols} FROM verdicts")  # noqa: S608
        conn.execute("DROP TABLE verdicts")
        conn.execute("ALTER TABLE verdicts_08 RENAME TO verdicts")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_verdicts_run ON verdicts(pipeline_run_id, claim_id)"
        )
    except BaseException:
        conn.execute("ROLLBACK TO upgrade_verdicts")
        conn.execute("RELEASE upgrade_verdicts")
        raise
    conn.execute("RELEASE upgrade_verdicts")
    return True
