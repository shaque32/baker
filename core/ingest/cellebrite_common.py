"""Shared mapping for Cellebrite Excel and PDF reports, also used by the UFDR importer.

Both readers turn their input into `RawTable`s (header text plus rows of cell values, each with a
locator). Everything after that (column mapping, party parsing, times, deleted flags, ids, writing
canonical rows and the coverage record) lives here so the two formats behave identically.

Layout assumptions are documented in docs/ingest/cellebrite_report.md. core/ingest/ufdr.py feeds
the message and call mapping and the writer with rows built from UFDR models instead of cells.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta, timezone
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
from core.ingest import forwarded, tested
from core.ingest.source_file import SourceFile
from core.review import audit_log

# 0.3.1: devices.timezone holds only the summary's Device time zone, never the report's display
# zone (with none, the phone's zone is unknown). 0.3.2: records the format check
# (core/ingest/tested.py).
IMPORTER_VERSION = "0.3.2"
HEADER_SCAN_ROWS = 10
MAX_LISTED = 50  # cap on ids listed in a coverage payload
FORWARDED_LABEL_RE = re.compile(r"\b(?:auto-?)?forward(?:ed)?\b", re.IGNORECASE)

EXCEL_CELL_LIMIT = 32767  # characters; Excel truncates longer cell text

type Cell = str | int | float | bool | datetime | None

_OFF = r"[+-]\s*\d{1,2}(?::?\d{2})?"  # a UTC offset as written: '+3', '-05:00', '+0530'


class RecordKind(StrEnum):
    CHATS = "chats"
    SMS = "sms"
    CALLS = "calls"
    CONTACTS = "contacts"
    ACCOUNTS = "accounts"


@dataclass(frozen=True)
class Merge:
    """A merged cell range, as 0-based indexes into RawTable.rows and into the row's cells."""

    first_row: int
    last_row: int
    first_col: int
    last_col: int


@dataclass
class RawTable:
    """One sheet (Excel) or one table (PDF) as read, before any interpretation."""

    name: str
    kind_hint: RecordKind | None  # from the sheet name or section title, if recognised
    rows: list[tuple[str, list[Cell]]]  # (locator, cells), header rows included
    reflowed: bool = False  # True for PDF: line breaks in cells may come from page layout
    app_hint: str | None = None  # app named in the sheet or section title ('Chats - WhatsApp')
    merges: list[Merge] = field(default_factory=list)  # merged ranges (Excel only)
    header_notes: list[str] = field(default_factory=list)  # e.g. a two-row header was joined


# ---------------------------------------------------------------- names and aliases

_INVISIBLE_RE = re.compile("[​‌‍⁠﻿]")


def norm(text: object) -> str:
    """Lowercase, whitespace collapsed (no-break spaces included), invisible marks removed."""
    s = _INVISIBLE_RE.sub("", str(text)).replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def header_norm(text: object) -> str:
    """A header name for alias lookup: `norm` plus a trailing ':' or '*' removed and the
    separators in 'Timestamp - Date' / 'Timestamp:Date' written as 'timestamp: date'."""
    n = norm(text).rstrip(":*").strip()
    n = re.sub(r"\s*[:–—]\s*", ": ", n)
    return re.sub(r"^(timestamp|start time|time stamp) - ", r"\1: ", n)


SHEET_KINDS: dict[str, RecordKind] = {
    "chats": RecordKind.CHATS,
    "chat": RecordKind.CHATS,
    "chat messages": RecordKind.CHATS,
    "instant messages": RecordKind.CHATS,
    "instant message": RecordKind.CHATS,
    "sms messages": RecordKind.SMS,
    "sms": RecordKind.SMS,
    "sms/mms": RecordKind.SMS,
    "sms & mms": RecordKind.SMS,
    "mms messages": RecordKind.SMS,
    "mms": RecordKind.SMS,
    "messages": RecordKind.SMS,
    "text messages": RecordKind.SMS,
    "call log": RecordKind.CALLS,
    "call logs": RecordKind.CALLS,
    "calls": RecordKind.CALLS,
    "call history": RecordKind.CALLS,
    "contacts": RecordKind.CONTACTS,
    "address book": RecordKind.CONTACTS,
    "user accounts": RecordKind.ACCOUNTS,
    "accounts": RecordKind.ACCOUNTS,
}
# Report categories Mabillon does not import (yet). The timeline repeats messages and calls, so it
# is never imported. Coverage lists every such sheet or section with its row count.
NOT_IMPORTED_CATEGORIES = {
    "timeline",
    "locations",
    "device locations",
    "web history",
    "web bookmarks",
    "searched items",
    "installed applications",
    "applications usage",
    "cell towers",
    "wireless networks",
    "calendar",
    "notes",
    "emails",
    "images",
    "videos",
    "audio",
    "documents",
    "data files",
    "cookies",
    "passwords",
    "social media",
    "voicemail",
    "recordings",
}
SUMMARY_SHEETS = {
    "summary",
    "extraction summary",
    "case information",
    "report summary",
    "device information",
    "device info",
    "extraction information",
}
# Apps a sheet or section title may name next to its kind ('Chats - WhatsApp',
# 'Instant Messages (Telegram)', 'Signal Chats'). Only these, so a title such as
# 'Chat Statistics' is never read as chats.
KNOWN_APPS = {
    "whatsapp": "WhatsApp",
    "whatsapp business": "WhatsApp Business",
    "telegram": "Telegram",
    "signal": "Signal",
    "instagram": "Instagram",
    "facebook messenger": "Facebook Messenger",
    "messenger": "Messenger",
    "snapchat": "Snapchat",
    "viber": "Viber",
    "wechat": "WeChat",
    "imessage": "iMessage",
    "skype": "Skype",
    "line": "Line",
    "kik": "Kik",
    "discord": "Discord",
    "wickr": "Wickr",
    "threema": "Threema",
    "sms": "SMS",
    "mms": "MMS",
}
_COUNT_SUFFIX_RE = re.compile(r"\s*\(\s*[\d,]+\s*\)$")  # "Chats (1,234)"


def _title_parts(title: str) -> tuple[RecordKind, str | None] | None:
    t = _COUNT_SUFFIX_RE.sub("", norm(title)).strip()
    if "timeline" in t:
        return None  # the timeline repeats messages and calls; never imported
    if t in SHEET_KINDS:
        return SHEET_KINDS[t], None
    candidates: list[tuple[str, str]] = []
    m = re.fullmatch(r"(.+?)\s*(?:-|–|:|\()\s*(.+?)\)?", t)
    if m:
        candidates += [(m.group(1), m.group(2)), (m.group(2), m.group(1))]
    for app in KNOWN_APPS:
        if t.startswith(app + " "):
            candidates.append((t[len(app) + 1 :], app))
    for kind_part, app_part in candidates:
        kind = SHEET_KINDS.get(kind_part.strip())
        app = KNOWN_APPS.get(app_part.strip())
        if kind is not None and app is not None:
            if kind is RecordKind.SMS and app not in ("SMS", "MMS", "iMessage"):
                kind = RecordKind.CHATS  # 'WhatsApp Messages' are chats, not SMS
            return kind, app
    return None


def kind_for_title(title: str) -> RecordKind | None:
    parts = _title_parts(title)
    return parts[0] if parts else None


def app_for_title(title: str) -> str | None:
    parts = _title_parts(title)
    return parts[1] if parts else None


_COMMON = {
    "app": ["source", "application", "app", "service", "app name", "application name"],
    "deleted": [
        "deleted",
        "deleted - instant message",
        "deleted - message",
        "deleted - call",
        "deleted - contact",
        "record status",
        "deleted state",
        "record state",
    ],
}
_TIME = {
    "ts": [
        "timestamp",
        "date/time",
        "time",
        "date",
        "timestamp: date/time",
        "start time",
        "date & time",
        "date and time",
        "datetime",
        "time stamp",
        "message timestamp",
        "message date/time",
    ],
    "ts_date": ["timestamp: date", "date (date)"],
    "ts_time": ["timestamp: time", "time (time)"],
}
TIME_FIELDS = ("ts", "ts_date", "ts_time")
_MSG = {
    **_COMMON,
    **_TIME,
    "from": ["from", "sender", "author", "from (sender)"],
    "to": ["to", "recipients", "recipient", "receiver", "receivers", "recipient(s)"],
    "body": ["body", "message", "text", "content", "message body", "body text", "message text"],
    "direction": ["direction", "message direction"],
    "type": ["type", "message type"],
    "folder": ["folder"],
    "status": ["status"],
    "owner_account": ["account", "owner account"],
    "tag": ["tag", "tags", "bookmark", "bookmarked"],
    "label": ["label", "labels", "message label"],
}
FIELD_ALIASES: dict[RecordKind, dict[str, list[str]]] = {
    RecordKind.CHATS: {
        **_MSG,
        "chat_id": [
            "chat #",
            "chat id",
            "chat identifier",
            "identifier",
            "thread",
            "thread id",
            "conversation",
            "conversation id",
        ],
        "chat_name": ["name", "chat name", "description", "conversation name", "group name"],
        "participants": ["participants", "members", "chat participants"],
    },
    RecordKind.SMS: {
        **_MSG,
        "parties": ["parties", "number", "phone number", "party"],
        "participants": ["participants"],
    },
    RecordKind.CALLS: {
        **_COMMON,
        **_TIME,
        "ts_date": [*_TIME["ts_date"], "start time: date", "call date"],
        "ts_time": [*_TIME["ts_time"], "start time: time", "call time"],
        "from": ["from", "caller"],
        "to": ["to", "callee"],
        "parties": ["parties", "number", "phone number", "party"],
        "name": ["name"],
        "direction": ["direction", "call direction"],
        "type": ["type", "call type"],
        "status": ["status"],
        "duration": ["duration", "call duration", "duration (hh:mm:ss)", "duration (seconds)"],
    },
    RecordKind.CONTACTS: {
        **_COMMON,
        "name": ["name", "display name", "contact name", "full name"],
        "entries": ["entries", "entry"],
        "phone": ["phone", "phone number", "phone numbers", "mobile", "number", "telephone"],
        "email": ["email", "e-mail", "emails", "email address", "e-mail address"],
        "username": ["username", "user name", "user id", "identifier"],
    },
    RecordKind.ACCOUNTS: {
        **_COMMON,
        "username": ["username", "user name", "user id", "identifier", "account"],
        "name": ["name", "display name"],
        "entries": ["entries"],
    },
}
# What a table must have to be read as its kind. A sheet titled 'Chats' that holds locations has
# 'Time' and 'Name' columns, which alone would pass a two-alias test; this stops it.
CORE_FIELDS: dict[RecordKind, tuple[set[str], str]] = {
    RecordKind.CHATS: ({"body"}, "message body or attachment column"),
    RecordKind.SMS: ({"body"}, "message body or attachment column"),
    RecordKind.CALLS: ({"duration", "parties", "from", "to"}, "duration or party column"),
    RecordKind.CONTACTS: ({"entries", "phone", "email", "username"}, "number or email column"),
    RecordKind.ACCOUNTS: ({"username", "entries"}, "username or identifier column"),
}  # fmt: skip
# Fields whose merged cells (Excel) are copied down to every row of the range: they label a group
# of rows (one chat, one sender). Bodies, times, attachments, flags and durations are never copied.
FILLABLE_FIELDS = {
    "chat_id",
    "chat_name",
    "participants",
    "app",
    "from",
    "to",
    "parties",
    "owner_account",
    "name",
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
ATTACHMENT_RE = re.compile(
    r"^(?:attachments?|attached files?)(?:\s*#?\s*\d+)?(?:\s*:\s*(?:file ?name|name|file))?$"
)
# A fixed-offset qualifier after a time column's name: 'Timestamp (UTC+3)', 'Time - UTC'.
_HEADER_OFFSET_RE = re.compile(
    rf"^(?P<base>.+?)\s*(?:-\s*|\(\s*|\[\s*)(?:UTC|GMT)\s*(?P<off>{_OFF})?\s*[\)\]]?$", re.I
)
_HEADER_QUALIFIER_RE = re.compile(r"^(?P<base>.+?)\s*\((?P<q>[^()]+)\)$")

_ALL_ALIASES: dict[str, str] = {}
for _kind_map in FIELD_ALIASES.values():
    for _field, _names in _kind_map.items():
        for _n in _names:
            _ALL_ALIASES.setdefault(_n, _field)


def known_header(name: object) -> bool:
    """True when `name` is a column name Mabillon knows for some record kind."""
    n = header_norm(name)
    return n in _ALL_ALIASES or bool(ATTACHMENT_RE.match(n)) or n in IGNORED_COLUMNS


@dataclass
class HeaderMap:
    fields: dict[str, int]  # field -> column index; the first matching column wins
    attachments: list[int]
    unknown: list[str]  # header names Mabillon does not know
    duplicates: list[tuple[str, str]]  # (column, field) for a field already mapped; not read
    offsets: dict[str, int]  # time field -> fixed offset stated in its header
    qualifiers: dict[str, str]  # time field -> zone named in its header, not applied

    @property
    def hits(self) -> int:
        return len(self.fields) + len(self.duplicates) + (1 if self.attachments else 0)


def _split_header(n: str, aliases: dict[str, str]) -> tuple[str, int | None, str | None]:
    """(name, fixed offset, other qualifier) for a time column written 'Timestamp (UTC+3)' or
    'Time (Device local)'. Only time columns are split: 'Body (Translated)' stays unknown."""
    if n in aliases:
        return n, None, None
    m = _HEADER_OFFSET_RE.match(n)
    if m and aliases.get(m.group("base")) in TIME_FIELDS:
        return m.group("base"), parse_offset(m.group("off")), None
    q = _HEADER_QUALIFIER_RE.match(n)
    if q and aliases.get(q.group("base")) in TIME_FIELDS:
        return q.group("base"), None, q.group("q").strip()
    return n, None, None


def map_headers(kind: RecordKind, headers: list[Cell]) -> HeaderMap:
    """Map header cells to fields by name, never by position."""
    aliases = {n: f for f, names in FIELD_ALIASES[kind].items() for n in names}
    parsed = [
        (i, str(h).strip(), *_split_header(header_norm(h), aliases))
        for i, h in enumerate(headers)
        if h is not None and str(h).strip()
    ]
    names = {p[2] for p in parsed}
    other_ts = {n for n in names if aliases.get(n) in TIME_FIELDS} - {"date", "time"}
    if {"date", "time"} <= names and not other_ts:
        # 'Date' and 'Time' in separate columns: read them together, not the date alone.
        aliases = {**aliases, "date": "ts_date", "time": "ts_time"}
    hm = HeaderMap({}, [], [], [], {}, {})
    for i, raw, n, offset, qualifier in parsed:
        if n in aliases:
            f = aliases[n]
            if f in hm.fields:
                hm.duplicates.append((raw, f))
                continue
            hm.fields[f] = i
            if offset is not None:
                hm.offsets[f] = offset
            if qualifier is not None:
                hm.qualifiers[f] = qualifier
        elif ATTACHMENT_RE.match(n) and kind in (RecordKind.CHATS, RecordKind.SMS):
            hm.attachments.append(i)
        elif n not in IGNORED_COLUMNS:
            hm.unknown.append(raw)
    return hm


def has_core_fields(kind: RecordKind, hm: HeaderMap) -> bool:
    need, _ = CORE_FIELDS[kind]
    return bool(need & hm.fields.keys()) or (
        kind in (RecordKind.CHATS, RecordKind.SMS) and bool(hm.attachments)
    )


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
    """Index into table.rows of the header row, and the record kind. A header row has at least
    two known column names and the columns its kind cannot do without."""
    for idx, (_loc, cells) in enumerate(table.rows[:HEADER_SCAN_ROWS]):
        if table.kind_hint is not None:
            kind = table.kind_hint
        else:
            names = [header_norm(c) for c in cells if c is not None and str(c).strip()]
            found = {_ALL_ALIASES[n] for n in names if n in _ALL_ALIASES}
            kind = classify(found) if len(found) >= 2 else None
            if kind is None:
                continue
        hm = map_headers(kind, cells)
        if hm.hits >= 2 and has_core_fields(kind, hm):
            return kind, idx
    return None


def header_problem(table: RawTable) -> str:
    """Plain reason a table had no usable header row, for coverage."""
    kind = table.kind_hint
    if kind is not None:
        for _loc, cells in table.rows[:HEADER_SCAN_ROWS]:
            if map_headers(kind, cells).hits >= 2:
                return f"columns do not look like {kind.value}: there is no {CORE_FIELDS[kind][1]}"
    return f"no recognised header row in the first {HEADER_SCAN_ROWS} rows"


def header_preview(table: RawTable, limit: int = 12) -> list[str]:
    """The first row with two or more text cells, trimmed, so the expert can see what the
    table held. Header-like text only; the cells are cut to 40 characters."""
    for _loc, cells in table.rows[:HEADER_SCAN_ROWS]:
        vals = [str(c).strip()[:40] for c in cells if isinstance(c, str) and c.strip()]
        if len(vals) >= 2:
            return vals[:limit]
    return []


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
# Parties are separated by new lines, ';', or ', ' when the next party starts with an identifier
# (a name like 'Smith, John' is not split).
_PARTY_SPLIT_RE = re.compile(
    r"[\n;]+|,\s*(?=\+?\d|[^\s,]+@|@|[A-Za-z0-9][\w]*[._\d][\w.]*(?:\s|$))"
)
# A lone token with no display name, such as an Instagram username 'm.reyes.auto'.
_BARE_HANDLE_RE = re.compile(r"(?=[\w.]*[._\d])[A-Za-z0-9][\w.]*")
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
    for piece in _PARTY_SPLIT_RE.split(t):
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
        if _IDENT_RE.fullmatch(tok) or (not rest and _BARE_HANDLE_RE.fullmatch(tok)):
            out.append(Party(tok, rest.strip() or None, owner, role))
        else:
            out.append(Party(None, p, owner, role))
    return out


# ---------------------------------------------------------------- times


_TS_RE = re.compile(
    rf"""^\s*
    (?P<a>\d{{1,4}})[/.\-](?P<b>\d{{1,2}})[/.\-](?P<c>\d{{1,4}})
    (?:[\sT,]+(?P<H>\d{{1,2}}):(?P<M>\d{{2}})(?::(?P<S>\d{{2}})(?:[.,](?P<f>\d{{1,6}}))?)?
       \s*(?P<ampm>[AaPp]\.?[Mm]\.?)?)?
    \s*(?:[\(\[]?\s*(?:(?P<utc>UTC|GMT|Z)\s*(?P<off>{_OFF})?|(?P<bare>[+-]\d{{2}}:?\d{{2}}))\s*[\)\]]?)?
    \s*$""",
    re.X | re.I,
)
_FIXED_TZ_RE = re.compile(rf"^[\(\[]?\s*(?:UTC|GMT)\s*(?P<off>{_OFF})?\s*[\)\]]?$", re.I)
# A value that parses as a date and time but ends in a zone name or abbreviation ('EST',
# '(Eastern Standard Time)', 'Europe/Moscow'). Named zones are never applied: their offset depends
# on daylight saving and on what the tool meant by the name.
_NAMED_ZONE_RE = re.compile(
    r"^(?P<dt>.*?\d)\s*[\(\[]?\s*(?P<zone>[A-Za-z][A-Za-z_/ ]{1,40})[\)\]]?\s*$"
)
_WEEKDAY_RE = re.compile(r"^\s*(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+", re.I)
_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}  # fmt: skip
# '05-Mar-2026 21:31', '5 March 2026 21:31' and 'Mar 5, 2026 9:31 PM'. English month names only.
_DMONY_RE = re.compile(
    r"^\s*(?P<d>\d{1,2})[\s\-/.]+(?P<mon>[A-Za-z]{3,9})\.?[\s\-/.,]+(?P<y>\d{4})(?P<rest>(?:[\sT,].*)?)$"
)
_MONDY_RE = re.compile(
    r"^\s*(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})(?P<rest>(?:[\sT,].*)?)$"
)


class TimeProblem(StrEnum):
    """Why a time value got no UTC instant. Each is counted in coverage; none is guessed."""

    UNPARSED = "unparsed"  # not a date and time Mabillon recognises
    DATE_ONLY = "date_only"  # a date with no time is not a point in time
    TWO_DIGIT_YEAR = "two_digit_year"
    AMBIGUOUS_DAY_MONTH = "ambiguous_day_month"  # 3/4/2026 with no row deciding the order
    NAMED_ZONE = "named_zone"  # 'EST', '(Eastern Standard Time)': not applied
    NUMERIC = "numeric"  # a bare number (an Excel serial date shown as a number)
    NO_OFFSET = "no_offset"  # a valid local time with no offset anywhere in the report
    # A 'Date' column whose date differs from the full date and time in the 'Time' column
    DATE_COLUMN_DISAGREES = "date_column_disagrees"


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


def _month_name_to_iso(s: str) -> str | None:
    """'05-Mar-2026 21:31' -> '2026-03-05 21:31'. None when there is no English month name."""
    for rx in (_DMONY_RE, _MONDY_RE):
        m = rx.match(s)
        if m and m.group("mon").lower() in _MONTHS:
            mo = _MONTHS[m.group("mon").lower()]
            return f"{m.group('y')}-{mo:02d}-{int(m.group('d')):02d}{m.group('rest')}"
    return None


def _canonical(s: str) -> str:
    """Strip a leading weekday and turn month names into numbers. Day and month order is then
    unambiguous (year first). The raw value is kept separately and never changed."""
    s = _WEEKDAY_RE.sub("", s)
    return _month_name_to_iso(s) or s


@dataclass
class DateOrder:
    """Day/month order, decided only from values that disambiguate (a first number above 12 is
    a day; a second number above 12 is a day). Nothing is assumed when no value decides."""

    dmy_votes: int = 0
    mdy_votes: int = 0

    def observe(self, raw: str) -> None:
        m = _TS_RE.match(_canonical(raw))
        if not m or len(m.group("a")) == 4:
            return
        a, b = int(m.group("a")), int(m.group("b"))
        if a > 12 >= b:
            self.dmy_votes += 1
        elif b > 12 >= a:
            self.mdy_votes += 1

    def merged(self, other: DateOrder) -> DateOrder:
        return DateOrder(self.dmy_votes + other.dmy_votes, self.mdy_votes + other.mdy_votes)

    @property
    def label(self) -> str:
        if self.dmy_votes and self.mdy_votes:
            return "conflict"
        if self.dmy_votes:
            return "dmy"
        if self.mdy_votes:
            return "mdy"
        return "undecided"


def _to_ts(naive: datetime, offset_min: int | None, raw: str) -> Timestamp:
    if offset_min is None:
        return Timestamp(utc=None, offset_min=None, raw=raw)
    aware = naive.replace(tzinfo=timezone(timedelta(minutes=offset_min)))
    return Timestamp(utc=aware.astimezone(UTC), offset_min=offset_min, raw=raw)


@dataclass
class TimeResult:
    ts: Timestamp
    offset_from_fallback: bool = False  # offset came from the column header or report settings
    problem: TimeProblem | None = None

    @property
    def unparsed(self) -> bool:
        return self.problem is not None and self.problem is not TimeProblem.NO_OFFSET


def _no_utc(raw: str | None, problem: TimeProblem | None) -> TimeResult:
    return TimeResult(Timestamp(utc=None, offset_min=None, raw=raw), problem=problem)


def parse_time(
    value: Cell, order: DateOrder, fallback_offset: int | None, raw_override: str | None = None
) -> TimeResult:
    """One time value. An offset written in the value wins; else `fallback_offset` (a fixed
    offset stated in the column header or the report settings) applies; else no UTC instant."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return _no_utc(None, None)
    if isinstance(value, datetime):
        raw = raw_override or value.isoformat(sep=" ")
        if value.tzinfo is not None:
            off = int(value.utcoffset().total_seconds() // 60)  # type: ignore[union-attr]
            return TimeResult(Timestamp(utc=value.astimezone(UTC), offset_min=off, raw=raw))
        return _with_fallback(value, fallback_offset, raw)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return _no_utc(raw_override or text(value), TimeProblem.NUMERIC)
    raw = raw_override or str(value)
    s = _canonical(raw.strip())
    m = _TS_RE.match(s)
    if m:
        return _parse_match(m, raw, order, fallback_offset)
    try:
        iso = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return _no_utc(raw, _diagnose(s, order))
    if iso.tzinfo is not None:
        off = int(iso.utcoffset().total_seconds() // 60)  # type: ignore[union-attr]
        return TimeResult(Timestamp(utc=iso.astimezone(UTC), offset_min=off, raw=raw))
    if len(s) <= 10:
        return _no_utc(raw, TimeProblem.DATE_ONLY)
    return _with_fallback(iso, fallback_offset, raw)


def _diagnose(s: str, order: DateOrder) -> TimeProblem:
    """Why a value did not parse: a readable time with a zone name, or not a time at all."""
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return TimeProblem.NUMERIC
    nz = _NAMED_ZONE_RE.match(s)
    if nz:
        inner = _TS_RE.match(nz.group("dt"))
        if inner and inner.group("H") is not None and not inner.group("utc"):
            if _parse_match(inner, s, order, 0).problem is None:
                return TimeProblem.NAMED_ZONE
    return TimeProblem.UNPARSED


def _with_fallback(naive: datetime, fallback_offset: int | None, raw: str) -> TimeResult:
    if fallback_offset is None:
        return _no_utc(raw, TimeProblem.NO_OFFSET)
    return TimeResult(_to_ts(naive, fallback_offset, raw), offset_from_fallback=True)


def _parse_match(
    m: re.Match[str], raw: str, order: DateOrder, fallback_offset: int | None
) -> TimeResult:
    if m.group("H") is None:
        return _no_utc(raw, TimeProblem.DATE_ONLY)
    a, b, c = m.group("a"), m.group("b"), m.group("c")
    if len(a) == 4:
        y, mo, d = int(a), int(b), int(c)
    elif len(c) == 4:
        x, z = int(a), int(b)
        label = order.label
        if x == z or x > 12 >= z or z > 12 >= x:
            # Unambiguous on its own (or both numbers are the same).
            d, mo = (x, z) if x > 12 else (z, x) if z > 12 else (x, z)
        elif label == "dmy":
            d, mo = x, z
        elif label == "mdy":
            mo, d = x, z
        else:  # undecided or conflicting: never guess the order
            return _no_utc(raw, TimeProblem.AMBIGUOUS_DAY_MONTH)
        y = int(c)
    else:
        return _no_utc(raw, TimeProblem.TWO_DIGIT_YEAR)
    hour, minute = int(m.group("H")), int(m.group("M"))
    sec = int(m.group("S") or 0)
    micro = int((m.group("f") or "0").ljust(6, "0"))
    ampm = (m.group("ampm") or "").lower().replace(".", "")
    if ampm:
        if not 1 <= hour <= 12:
            return _no_utc(raw, TimeProblem.UNPARSED)
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    try:
        naive = datetime(y, mo, d, hour, minute, sec, micro)
    except ValueError:
        return _no_utc(raw, TimeProblem.UNPARSED)
    if m.group("utc"):
        return TimeResult(_to_ts(naive, parse_offset(m.group("off")), raw))
    if m.group("bare"):
        return TimeResult(_to_ts(naive, parse_offset(m.group("bare")), raw))
    return _with_fallback(naive, fallback_offset, raw)


# ---------------------------------------------------------------- report metadata

SUMMARY_KEYS: dict[str, list[str]] = {
    "extraction_start": [
        "extraction start date/time",
        "extraction start time",
        "extraction start date",
        "extraction date",
        "extraction date/time",
        "extraction end",
        "extraction end date/time",
    ],
    "extraction_type": ["extraction type", "extraction method"],
    "device": ["device", "model", "device model", "device name"],
    "os": ["os version", "os", "operating system"],
    "tool": ["tool", "tool name"],
    "tool_version": [
        "tool version",
        "ufed physical analyzer version",
        "physical analyzer version",
        "ufed reader version",
        "reader version",
        "report version",
        "version",
    ],
    "time_zone": ["report time zone", "time zone", "timezone", "time zone settings"],
    "device_time_zone": ["device time zone"],
}


def summary_entry(pairs: list[tuple[str, str, str]], key: str) -> tuple[str, str] | None:
    """(value, locator) of the first summary pair whose key matches, in alias order."""
    for alias in SUMMARY_KEYS[key]:
        for k, v, loc in pairs:
            if norm(k).rstrip(":") == alias and v.strip():
                return v.strip(), loc
    return None


def summary_field(pairs: list[tuple[str, str, str]], key: str) -> str | None:
    e = summary_entry(pairs, key)
    return e[0] if e else None


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

    def empty_in_known_columns(self) -> bool:
        """True when every mapped column and attachment column is blank (a footer such as
        'Total: 45', or a value only in a column Mabillon does not read)."""
        cols = [*self.fields.values(), *self.attachment_cols]
        return all(text(self.cells[i]) is None for i in cols if i < len(self.cells))


# ---------------------------------------------------------------- coverage


def is_forwarded_label(label: str | None) -> bool:
    """A message label cell or value that marks the message as forwarded ("Forwarded",
    "Forwarded, Starred")."""
    return bool(label) and bool(FORWARDED_LABEL_RE.search(label or ""))


def _listed(d: dict[str, list[str]], key: str, value: str) -> None:
    """Append to a capped list of locators in a coverage payload."""
    items = d.setdefault(key, [])
    if len(items) < MAX_LISTED:
        items.append(value)


# Fields whose absence from a table the expert must see: without them the records are thin.
KEY_FIELDS: dict[RecordKind, list[str]] = {
    RecordKind.CHATS: ["time", "body", "from"],
    RecordKind.SMS: ["time", "body"],
    RecordKind.CALLS: ["time"],
    RecordKind.CONTACTS: ["name"],
    RecordKind.ACCOUNTS: [],
}


def _has_time(hm: HeaderMap) -> bool:
    return bool({"ts", "ts_time"} & hm.fields.keys())


def missing_key_fields(kind: RecordKind, hm: HeaderMap) -> list[str]:
    f = hm.fields
    have = {
        "time": _has_time(hm),
        "body": "body" in f,
        "from": "from" in f,
        "name": "name" in f,
    }
    return [k for k in KEY_FIELDS[kind] if not have[k]]


@dataclass
class TableCoverage:
    name: str
    kind: str | None
    header_locator: str | None = None
    rows_read: int = 0
    rows_imported: int = 0
    rows_skipped: Counter[str] = field(default_factory=Counter)
    skipped_locators: dict[str, list[str]] = field(default_factory=dict)
    unknown_columns: list[str] = field(default_factory=list)
    duplicate_columns: list[dict[str, str]] = field(default_factory=list)
    absent_fields: list[str] = field(default_factory=list)
    missing_key_fields: list[str] = field(default_factory=list)
    header_offsets: dict[str, int] = field(default_factory=dict)  # column -> offset applied
    header_zone_names: dict[str, str] = field(default_factory=dict)  # column -> zone, not applied
    date_order: str | None = None
    date_order_basis: str | None = None  # 'this table', 'other tables in the report', 'none'
    time_problems: Counter[str] = field(default_factory=Counter)
    time_problem_locators: dict[str, list[str]] = field(default_factory=dict)
    app_from_title: str | None = None
    merged_cells_filled: int = 0
    merged_columns_not_filled: list[str] = field(default_factory=list)
    header_notes: list[str] = field(default_factory=list)
    flagged_locators: dict[str, list[str]] = field(default_factory=dict)
    flag_counts: Counter[str] = field(default_factory=Counter)  # flagged_locators is capped
    numbered_copies: set[str] = field(default_factory=set)  # every copy row's locator, uncapped

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "header_locator": self.header_locator,
            "rows_read": self.rows_read,
            "rows_imported": self.rows_imported,
            "rows_skipped": dict(self.rows_skipped),
            "skipped_locators": self.skipped_locators,
            "unknown_columns": self.unknown_columns,
            "duplicate_columns": self.duplicate_columns,
            "absent_fields": self.absent_fields,
            "missing_key_fields": self.missing_key_fields,
            "header_offsets": self.header_offsets,
            "header_zone_names": self.header_zone_names,
            "date_order": self.date_order,
            "date_order_basis": self.date_order_basis,
            "time_problems": dict(self.time_problems),
            "time_problem_locators": self.time_problem_locators,
            "app_from_title": self.app_from_title,
            "merged_cells_filled": self.merged_cells_filled,
            "merged_columns_not_filled": self.merged_columns_not_filled,
            "header_notes": self.header_notes,
            "flagged_locators": self.flagged_locators,
            **({"flag_counts": dict(self.flag_counts)} if self.flag_counts else {}),
        }


@dataclass
class Coverage:
    tables: list[TableCoverage] = field(default_factory=list)
    not_imported: list[dict[str, object]] = field(default_factory=list)
    counters: Counter[str] = field(default_factory=Counter)
    unmapped_direction_values: Counter[str] = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)
    summary_found: bool = True
    hidden_sheets: list[str] = field(default_factory=list)
    multi_name_accounts: list[str] = field(default_factory=list)
    # message ids by reason, in full (core/ingest/forwarded.py reads them downstream)
    forwarded_records: dict[str, list[str]] = field(default_factory=dict)
    # message ids the tool numbered as a copy of another row, in full (count check reads them)
    numbered_copy_records: list[str] = field(default_factory=list)
    # forwarded message id -> its original author as the source wrote it, when it says
    forwarded_from: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------- writer


@dataclass(frozen=True)
class ReportInput:
    """What a reader hands to `write_report`."""

    summary: list[tuple[str, str, str]]  # (key, value, locator)
    tables: list[RawTable]
    coverage: Coverage


def _slug(app: str) -> str:
    """App as it appears in ids: the report's spelling, whitespace-normalised."""
    return re.sub(r"\s+", " ", app).strip()


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
        """Thread for (app, chat key). Its locator and title come from the first row seen."""
        tid = f"thr:{self.src}:{_slug(app)}:{key}"
        if tid not in self.threads:
            self.threads[tid] = (locator, app, title)
        return tid

    # flush ---------------------------------------------------------------

    def flush(self) -> None:
        multi = [a for a, names in self.account_names.items() if len(names) > 1]
        if multi:
            self.cov.counters["accounts_with_multiple_display_names"] = len(multi)
            self.cov.multi_name_accounts = sorted(multi)[:MAX_LISTED]
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
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
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


@dataclass
class TimeContext:
    """What one table's times are read with."""

    order: DateOrder
    report_offset: int | None
    header_offsets: dict[str, int]
    tc: TableCoverage


def _row_time(row: Row, tctx: TimeContext, cov: Coverage) -> Timestamp:
    if row.has("ts_time") and not row.has("ts") and not row.has("ts_date"):
        used, value = "ts_time", row.get("ts_time")  # full value in one column
    elif row.has("ts_date") and row.has("ts_time") and _holds_date_and_time(row.get("ts_time")):
        # Physical Analyzer's per-category Excel export writes 'Date' as an Excel serial number
        # and 'Time' as the full value ('2/14/2020 1:09:03 PM(UTC+0)'). The full value is read;
        # the Date column is only a check on it.
        return _time_with_date_check(row, tctx, cov)
    elif row.has("ts_date") and row.has("ts_time"):
        dv = row.get("ts_date")
        d = dv.date().isoformat() if isinstance(dv, datetime) else row.text("ts_date")
        t = row.text("ts_time")
        used = "ts_time" if "ts_time" in tctx.header_offsets else "ts_date"
        value = None if d is None and t is None else f"{d or ''} {t or ''}".strip()
    else:
        used, value = "ts", row.get("ts")
    return _counted(parse_time(value, tctx.order, _fallback(used, tctx)), used, row, tctx, cov)


def _fallback(used: str, tctx: TimeContext) -> int | None:
    header_off = tctx.header_offsets.get(used)
    return header_off if header_off is not None else tctx.report_offset


def _holds_date_and_time(cell: Cell) -> bool:
    """A 'Time' cell written as a whole date and time, not a time of day alone."""
    if not isinstance(cell, str):
        return False
    m = _TS_RE.match(_canonical(cell.strip()))
    return m is not None and m.group("H") is not None


# Excel's 1900 date system: serial 1 is 1900-01-01, counted from 1899-12-30 for serials past
# the leap-day bug at 60. A workbook in the 1904 system gives other dates, and so fails the check.
_EXCEL_EPOCH = datetime(1899, 12, 30)


def _date_column_value(cell: Cell, order: DateOrder) -> date | None:
    """The calendar date a 'Date' cell holds: an Excel date cell, an Excel serial number, or a
    date written as text. None when it holds none of these."""
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, int | float) and not isinstance(cell, bool):
        if not 61 <= cell < 2958466:  # 1900-03-01 to 9999-12-31
            return None
        return (_EXCEL_EPOCH + timedelta(days=int(cell))).date()
    if isinstance(cell, str):
        res = parse_time(f"{cell.strip()} 00:00", order, 0)
        return res.ts.utc.date() if res.ts.utc is not None else None
    return None


def _time_with_date_check(row: Row, tctx: TimeContext, cov: Coverage) -> Timestamp:
    """Read the full value in 'Time'. When 'Date' holds a date, it must be the date written in
    'Time' (local, in the value's own offset); when it is another date, or not a date at all,
    no UTC time is set, because Mabillon cannot tell which column is right."""
    res = parse_time(row.get("ts_time"), tctx.order, _fallback("ts_time", tctx))
    dv = row.get("ts_date")
    if res.ts.utc is not None and text(dv) is not None:
        local = res.ts.utc + timedelta(minutes=res.ts.offset_min or 0)
        if _date_column_value(dv, tctx.order) != local.date():
            raw = f"{text(dv)} {res.ts.raw}"
            res = _no_utc(raw, TimeProblem.DATE_COLUMN_DISAGREES)
    return _counted(res, "ts_time", row, tctx, cov)


def _counted(res: TimeResult, used: str, row: Row, tctx: TimeContext, cov: Coverage) -> Timestamp:
    header_off = tctx.header_offsets.get(used)
    if res.problem is not None:
        tctx.tc.time_problems[res.problem.value] += 1
        _listed(tctx.tc.time_problem_locators, res.problem.value, row.locator)
    if res.unparsed:
        cov.counters["times_unparsed"] += 1
    elif res.problem is TimeProblem.NO_OFFSET:
        cov.counters["times_without_offset"] += 1
    if res.offset_from_fallback:
        key = "column_header" if header_off is not None else "report_settings"
        cov.counters[f"times_offset_from_{key}"] += 1
    return res.ts


def _raw_time_values(rows: list[Row]) -> list[str]:
    out = []
    for r in rows:
        if r.has("ts_date"):
            v = r.text("ts_date")
            if v:
                out.append(f"{v} 00:00")
        for f in ("ts", "ts_time"):
            v = r.get(f)
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
    w: _Writer, kind: RecordKind, rows: list[Row], tctx: TimeContext, app_hint: str | None
) -> None:
    cov = w.cov
    tc = tctx.tc
    for r in rows:
        app = _app(r, app_hint or ("SMS" if kind is RecordKind.SMS else "unknown"))
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

        title = r.text("chat_name") or r.text("participants")
        tid = w.thread(app, chat_key, r.locator, title)
        ts = _row_time(r, tctx, cov)
        mid = f"msg:{w.src}:{r.locator}"
        if r.locator in tc.numbered_copies:
            cov.numbered_copy_records.append(mid)
        if is_forwarded_label(r.text("label")):
            cov.forwarded_records.setdefault("forwarded", []).append(mid)
            cov.counters["messages_marked_forwarded"] += 1
            tc.flag_counts["forwarded"] += 1
            _listed(tc.flagged_locators, "forwarded", r.locator)
        body = body_text(r.get("body"))
        if len(body) >= EXCEL_CELL_LIMIT:
            cov.counters["bodies_at_excel_cell_limit"] += 1
            _listed(tc.flagged_locators, "body_at_excel_cell_limit", r.locator)
        w.messages.append(
            (
                mid,
                w.src,
                r.locator,
                tid,
                sender_id,
                direction.value,
                *_ts_cols(ts),
                body,
                _db_bool(_deleted(r, cov)),
                1 if r.text("tag") else None,  # examiner tag; blank means not stated
            )
        )
        w.recipients.extend((mid, a) for a in dict.fromkeys(recip_ids))
        n_before = len(w.attachments)
        n = 0
        for col in r.attachment_cols:
            name = text(r.cells[col]) if col < len(r.cells) else None
            for fname in (name or "").splitlines():
                if fname.strip():
                    n += 1
                    w.attachments.append(
                        (f"att:{w.src}:{r.locator}:{n}", w.src, r.locator, mid, fname.strip())
                    )
        if not body.strip() and len(w.attachments) == n_before:
            cov.counters["messages_without_body_or_attachment"] += 1
            _listed(tc.flagged_locators, "no_body_or_attachment", r.locator)


def _calls(w: _Writer, rows: list[Row], tctx: TimeContext, app_hint: str | None) -> None:
    cov = w.cov
    for r in rows:
        app = _app(r, app_hint or "unknown")
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
        ts = _row_time(r, tctx, cov)
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


def _accounts(w: _Writer, rows: list[Row], tc: TableCoverage, app_hint: str | None) -> None:
    for r in rows:
        app = _app(r, app_hint or "unknown")
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


def default_source_id(sf: SourceFile) -> str:
    """The file stem (`item1.xlsx` -> `item1`) when it is a plain token, else `src_<sha12>`."""
    stem = sf.path.stem
    if re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", stem):
        return stem
    return f"src_{sf.sha256[:12]}"


def _fill_merges(table: RawTable, hidx: int, hm: HeaderMap, tc: TableCoverage) -> None:
    """Copy a merged cell's value down its range, for columns that label a group of rows (chat,
    sender, app). Other merged columns are left blank and named in coverage."""
    by_col = {i: f for f, i in hm.fields.items()}
    headers = table.rows[hidx][1]
    for mg in table.merges:
        if mg.last_row <= hidx or mg.last_row == mg.first_row:
            continue  # header rows, or a merge across columns only
        top = table.rows[mg.first_row][1]
        value = top[mg.first_col] if mg.first_col < len(top) else None
        f = by_col.get(mg.first_col)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue  # an empty merged cell: there is nothing to copy or lose
        if f in FILLABLE_FIELDS and mg.first_row >= hidx + 1:
            for r in range(mg.first_row + 1, mg.last_row + 1):
                cells = table.rows[r][1]
                if mg.first_col < len(cells) and cells[mg.first_col] is None:
                    cells[mg.first_col] = value
                    tc.merged_cells_filled += 1
        elif mg.first_row >= hidx + 1:
            name = str(headers[mg.first_col]).strip() if mg.first_col < len(headers) else "?"
            if name not in tc.merged_columns_not_filled:
                tc.merged_columns_not_filled.append(name)


def _header_like(cells: list[Cell]) -> bool:
    """Two or more filled cells, every one a known column name."""
    vals = [c for c in cells if text(c) is not None]
    return len(vals) >= 2 and all(isinstance(c, str) and known_header(c) for c in vals)


# Physical Analyzer numbers a record it lists again '3(1)' after '3': in a rooted Android
# extraction the same database is read twice, at its own path and under /sbin/.magisk/mirror/.
NUMBERED_COPIES_KEY = "numbered_copy_records"
_COPY_NUMBER_RE = re.compile(r"^(\d+)\s*\(\d+\)$")


def _flag_numbered_copies(rows: list[Row], header_norms: list[str], tc: TableCoverage) -> None:
    """List rows numbered as a further copy of another row in the table. Each stays a record
    of its own: whether two rows are one message is the expert's call, never Mabillon's."""
    col = next((i for i, h in enumerate(header_norms) if h == "#"), None)
    if col is None:
        return
    numbers = {text(r.cells[col]) for r in rows if col < len(r.cells)}
    for r in rows:
        m = _COPY_NUMBER_RE.match(text(r.cells[col]) or "") if col < len(r.cells) else None
        if m and m.group(1) in numbers:
            tc.flag_counts["numbered_as_copy"] += 1
            tc.numbered_copies.add(r.locator)
            _listed(tc.flagged_locators, "numbered_as_copy", r.locator)


def _table_rows(
    table: RawTable, cov: Coverage
) -> tuple[RecordKind, list[Row], DateOrder, HeaderMap, TableCoverage, RawTable] | None:
    tc = TableCoverage(name=table.name, kind=table.kind_hint)
    found = find_header(table)
    if found is None:
        cov.not_imported.append(
            {
                "name": table.name,
                "reason": header_problem(table),
                "rows": sum(1 for _l, c in table.rows if any(text(x) is not None for x in c)),
                "columns": header_preview(table),
            }
        )
        return None
    rkind, hidx = found
    tc.kind = rkind.value
    tc.app_from_title = table.app_hint
    tc.header_notes = list(table.header_notes)
    hloc, headers = table.rows[hidx]
    tc.header_locator = hloc
    hm = map_headers(rkind, headers)
    tc.unknown_columns = hm.unknown
    tc.duplicate_columns = [
        {"column": col, "field": f, "used": str(headers[hm.fields[f]]).strip()}
        for col, f in hm.duplicates
    ]
    tc.header_offsets = {str(headers[hm.fields[f]]).strip(): o for f, o in hm.offsets.items()}
    tc.header_zone_names = {str(headers[hm.fields[f]]).strip(): q for f, q in hm.qualifiers.items()}
    expected = {"deleted", "app"} | (
        {"ts"} if rkind not in (RecordKind.CONTACTS, RecordKind.ACCOUNTS) else set()
    )
    has_time = _has_time(hm)
    tc.absent_fields = sorted(
        f
        for f in expected
        if f not in hm.fields
        and not (f == "ts" and has_time)
        and not (f == "app" and table.app_hint)
    )
    tc.missing_key_fields = missing_key_fields(rkind, hm)
    _fill_merges(table, hidx, hm, tc)
    rows: list[Row] = []
    header_norms = [norm(h) for h in headers]
    h0 = next((i for i, h in enumerate(headers) if text(h) is not None), 0)
    for loc, cells in table.rows[hidx + 1 :]:
        tc.rows_read += 1
        row = Row(loc, cells, hm.fields, hm.attachments, table.reflowed)
        if row.empty():
            tc.rows_skipped["empty"] += 1
            continue
        first = cells[h0] if h0 < len(cells) else None
        if (
            isinstance(first, str)
            and norm(first) == header_norms[h0]
            and [norm(c) for c in cells] == header_norms
        ):
            tc.rows_skipped["repeated_header"] += 1
            continue
        if _header_like(cells):
            # A second header row Mabillon could not join (a group name over its columns).
            tc.rows_skipped["header_like_row"] += 1
            _listed(tc.skipped_locators, "header_like_row", loc)
            continue
        if row.empty_in_known_columns():
            # Not a record Mabillon can read: a footer ('Total: 45'), a sub-heading, or values only
            # in columns it does not know. Listed so the expert can open the row.
            tc.rows_skipped["no_values_in_known_columns"] += 1
            _listed(tc.skipped_locators, "no_values_in_known_columns", loc)
            continue
        rows.append(row)
    tc.rows_imported = len(rows)
    _flag_numbered_copies(rows, header_norms, tc)
    order = DateOrder()
    for v in _raw_time_values(rows):
        order.observe(v)
    cov.tables.append(tc)
    return rkind, rows, order, hm, tc, table


def write_report(
    conn: sqlite3.Connection,
    sf: SourceFile,
    kind: SourceKind,
    importer_name: str,
    source_id: str | None,
    imported_at: datetime,
    report: ReportInput,
    date_order: str | None = None,
) -> Source:
    """Write a parsed report as canonical rows, one source_coverage row and one coverage entry
    in the audit log, in one transaction.

    `date_order` ('mdy' or 'dmy') is the day/month order a person stated at import, from the
    report's date format. Without it, the order comes only from values that decide it."""
    if date_order not in (None, "mdy", "dmy"):
        raise ValueError(f"date_order must be 'mdy' or 'dmy', not {date_order!r}")
    src = source_id or default_source_id(sf)
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

    # Parse tables into rows grouped by kind. Day/month order is decided per table from the
    # values that disambiguate; a table with none borrows the order the rest of the report
    # shows (one report, one date format). With no deciding value anywhere, ambiguous dates
    # stay unread.
    parsed = [t for t in (_table_rows(table, cov) for table in report.tables) if t is not None]
    report_order = DateOrder()
    for p in parsed:
        report_order = report_order.merged(p[2])
    grouped: dict[RecordKind, list[tuple[list[Row], TimeContext, str | None]]] = defaultdict(list)
    for rkind, rows, order, hm, tc, table in parsed:
        effective = order
        if rkind not in (RecordKind.CONTACTS, RecordKind.ACCOUNTS) and "time" not in (
            tc.missing_key_fields
        ):
            if date_order is not None:
                effective = DateOrder(int(date_order == "dmy"), int(date_order == "mdy"))
                tc.date_order_basis = "stated at import"
                if order.label not in ("undecided", date_order):
                    # Some values can only be read the other way; each is still read as written.
                    cov.counters["values_contradicting_stated_date_order"] += (
                        order.mdy_votes if date_order == "dmy" else order.dmy_votes
                    )
            elif order.label != "undecided":
                tc.date_order_basis = "this table"
            elif report_order.label in ("dmy", "mdy"):
                effective = report_order
                tc.date_order_basis = "other tables in the report"
            else:
                tc.date_order_basis = "none"
            tc.date_order = effective.label
        tctx = TimeContext(effective, rep_off, hm.offsets, tc)
        grouped[rkind].append((rows, tctx, table.app_hint))

    tool_version = summary_field(summary, "tool_version")
    extracted_raw = summary_field(summary, "extraction_start")
    extracted_utc = None
    if extracted_raw:
        order = report_order if report_order.label in ("dmy", "mdy") else DateOrder()
        if date_order is not None:
            order = DateOrder(int(date_order == "dmy"), int(date_order == "mdy"))
        extracted_utc = parse_time(extracted_raw, order, rep_off).ts.utc
        if extracted_utc is None:
            cov.counters["extraction_time_unread"] += 1
    source = Source(
        id=src,
        kind=kind,
        fidelity=Fidelity.CURATED_REPORT,
        extraction_type=extraction_type(summary_field(summary, "extraction_type")),
        file_name=sf.path.name,
        sha256=sf.sha256,
        tool_name=summary_field(summary, "tool")
        or "Cellebrite" + (" Physical Analyzer" if tool_version else ""),
        tool_version=tool_version,
        extracted_at_utc=extracted_utc,
        imported_at_utc=imported_at,
    )
    dev = f"dev:{src}"

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
                (summary_entry(summary, "device") or ("", "Summary"))[1],
                summary_field(summary, "device") or f"Device in {sf.path.name}",
                summary_field(summary, "device"),
                summary_field(summary, "os"),
                # The phone's own zone only. The report's time zone is the examiner's display
                # setting (kept in the coverage notes), never the phone's.
                summary_field(summary, "device_time_zone"),
            ),
        )
        for rkind in KIND_ORDER:
            for rows, tctx, app_hint in grouped.get(rkind, []):
                if rkind is RecordKind.ACCOUNTS:
                    _accounts(w, rows, tctx.tc, app_hint)
                elif rkind is RecordKind.CONTACTS:
                    _contacts(w, rows)
                elif rkind is RecordKind.CALLS:
                    _calls(w, rows, tctx, app_hint)
                else:
                    _messages(w, rkind, rows, tctx, app_hint)
        w.flush()
        forwarded.mark(conn, cov.forwarded_records, cov.forwarded_from)
        payload = coverage_payload(
            source, importer_name, tz_raw, rep_off, cov, sorted(grouped), report_order, date_order
        )
        check = tested.at_import(importer_name, source.id, source.file_name, source.tool_version)
        payload["format_check"] = check.payload()
        conn.execute(
            "INSERT INTO source_coverage (source_id, importer, importer_version, payload_json)"
            " VALUES (?, ?, ?, ?)",
            (source.id, importer_name, IMPORTER_VERSION, json.dumps(payload, sort_keys=True)),
        )
        audit_log.append(conn, imported_at, "system", "import", payload)
        audit_log.append(conn, imported_at, "system", tested.ACTION, check.payload())
    return source


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def coverage_payload(
    source: Source,
    importer: str,
    tz_raw: str | None,
    rep_off: int | None,
    cov: Coverage,
    kinds_read: list[RecordKind] | None = None,
    report_order: DateOrder | None = None,
    stated_date_order: str | None = None,
) -> dict[str, object]:
    """The coverage record for one import. Shape: docs/ingest/coverage.md."""
    read = set(kinds_read or [])
    payload: dict[str, object] = {
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
        "report_date_order": report_order.label if report_order else None,
        "date_order_stated_at_import": stated_date_order,
        "summary_found": cov.summary_found,
        "hidden_sheets": cov.hidden_sheets,
        "accounts_with_multiple_display_names": cov.multi_name_accounts,
        "categories_read": [k.value for k in KIND_ORDER if k in read],
        "categories_not_found": [k.value for k in KIND_ORDER if k not in read],
        "tables": [t.as_dict() for t in cov.tables],
        "not_imported": cov.not_imported,
        "counts": dict(sorted(cov.counters.items())),
        "unmapped_direction_values": dict(cov.unmapped_direction_values),
        "notes": cov.notes,
    }
    if cov.forwarded_records:
        payload[forwarded.PAYLOAD_KEY] = {
            k: list(dict.fromkeys(v)) for k, v in sorted(cov.forwarded_records.items())
        }
    if cov.numbered_copy_records:
        payload[NUMBERED_COPIES_KEY] = list(dict.fromkeys(cov.numbered_copy_records))
    return payload
