"""Shared mapping for Cellebrite Excel and PDF reports.

Both readers turn their input into `RawTable`s (header text plus rows of cell values, each with a
locator). Everything after that (column mapping, party parsing, times, deleted flags, ids, writing
canonical rows and the coverage record) lives here so the two formats behave identically.

Layout assumptions are documented in docs/ingest/cellebrite_report.md.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

from core.contracts import (
    CallDirection,
    ExtractionType,
    Fidelity,
    MessageDirection,
    Source,
    SourceKind,
    Timestamp,
)
from core.ingest.source_file import SourceFile
from core.review import audit_log

IMPORTER_VERSION = "0.1.0"
HEADER_SCAN_ROWS = 10
MAX_LISTED = 50  # cap on ids listed in a coverage payload

type Cell = str | int | float | bool | datetime | None


class RecordKind(StrEnum):
    CHATS = "chats"
    SMS = "sms"
    CALLS = "calls"
    CONTACTS = "contacts"
    ACCOUNTS = "accounts"


@dataclass
class RawTable:
    """One sheet (Excel) or one table (PDF) as read, before any interpretation."""

    name: str
    kind_hint: RecordKind | None  # from the sheet name or section title, if recognised
    rows: list[tuple[str, list[Cell]]]  # (locator, cells), header rows included
    reflowed: bool = False  # True for PDF: line breaks in cells may come from page layout


# ---------------------------------------------------------------- names and aliases


def norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


SHEET_KINDS: dict[str, RecordKind] = {
    "chats": RecordKind.CHATS,
    "chat": RecordKind.CHATS,
    "instant messages": RecordKind.CHATS,
    "sms messages": RecordKind.SMS,
    "sms": RecordKind.SMS,
    "mms messages": RecordKind.SMS,
    "messages": RecordKind.SMS,
    "call log": RecordKind.CALLS,
    "calls": RecordKind.CALLS,
    "contacts": RecordKind.CONTACTS,
    "user accounts": RecordKind.ACCOUNTS,
    "accounts": RecordKind.ACCOUNTS,
}
SUMMARY_SHEETS = {"summary", "extraction summary", "case information", "report summary"}


def kind_for_title(title: str) -> RecordKind | None:
    t = norm(title)
    t = re.sub(r"\s*\(\d+\)$", "", t)  # "Chats (123)"
    return SHEET_KINDS.get(t)


_COMMON = {
    "app": ["source", "application", "app", "service"],
    "deleted": [
        "deleted",
        "deleted - instant message",
        "deleted - message",
        "deleted - call",
        "deleted - contact",
        "record status",
        "deleted state",
    ],
}
_TIME = {
    "ts": ["timestamp", "date/time", "time", "date", "timestamp: date/time", "start time"],
    "ts_date": ["timestamp: date", "date (date)"],
    "ts_time": ["timestamp: time", "time (time)"],
}
_MSG = {
    **_COMMON,
    **_TIME,
    "from": ["from", "sender"],
    "to": ["to", "recipients", "recipient"],
    "body": ["body", "message", "text", "content"],
    "direction": ["direction"],
    "type": ["type"],
    "folder": ["folder"],
    "status": ["status"],
    "owner_account": ["account", "owner account"],
}
FIELD_ALIASES: dict[RecordKind, dict[str, list[str]]] = {
    RecordKind.CHATS: {
        **_MSG,
        "chat_id": ["chat #", "chat id", "chat identifier", "identifier", "thread", "thread id"],
        "chat_name": ["name", "chat name", "description"],
        "participants": ["participants"],
    },
    RecordKind.SMS: {
        **_MSG,
        "parties": ["parties", "number", "phone number"],
        "participants": ["participants"],
    },
    RecordKind.CALLS: {
        **_COMMON,
        **_TIME,
        "from": ["from", "caller"],
        "to": ["to", "callee"],
        "parties": ["parties", "number", "phone number", "party"],
        "name": ["name"],
        "direction": ["direction"],
        "type": ["type", "call type"],
        "status": ["status"],
        "duration": ["duration"],
    },
    RecordKind.CONTACTS: {
        **_COMMON,
        "name": ["name", "display name", "contact name"],
        "entries": ["entries", "entry"],
        "phone": ["phone", "phone number", "phone numbers", "mobile", "number"],
        "email": ["email", "e-mail", "emails"],
        "username": ["username", "user name", "user id", "identifier"],
    },
    RecordKind.ACCOUNTS: {
        **_COMMON,
        "username": ["username", "user name", "user id", "identifier", "account"],
        "name": ["name", "display name"],
        "entries": ["entries"],
    },
}
# Present in real reports, deliberately not imported, so not reported as unknown.
IGNORED_COLUMNS = {
    "#",
    "deleted - chat",
    "instant message #",
    "start time: date",
    "start time: time",
    "last activity",
    "last activity: date",
    "last activity: time",
    "number of attachments",
    "tags",
    "tag note",
    "carved",
    "manually decoded",
    "platform",
    "label",
    "source info",
    "source file information",
    "extraction",
    "notes",
    "read",
    "starred message",
    "priority",
    "smsc",
}
ATTACHMENT_RE = re.compile(r"^attachments?(?: #?\d+)?$")

_ALL_ALIASES: dict[str, str] = {}
for _kind_map in FIELD_ALIASES.values():
    for _field, _names in _kind_map.items():
        for _n in _names:
            _ALL_ALIASES.setdefault(_n, _field)


def map_headers(
    kind: RecordKind, headers: list[Cell]
) -> tuple[dict[str, int], list[int], list[str]]:
    """Map header cells to fields. Returns (field -> column index, attachment columns, unknown
    header names). First matching column wins for a field."""
    aliases = {n: f for f, names in FIELD_ALIASES[kind].items() for n in names}
    fields: dict[str, int] = {}
    attachments: list[int] = []
    unknown: list[str] = []
    for i, h in enumerate(headers):
        if h is None or str(h).strip() == "":
            continue
        n = norm(h)
        if n in aliases:
            fields.setdefault(aliases[n], i)
        elif ATTACHMENT_RE.match(n) and kind in (RecordKind.CHATS, RecordKind.SMS):
            attachments.append(i)
        elif n not in IGNORED_COLUMNS:
            unknown.append(str(h).strip())
    return fields, attachments, unknown


def classify(field_names: set[str]) -> RecordKind | None:
    """Pick a record kind from header fields when the sheet or section name did not say."""
    if "body" in field_names:
        return RecordKind.CHATS if {"chat_id", "participants"} & field_names else RecordKind.SMS
    if "duration" in field_names:
        return RecordKind.CALLS
    if {"entries", "phone", "email"} & field_names:
        return RecordKind.CONTACTS
    if "username" in field_names:
        return RecordKind.ACCOUNTS
    return None


def find_header(table: RawTable) -> tuple[RecordKind, int] | None:
    """Index into table.rows of the header row, and the record kind."""
    for idx, (_loc, cells) in enumerate(table.rows[:HEADER_SCAN_ROWS]):
        names = [norm(c) for c in cells if c is not None and str(c).strip()]
        if table.kind_hint is not None:
            aliases = {n for names_ in FIELD_ALIASES[table.kind_hint].values() for n in names_}
            if sum(1 for n in names if n in aliases) >= 2:
                return table.kind_hint, idx
        else:
            found = {_ALL_ALIASES[n] for n in names if n in _ALL_ALIASES}
            kind = classify(found) if len(found) >= 2 else None
            if kind is not None:
                return kind, idx
    return None


# ---------------------------------------------------------------- cell parsing


def text(cell: Cell) -> str | None:
    """Cell as stripped text; None when empty. Not for message bodies (those stay verbatim)."""
    if cell is None:
        return None
    if isinstance(cell, bool):
        s = str(cell)
    elif isinstance(cell, float) and cell.is_integer():
        s = str(int(cell))
    elif isinstance(cell, datetime):
        s = cell.isoformat(sep=" ")
    else:
        s = str(cell)
    s = s.strip()
    return s or None


def body_text(cell: Cell) -> str:
    """Message body exactly as the cell holds it (no stripping); empty string if blank."""
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell
    return text(cell) or ""


_DELETED_YES = {"deleted", "yes", "y", "trash", "true", "1"}
_DELETED_NO = {"intact", "no", "n", "false", "0", "active"}


def parse_deleted(cell: Cell) -> bool | None:
    t = text(cell)
    if t is None:
        return None
    t = norm(t)
    if t in _DELETED_YES:
        return True
    if t in _DELETED_NO:
        return False
    return None


_MSG_IN = {"incoming", "received", "inbox", "in"}
_MSG_OUT = {"outgoing", "sent", "outbox", "out"}
_STATUS_IN = {"received", "incoming"}
_STATUS_OUT = {"sent", "outgoing"}
_CALL_DIR = {
    "incoming": CallDirection.INCOMING,
    "received": CallDirection.INCOMING,
    "outgoing": CallDirection.OUTGOING,
    "dialed": CallDirection.OUTGOING,
    "dialled": CallDirection.OUTGOING,
    "missed": CallDirection.MISSED,
}


def _first_word(value: str) -> str:
    return norm(value).split(" ")[0] if value.strip() else ""


def stated_message_direction(row: Row) -> tuple[MessageDirection | None, str | None]:
    """Direction from the Direction, Type, Folder or Status column, in that order.
    Returns (direction, unmapped raw value)."""
    unmapped = None
    for f in ("direction", "type", "folder", "status"):
        v = row.text(f)
        if v is None:
            continue
        w = _first_word(v)
        ins, outs = (_STATUS_IN, _STATUS_OUT) if f == "status" else (_MSG_IN, _MSG_OUT)
        if w in ins:
            return MessageDirection.INCOMING, None
        if w in outs:
            return MessageDirection.OUTGOING, None
        if f != "status":
            unmapped = unmapped or v
    return None, unmapped


def stated_call_direction(row: Row) -> tuple[CallDirection | None, str | None]:
    unmapped = None
    for f in ("direction", "type", "status"):
        v = row.text(f)
        if v is None:
            continue
        d = _CALL_DIR.get(_first_word(v))
        if d is not None:
            return d, None
        unmapped = unmapped or v
    return None, unmapped


def parse_duration(cell: Cell) -> int | None:
    if isinstance(cell, int | float) and not isinstance(cell, bool):
        return int(cell)
    t = text(cell)
    if t is None:
        return None
    if re.fullmatch(r"\d+", t):
        return int(t)
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", t)
    if m:
        h, mi, s = m.groups()
        return int(h or 0) * 3600 + int(mi) * 60 + int(s)
    return None


# ---------------------------------------------------------------- parties


_IDENT_RE = re.compile(r"\+?\d[\d\-().]{3,}|[^@\s]+@[^@\s]+|@\w[\w.]*|\d{5,}")
_ROLE_RE = re.compile(r"^(from|to)\s*:\s*", re.I)
_OWNER_RE = re.compile(r"\s*\(owner\)\s*$", re.I)


@dataclass(frozen=True)
class Party:
    identifier: str | None  # None when the report showed only a name
    name: str | None
    owner: bool
    role: str | None  # 'from' / 'to' when a Parties cell prefixed it


def _starts_party(line: str) -> bool:
    tok = _ROLE_RE.sub("", line).partition(" ")[0]
    return bool(_ROLE_RE.match(line)) or bool(_IDENT_RE.fullmatch(tok))


def parse_parties(cell: Cell, reflowed: bool = False) -> list[Party]:
    """Parties in a From/To/Participants/Parties cell. With `reflowed` (PDF), a line that does
    not start with an identifier continues the previous line instead of starting a new party."""
    t = text(cell)
    if t is None:
        return []
    if reflowed:
        lines: list[str] = []
        for line in (ln.strip() for ln in t.splitlines()):
            if lines and line and not _starts_party(line):
                lines[-1] = f"{lines[-1]} {line}"
            elif line:
                lines.append(line)
        t = "\n".join(lines)
    out: list[Party] = []
    for piece in re.split(r"[\n;]+", t):
        p = piece.strip()
        if not p:
            continue
        role = None
        m = _ROLE_RE.match(p)
        if m:
            role = m.group(1).lower()
            p = p[m.end() :]
        owner = bool(_OWNER_RE.search(p))
        p = _OWNER_RE.sub("", p).strip()
        if not p:
            continue
        tok, _, rest = p.partition(" ")
        if _IDENT_RE.fullmatch(tok):
            out.append(Party(tok, rest.strip() or None, owner, role))
        else:
            out.append(Party(None, p, owner, role))
    return out


# ---------------------------------------------------------------- times


_TS_RE = re.compile(
    r"""^\s*
    (?P<a>\d{1,4})[/.\-](?P<b>\d{1,2})[/.\-](?P<c>\d{1,4})
    (?:[\sT,]+(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2})(?:\.(?P<f>\d{1,6}))?)?
       \s*(?P<ampm>[AaPp]\.?[Mm]\.?)?)?
    \s*(?:\(?\s*(?P<utc>UTC|GMT)\s*(?P<off>[+-]\s*\d{1,2}(?::?\d{2})?)?\s*\)?)?
    \s*$""",
    re.X,
)
_FIXED_TZ_RE = re.compile(r"^\(?\s*(?:UTC|GMT)\s*(?P<off>[+-]\s*\d{1,2}(?::?\d{2})?)?\s*\)?$", re.I)


def parse_offset(off: str | None) -> int:
    """'+5' -> 300, '-05:00' -> -300, '+0530' -> 330, None -> 0."""
    if not off:
        return 0
    off = off.replace(" ", "")
    sign = -1 if off[0] == "-" else 1
    digits = off[1:].replace(":", "")
    if len(digits) <= 2:
        h, m = int(digits), 0
    else:
        h, m = int(digits[:-2]), int(digits[-2:])
    return sign * (h * 60 + m)


def fixed_report_offset(tz_raw: str | None) -> int | None:
    """A report-level time zone is used only when it is a fixed UTC offset. Named zones
    ('(UTC-05:00) Eastern Time') observe DST, so applying their standard offset could be wrong."""
    if tz_raw is None:
        return None
    m = _FIXED_TZ_RE.match(tz_raw.strip())
    return parse_offset(m.group("off")) if m else None


@dataclass
class DateOrder:
    """Day/month order for one table, decided from the values that disambiguate."""

    dmy_votes: int = 0
    mdy_votes: int = 0

    def observe(self, raw: str) -> None:
        m = _TS_RE.match(raw)
        if not m or len(m.group("a")) == 4:
            return
        a, b = int(m.group("a")), int(m.group("b"))
        if a > 12 >= b:
            self.dmy_votes += 1
        elif b > 12 >= a:
            self.mdy_votes += 1

    @property
    def label(self) -> str:
        if self.dmy_votes and self.mdy_votes:
            return "conflict"
        if self.dmy_votes:
            return "dmy"
        if self.mdy_votes:
            return "mdy"
        return "mdy_assumed"


def _to_ts(naive: datetime, offset_min: int | None, raw: str) -> Timestamp:
    if offset_min is None:
        return Timestamp(utc=None, offset_min=None, raw=raw)
    aware = naive.replace(tzinfo=timezone(timedelta(minutes=offset_min)))
    return Timestamp(utc=aware.astimezone(UTC), offset_min=offset_min, raw=raw)


@dataclass
class TimeResult:
    ts: Timestamp
    offset_from_report: bool = False
    unparsed: bool = False


def parse_time(
    value: Cell, order: DateOrder, report_offset: int | None, raw_override: str | None = None
) -> TimeResult:
    if value is None or (isinstance(value, str) and not value.strip()):
        return TimeResult(Timestamp(utc=None, offset_min=None, raw=None))
    if isinstance(value, datetime):
        raw = raw_override or value.isoformat(sep=" ")
        if value.tzinfo is not None:
            off = int(value.utcoffset().total_seconds() // 60)  # type: ignore[union-attr]
            return TimeResult(Timestamp(utc=value.astimezone(UTC), offset_min=off, raw=raw))
        return TimeResult(
            _to_ts(value, report_offset, raw), offset_from_report=report_offset is not None
        )
    raw = raw_override or str(value)
    s = raw.strip()
    m = _TS_RE.match(s)
    if m:
        return _parse_match(m, raw, order, report_offset)
    try:
        iso = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return TimeResult(Timestamp(utc=None, offset_min=None, raw=raw), unparsed=True)
    if iso.tzinfo is not None:
        off = int(iso.utcoffset().total_seconds() // 60)  # type: ignore[union-attr]
        return TimeResult(Timestamp(utc=iso.astimezone(UTC), offset_min=off, raw=raw))
    return TimeResult(_to_ts(iso, report_offset, raw), offset_from_report=report_offset is not None)


def _parse_match(
    m: re.Match[str], raw: str, order: DateOrder, report_offset: int | None
) -> TimeResult:
    unparsed = TimeResult(Timestamp(utc=None, offset_min=None, raw=raw), unparsed=True)
    if m.group("H") is None:
        return unparsed  # a date with no time is not a point in time
    a, b, c = m.group("a"), m.group("b"), m.group("c")
    if len(a) == 4:
        y, mo, d = int(a), int(b), int(c)
    elif len(c) == 4:
        x, z = int(a), int(b)
        label = order.label
        if label == "dmy":
            d, mo = x, z
        elif label in ("mdy", "mdy_assumed"):
            mo, d = x, z
        elif x > 12 >= z:  # conflicting table: parse only values that are unambiguous
            d, mo = x, z
        elif z > 12 >= x:
            mo, d = x, z
        else:
            return unparsed
        y = int(c)
    else:
        return unparsed  # two-digit years are not guessed
    hour, minute = int(m.group("H")), int(m.group("M"))
    sec = int(m.group("S") or 0)
    micro = int((m.group("f") or "0").ljust(6, "0"))
    ampm = (m.group("ampm") or "").lower().replace(".", "")
    if ampm:
        if not 1 <= hour <= 12:
            return unparsed
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    try:
        naive = datetime(y, mo, d, hour, minute, sec, micro)
    except ValueError:
        return unparsed
    if m.group("utc"):
        return TimeResult(_to_ts(naive, parse_offset(m.group("off")), raw))
    return TimeResult(
        _to_ts(naive, report_offset, raw), offset_from_report=report_offset is not None
    )


# ---------------------------------------------------------------- report metadata

SUMMARY_KEYS: dict[str, list[str]] = {
    "extraction_start": [
        "extraction start date/time",
        "extraction start time",
        "extraction start date",
        "extraction date",
        "extraction date/time",
    ],
    "extraction_type": ["extraction type", "extraction method"],
    "device": ["device", "model", "device model", "device name"],
    "os": ["os version", "os", "operating system"],
    "tool_version": [
        "ufed physical analyzer version",
        "physical analyzer version",
        "ufed reader version",
        "reader version",
        "report version",
        "version",
    ],
    "time_zone": ["time zone", "timezone", "time zone settings"],
}


def summary_field(pairs: list[tuple[str, str]], key: str) -> str | None:
    wanted = SUMMARY_KEYS[key]
    for k, v in pairs:
        if norm(k).rstrip(":") in wanted and v.strip():
            return v.strip()
    return None


def extraction_type(raw: str | None) -> ExtractionType:
    if raw is None:
        return ExtractionType.UNKNOWN
    t = norm(raw)
    if "physical" in t:
        return ExtractionType.PHYSICAL
    if "file system" in t or "filesystem" in t:
        return ExtractionType.FILE_SYSTEM
    if "logical" in t:
        return ExtractionType.LOGICAL
    return ExtractionType.UNKNOWN


# ---------------------------------------------------------------- rows


@dataclass
class Row:
    locator: str
    cells: list[Cell]
    fields: dict[str, int]
    attachment_cols: list[int]
    reflowed: bool = False

    def get(self, f: str) -> Cell:
        i = self.fields.get(f)
        return self.cells[i] if i is not None and i < len(self.cells) else None

    def text(self, f: str) -> str | None:
        return text(self.get(f))

    def has(self, f: str) -> bool:
        return f in self.fields

    def parties(self, f: str) -> list[Party]:
        return parse_parties(self.get(f), self.reflowed)

    def empty(self) -> bool:
        return all(text(c) is None for c in self.cells)


# ---------------------------------------------------------------- coverage


@dataclass
class TableCoverage:
    name: str
    kind: str | None
    header_locator: str | None = None
    rows_read: int = 0
    rows_imported: int = 0
    rows_skipped: Counter[str] = field(default_factory=Counter)
    unknown_columns: list[str] = field(default_factory=list)
    absent_fields: list[str] = field(default_factory=list)
    date_order: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "header_locator": self.header_locator,
            "rows_read": self.rows_read,
            "rows_imported": self.rows_imported,
            "rows_skipped": dict(self.rows_skipped),
            "unknown_columns": self.unknown_columns,
            "absent_fields": self.absent_fields,
            "date_order": self.date_order,
        }


@dataclass
class Coverage:
    tables: list[TableCoverage] = field(default_factory=list)
    not_imported: list[dict[str, str]] = field(default_factory=list)
    counters: Counter[str] = field(default_factory=Counter)
    unmapped_direction_values: Counter[str] = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- writer


@dataclass(frozen=True)
class ReportInput:
    """What a reader hands to `write_report`."""

    summary: list[tuple[str, str]]
    tables: list[RawTable]
    coverage: Coverage


def _slug(app: str) -> str:
    return norm(app)


class _Writer:
    def __init__(self, conn: sqlite3.Connection, source_id: str, device_id: str, cov: Coverage):
        self.conn = conn
        self.src = source_id
        self.dev = device_id
        self.cov = cov
        self.accounts: dict[str, tuple[str, str, str, str | None, str | None]] = {}
        self.account_names: dict[str, list[str]] = defaultdict(list)
        self.owner_accounts: set[str] = set()
        self.owner_idents: set[tuple[str, str]] = set()  # (app slug, identifier)
        self.threads: dict[str, tuple[str, str, str | None]] = {}
        self.messages: list[tuple[object, ...]] = []
        self.recipients: list[tuple[str, str]] = []
        self.attachments: list[tuple[object, ...]] = []
        self.calls: list[tuple[object, ...]] = []
        self.contacts: list[tuple[object, ...]] = []

    # accounts ------------------------------------------------------------

    def account(self, app: str, party: Party, locator: str, scope: str) -> str:
        """Account id for a party. Exact identifier match within this source and app only.
        A name-only party is scoped to `scope` (its thread) so two people who share a
        display name are never collapsed into one account."""
        slug = _slug(app)
        if party.identifier is not None:
            ident = party.identifier
        else:
            ident = f"name:{scope}:{party.name}"
            self.cov.counters["parties_name_only"] += 1
        aid = f"acct:{self.src}:{slug}:{ident}"
        if aid not in self.accounts:
            self.accounts[aid] = (
                locator,
                app,
                party.identifier if party.identifier is not None else (party.name or ""),
                None,
                party.name,
            )
        if party.name and party.name not in self.account_names[aid]:
            self.account_names[aid].append(party.name)
        if party.owner or (slug, party.identifier) in self.owner_idents:
            self.mark_owner(aid)
        return aid

    def mark_owner(self, aid: str) -> None:
        loc, app, ident, _dev, name = self.accounts[aid]
        self.accounts[aid] = (loc, app, ident, self.dev, name)
        self.owner_accounts.add(aid)

    def is_owner(self, aid: str | None) -> bool:
        return aid is not None and aid in self.owner_accounts

    # threads -------------------------------------------------------------

    def thread(self, app: str, key: str, locator: str, title: str | None) -> str:
        tid = f"thr:{self.src}:{_slug(app)}:{key}"
        if tid not in self.threads:
            self.threads[tid] = (locator, app, title)
        return tid

    # flush ---------------------------------------------------------------

    def flush(self) -> None:
        multi = [a for a, names in self.account_names.items() if len(names) > 1]
        if multi:
            self.cov.counters["accounts_with_multiple_display_names"] = len(multi)
            self.cov.notes.append(
                "Some accounts appear with more than one display name; the first one seen is "
                "stored. Ids: " + ", ".join(sorted(multi)[:MAX_LISTED])
            )
        c = self.conn
        c.executemany(
            "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier,"
            " display_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (aid, self.src, loc, dev, app, ident, name)
                for aid, (loc, app, ident, dev, name) in self.accounts.items()
            ],
        )
        c.executemany(
            "INSERT INTO threads (id, source_id, locator, device_id, app, title)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(tid, self.src, loc, self.dev, app, t) for tid, (loc, app, t) in self.threads.items()],
        )
        c.executemany(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, ts_utc, ts_offset_min, ts_raw, body, lang, deleted_flag, bookmarked)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)",
            self.messages,
        )
        c.executemany(
            "INSERT OR IGNORE INTO message_recipients (message_id, account_id) VALUES (?, ?)",
            self.recipients,
        )
        c.executemany(
            "INSERT INTO attachments (id, source_id, locator, message_id, file_name, mime_type,"
            " sha256) VALUES (?, ?, ?, ?, ?, NULL, NULL)",
            self.attachments,
        )
        c.executemany(
            "INSERT INTO calls (id, source_id, locator, device_id, app, from_account_id,"
            " to_account_id, direction, ts_utc, ts_offset_min, ts_raw, duration_s, deleted_flag)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            self.calls,
        )
        c.executemany(
            "INSERT INTO contacts (id, source_id, locator, device_id, name, identifier)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            self.contacts,
        )
        counts = self.cov.counters
        counts["accounts"] = len(self.accounts)
        counts["threads"] = len(self.threads)
        counts["messages"] = len(self.messages)
        counts["message_recipients"] = len(set(self.recipients))
        counts["attachments"] = len(self.attachments)
        counts["calls"] = len(self.calls)
        counts["contacts"] = len(self.contacts)


def _ts_cols(ts: Timestamp) -> tuple[str | None, int | None, str | None]:
    utc = ts.utc.isoformat().replace("+00:00", "Z") if ts.utc else None
    return utc, ts.offset_min, ts.raw


def _db_bool(v: bool | None) -> int | None:
    return None if v is None else int(v)


def _row_time(row: Row, order: DateOrder, report_offset: int | None, cov: Coverage) -> Timestamp:
    if row.has("ts_date") and row.has("ts_time"):
        dv = row.get("ts_date")
        d = dv.date().isoformat() if isinstance(dv, datetime) else row.text("ts_date")
        t = row.text("ts_time")
        if d is None and t is None:
            res = parse_time(None, order, report_offset)
        else:
            raw = f"{d or ''} {t or ''}".strip()
            res = parse_time(raw, order, report_offset)
    else:
        res = parse_time(row.get("ts"), order, report_offset)
    if res.unparsed:
        cov.counters["times_unparsed"] += 1
    elif res.ts.raw is not None and res.ts.utc is None:
        cov.counters["times_without_offset"] += 1
    if res.offset_from_report:
        cov.counters["times_offset_from_report_settings"] += 1
    return res.ts


def _raw_time_values(rows: list[Row]) -> list[str]:
    out = []
    for r in rows:
        if r.has("ts_date"):
            v = r.text("ts_date")
            if v:
                out.append(f"{v} 00:00")
        v = r.get("ts")
        if isinstance(v, str):
            out.append(v)
    return out


def _deleted(row: Row, cov: Coverage) -> bool | None:
    v = parse_deleted(row.get("deleted"))
    cov.counters["deleted_flag_stated" if v is not None else "deleted_flag_not_stated"] += 1
    return v


def _app(row: Row, default: str) -> str:
    return row.text("app") or default


def _messages(
    w: _Writer, kind: RecordKind, rows: list[Row], order: DateOrder, rep_off: int | None
) -> None:
    cov = w.cov
    for r in rows:
        app = _app(r, "SMS" if kind is RecordKind.SMS else "unknown")
        senders = r.parties("from")
        to_parties = r.parties("to")
        participants = r.parties("participants")
        counterpart = r.parties("parties")
        owner_acct_parties = r.parties("owner_account")

        # thread key
        if kind is RecordKind.CHATS:
            chat_key = r.text("chat_id")
            if chat_key is None:
                ids = sorted(
                    p.identifier or f"name:{p.name}" for p in (participants or senders + to_parties)
                )
                chat_key = "participants:" + "|".join(ids) if ids else f"row:{r.locator}"
                cov.counters["threads_keyed_by_participants"] += 1
        else:
            chat_key = None
        scope = chat_key or f"row:{r.locator}"

        for p in owner_acct_parties:
            w.account(app, replace(p, owner=True), r.locator, scope)

        sender_id = w.account(app, senders[0], r.locator, scope) if senders else None
        if len(senders) > 1:
            cov.counters["messages_with_multiple_senders_first_kept"] += 1

        if to_parties:
            recips = to_parties
        elif participants and senders:
            s = senders[0]
            recips = [p for p in participants if (p.identifier, p.name) != (s.identifier, s.name)]
            cov.counters["recipients_from_participants"] += 1
        else:
            recips = []
        recip_ids = [w.account(app, p, r.locator, scope) for p in recips]

        direction, unmapped = stated_message_direction(r)
        if unmapped:
            cov.unmapped_direction_values[unmapped] += 1
        if direction is None:
            if w.is_owner(sender_id):
                direction = MessageDirection.OUTGOING
                cov.counters["direction_derived_from_owner"] += 1
            elif sender_id and any(w.is_owner(a) for a in recip_ids):
                direction = MessageDirection.INCOMING
                cov.counters["direction_derived_from_owner"] += 1
            else:
                direction = MessageDirection.UNKNOWN
                cov.counters["direction_unknown"] += 1
        else:
            cov.counters["direction_stated"] += 1

        if kind is RecordKind.SMS:
            other = counterpart or (
                to_parties if direction is MessageDirection.OUTGOING else senders
            )
            other = [p for p in other if not p.owner]
            if other:
                p = other[0]
                chat_key = "sms:" + (p.identifier or f"name:{p.name}")
                if p.identifier is None:
                    chat_key = f"sms:row:{r.locator}"  # name-only counterpart: no grouping
                if counterpart:
                    acct = w.account(app, p, r.locator, scope)
                    if direction is MessageDirection.OUTGOING and acct not in recip_ids:
                        recip_ids.append(acct)
                    elif direction is MessageDirection.INCOMING and sender_id is None:
                        sender_id = acct
            else:
                chat_key = f"row:{r.locator}"

        tid = w.thread(app, chat_key, r.locator, r.text("chat_name"))
        ts = _row_time(r, order, rep_off, cov)
        mid = f"msg:{w.src}:{r.locator}"
        w.messages.append(
            (
                mid,
                w.src,
                r.locator,
                tid,
                sender_id,
                direction.value,
                *_ts_cols(ts),
                body_text(r.get("body")),
                _db_bool(_deleted(r, cov)),
            )
        )
        w.recipients.extend((mid, a) for a in dict.fromkeys(recip_ids))
        n = 0
        for col in r.attachment_cols:
            name = text(r.cells[col]) if col < len(r.cells) else None
            for fname in (name or "").splitlines():
                if fname.strip():
                    n += 1
                    loc = f"{r.locator}#att{n}"
                    w.attachments.append((f"att:{w.src}:{loc}", w.src, loc, mid, fname.strip()))


def _calls(w: _Writer, rows: list[Row], order: DateOrder, rep_off: int | None) -> None:
    cov = w.cov
    for r in rows:
        app = _app(r, "unknown")
        scope = f"row:{r.locator}"
        direction, unmapped = stated_call_direction(r)
        if unmapped:
            cov.unmapped_direction_values[unmapped] += 1
        direction = direction or CallDirection.UNKNOWN
        frm = r.parties("from")
        to = r.parties("to")
        parties = r.parties("parties")
        name = r.text("name")
        if name and parties and len(parties) == 1 and parties[0].name is None:
            parties = [replace(parties[0], name=name)]
        for p in parties:
            if p.role == "from":
                frm.append(p)
            elif p.role == "to":
                to.append(p)
        unroled = [p for p in parties if p.role is None]
        if unroled and not frm and not to:
            if direction in (CallDirection.INCOMING, CallDirection.MISSED):
                frm = unroled
            elif direction is CallDirection.OUTGOING:
                to = unroled
            else:
                for p in unroled:
                    w.account(app, p, r.locator, scope)
                cov.counters["calls_party_unattributed"] += 1
        from_id = w.account(app, frm[0], r.locator, scope) if frm else None
        to_id = w.account(app, to[0], r.locator, scope) if to else None
        if len(frm) > 1 or len(to) > 1:
            cov.counters["calls_with_extra_parties_dropped"] += 1
        ts = _row_time(r, order, rep_off, cov)
        w.calls.append(
            (
                f"call:{w.src}:{r.locator}",
                w.src,
                r.locator,
                w.dev,
                app,
                from_id,
                to_id,
                direction.value,
                *_ts_cols(ts),
                parse_duration(r.get("duration")),
                _db_bool(_deleted(r, cov)),
            )
        )


def _entry_values(cell: Cell) -> list[str]:
    """Identifiers from a multi-line cell. 'Phone-Mobile: +15551230001' gives '+15551230001';
    a line without a 'Label:' prefix is kept whole."""
    t = text(cell)
    if t is None:
        return []
    out = []
    for line in (ln.strip() for ln in t.splitlines()):
        if not line:
            continue
        label, sep, value = line.partition(":")
        if sep and value.strip() and re.fullmatch(r"[A-Za-z][A-Za-z \-_]*", label):
            if label.lower() not in ("http", "https", "mailto", "tel"):
                line = value.strip()
        out.append(line)
    return out


def _contacts(w: _Writer, rows: list[Row]) -> None:
    for r in rows:
        name = r.text("name")
        idents: list[str] = []
        for f in ("entries", "phone", "email", "username"):
            idents.extend(_entry_values(r.get(f)))
        idents = list(dict.fromkeys(idents))
        if not idents:
            idents = [""]
            w.cov.counters["contacts_without_identifier"] += 1
        for n, ident in enumerate(idents, start=1):
            w.contacts.append(
                (f"contact:{w.src}:{r.locator}#{n}", w.src, r.locator, w.dev, name, ident)
            )


def _accounts(w: _Writer, rows: list[Row], tc: TableCoverage) -> None:
    for r in rows:
        app = _app(r, "unknown")
        idents = _entry_values(r.get("username")) or _entry_values(r.get("entries"))
        if not idents:
            tc.rows_skipped["account_without_identifier"] += 1
            tc.rows_imported -= 1
            continue
        aid = w.account(app, Party(idents[0], r.text("name"), True, None), r.locator, "")
        w.owner_idents.add((_slug(app), idents[0]))
        w.mark_owner(aid)


KIND_ORDER = [RecordKind.ACCOUNTS, RecordKind.CONTACTS, RecordKind.CHATS, RecordKind.SMS,
              RecordKind.CALLS]  # fmt: skip


def write_report(
    conn: sqlite3.Connection,
    sf: SourceFile,
    kind: SourceKind,
    importer_name: str,
    source_id: str | None,
    imported_at: datetime,
    report: ReportInput,
) -> Source:
    """Write a parsed report as canonical rows plus one coverage entry in the audit log."""
    src = source_id or f"src_{sf.sha256[:12]}"
    if conn.execute("SELECT 1 FROM sources WHERE id = ?", (src,)).fetchone():
        raise ValueError(f"source {src} is already in this case database")
    cov = report.coverage
    summary = report.summary
    tz_raw = summary_field(summary, "time_zone")
    rep_off = fixed_report_offset(tz_raw)
    if tz_raw is not None and rep_off is None:
        cov.notes.append(
            f"Report time zone {tz_raw!r} is not a fixed UTC offset; it was not applied to "
            "times that lack their own offset."
        )
    tool_version = summary_field(summary, "tool_version")
    extracted_raw = summary_field(summary, "extraction_start")
    extracted_utc = None
    if extracted_raw:
        ts = parse_time(extracted_raw, DateOrder(), rep_off).ts
        extracted_utc = ts.utc
    source = Source(
        id=src,
        kind=kind,
        fidelity=Fidelity.CURATED_REPORT,
        extraction_type=extraction_type(summary_field(summary, "extraction_type")),
        file_name=sf.path.name,
        sha256=sf.sha256,
        tool_name="Cellebrite" + (" Physical Analyzer" if tool_version else ""),
        tool_version=tool_version,
        extracted_at_utc=extracted_utc,
        imported_at_utc=imported_at,
    )
    dev = f"dev:{src}"

    # Parse tables into rows grouped by kind.
    grouped: dict[RecordKind, list[tuple[list[Row], DateOrder, TableCoverage]]] = defaultdict(list)
    for table in report.tables:
        tc = TableCoverage(name=table.name, kind=table.kind_hint)
        found = find_header(table)
        if found is None:
            cov.not_imported.append({"name": table.name, "reason": "no recognised header row"})
            continue
        rkind, hidx = found
        tc.kind = rkind.value
        hloc, headers = table.rows[hidx]
        tc.header_locator = hloc
        fields, att_cols, unknown = map_headers(rkind, headers)
        tc.unknown_columns = unknown
        expected = {"deleted", "app"} | (
            {"ts"} if rkind not in (RecordKind.CONTACTS, RecordKind.ACCOUNTS) else set()
        )
        tc.absent_fields = sorted(
            f for f in expected if f not in fields and not (f == "ts" and "ts_date" in fields)
        )
        rows: list[Row] = []
        for loc, cells in table.rows[hidx + 1 :]:
            tc.rows_read += 1
            row = Row(loc, cells, fields, att_cols, table.reflowed)
            if row.empty():
                tc.rows_skipped["empty"] += 1
                continue
            if [norm(c) for c in cells] == [norm(h) for h in headers]:
                tc.rows_skipped["repeated_header"] += 1
                continue
            rows.append(row)
        tc.rows_imported = len(rows)
        order = DateOrder()
        for v in _raw_time_values(rows):
            order.observe(v)
        if rkind not in (RecordKind.CONTACTS, RecordKind.ACCOUNTS):
            tc.date_order = order.label
        grouped[rkind].append((rows, order, tc))
        cov.tables.append(tc)

    w = _Writer(conn, src, dev, cov)
    with conn:
        conn.execute(
            "INSERT INTO sources (id, kind, fidelity, extraction_type, file_name, sha256,"
            " tool_name, tool_version, extracted_at_utc, imported_at_utc)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source.id,
                source.kind.value,
                source.fidelity.value,
                source.extraction_type.value,
                source.file_name,
                source.sha256,
                source.tool_name,
                source.tool_version,
                _iso(source.extracted_at_utc),
                _iso(source.imported_at_utc),
            ),
        )
        conn.execute(
            "INSERT INTO devices (id, source_id, locator, label, model, os_version, timezone)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                dev,
                src,
                "Summary",
                summary_field(summary, "device") or f"Device in {sf.path.name}",
                summary_field(summary, "device"),
                summary_field(summary, "os"),
                tz_raw,
            ),
        )
        for rkind in KIND_ORDER:
            for rows, order, tc in grouped.get(rkind, []):
                if rkind is RecordKind.ACCOUNTS:
                    _accounts(w, rows, tc)
                elif rkind is RecordKind.CONTACTS:
                    _contacts(w, rows)
                elif rkind is RecordKind.CALLS:
                    _calls(w, rows, order, rep_off)
                else:
                    _messages(w, rkind, rows, order, rep_off)
        w.flush()
        audit_log.append(
            conn,
            imported_at,
            "system",
            "import",
            coverage_payload(source, importer_name, tz_raw, rep_off, cov),
        )
    return source


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def coverage_payload(
    source: Source, importer: str, tz_raw: str | None, rep_off: int | None, cov: Coverage
) -> dict[str, object]:
    return {
        "importer": importer,
        "importer_version": IMPORTER_VERSION,
        "source_id": source.id,
        "sha256": source.sha256,
        "file_name": source.file_name,
        "fidelity": source.fidelity.value,
        "fidelity_reason": (
            "Examiner-generated report: the examiner chooses what it contains, so it cannot "
            "support a claim that something is absent from the device."
        ),
        "report_time_zone_raw": tz_raw,
        "report_offset_min_applied": rep_off,
        "tables": [t.as_dict() for t in cov.tables],
        "not_imported": cov.not_imported,
        "counts": dict(sorted(cov.counters.items())),
        "unmapped_direction_values": dict(cov.unmapped_direction_values),
        "notes": cov.notes,
    }
