"""Case folders, made and filled from the review screen.

    <cases folder>/<case>/
        case.db       the case database (core/schema.sql)
        case.json     the case name, when it was made, the expert's claim order
        inputs/       read-only copies of every imported file
        case.key      only in an encrypted case: its wrapped key (core/encryption.py); the
                      database and every copy in inputs/ are then encrypted too

The cases folder is $BAKER_CASES, else ~/Baker/cases. `baker serve --db some.db` works on a
single database the same way: its settings sit beside it (some.json) and its copies in
some-inputs/.

Importing a file. The upload is written into the case's inputs folder and SHA-256 hashed as it
is written, then made read-only. The importer then opens that copy read-only and hashes exactly
the bytes it parses (core/ingest/source_file.py, core/ingest/govdoc.py); the two hashes must
agree or nothing is stored. The expert's original file is never opened by Baker. A file whose
hash is already in the case is refused, so nothing is imported twice. In an encrypted case the
upload is encrypted as it is written, and the hashes are of the plain bytes, so they still
match the expert's original file.

Encrypting a case made before encryption existed is a separate, deliberate step
(core/casework/protect.py); nothing here encrypts or changes an existing plain case.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from core import encryption, pipeline
from core.db import OperationalError, apply_schema, connect
from core.review import audit_log
from core.review.actions import ReviewError, _expert

CASES_ENV = "BAKER_CASES"
DEFAULT_HOME = Path.home() / "Baker" / "cases"
DB_NAME = "case.db"
UPLOAD_PREFIX = ".upload-"

REPORT_SUFFIXES = (".xlsx", ".pdf", ".ufdr", ".zip")
UFDR_SUFFIXES = (".ufdr", ".zip")
GOVDOC_SUFFIXES = (".pdf",)

Clock = Callable[[], datetime]


def cases_home() -> Path:
    env = os.environ.get(CASES_ENV, "").strip()
    return Path(env).expanduser() if env else DEFAULT_HOME


def _now(clock: Clock | None) -> datetime:
    return (clock or (lambda: datetime.now(UTC)))()


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Case:
    db: Path

    @property
    def folder(self) -> Path:
        return self.db.parent

    @property
    def settings_path(self) -> Path:
        return self.db.with_suffix(".json")

    @property
    def inputs(self) -> Path:
        name = "inputs" if self.db.name == DB_NAME else f"{self.db.stem}-inputs"
        return self.folder / name

    @property
    def settings(self) -> dict:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def name(self) -> str:
        return str(self.settings.get("name") or self.db.stem)

    def save_settings(self, **changes: object) -> None:
        data = {**self.settings, **changes}
        tmp = self.settings_path.with_name(f".{self.settings_path.name}.{secrets.token_hex(4)}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.settings_path)


def list_cases(home: Path) -> list[Case]:
    if not home.is_dir():
        return []
    return sorted(
        (Case(d / DB_NAME) for d in home.iterdir() if (d / DB_NAME).is_file()),
        key=lambda c: c.name.lower(),
    )


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()[:40]
    return slug or "case"


def check_case_name(name: str) -> str:
    name = " ".join(name.split())
    if not name or len(name) > 80 or any(not ch.isprintable() for ch in name):
        raise ReviewError("name the case (up to 80 characters)")
    return name


def create_case(
    home: Path,
    name: str,
    actor: str,
    clock: Clock | None = None,
    passphrase: str | None = None,
    kdf: encryption.Kdf | None = None,
) -> Case:
    """A new case folder with an empty case database. The audit log records who made it.

    With a passphrase the case is encrypted from the start (core/encryption.py) and unlocked
    in this process; read its recovery key once with `recovery_key_for` right after."""
    _expert(actor)
    name = check_case_name(name)
    if passphrase is not None:
        try:
            encryption.check_new_passphrase(passphrase)
            encryption.require()
        except (ValueError, encryption.EncryptionError) as err:
            raise ReviewError(str(err)) from err
    home.mkdir(parents=True, exist_ok=True)
    base = _slug(name)
    folder, n = home / base, 1
    while folder.exists():
        n += 1
        folder = home / f"{base}-{n}"
    folder.mkdir()
    case = Case(folder / DB_NAME)
    case.inputs.mkdir()
    now = _now(clock)
    if passphrase is not None:
        _new_recovery[case.db] = encryption.create_key(case.db, passphrase, kdf, now)
    conn = connect(case.db)
    try:
        apply_schema(conn)
        _logged(
            conn,
            now,
            actor,
            "case.create",
            {"name": name, "encrypted": True} if passphrase is not None else {"name": name},
        )
    finally:
        conn.close()
    case.save_settings(name=name, created_at_utc=_iso(now), created_by=actor)
    return case


_new_recovery: dict[Path, str] = {}


def recovery_key_for(case: Case) -> str | None:
    """The recovery key of a case this process just encrypted, once; None after that."""
    return _new_recovery.pop(case.db, None)


def _logged(conn: sqlite3.Connection, at: datetime, actor: str, action: str, payload: dict) -> None:
    """One audit-log entry in its own write transaction (taken before the log reads its last
    entry, so a concurrent writer cannot take the same seq)."""
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        audit_log.append(conn, at, actor, action, payload)
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


# ---------------------------------------------------------------- claim order


def document_order(conn: sqlite3.Connection) -> list[str]:
    """Claims that are not removed, in the order their paragraphs appear, then by id."""
    rows = conn.execute(
        "SELECT c.id FROM claims c LEFT JOIN govdoc_paragraphs p ON p.id = c.paragraph_id"
        " WHERE c.status != 'removed'"
        " ORDER BY p.govdoc_id, p.page, p.para_no, c.id"
    )
    return [r[0] for r in rows]


def claim_order(case: Case, conn: sqlite3.Connection) -> list[str]:
    """The expert's order: claims they placed first, the rest in document order."""
    live = document_order(conn)
    saved = [c for c in case.settings.get("claim_order") or [] if c in live]
    return saved + [c for c in live if c not in saved]


def move_claim(case: Case, conn: sqlite3.Connection, claim_id: str, delta: int) -> list[str]:
    order = claim_order(case, conn)
    if claim_id not in order:
        raise ReviewError(f"no claim {claim_id} to move")
    i = order.index(claim_id)
    j = max(0, min(len(order) - 1, i + delta))
    order.insert(j, order.pop(i))
    case.save_settings(claim_order=order)
    return order


# ---------------------------------------------------------------- importing files


def safe_file_name(name: str) -> str:
    """The base name only, with characters every file system accepts."""
    base = re.split(r"[\\/]", name or "")[-1].strip()
    base = re.sub(r"[^\w .()\-]", "_", base).strip(" .")
    if not base or base.startswith(UPLOAD_PREFIX):
        base = "file" + base
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        stem, suffix = base, ""
    stem = stem[:100] or "file"
    return f"{stem}.{suffix.lower()}" if suffix else stem


def input_writer(case: Case) -> Callable[[BinaryIO], BinaryIO] | None:
    """For an encrypted case, what wraps an upload's file so it is encrypted as it is
    written (CaseLocked when the case is locked); None for a plain case."""
    if not encryption.is_encrypted_case(case.db):
        return None
    key_id, dek = encryption.case_key(case.db)
    return lambda f: encryption.EncryptedWriter(f, dek, key_id)  # type: ignore[return-value]


def upload_path(case: Case) -> Path:
    case.inputs.mkdir(parents=True, exist_ok=True)
    return case.inputs / f"{UPLOAD_PREFIX}{secrets.token_hex(8)}"


def _make_writable(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def discard(path: Path) -> None:
    if path.exists():
        _make_writable(path)
        path.unlink()


def _place(case: Case, upload: Path, file_name: str) -> Path:
    """Move the finished upload to its own name in inputs/ and make it read-only."""
    target = case.inputs / file_name
    stem, suffix = target.stem, target.suffix
    n = 1
    while target.exists():
        n += 1
        target = case.inputs / f"{stem} ({n}){suffix}"
    os.replace(upload, target)
    target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return target


@dataclass(frozen=True)
class Imported:
    source_id: str
    file_name: str
    sha256: str
    path: Path
    summary: str


def import_upload(
    case: Case,
    conn: sqlite3.Connection,
    upload: Path,
    upload_sha256: str,
    original_name: str,
    kind: str,
    actor: str,
    clock: Clock | None = None,
    date_order: str | None = None,
) -> Imported:
    """Import one uploaded file: 'report' (Cellebrite Excel, PDF or UFDR) or 'govdoc' (PDF).

    `date_order` ('mdy' or 'dmy') is the report's date order when the expert states it; left
    out, the importer works it out from the report or leaves ambiguous dates unread.

    `upload` is the file the screen just wrote into inputs/ and `upload_sha256` the hash taken
    while writing it. On any error the upload is deleted and nothing is stored."""
    _expert(actor)
    try:
        name = safe_file_name(original_name)
        suffix = Path(name).suffix.lower()
        if kind == "report" and suffix not in REPORT_SUFFIXES:
            raise ReviewError(
                "a Cellebrite report is an Excel (.xlsx), PDF (.pdf) or UFDR (.ufdr or .zip) file"
            )
        if kind == "govdoc" and suffix not in GOVDOC_SUFFIXES:
            raise ReviewError("the government document is imported from a PDF")
        if kind not in ("report", "govdoc"):
            raise ReviewError("choose what kind of file this is")
        date_order = date_order or None
        if date_order not in (None, "mdy", "dmy"):
            raise ReviewError("the date order is month first or day first")
        if encryption.input_size(upload) == 0:
            raise ReviewError(f"{name} is empty")
        dup = conn.execute(
            "SELECT id, file_name FROM sources WHERE sha256 = ?", (upload_sha256,)
        ).fetchone()
        if dup is not None:
            raise ReviewError(f"this file is already in the case, as {dup[1]} ({dup[0]})")
    except BaseException:
        discard(upload)
        raise

    path = _place(case, upload, name)
    try:
        if kind == "govdoc":
            from core.ingest.govdoc import PdfGovDocIngester

            result = PdfGovDocIngester().ingest_full(path, conn)
            src = result.source
            ocr = f", OCR on pages {list(result.ocr_pages)}" if result.ocr_pages else ""
            summary = f"{len(result.paragraphs)} paragraphs{ocr}"
        else:
            if suffix == ".pdf":
                from core.ingest.cellebrite_pdf import CellebritePdfImporter as Importer
            elif suffix in UFDR_SUFFIXES:
                from core.ingest.ufdr import UfdrImporter as Importer  # type: ignore[assignment]
            else:
                from core.ingest.cellebrite_excel import CellebriteExcelImporter as Importer
            from core.ingest.coverage import summary as coverage_summary

            src = Importer(date_order=date_order).import_source(path, conn)
            summary = (
                "coverage not known"
                if src.fidelity.value == "unknown"
                else src.fidelity.value.replace("_", " ")
            )
            cov = coverage_summary(conn, src.id)
            if cov is not None:
                summary += f". {cov.headline.removesuffix('.')}"
        if src.sha256 != upload_sha256:  # the bytes parsed are not the bytes received
            raise ReviewError(
                f"{name} changed between upload and import (SHA-256 {upload_sha256} then "
                f"{src.sha256}); nothing should change a copied input, so check the case folder"
            )
    except BaseException:
        _forget(conn, path, upload_sha256)
        raise
    _logged(
        conn,
        _now(clock),
        actor,
        "case.import",
        {
            "kind": kind,
            "source_id": src.id,
            "original_name": original_name[:200],
            "copied_to": str(path.relative_to(case.folder)),
            "sha256": src.sha256,
        },
    )
    return Imported(src.id, path.name, src.sha256, path, summary)


def _forget(conn: sqlite3.Connection, path: Path, sha: str) -> None:
    """Undo a failed import: the copy is deleted. The importers store nothing until they have
    parsed the whole file, so the database needs no clean-up unless a source row landed."""
    if conn.in_transaction:
        conn.rollback()
    row = conn.execute("SELECT id FROM sources WHERE sha256 = ?", (sha,)).fetchone()
    if row is None:
        discard(path)


def source_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Records per source, for the setup page."""
    out: dict[str, int] = {}
    for table in ("messages", "calls", "contacts", "locations"):
        try:
            rows = conn.execute(
                f"SELECT source_id, COUNT(*) FROM {table} GROUP BY source_id"  # noqa: S608
            ).fetchall()
        except OperationalError:
            continue
        for sid, n in rows:
            out[sid] = out.get(sid, 0) + n
    return out


def last_audit_line(conn: sqlite3.Connection) -> str:
    run = pipeline.view_run(conn)
    if run is None:
        return "not audited"
    if run.get("partial"):
        return f"audit not finished ({len(run['manifest'])} of {len(run['claim_order'] or ())})"
    return f"audited {run['started_at_utc'][:10]}"


# ---------------------------------------------------------------- ready to audit?


@dataclass(frozen=True)
class Ready:
    ok: bool
    text: str
    blocks: bool = True  # the audit cannot start until this is ok
    acknowledge: str | None = None  # form field that lets the expert go on anyway


def readiness(case: Case, conn: sqlite3.Connection) -> list[Ready]:
    """What must be true before the audit starts, in the order the setup page shows it."""
    out: list[Ready] = []
    govdocs = conn.execute("SELECT COUNT(*) FROM govdocs").fetchone()[0]
    reports = conn.execute("SELECT COUNT(*) FROM sources WHERE kind != 'govdoc'").fetchone()[0]
    out.append(
        Ready(
            bool(govdocs),
            "The government document is imported."
            if govdocs
            else "Import the government document.",
        )
    )
    out.append(
        Ready(
            bool(reports),
            f"{reports} extraction report(s) imported."
            if reports
            else "Import at least one extraction report.",
        )
    )
    proposed = conn.execute("SELECT COUNT(*) FROM claims WHERE status = 'proposed'").fetchone()[0]
    order = claim_order(case, conn)
    if not order:
        out.append(Ready(False, "Add claims: propose them with the local model, or add your own."))
    elif proposed:
        out.append(
            Ready(
                False,
                f"{proposed} proposed claim(s) still need your decision: accept, edit "
                "or remove each one.",
            )
        )
    else:
        out.append(Ready(True, f"{len(order)} claim(s) to audit, in the order shown."))
    devices = list(conn.execute("SELECT id FROM devices ORDER BY id"))
    stipulated = {
        r[0]
        for r in conn.execute(
            "SELECT subject_id FROM stipulations WHERE kind = 'device_owner'"
            " AND status = 'confirmed'"
        )
    }
    missing = [d for (d,) in devices if d not in stipulated]
    if devices and missing:
        out.append(
            Ready(
                False,
                f"Confirm who used each phone: {', '.join(missing)} has no stipulated user. "
                "Without one, checks on who sent a message come back inconclusive.",
                acknowledge="owners_ok",
            )
        )
    elif devices:
        out.append(Ready(True, "Every phone has a stipulated user."))
    return out
