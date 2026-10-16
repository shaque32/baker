"""Cellebrite UFDR package importer. UNVERIFIED format support.

A UFDR ("Universal Forensic Data Reader" package, opened with Cellebrite Reader) is a zip file
holding `report.xml`, the decoded data of one extraction, plus the extracted files it points to.
This importer was built from Cellebrite's public descriptions of that structure and tested on
synthetic packages only (eval/synthetic/ufdr.py). Until a real UFDR has been compared with
Cellebrite Reader, every import says so in its coverage record, on the case screen and in the
report's limitations. Layout assumptions: docs/ingest/ufdr.md.

What it shares with the Excel and PDF importers (core/ingest/cellebrite_common.py): the record
mapping for messages and calls (threads, senders, recipients, direction, owner accounts), time
parsing (no guessed day/month order, no guessed zone), the deleted-flag reading, the stable id
scheme and the coverage record. What differs: records come from XML models instead of table rows,
parties come with their own identifier, name, owner flag and role instead of a text cell, and
the package is streamed, never loaded into memory whole.

Streaming: the package is hashed in chunks, report.xml is read twice in chunks through expat
(first the device details, the phone's own accounts and the date order; then the records), and
rows go to the database in batches inside one transaction. Only one chat's messages and the
account and thread lists are held in memory at a time.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO
from xml.parsers import expat

from core.contracts import (
    ExtractionType,
    Fidelity,
    Source,
    SourceKind,
)
from core.encryption import open_input
from core.ingest import forwarded
from core.ingest.cellebrite_common import (
    MAX_LISTED,
    Cell,
    Coverage,
    DateOrder,
    Party,
    RecordKind,
    Row,
    TableCoverage,
    TimeContext,
    _calls,
    _listed,
    _messages,
    _slug,
    _Writer,
    coverage_payload,
    is_forwarded_label,
    norm,
    parse_time,
)
from core.review import audit_log

IMPORTER_NAME = "ufdr"
IMPORTER_VERSION = "0.1.1"
# Becomes "verified" only after a real UFDR has been checked against Cellebrite Reader
# (docs/ingest/ufdr.md, "Before calling it verified"). Every import records it.
FORMAT_SUPPORT = "unverified"
KNOWN_NAMESPACE = "http://pa.cellebrite.com/report/2.0"
CHUNK = 1 << 20
BATCH = 5000  # canonical rows written per batch
MAX_FIELD_NAMES = 30  # field names listed per record type in coverage

FIDELITY_REASON = (
    "UFDR package. A UFDR may hold a whole extraction or only what the examiner selected, and "
    "Baker's UFDR reader is not yet verified against a real package, so its coverage is "
    "treated as not known: it cannot support a claim that something is absent from the device."
)

# ---------------------------------------------------------------- model types

TABLE_KIND: dict[str, RecordKind] = {
    "Chat": RecordKind.CHATS,
    "InstantMessage": RecordKind.CHATS,
    "SMS": RecordKind.SMS,
    "MMS": RecordKind.SMS,
    "Call": RecordKind.CALLS,
    "Contact": RecordKind.CONTACTS,
    "UserAccount": RecordKind.ACCOUNTS,
}
MESSAGE_TYPES = {"InstantMessage", "Message", "SMS", "MMS"}  # message models inside a chat
# Model types Baker knows and deliberately does not import (yet). Listed in coverage as
# categories not imported; any other type is listed as not recognised.
NOT_IMPORTED_TYPES = {
    "Location",
    "Email",
    "WebBookmark",
    "VisitedPage",
    "SearchedItem",
    "InstalledApplication",
    "ApplicationUsage",
    "CalendarEntry",
    "Note",
    "CellTower",
    "WirelessNetwork",
    "Cookie",
    "Password",
    "SocialMediaActivity",
    "Voicemail",
    "Recording",
    "DeviceEvent",
    "Notification",
    "FileDownload",
    "Autofill",
    "DeviceConnectivity",
    "Journey",
    "PoweringEvent",
    "Dictionary",
    "UserWord",
    "Timeline",
}

# Field names, compared case-insensitively. The first name present wins.
TS_FIELDS = ("timestamp", "datetime")
CALL_TS_FIELDS = (*TS_FIELDS, "starttime")
BODY_FIELDS = ("body", "text", "message", "content")
CHAT_ID_FIELDS = ("id", "chatid", "threadid", "identifier")
CHAT_NAME_FIELDS = ("name", "title")
ATT_NAME_FIELDS = ("filename", "name", "file name")
ATT_MIME_FIELDS = ("contenttype", "mimetype", "content type")
ATT_PATH_FIELDS = ("attachment_extracted_path", "localpath", "local path", "extractedpath", "path")
ATT_HASH_FIELDS = ("sha256", "sha-256", "hash")
# Fields each type reads (beyond those above) or knowingly ignores; any other field name is
# listed in coverage as a field Baker does not read.
_KNOWN = {
    "Chat": {
        *CHAT_ID_FIELDS, *CHAT_NAME_FIELDS, "source", "participants", "messages",
        "starttime", "lastactivity", "account", "chattype", "photos", "isrelated",
    },
    "message": {
        *TS_FIELDS, *BODY_FIELDS, "source", "from", "to", "parties", "participants", "status",
        "direction", "folder", "attachments", "attachment", "dateread", "datedelivered",
        "label", "position", "identifier", "smsc", "messagetype", "type", "subject",
    },
    "Call": {
        *CALL_TS_FIELDS, "source", "parties", "from", "to", "duration", "direction", "type",
        "status", "videocall", "account", "countrycode", "networkcode", "networkname",
    },
    "Contact": {"name", "source", "entries", "account", "group", "notes", "photos", "type"},
    "UserAccount": {"name", "username", "source", "entries", "servicetype", "serviceidentifier"},
}  # fmt: skip
# 'Subject' and 'Type' are knowingly not read: an MMS subject is not the message text, and a
# message 'Type' names its content kind (text, picture), not its direction.

# Metadata items (anywhere outside decodedData), keyed by their name with everything but
# letters and digits removed, lowercased. First alias present wins.
META_KEYS: dict[str, tuple[str, ...]] = {
    "extraction_start": (
        "deviceinfoextractionstartdatetime",
        "extractionstartdatetime",
        "extractionstartdate",
        "extractiondate",
        "deviceinfoextractionenddatetime",
        "extractionenddatetime",
    ),
    "device": (
        "deviceinfoselecteddevicename",
        "deviceinfodetectedmodel",
        "deviceinfoselectedmodel",
        "devicename",
        "devicemodel",
        "model",
    ),
    "manufacturer": ("deviceinfoselectedmanufacturer", "deviceinfodetectedmanufacturer"),
    "os": ("deviceinfoosversion", "deviceinfodetectedosversion", "osversion", "os"),
    "tool_version": (
        "ufedphysicalanalyzerversion",
        "physicalanalyzerversion",
        "deviceinfopaversion",
        "paversion",
    ),
    "device_time_zone": ("deviceinfotimezone", "devicetimezone", "timezone"),
}

_TIMESPAN_RE = re.compile(r"^(?:(\d+)\.)?(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?$")
_TRUE = {"true", "1", "yes"}
PICTURE_TYPE_RE = re.compile(r"picture|photo", re.IGNORECASE)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ---------------------------------------------------------------- XML elements and models


@dataclass(slots=True)
class _El:
    tag: str
    attrs: dict[str, str]
    children: list[_El] = field(default_factory=list)
    text: list[str] | None = None  # collected for <value> and <item> only
    locator: str = ""
    pending: list[tuple[str, _Model]] | None = None  # a chat's messages, read as they close
    seen: dict[str, int] | None = None  # messages read so far per field of the chat

    def joined(self) -> str:
        return "".join(self.text or ())


@dataclass
class _Model:
    """One decoded model: its attributes, simple fields (first value), and nested models."""

    type: str
    attrs: dict[str, str]
    fields: dict[str, str] = field(default_factory=dict)  # lowercased name -> first value
    field_names: list[str] = field(default_factory=list)  # names as written, in order
    duplicates: list[str] = field(default_factory=list)  # a field name given twice
    one: dict[str, _Model] = field(default_factory=dict)  # modelField
    many: dict[str, list[_Model]] = field(default_factory=dict)  # multiModelField
    multi_values: dict[str, list[str]] = field(default_factory=dict)  # multiField

    def raw(self, *names: str) -> str | None:
        """The first named field's value exactly as written; None when absent."""
        for n in names:
            if n in self.fields:
                return self.fields[n]
        return None

    def text(self, *names: str) -> str | None:
        """The first named field with a non-blank value, stripped."""
        for n in names:
            v = self.fields.get(n)
            if v is not None and v.strip():
                return v.strip()
        return None

    def models(self, *names: str) -> list[_Model]:
        out: list[_Model] = []
        for n in names:
            out += self.many.get(n, [])
            if n in self.one:
                out.append(self.one[n])
        return out


def _model(el: _El) -> _Model:
    m = _Model(type=el.attrs.get("type", ""), attrs=el.attrs)
    for ch in el.children:
        name = ch.attrs.get("name", "")
        key = name.lower()
        if ch.tag == "field":
            m.field_names.append(name)
            if key in m.fields:
                m.duplicates.append(name)
                continue
            values = [v for v in ch.children if v.tag == "value"]
            if values:
                m.fields[key] = values[0].joined()
        elif ch.tag == "multiField":
            m.field_names.append(name)
            m.multi_values[key] = [v.joined() for v in ch.children if v.tag == "value"]
        elif ch.tag == "modelField":
            m.field_names.append(name)
            sub = [c for c in ch.children if c.tag == "model"]
            if sub:
                m.one[key] = _model(sub[0])
        elif ch.tag == "multiModelField":
            m.field_names.append(name)
            m.many[key] = [_model(c) for c in ch.children if c.tag == "model"]
        elif name:
            # Any other named child (a nodeField, say) is not read; naming it puts it among the
            # fields Baker does not read in coverage instead of passing it over in silence.
            m.field_names.append(name)
    return m


# ---------------------------------------------------------------- streaming reader


class _Reader:
    """Feeds report.xml through expat and hands over each top-level decoded model as it closes.

    `build(type)` says which top-level models to build; `on_model(el)` receives each built one.
    With `stream_chats`, each message inside a Chat's Messages field is turned into a _Model
    when it closes and kept on the chat (`el.pending`), so the chat's XML is never held whole.
    Without building, the reader still counts models per type, collects metadata items and
    extraction details, and observes record times for the date order.
    """

    def __init__(
        self,
        build: Callable[[str], bool],
        on_model: Callable[[_El], None],
        stream_chats: bool,
    ) -> None:
        self.build = build
        self.on_model = on_model
        self.stream_chats = stream_chats
        self.path: list[str] = []
        self.attr_stack: list[dict[str, str]] = []
        self.building: list[_El] = []
        self.namespace: str | None = None
        self.root: str | None = None
        self.project_attrs: dict[str, str] = {}
        self.counts: Counter[str] = Counter()
        self.extractions: list[dict[str, str]] = []
        self.metadata: list[tuple[str, str, str, str]] = []  # (section, name, value, locator)
        self.tagged_files = 0
        # taggedFiles file id -> its "Local Path" in the package; an Attachment may name its
        # file only through file_id (seen in a third-party sample, docs/ingest/ufdr.md)
        self.tagged_paths: dict[str, str] = {}
        self.tagged_conflicts: set[str] = set()  # ids listed twice with different paths
        self._tagged: tuple[str, list[str]] | None = None
        self._tagged_id: str | None = None
        self.votes: dict[str, DateOrder] = {}
        self._top_type: str | None = None
        self._ts_text: list[str] | None = None
        self._item: tuple[str, str, list[str]] | None = None

    # expat handlers ------------------------------------------------------

    def start(self, name: str, attrs: dict[str, str]) -> None:
        ns, _, local = name.rpartition(" ")
        parent = self.path[-1] if self.path else None
        if not self.path:
            self.root, self.namespace, self.project_attrs = local, ns or None, dict(attrs)
        self.path.append(local)
        self.attr_stack.append(attrs)
        if self.building:
            el = _El(local, attrs)
            if local == "value":
                el.text = []
            self.building[-1].children.append(el)
            self.building.append(el)
            return
        depth = len(self.path)
        if local == "model" and parent == "modelType" and depth >= 3:
            if self.path[-3] != "decodedData":
                return
            mtype = attrs.get("type") or self.attr_stack[-2].get("type", "")
            self.counts[mtype] += 1
            self._top_type = mtype
            if self.build(mtype):
                el = _El(local, attrs, locator=f"{mtype}[{self.counts[mtype]}]")
                if self.stream_chats and mtype == "Chat":
                    el.pending, el.seen = [], {}
                self.building.append(el)
            return
        if local == "extractionInfo":
            self.extractions.append(dict(attrs))
        elif local == "file" and parent == "taggedFiles":
            self.tagged_files += 1
            self._tagged_id = attrs.get("id") or None
        elif local == "item" and "taggedFiles" in self.path and "decodedData" not in self.path:
            if self._tagged_id and _key(attrs.get("name", "")) == "localpath":
                self._tagged = (self._tagged_id, [])
        elif local == "item" and "decodedData" not in self.path and "taggedFiles" not in self.path:
            section = next(
                (a.get("section", "") for a in reversed(self.attr_stack) if "section" in a), ""
            )
            self._item = (section, attrs.get("name", ""), [])
        elif local == "value" and self._top_type in TABLE_KIND and parent == "field":
            if self.attr_stack[-2].get("name", "").lower() in CALL_TS_FIELDS:
                self._ts_text = []

    def end(self, name: str) -> None:
        local = self.path.pop()
        self.attr_stack.pop()
        if self.building:
            el = self.building.pop()
            if not self.building:
                self.on_model(el)
                self._top_type = None
            elif (
                el.tag == "model"
                and len(self.building) == 2
                and (pending := self.building[0].pending) is not None
                and (seen := self.building[0].seen) is not None
                and self.building[-1].tag == "multiModelField"
                and (
                    self.building[-1].attrs.get("name", "").lower() == "messages"
                    or el.attrs.get("type") in MESSAGE_TYPES
                )
            ):
                # A message of a chat, under 'Messages' or any field holding message models
                # (never left inside the chat unread).
                fname = self.building[-1].attrs.get("name", "")
                seen[fname] = seen.get(fname, 0) + 1
                self.building[-1].children.pop()  # free the message's XML
                pending.append((f"{self.building[0].locator}/{fname}[{seen[fname]}]", _model(el)))
            return
        if local == "model" and self.path and self.path[-1] == "modelType":
            self._top_type = None
        elif local == "item" and self._tagged is not None:
            fid, parts = self._tagged
            path = "".join(parts).strip()
            if path:
                _add_tagged(self.tagged_paths, self.tagged_conflicts, fid, path)
            self._tagged = None
        elif local == "file" and self._tagged_id is not None:
            self._tagged_id = None
        elif local == "item" and self._item is not None:
            section, nm, parts = self._item
            n = len(self.metadata) + 1
            self.metadata.append((section, nm, "".join(parts), f"metadata[{n}]"))
            self._item = None
        elif local == "value" and self._ts_text is not None:
            table = self._top_type or ""
            self.votes.setdefault(table, DateOrder()).observe("".join(self._ts_text))
            self._ts_text = None

    def chars(self, data: str) -> None:
        if self.building:
            top = self.building[-1]
            if top.text is not None:
                top.text.append(data)
        elif self._item is not None:
            self._item[2].append(data)
        elif self._tagged is not None:
            self._tagged[1].append(data)
        elif self._ts_text is not None:
            self._ts_text.append(data)

    # driving -------------------------------------------------------------

    def read(self, stream: IO[bytes]) -> None:
        p = expat.ParserCreate(namespace_separator=" ")
        p.buffer_text = True
        p.StartElementHandler = self.start
        p.EndElementHandler = self.end
        p.CharacterDataHandler = self.chars
        p.StartDoctypeDeclHandler = _refuse_doctype
        p.EntityDeclHandler = _refuse_entity
        p.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        try:
            while chunk := stream.read(CHUNK):
                p.Parse(chunk, False)
            p.Parse(b"", True)
        except expat.ExpatError as err:
            raise ValueError(f"report.xml is not well-formed XML ({err})") from err
        if self.root != "project":
            raise ValueError(
                f"report.xml has root element {self.root!r}, not 'project'; it is not a "
                "Cellebrite UFDR report Baker can read"
            )


def _refuse_doctype(*_a: object) -> None:
    raise ValueError("report.xml declares a document type; Baker does not read such XML")


def _refuse_entity(*_a: object) -> None:
    raise ValueError("report.xml declares an entity; Baker does not read such XML")


class _HashingReader:
    """A read-only stream that SHA-256 hashes what passes through it."""

    def __init__(self, raw: IO[bytes]) -> None:
        self.raw = raw
        self.h = hashlib.sha256()
        self.size = 0

    def read(self, n: int = -1) -> bytes:
        b = self.raw.read(n)
        self.h.update(b)
        self.size += len(b)
        return b


# ---------------------------------------------------------------- package


def sha256_file(path: Path) -> str:
    """SHA-256 of the package's plain bytes (decrypted as read, in an encrypted case)."""
    h = hashlib.sha256()
    with open_input(path) as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _norm_member(name: str) -> str:
    return re.sub(r"^(?:\./|/)+", "", name.replace("\\", "/"))


def find_report(z: zipfile.ZipFile) -> zipfile.ZipInfo:
    found = [
        i
        for i in z.infolist()
        if not i.is_dir() and PurePosixPath(_norm_member(i.filename)).name.lower() == "report.xml"
    ]
    if not found:
        raise ValueError("the package holds no report.xml, so it is not a UFDR Baker can read")
    depth = min(_norm_member(i.filename).count("/") for i in found)
    top = [i for i in found if _norm_member(i.filename).count("/") == depth]
    if len(top) > 1:
        raise ValueError(
            "the package holds more than one report.xml at the same level ("
            + ", ".join(i.filename for i in top)
            + "); Baker cannot tell which one is the report"
        )
    if top[0].flag_bits & 0x1:
        raise ValueError("report.xml is encrypted in the package; Baker cannot read it")
    return top[0]


class _Package:
    """The zip's member names, to find attachment files, and SHA-256 of members on request."""

    def __init__(self, z: zipfile.ZipFile, report: zipfile.ZipInfo) -> None:
        self.z = z
        self.members: dict[str, zipfile.ZipInfo] = {}
        self.folded: dict[str, zipfile.ZipInfo | None] = {}
        for i in z.infolist():
            if i.is_dir() or i is report:
                continue
            n = _norm_member(i.filename)
            self.members[n] = i
            k = n.lower()
            self.folded[k] = None if k in self.folded else i  # None: two members differ by case
        self.hashed: set[str] = set()

    def lookup(self, path: str) -> zipfile.ZipInfo | None:
        n = _norm_member(path.strip())
        return self.members.get(n) or self.folded.get(n.lower())

    def sha256(self, info: zipfile.ZipInfo) -> str | None:
        if info.flag_bits & 0x1:
            return None  # encrypted
        h = hashlib.sha256()
        with self.z.open(info) as f:
            while chunk := f.read(CHUNK):
                h.update(chunk)
        self.hashed.add(info.filename)
        return h.hexdigest()


# ---------------------------------------------------------------- rows


@dataclass
class _ModelRow(Row):
    """A Row whose parties come from Party models, not from a text cell."""

    party_lists: dict[str, list[Party]] = field(default_factory=dict)

    def parties(self, f: str) -> list[Party]:
        return list(self.party_lists.get(f, []))


def _row(
    locator: str,
    values: dict[str, Cell],
    parties: dict[str, list[Party]],
    attachments: list[str] | None = None,
) -> _ModelRow:
    cells: list[Cell] = [*values.values(), *(attachments or [])]
    return _ModelRow(
        locator,
        cells,
        {k: i for i, k in enumerate(values)},
        list(range(len(values), len(cells))),
        party_lists=parties,
    )


def _party(m: _Model) -> Party | None:
    ident = m.text("identifier")
    name = m.text("name")
    if ident is None and name is None:
        return None
    role = (m.text("role") or "").lower()
    return Party(
        ident,
        name,
        (m.text("isphoneowner") or "").lower() in _TRUE,
        role if role in ("from", "to") else None,
    )


def _parties(models: list[_Model]) -> Iterator[tuple[Party, str]]:
    """Each party with its role as written ('from', 'to', 'cc', ... or '')."""
    for m in models:
        p = _party(m)
        if p is not None:
            yield p, (m.text("role") or "").lower()


def _duration(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    t = raw.strip()
    if re.fullmatch(r"\d+", t):
        return int(t)
    m = _TIMESPAN_RE.match(t)
    if not m:
        return None
    d, h, mi, s = m.groups()
    return int(d or 0) * 86400 + int(h) * 3600 + int(mi) * 60 + int(s)


# ---------------------------------------------------------------- writer


class _StreamWriter(_Writer):
    """The shared writer, flushed in batches: accounts and threads go in when first seen, an
    account later found to be the phone's own is updated, and record lists are cleared after
    each batch."""

    def __init__(self, conn: sqlite3.Connection, source_id: str, device_id: str, cov: Coverage):
        super().__init__(conn, source_id, device_id, cov)
        self.new_accounts: list[str] = []
        self.dirty_accounts: set[str] = set()
        self.written_accounts: set[str] = set()
        self.new_threads: list[str] = []
        self.att_meta: dict[str, tuple[str | None, str | None]] = {}  # att id -> (mime, sha)
        self.totals: Counter[str] = Counter()

    def account(self, app: str, party: Party, locator: str, scope: str) -> str:
        known = len(self.accounts)
        aid = super().account(app, party, locator, scope)
        if len(self.accounts) != known:
            self.new_accounts.append(aid)
        return aid

    def mark_owner(self, aid: str) -> None:
        super().mark_owner(aid)
        if aid in self.written_accounts:
            self.dirty_accounts.add(aid)

    def thread(self, app: str, key: str, locator: str, title: str | None) -> str:
        known = len(self.threads)
        tid = super().thread(app, key, locator, title)
        if len(self.threads) != known:
            self.new_threads.append(tid)
        return tid

    def pending(self) -> int:
        return len(self.messages) + len(self.calls) + len(self.contacts)

    def write_pending(self) -> None:
        c = self.conn
        c.executemany(
            "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier,"
            " display_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(aid, self.src, *self._acct(aid)) for aid in self.new_accounts],
        )
        self.written_accounts.update(self.new_accounts)
        self.new_accounts.clear()
        c.executemany(
            "UPDATE accounts SET device_id = ? WHERE id = ?",
            [(self.dev, aid) for aid in sorted(self.dirty_accounts)],
        )
        self.dirty_accounts.clear()
        c.executemany(
            "INSERT INTO threads (id, source_id, locator, device_id, app, title)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(tid, self.src, *self._thr(tid)) for tid in self.new_threads],
        )
        self.new_threads.clear()
        c.executemany(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, ts_utc, ts_offset_min, ts_raw, body, lang, deleted_flag, bookmarked)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            self.messages,
        )
        before = c.total_changes
        c.executemany(
            "INSERT OR IGNORE INTO message_recipients (message_id, account_id) VALUES (?, ?)",
            self.recipients,
        )
        self.totals["message_recipients"] += c.total_changes - before
        c.executemany(
            "INSERT INTO attachments (id, source_id, locator, message_id, file_name, mime_type,"
            " sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(*a, *self.att_meta.pop(str(a[0]), (None, None))) for a in self.attachments],
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
        for key, rows in (
            ("messages", self.messages),
            ("attachments", self.attachments),
            ("calls", self.calls),
            ("contacts", self.contacts),
        ):
            self.totals[key] += len(rows)
            rows.clear()
        self.recipients.clear()

    def _acct(self, aid: str) -> tuple[object, ...]:
        loc, app, ident, dev, name = self.accounts[aid]
        return loc, dev, app, ident, name

    def _thr(self, tid: str) -> tuple[object, ...]:
        loc, app, title = self.threads[tid]
        return loc, self.dev, app, title

    def flush(self) -> None:
        self.write_pending()
        multi = [a for a, names in self.account_names.items() if len(names) > 1]
        if multi:
            self.cov.counters["accounts_with_multiple_display_names"] = len(multi)
            self.cov.multi_name_accounts = sorted(multi)[:MAX_LISTED]
            self.cov.notes.append(
                "Some accounts appear with more than one display name; the first one seen is "
                "stored. Ids: " + ", ".join(sorted(multi)[:MAX_LISTED])
            )
        counts = self.cov.counters
        counts["accounts"] = len(self.accounts)
        counts["threads"] = len(self.threads)
        for k in ("messages", "message_recipients", "attachments", "calls", "contacts"):
            counts[k] = self.totals[k]


# ---------------------------------------------------------------- the importer


@dataclass
class _Scan:
    """What the first pass learns before any record is written."""

    namespace: str | None
    project_attrs: dict[str, str]
    counts: Counter[str]
    extractions: list[dict[str, str]]
    metadata: list[tuple[str, str, str, str]]
    tagged_files: int
    tagged_paths: dict[str, str]
    tagged_conflicts: set[str]
    votes: dict[str, DateOrder]
    accounts: list[_El]


class UfdrImporter:
    """Implements core.contracts.EvidenceImporter for Cellebrite UFDR packages (.ufdr or .zip).

    Format support is UNVERIFIED (see the module docstring); each import records that."""

    name = IMPORTER_NAME

    def __init__(
        self,
        source_id: str | None = None,
        now: datetime | None = None,
        date_order: str | None = None,
    ) -> None:
        """`date_order` ('mdy' or 'dmy'): the day/month order a person states for times that
        are not ISO 8601. UFDR times are normally ISO 8601 (year first), which is never
        ambiguous; any other form is read only when the package or the stated order decides."""
        if date_order not in (None, "mdy", "dmy"):
            raise ValueError(f"date_order must be 'mdy' or 'dmy', not {date_order!r}")
        self.source_id = source_id
        self.now = now
        self.date_order = date_order

    def import_source(self, path: Path, conn: sqlite3.Connection) -> Source:
        sha = sha256_file(path)
        with open_input(path) as raw:
            if not zipfile.is_zipfile(raw):
                raise ValueError(f"{path.name} is not a zip package, so it is not a UFDR")
        with open_input(path) as raw, zipfile.ZipFile(raw) as z:
            report = find_report(z)
            scan = _scan(z, report)
            return self._write(path, sha, conn, z, report, scan)

    # ------------------------------------------------------------------

    def _write(
        self,
        path: Path,
        sha: str,
        conn: sqlite3.Connection,
        z: zipfile.ZipFile,
        report: zipfile.ZipInfo,
        scan: _Scan,
    ) -> Source:
        src = self.source_id or _source_id(path, sha)
        if conn.execute("SELECT 1 FROM sources WHERE id = ?", (src,)).fetchone():
            raise ValueError(f"source {src} is already in this case database")
        cov = Coverage()
        cov.summary_found = bool(scan.metadata)
        meta = _meta(scan.metadata)
        devices = sorted({e.get("deviceName", "").strip() for e in scan.extractions} - {""})
        if len(devices) > 1:
            raise ValueError(
                "this UFDR holds extractions from more than one device ("
                + ", ".join(repr(d) for d in devices)
                + "); Baker imports one device per file, so its records cannot be attributed. "
                "Ask for one package per device"
            )

        report_order = DateOrder()
        for v in scan.votes.values():
            report_order = report_order.merged(v)
        stated = (
            DateOrder(int(self.date_order == "dmy"), int(self.date_order == "mdy"))
            if self.date_order
            else None
        )
        extracted_utc = None
        if "extraction_start" in meta:
            order = stated or (
                report_order if report_order.label in ("dmy", "mdy") else DateOrder()
            )
            extracted_utc = parse_time(meta["extraction_start"][0], order, None).ts.utc
            if extracted_utc is None:
                cov.counters["extraction_time_unread"] += 1
        types = sorted({_extraction_type(e.get("type")) for e in scan.extractions}, key=str)
        ext_type = types[0] if len(types) == 1 else ExtractionType.UNKNOWN
        if len(types) > 1:
            cov.notes.append(
                "The package holds extractions of more than one type, so the source's extraction "
                "type is recorded as unknown; the types are listed in the coverage record."
            )
        device_label = _device_label(meta, devices)
        tool_version = meta.get("tool_version", (None, ""))[0]
        source = Source(
            id=src,
            kind=SourceKind.UFDR,
            fidelity=Fidelity.UNKNOWN,
            extraction_type=ext_type,
            file_name=path.name,
            sha256=sha,
            tool_name="Cellebrite (UFDR package)",
            tool_version=tool_version,
            extracted_at_utc=extracted_utc,
            imported_at_utc=self.now or datetime.now(UTC),
        )
        dev = f"dev:{src}"
        tables: dict[str, TableCoverage] = {}
        tctx: dict[str, TimeContext] = {}
        for t, kind in TABLE_KIND.items():
            if not scan.counts.get(t):
                continue
            tc = TableCoverage(name=t, kind=kind.value, header_locator=None)
            tables[t] = tc
            own = scan.votes.get(t, DateOrder())
            if kind in (RecordKind.CONTACTS, RecordKind.ACCOUNTS):
                eff = own
            elif stated is not None:
                eff = stated
                tc.date_order_basis = "stated at import"
                if own.label not in ("undecided", self.date_order):
                    cov.counters["values_contradicting_stated_date_order"] += (
                        own.mdy_votes if self.date_order == "dmy" else own.dmy_votes
                    )
            elif own.label != "undecided":
                eff = own
                tc.date_order_basis = "this table"
            elif report_order.label in ("dmy", "mdy"):
                eff = report_order
                tc.date_order_basis = "other tables in the report"
            else:
                eff = own
                tc.date_order_basis = "none"
            if kind not in (RecordKind.CONTACTS, RecordKind.ACCOUNTS):
                tc.date_order = eff.label
            tctx[t] = TimeContext(eff, None, {}, tc)
        for t, n in sorted(scan.counts.items()):
            if t in TABLE_KIND:
                continue
            cov.not_imported.append(
                {
                    "name": t,
                    "reason": (
                        "category not imported"
                        if t in NOT_IMPORTED_TYPES
                        else "model type not recognised"
                    ),
                    "records": n,
                }
            )

        w = _StreamWriter(conn, src, dev, cov)
        pkg = _Package(z, report)
        rd = _RecordMapper(w, pkg, tables, tctx, scan.tagged_paths, scan.tagged_conflicts)
        if scan.tagged_conflicts:
            cov.counters["tagged_file_ids_repeated"] = len(scan.tagged_conflicts)
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
                    meta["device"][1] if "device" in meta else "extractionInfo[1]",
                    device_label or f"Device in {path.name}",
                    device_label,
                    meta.get("os", (None, ""))[0],
                    meta.get("device_time_zone", (None, ""))[0],
                ),
            )
            for el in scan.accounts:
                rd.user_account(el)
            reader = _Reader(lambda t: t in TABLE_KIND and t != "UserAccount", rd.model, True)
            with z.open(report) as f:
                hashing = _HashingReader(f)
                reader.read(hashing)
            w.flush()
            for t, tc in tables.items():
                if t not in ("Chat", "UserAccount") and tc.rows_read != scan.counts[t]:
                    raise ValueError(  # the two passes over one file disagree: store nothing
                        f"report.xml gave {scan.counts[t]} {t} records on the first read and "
                        f"{tc.rows_read} on the second; nothing was imported"
                    )
            payload = coverage_payload(
                source,
                IMPORTER_NAME,
                None,
                None,
                cov,
                sorted({TABLE_KIND[t] for t in tables}),
                report_order,
                self.date_order,
            )
            cov.tables = list(tables.values())
            payload["tables"] = [_table_dict(tc, rd) for tc in cov.tables]
            payload.update(
                importer_version=IMPORTER_VERSION,
                fidelity_reason=FIDELITY_REASON,
                format_support=FORMAT_SUPPORT,
                layout="xml",
                ufdr={
                    "report_member": report.filename,
                    "report_sha256": hashing.h.hexdigest(),
                    "report_bytes": hashing.size,
                    "namespace": scan.namespace,
                    "namespace_known": scan.namespace == KNOWN_NAMESPACE,
                    "report_version": scan.project_attrs.get("reportVersion"),
                    "extractions": [_extraction(e) for e in scan.extractions],
                    "partial_extractions": [
                        e.get("name") or e.get("id", "")
                        for e in scan.extractions
                        if (e.get("IsPartialData") or "").lower() in _TRUE
                    ],
                    "metadata_items": len(scan.metadata),
                    "metadata_read": {k: v[1] for k, v in sorted(meta.items())},
                    "tagged_files": scan.tagged_files,
                    "package_files": len(pkg.members),
                    "package_files_hashed": len(pkg.hashed),
                    "model_counts": dict(sorted(scan.counts.items())),
                    "deleted_state_values": dict(sorted(rd.deleted_states.items())),
                },
            )
            forwarded.mark(conn, cov.forwarded_records, cov.forwarded_from)
            payload["counts"] = dict(sorted(cov.counters.items()))
            payload["unmapped_direction_values"] = dict(cov.unmapped_direction_values)
            payload["notes"] = cov.notes
            conn.execute(
                "INSERT INTO source_coverage (source_id, importer, importer_version, payload_json)"
                " VALUES (?, ?, ?, ?)",
                (source.id, IMPORTER_NAME, IMPORTER_VERSION, json.dumps(payload, sort_keys=True)),
            )
            audit_log.append(conn, source.imported_at_utc, "system", "import", payload)
            if sha256_file(path) != sha:  # the package changed while it was read: store nothing
                raise ValueError(
                    f"{path.name} changed while Baker read it; nothing was imported. Nothing "
                    "should change a copied input, so check the case folder"
                )
        return source


def _scan(z: zipfile.ZipFile, report: zipfile.ZipInfo) -> _Scan:
    accounts: list[_El] = []
    reader = _Reader(lambda t: t == "UserAccount", accounts.append, False)
    with z.open(report) as f:
        reader.read(f)
    return _Scan(
        namespace=reader.namespace,
        project_attrs=reader.project_attrs,
        counts=reader.counts,
        extractions=reader.extractions,
        metadata=reader.metadata,
        tagged_files=reader.tagged_files,
        tagged_paths=reader.tagged_paths,
        tagged_conflicts=reader.tagged_conflicts,
        votes=reader.votes,
        accounts=accounts,
    )


# ---------------------------------------------------------------- models -> canonical rows


class _RecordMapper:
    def __init__(
        self,
        w: _StreamWriter,
        pkg: _Package,
        tables: dict[str, TableCoverage],
        tctx: dict[str, TimeContext],
        tagged_paths: dict[str, str] | None = None,
        tagged_conflicts: set[str] | None = None,
    ) -> None:
        self.w = w
        self.pkg = pkg
        self.tagged_paths = tagged_paths or {}
        self.tagged_conflicts = tagged_conflicts or set()
        self.tables = tables
        self.tctx = tctx
        self.cov = w.cov
        self.deleted_states: Counter[str] = Counter()
        self.unknown_fields: dict[str, list[str]] = {}
        self.flag_counts: dict[str, Counter[str]] = {}
        self.model_ids: set[str] = set()

    def _repeat(self, table: str, m: _Model, locator: str) -> bool:
        """True for a message or call whose model id an earlier record already had: the same
        record listed twice (say, inside a chat and on its own) is imported once."""
        mid = m.attrs.get("id")
        if not mid:
            return False
        if mid not in self.model_ids:
            self.model_ids.add(mid)
            return False
        tc = self.tables[table]
        tc.rows_read += 1
        tc.rows_skipped["same_id_as_an_earlier_record"] += 1
        _listed(tc.skipped_locators, "same_id_as_an_earlier_record", locator)
        return True

    def _count_pictures(self, m: _Model) -> None:
        n = sum(1 for e in m.models("entries") if _is_picture(e))
        if n:
            self.cov.counters["picture_entries_not_identifiers"] += n

    def _flag(self, table: str, reason: str, locator: str) -> None:
        """A record the expert should open: counted per record type, first locators listed."""
        self.flag_counts.setdefault(table, Counter())[reason] += 1
        _listed(self.tables[table].flagged_locators, reason, locator)

    # bookkeeping ---------------------------------------------------------

    def _fields(self, table: str, known_key: str, m: _Model) -> None:
        seen = self.unknown_fields.setdefault(table, [])
        known = _KNOWN[known_key]
        for n in m.field_names:
            if n.lower() not in known and n not in seen and len(seen) < MAX_FIELD_NAMES:
                seen.append(n)
        tc = self.tables[table]
        for n in m.duplicates:
            if all(d["column"] != n for d in tc.duplicate_columns):
                tc.duplicate_columns.append({"column": n, "field": n.lower(), "used": n})

    def _flags(self, table: str, m: _Model, locator: str) -> str | None:
        """The record's deleted state as the package wrote it, and its recovery flags."""
        state = m.attrs.get("deleted_state") or m.attrs.get("deleted")
        if state is None:
            state = m.text("deleted_state", "deletedstate", "recordstatus")
        if state is not None:
            self.deleted_states[state] += 1
        carved = any(
            k.lower() in ("carved", "iscarved") and v.strip().lower() in _TRUE | {"carved"}
            for k, v in m.attrs.items()
        ) or (m.text("carved", "iscarved") or "").lower() in _TRUE | {"carved"}
        if carved:
            self.cov.counters["records_recovered_by_carving"] += 1
            self._flag(table, "carved", locator)
        conf = m.attrs.get("decoding_confidence")
        if conf is not None and conf.strip().lower() != "high":
            self.cov.counters["records_decoding_confidence_not_high"] += 1
            self._flag(table, "decoding_confidence_not_high", locator)
        if table != "Contact" and table != "Call":
            # The message stays the forwarder's (sender, direction); it is marked forwarded, with
            # the original author when the package names one, and core/ingest/forwarded.py keeps
            # it from supporting or contradicting a claim, and the expert is told which ones.
            mid = f"msg:{self.w.src}:{locator}"
            if _forwarded(m):
                self.cov.counters["messages_marked_forwarded"] += 1
                self.cov.forwarded_records.setdefault("forwarded", []).append(mid)
                author = _original_author(m)
                if author:
                    self.cov.forwarded_from[mid] = author
                self._flag(table, "forwarded", locator)
            if m.models("embeddedinstantmessage"):
                self.cov.counters["messages_with_embedded_message_not_imported"] += 1
                self.cov.forwarded_records.setdefault("embedded", []).append(mid)
                self._flag(table, "embedded_message_not_imported", locator)
        return state

    def _time(self, table: str, m: _Model, locator: str, names: tuple[str, ...]) -> str | None:
        """The record's time as written; a record with none is listed, never given one."""
        raw = m.raw(*names)
        if raw is None or not raw.strip():
            self._flag(table, "no_time", locator)
        return raw

    def _maybe_write(self) -> None:
        if self.w.pending() >= BATCH:
            self.w.write_pending()

    # dispatch ------------------------------------------------------------

    def model(self, el: _El) -> None:
        t = el.attrs.get("type", "")
        m = _model(el)
        if t == "Chat":
            self.chat(el, m)
        elif t == "InstantMessage":
            if not self._repeat(t, m, el.locator):
                self.messages(t, RecordKind.CHATS, [self.message_row(None, el.locator, m)])
        elif t in ("SMS", "MMS"):
            if not self._repeat(t, m, el.locator):
                self.messages(t, RecordKind.SMS, [self.sms_row(t, el.locator, m)])
        elif t == "Call":
            if not self._repeat(t, m, el.locator):
                self.call(el.locator, m)
        elif t == "Contact":
            self.contact(el.locator, m)
        self._maybe_write()

    def messages(self, table: str, kind: RecordKind, rows: list[_ModelRow]) -> None:
        tc = self.tables[table]
        tc.rows_read += len(rows)
        tc.rows_imported += len(rows)
        _messages(self.w, kind, rows, self.tctx[table], None)

    # chats ---------------------------------------------------------------

    def chat(self, el: _El, chat: _Model) -> None:
        self._fields("Chat", "Chat", chat)
        pending = el.pending or []
        if not pending:
            self.cov.counters["chats_without_messages"] += 1
        pending = [(loc, m) for loc, m in pending if not self._repeat("Chat", m, loc)]
        for i in range(0, len(pending), BATCH):
            rows = [self.message_row(chat, loc, m) for loc, m in pending[i : i + BATCH]]
            self.messages("Chat", RecordKind.CHATS, rows)
            self._maybe_write()

    def message_row(self, chat: _Model | None, locator: str, m: _Model) -> _ModelRow:
        table = "Chat" if chat is not None else "InstantMessage"
        self._fields(table, "message", m)
        state = self._flags(table, m, locator)
        senders = [p for p, _r in _parties(m.models("from"))]
        to = [p for p, _r in _parties(m.models("to"))]
        for p, role in _parties(m.models("parties")):
            if role == "from":
                senders.append(p)
            elif role in ("to", "cc", "bcc"):
                to.append(p)
        participants = [p for p, _r in _parties(chat.models("participants"))] if chat else []
        app = m.text("source") or (chat.text("source") if chat else None)
        values: dict[str, Cell] = {
            "app": app,
            "chat_id": chat.text(*CHAT_ID_FIELDS) if chat else None,
            "chat_name": chat.text(*CHAT_NAME_FIELDS) if chat else None,
            "participants": "\n".join(_party_text(p) for p in participants) or None,
            "body": m.raw(*BODY_FIELDS),
            "ts": self._time(table, m, locator, TS_FIELDS),
            "direction": m.text("direction"),
            "folder": m.text("folder"),
            "status": m.text("status"),
            "deleted": state,
        }
        parties = {"from": senders, "to": to, "participants": participants}
        return _row(locator, values, parties, self.attachments(table, locator, m))

    def sms_row(self, table: str, locator: str, m: _Model) -> _ModelRow:
        self._fields(table, "message", m)
        state = self._flags(table, m, locator)
        senders = [p for p, _r in _parties(m.models("from"))]
        to = [p for p, _r in _parties(m.models("to"))]
        counterpart: list[Party] = []
        for p, role in _parties(m.models("parties", "participants")):
            if role == "from":
                senders.append(p)
            elif role in ("to", "cc", "bcc"):
                to.append(p)
            else:
                counterpart.append(p)
        values: dict[str, Cell] = {
            "app": m.text("source"),
            "body": m.raw(*BODY_FIELDS),
            "ts": self._time(table, m, locator, TS_FIELDS),
            "direction": m.text("direction"),
            "folder": m.text("folder"),
            "status": m.text("status"),
            "deleted": state,
        }
        parties = {"from": senders, "to": to, "parties": counterpart}
        return _row(locator, values, parties, self.attachments(table, locator, m))

    def attachments(self, table: str, locator: str, m: _Model) -> list[str]:
        """File names for the shared mapper, in order; the MIME type and SHA-256 of each go to
        the writer under the attachment id the mapper will give it."""
        names: list[str] = []
        for a in m.models("attachments", "attachment"):
            fid = a.attrs.get("file_id", "")
            path = a.text(*ATT_PATH_FIELDS)
            if path is None and fid in self.tagged_conflicts:
                # the package names two files for this id: link neither, never guess
                self.cov.counters["attachments_with_ambiguous_file_id"] += 1
                self._flag(table, "attachment_file_ambiguous", locator)
            elif path is None:
                path = self.tagged_paths.get(fid)
            info = self.pkg.lookup(path) if path else None
            name = a.text(*ATT_NAME_FIELDS) or (
                PurePosixPath(_norm_member(path)).name if path else None
            )
            if not name:
                self.cov.counters["attachments_without_name_or_file"] += 1
                self._flag(table, "attachment_without_name", locator)
                continue
            name = " ".join(name.splitlines()).strip()
            sha = None
            if info is not None:
                sha = self.pkg.sha256(info)
                self.cov.counters[
                    "attachment_files_hashed" if sha else "attachment_files_encrypted_not_hashed"
                ] += 1
                stated = a.text(*ATT_HASH_FIELDS)
                if sha and stated and re.fullmatch(r"[0-9A-Fa-f]{64}", stated):
                    if stated.lower() != sha:
                        self.cov.counters["attachment_hash_differs_from_package"] += 1
                        self._flag(table, "attachment_hash_differs", locator)
            elif path:
                self.cov.counters["attachment_files_not_in_package"] += 1
                self._flag(table, "attachment_file_not_in_package", locator)
            else:
                self.cov.counters["attachments_without_file_reference"] += 1
            names.append(name)
            self.w.att_meta[f"att:{self.w.src}:{locator}:{len(names)}"] = (
                a.text(*ATT_MIME_FIELDS),
                sha,
            )
        return names

    # calls, contacts, accounts -------------------------------------------

    def call(self, locator: str, m: _Model) -> None:
        table = "Call"
        self._fields(table, "Call", m)
        state = self._flags(table, m, locator)
        tc = self.tables[table]
        raw_duration = m.text("duration")
        duration = _duration(raw_duration)
        if raw_duration is not None and duration is None:
            self.cov.counters["call_durations_unread"] += 1
            self._flag(table, "duration_unread", locator)
        senders = [p for p, _r in _parties(m.models("from"))]
        to = [p for p, _r in _parties(m.models("to"))]
        values: dict[str, Cell] = {
            "app": m.text("source"),
            "ts": self._time(table, m, locator, CALL_TS_FIELDS),
            "duration": duration,
            "direction": m.text("direction"),
            "type": m.text("type"),
            "status": m.text("status"),
            "deleted": state,
        }
        parties = {
            "from": senders,
            "to": to,
            "parties": [p for p, _r in _parties(m.models("parties"))],
        }
        tc.rows_read += 1
        tc.rows_imported += 1
        _calls(self.w, [_row(locator, values, parties)], self.tctx["Call"], None)

    def contact(self, locator: str, m: _Model) -> None:
        self._fields("Contact", "Contact", m)
        self._flags("Contact", m, locator)
        tc = self.tables["Contact"]
        tc.rows_read += 1
        tc.rows_imported += 1
        self._count_pictures(m)
        idents = _entries(m)
        if not idents:
            idents = [""]
            self.cov.counters["contacts_without_identifier"] += 1
        for n, ident in enumerate(idents, start=1):
            self.w.contacts.append(
                (f"contact:{self.w.src}:{locator}#{n}", self.w.src, locator, self.w.dev,
                 m.text("name"), ident)
            )  # fmt: skip

    def user_account(self, el: _El) -> None:
        m = _model(el)
        self._fields("UserAccount", "UserAccount", m)
        tc = self.tables["UserAccount"]
        tc.rows_read += 1
        self._count_pictures(m)
        ident = m.text("username") or _account_identifier(m)
        if not ident:
            tc.rows_skipped["account_without_identifier"] += 1
            _listed(tc.skipped_locators, "account_without_identifier", el.locator)
            return
        tc.rows_imported += 1
        app = m.text("source") or "unknown"
        aid = self.w.account(app, Party(ident, m.text("name"), True, None), el.locator, "")
        self.w.owner_idents.add((_slug(app), ident))
        self.w.mark_owner(aid)


def _add_tagged(paths: dict[str, str], conflicts: set[str], fid: str, path: str) -> None:
    """Record a taggedFiles id's Local Path; an id given two different paths links to neither."""
    if fid in conflicts:
        return
    if fid in paths and paths[fid] != path:
        del paths[fid]
        conflicts.add(fid)
    else:
        paths.setdefault(fid, path)


def _forwarded(m: _Model) -> bool:
    """The package marks the message forwarded: a Forwarded label in its Labels, or on a model
    in its MessageExtraData (MessageLabel, QuotedMessageData), as seen in public samples."""
    labels = list(m.multi_values.get("labels", []))
    labels += [x.text("label") or "" for x in m.models("messageextradata")]
    labels += [v for x in m.models("messageextradata") for v in x.multi_values.get("labels", [])]
    return any(is_forwarded_label(v) for v in labels)


def _original_author(m: _Model) -> str | None:
    """The sender of the forwarded original, when the package embeds it and names exactly one
    (as written); never guessed."""
    authors = {
        _party_text(p)
        for e in m.models("embeddedinstantmessage")
        for p, _r in _parties(e.models("from"))
    }
    authors.discard("")
    return authors.pop() if len(authors) == 1 else None


def _is_picture(m: _Model) -> bool:
    """A picture entry (ProfilePicture, ContactPhoto): its value is an image link, never an
    identifier of the person or account."""
    return bool(PICTURE_TYPE_RE.search(m.type))


def _account_identifier(m: _Model) -> str | None:
    """A UserAccount without a Username: its first UserID entry, else its first other
    identifier entry."""
    user_ids = [e for e in m.models("entries") if _key(e.type) == "userid"]
    for e in user_ids:
        v = e.text("value", "identifier", "number", "address")
        if v:
            return v
    return next(iter(_entries(m)), None)


def _entries(m: _Model) -> list[str]:
    """Identifiers in a contact's or account's Entries (phone numbers, emails, user ids), as
    written, first seen first. Picture entries are not identifiers and are skipped."""
    out: list[str] = []
    for e in m.models("entries"):
        if _is_picture(e):
            continue
        v = e.text("value", "identifier", "number", "address")
        if v and v not in out:
            out.append(v)
    return out


def _party_text(p: Party) -> str:
    return " ".join(x for x in (p.identifier, p.name) if x)


def _table_dict(tc: TableCoverage, rd: _RecordMapper) -> dict[str, object]:
    d = tc.as_dict()
    d["unknown_columns"] = rd.unknown_fields.get(tc.name, [])
    d["record_type"] = tc.name
    d["flag_counts"] = dict(rd.flag_counts.get(tc.name, {}))
    return d


# ---------------------------------------------------------------- metadata


def _meta(items: list[tuple[str, str, str, str]]) -> dict[str, tuple[str, str]]:
    """key -> (value, locator) for the metadata Baker reads, first alias present wins."""
    by_name: dict[str, tuple[str, str]] = {}
    for _section, name, value, loc in items:
        k = _key(name)
        if k not in by_name and value.strip():
            by_name[k] = (value.strip(), loc)
    out: dict[str, tuple[str, str]] = {}
    for key, aliases in META_KEYS.items():
        for a in aliases:
            if a in by_name:
                out[key] = by_name[a]
                break
    return out


def _device_label(meta: dict[str, tuple[str, str]], devices: list[str]) -> str | None:
    model = meta["device"][0] if "device" in meta else (devices[0] if devices else None)
    make = meta.get("manufacturer", (None, ""))[0]
    if model and make and not norm(model).startswith(norm(make)):
        return f"{make} {model}"
    return model


def _extraction_type(raw: str | None) -> ExtractionType:
    t = _key(raw or "")
    if "physical" in t:
        return ExtractionType.PHYSICAL
    if "filesystem" in t:
        return ExtractionType.FILE_SYSTEM
    if "logical" in t:
        return ExtractionType.LOGICAL
    return ExtractionType.UNKNOWN


def _extraction(e: dict[str, str]) -> dict[str, str | None]:
    return {
        k: e.get(a)
        for k, a in (
            ("id", "id"),
            ("name", "name"),
            ("type", "type"),
            ("device_name", "deviceName"),
            ("partial", "IsPartialData"),
        )
    }


def _source_id(path: Path, sha: str) -> str:
    """The file stem when it is a plain token, else `src_<sha12>` (as the report importers)."""
    if re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", path.stem):
        return path.stem
    return f"src_{sha[:12]}"


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None
