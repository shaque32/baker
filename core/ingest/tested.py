"""The export formats and versions Mabillon has been tested with, and each source's notice.

TESTED is the one list, kept here only: a Cellebrite UFDR whose report.xml states reportVersion
7.48, the version of the three public Hickman test-phone packages (#117, #130). Version matching
is exact: the version the export states, as written, must equal the listed one. A missing or
blank version is not tested. Every other format or version (another UFDR report version,
Cellebrite Excel or PDF, Magnet AXIOM) is not tested.

At import each importer records the source's format, its stated version as written and whether
it is in the tested set, in the coverage payload (`format_check`) and in the audit log (action
`import.format`). The case overview, the setup screen's file list, every claim page that rests
on the source and the report (Limitations, and each such claim) print the same notice for it.

The notice only discloses. It never changes a verdict, a rule, a check or what an import reads.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.ingest import coverage

VERSION = "1.0.0"  # the tested set and the notice wording; recorded with every import
ACTION = "import.format"  # the audit-log entry each import writes

# (importer, stated version exactly as the export writes it)
TESTED: frozenset[tuple[str, str]] = frozenset({("ufdr", "7.48")})
TESTED_NOTICE = {
    ("ufdr", "7.48"): (
        "Tested on public test phones (Cellebrite Reader 7.48). Not tested on your case data."
    ),
}
NOT_TESTED = "Not tested: {format} {version} has not been tested with Mabillon."
CHECK_STEP = " Check results against the source tool."

# importer -> (the format as the notice names it, what its stated version is called)
FORMATS: dict[str, tuple[str, str]] = {
    "ufdr": ("Cellebrite UFDR", "report version"),
    "cellebrite_excel": ("Cellebrite Excel export", "version"),
    "cellebrite_pdf": ("Cellebrite PDF report", "version"),
    "axiom": ("Magnet AXIOM report", "version"),
}
_AXIOM_FORMATS = {"xml": "Magnet AXIOM XML report", "xlsx": "Magnet AXIOM Excel report"}

# record id prefix -> the query for the record's source (core/enrich/records.py, the importers)
_RECORD_SOURCE = {
    "msg": "SELECT source_id FROM messages WHERE id = ?",
    "call": "SELECT source_id FROM calls WHERE id = ?",
    "contact": "SELECT source_id FROM contacts WHERE id = ?",
    "att": "SELECT source_id FROM attachments WHERE id = ?",
    "acct": "SELECT source_id FROM accounts WHERE id = ?",
    "thr": "SELECT source_id FROM threads WHERE id = ?",
}


@dataclass(frozen=True)
class FormatCheck:
    source_id: str
    file_name: str
    importer: str
    format: str  # as the notice names it
    version_kind: str  # "report version", "version"
    stated_version: str | None  # as the export writes it; None when it states none

    @property
    def tested(self) -> bool:
        v = self.stated_version
        return v is not None and (self.importer, v) in TESTED

    @property
    def parts(self) -> tuple[coverage.Segment, ...]:
        """The notice as segments; the stated version is the export's own text (quoted)."""
        if self.tested:
            return ((TESTED_NOTICE[(self.importer, str(self.stated_version))], False),)
        v = self.stated_version
        if v is None or not v.strip():
            missing = f"(no {self.version_kind} stated)"
            return ((NOT_TESTED.format(format=self.format, version=missing) + CHECK_STEP, False),)
        head, tail = NOT_TESTED.format(format=self.format, version="\0").split("\0")
        return ((f"{head}{self.version_kind} ", False), (v, True), (tail + CHECK_STEP, False))

    @property
    def notice(self) -> str:
        return "".join(t for t, _q in self.parts)

    def payload(self) -> dict[str, object]:
        """What the import records (coverage payload and audit log)."""
        return {
            "source_id": self.source_id,
            "format": self.format,
            "version_kind": self.version_kind,
            "stated_version": self.stated_version,
            "tested": self.tested,
            "tested_set_version": VERSION,
            "notice": self.notice,
        }


def format_name(importer: str, axiom_format: str | None = None) -> tuple[str, str]:
    name, kind = FORMATS.get(importer, (importer, "version"))
    if importer == "axiom" and axiom_format in _AXIOM_FORMATS:
        name = _AXIOM_FORMATS[axiom_format]
    return name, kind


def at_import(
    importer: str,
    source_id: str,
    file_name: str,
    stated_version: str | None,
    axiom_format: str | None = None,
) -> FormatCheck:
    """The check an importer records: the version is passed exactly as the export states it."""
    name, kind = format_name(importer, axiom_format)
    return FormatCheck(source_id, file_name, importer, name, kind, stated_version)


def _stated(importer: str, payload: Mapping[str, object], tool_version: str | None) -> str | None:
    """The stated version of an import made before format checks were recorded: a UFDR's
    reportVersion (in its coverage record), else the tool version the source row holds."""
    if importer == "ufdr":
        u = payload.get("ufdr")
        v = u.get("report_version") if isinstance(u, dict) else None
        return v if isinstance(v, str) else None
    return tool_version


def for_source(conn: sqlite3.Connection, source_id: str) -> FormatCheck | None:
    """The format check of one evidence source, or None for a government document. Tested or
    not is decided by TESTED as it is in this build, from the version recorded at import."""
    row = conn.execute(
        "SELECT kind, file_name, tool_version FROM sources WHERE id = ?", (source_id,)
    ).fetchone()
    if row is None or row[0] == "govdoc":
        return None
    kind, file_name, tool_version = row
    cov = coverage.load(conn, source_id)
    payload = cov.payload if cov is not None else {}
    importer = cov.importer if cov is not None else str(kind)
    recorded = payload.get("format_check")
    if isinstance(recorded, dict) and "stated_version" in recorded:
        v = recorded["stated_version"]
        stated = v if isinstance(v, str) else None
    else:
        stated = _stated(importer, payload, tool_version)
    ax = payload.get("axiom")
    axiom_format = ax.get("format") if isinstance(ax, dict) else None
    return at_import(importer, source_id, str(file_name), stated, axiom_format)


def all_sources(conn: sqlite3.Connection) -> list[FormatCheck]:
    """One check per evidence source, in source id order."""
    ids = [r[0] for r in conn.execute("SELECT id FROM sources WHERE kind != 'govdoc' ORDER BY id")]
    return [c for c in (for_source(conn, i) for i in ids) if c is not None]


def record_sources(conn: sqlite3.Connection, record_ids: Iterable[str]) -> set[str] | None:
    """The sources the records come from, or None when one cannot be traced (the caller then
    names every source, so a notice is never left out)."""
    out: set[str] = set()
    for rid in dict.fromkeys(record_ids):
        sql = _RECORD_SOURCE.get(rid.split(":", 1)[0])
        row = conn.execute(sql, (rid,)).fetchone() if sql else None
        if row is None:
            return None
        out.add(row[0])
    return out


def for_claim(
    conn: sqlite3.Connection,
    evidence_sources: Iterable[str],
    check_sources: Iterable[str],
    record_ids: Iterable[str],
) -> list[FormatCheck]:
    """The checks of the sources a claim rests on: where its evidence items come from, what its
    checks searched and where the records its checks cite come from."""
    rests = set(evidence_sources) | set(check_sources)
    traced = record_sources(conn, record_ids)
    every = all_sources(conn)
    if traced is None:
        return every
    rests |= traced
    return [c for c in every if c.source_id in rests]
