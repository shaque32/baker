"""UFDR self-check: does what Mabillon imported from a UFDR match the package's own report.xml?

Mabillon's UFDR reader (core/ingest/ufdr.py) was built from public descriptions of the format and
has not yet been compared with a real package. This check is what an expert runs, offline, on
their first real UFDR. It:

1. reads report.xml a second time with its own small reader, independent of the importer's
   record mapping: every model, field and attribute is counted, and for each record Mabillon should
   import it notes the body (as a hash), time, sender, recipients, record state, attachments,
   call duration and contact entries;
2. imports the package with Mabillon's importer into a throwaway in-memory database (nothing is
   written to a case, nothing leaves the computer);
3. compares the two record by record, by locator.

It writes two files:

- `ufdr-check.md` and `ufdr-check.json`: SHAREABLE. Counts, field names, record positions
  (locators such as `Chat[3]/Messages[17]`) and value shapes (`9999-99-99A99:99:99.999-99:99`)
  only. No message text, name, phone number, identifier, file name, hash or device detail.
  Every string written to them is either built by this module or passes `_safe_name`, and a
  test plants marker strings in every value of a package and checks none comes out.
- `ufdr-check-private.md`: STAYS ON THE COMPUTER. A sample of records with what Mabillon read for
  each, to open side by side in Cellebrite Reader, and blanks for the counts Reader shows. The
  expert copies the yes/no totals into the shareable file.

The check reads nothing but the package and writes nothing but those files.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO
from xml.parsers import expat

from core.db import apply_schema
from core.encryption import open_input
from core.ingest import ufdr

CHECK_VERSION = "0.1.0"
SHAREABLE_MD = "ufdr-check.md"
SHAREABLE_JSON = "ufdr-check.json"
PRIVATE_MD = "ufdr-check-private.md"
SOURCE_ID = "ufdrcheck"
MAX_LOCATORS = 10  # first differing locators listed per check
MAX_SHAPES = 25  # value shapes listed per field
MAX_SCHEMA_FIELDS = 60  # field names listed per model kind

PARTY_HOLDERS = {"from", "to", "parties", "participants"}  # fields holding parties, any type
TOP_MESSAGE_TYPES = {"InstantMessage", "Message", "SMS", "MMS"}
CHAT_MESSAGE_TYPES = ufdr.MESSAGE_TYPES
BODY = ("body", "text", "message", "content")
TS = ("timestamp", "datetime")
CALL_TS = (*TS, "starttime")
ATT_NAME = ("filename", "name", "file name")
ATT_PATH = ("attachment_extracted_path", "localpath", "local path", "extractedpath", "path")
# Fields whose values are a closed vocabulary in Cellebrite's schema. Their values are reported
# only when they are in VOCABULARY; anything else is reported by shape (letters as A or a).
ENUM_FIELDS = {"direction", "type", "status", "folder", "role", "isphoneowner", "source"}
VOCABULARY = {
    w.lower()
    for w in (
        "Incoming Outgoing Missed Rejected Declined Cancelled Canceled Blocked Unknown None "
        "Inbox Sent Outbox Draft Drafts Trash Deleted Archived Read Unread Delivered Sending "
        "Failed Received Seen Pending Error From To CC BCC General Owner Participant True False "
        "Intact High Medium Low Video Voice Audio Text Picture Image Location Contact Sticker "
        "Undefined Normal Group Private Broadcast Channel SMS MMS iMessage RCS WhatsApp Telegram "
        "Signal Viber Messenger Facebook Instagram Snapchat WeChat Line Skype Kik Discord "
        "TikTok Twitter Threema Wickr Native Phone Cellular FaceTime Duo Teams Zoom Gmail "
        "Logical Physical FileSystem File System Full Advanced AdvancedLogical FullFileSystem "
        "Cloud Backup Extraction Partial"
    ).split()
}
_SAFE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{0,63}")
_VERSION = re.compile(r"\d{1,4}(?:\.\d{1,6}){0,4}")
_ISO = re.compile(
    r"\s*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,7})?)?(?:Z|[+-]\d{2}:?\d{2})\s*", re.I
)
_TIMESPAN = re.compile(r"(?:(\d+)\.)?(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?")
_SHAPE_WORDS = {"t", "z", "am", "pm", "utc", "gmt"}
_TRUE = {"true", "1", "yes"}


# ---------------------------------------------------------------- content-free strings


def _safe_name(s: str | None) -> str:
    """A schema name (model type, field, attribute) as written when it looks like one; else its
    shape, so nothing free-form reaches the shareable report."""
    if s is None:
        return "(none)"
    return s if _SAFE_NAME.fullmatch(s) else f"(shape {shape(s)})"


def shape(value: str, keep_words: bool = True) -> str:
    """'2026-03-05T21:31:00.000-05:00' -> '9999-99-99T99:99:99.999-99:99'. Digits become 9;
    letter runs become A/a by case, except T, Z, AM, PM, UTC and GMT when `keep_words`."""
    v = value.strip()
    if len(v) > 48:
        v = v[:48] + "..."

    def letters(m: re.Match[str]) -> str:
        w = m.group(0)
        if keep_words and w.lower() in _SHAPE_WORDS:
            return w
        return "".join("A" if c.isupper() else "a" for c in w)

    v = re.sub(r"\d", "9", v)
    v = re.sub(r"[^\W\d_]+", letters, v)
    return re.sub(r"[^\x20-\x7e]", "?", v)


def _enum_value(value: str) -> str:
    v = value.strip()
    if not v:
        return "(blank)"
    if all(w in VOCABULARY for w in v.lower().split()):
        return v
    return f"(shape {shape(v, keep_words=False)})"


def _digest(s: str | None) -> bytes:
    return hashlib.blake2b((s or "").encode("utf-8", "surrogatepass"), digest_size=16).digest()


# ---------------------------------------------------------------- the independent reader


@dataclass
class _Frame:
    type: str
    attrs: dict[str, str]
    depth: int  # len(path) when the model element opened
    key: str  # schema key: 'Chat', 'Chat.Messages>InstantMessage', ...
    locator: str | None
    top: bool
    fields: dict[str, str] = field(default_factory=dict)  # lowercased name -> first value
    parties: dict[str, list[tuple[str | None, str | None, str, bool]]] = field(default_factory=dict)
    # (named, path, file_id): a file_id is resolved through taggedFiles once the read ends
    attachments: list[tuple[bool, str | None, str | None]] = field(default_factory=list)
    entries: list[str] = field(default_factory=list)
    user_ids: list[str] = field(default_factory=list)  # UserID entries, for a UserAccount
    msg_seen: Counter[str] = field(default_factory=Counter)


@dataclass
class _Kind:
    """What the reader saw for one model kind."""

    count: int = 0
    fields: Counter[str] = field(default_factory=Counter)  # 'Body (field)'
    attributes: Counter[str] = field(default_factory=Counter)
    other_elements: Counter[str] = field(default_factory=Counter)
    value_types: Counter[str] = field(default_factory=Counter)  # 'TimeStamp: TimeStamp'
    value_attributes: Counter[str] = field(default_factory=Counter)


@dataclass
class MessageRec:
    locator: str
    type: str
    model_id: str | None
    body: bytes  # blake2b of the body as written ('' when absent)
    body_present: bool
    ts_raw: str | None
    sender: str | None  # identifier, else name, of the stated sender
    sender_owner: bool  # the sender party says IsPhoneOwner
    recipient_owner: bool  # a stated recipient says IsPhoneOwner
    recipients: list[str]  # identifiers (else names) of stated recipients
    direction: str | None  # Direction field as written
    folder: str | None
    status: str | None
    state: str | None
    att_refs: list[tuple[bool, str | None, str | None]]
    attachments: int = 0  # set when the read ends (file ids need taggedFiles)
    attachment_files: int = 0  # attachments naming a path that is in the package


@dataclass
class CallRec:
    locator: str
    model_id: str | None
    ts_raw: str | None
    duration_raw: str | None
    direction: str | None  # Direction, else Type, as written
    sender: str | None
    recipient: str | None
    state: str | None


@dataclass
class ContactRec:
    locator: str
    name: bytes
    entries: int


class Tally:
    """Streams report.xml once through expat and keeps counts, value shapes and one small
    summary per record; never the record text itself (bodies are kept as hashes)."""

    def __init__(self, members: set[str]) -> None:
        self.members = members  # lowercased package member paths, for attachment files
        self.path: list[str] = []
        self.attr_stack: list[dict[str, str]] = []
        self.frames: list[_Frame] = []
        self.root: str | None = None
        self.namespace: str | None = None
        self.project_attrs: dict[str, str] = {}
        self.extraction_types: Counter[str] = Counter()
        self.partial_extractions = 0
        self.metadata_items = 0
        self.metadata_names: set[str] = set()
        self.meta_values: dict[str, str] = {}  # metadata name key -> value (kept in memory only)
        self.tagged_files = 0
        self.tagged_paths: dict[str, str] = {}  # taggedFiles file id -> its "Local Path"
        self.tagged_conflicts: set[str] = set()  # ids listed twice with different paths
        self._tagged: tuple[str, list[str]] | None = None
        self._tagged_id: str | None = None
        self.kinds: dict[str, _Kind] = {}
        self.top_counts: Counter[str] = Counter()
        self.shapes: dict[str, Counter[str]] = {}  # 'InstantMessage.TimeStamp' -> shape counts
        self.enums: dict[str, Counter[str]] = {}
        self.messages: dict[str, MessageRec] = {}
        self.calls: dict[str, CallRec] = {}
        self.contacts: dict[str, ContactRec] = {}
        self.user_accounts: dict[str, str | None] = {}  # locator -> expected identifier
        self.owner_ids: set[str] = set()  # UserAccount identifiers: the phone's own accounts
        self.ids: Counter[str] = Counter()  # model ids of messages and calls
        self.repeats: set[str] = set()  # locators whose model id an earlier record had
        self._capture: tuple[_Frame, str, list[str]] | None = None
        self._item: list[str] | None = None
        self._item_name = ""

    # expat handlers ------------------------------------------------------

    def start(self, name: str, attrs: dict[str, str]) -> None:
        ns, _, local = name.rpartition(" ")
        parent = self.path[-1] if self.path else None
        if not self.path:
            self.root, self.namespace, self.project_attrs = local, ns or None, dict(attrs)
        self.path.append(local)
        self.attr_stack.append(attrs)
        depth = len(self.path)
        frame = self.frames[-1] if self.frames else None

        if local == "model" and "decodedData" in self.path:
            mtype = attrs.get("type", "")
            if parent == "modelType" and depth >= 3 and self.path[-3] == "decodedData":
                mtype = mtype or self.attr_stack[-2].get("type", "")
                self.top_counts[mtype] += 1
                f = _Frame(mtype, dict(attrs), depth, mtype, f"{mtype}[{self.top_counts[mtype]}]",
                           True)  # fmt: skip
            elif frame is not None and parent in ("modelField", "multiModelField"):
                fname = self.attr_stack[-2].get("name", "")
                loc = None
                if (
                    frame.top
                    and frame.type == "Chat"
                    and len(self.frames) == 1
                    and parent == "multiModelField"
                    and (fname.lower() == "messages" or mtype in CHAT_MESSAGE_TYPES)
                ):
                    frame.msg_seen[fname] += 1
                    loc = f"{frame.locator}/{fname}[{frame.msg_seen[fname]}]"
                key = f"{frame.type}.{fname}>{mtype}"
                f = _Frame(mtype, dict(attrs), depth, key, loc, False)
            else:
                return
            kind = self.kinds.setdefault(f.key, _Kind())
            kind.count += 1
            kind.attributes.update(attrs.keys())
            for a in ("deleted_state", "decoding_confidence"):
                if a in attrs:
                    self.enums.setdefault(f"{f.key}@{a}", Counter())[_enum_value(attrs[a])] += 1
            self.frames.append(f)
            return

        if frame is not None and depth == frame.depth + 1:  # a direct child of a model
            kind = self.kinds[frame.key]
            if local in ("field", "multiField", "modelField", "multiModelField") or "name" in attrs:
                kind.fields[f"{attrs.get('name', '')} ({local})"] += 1
            else:
                kind.other_elements[local] += 1
            return
        if (
            frame is not None
            and local == "value"
            and parent == "field"
            and depth == frame.depth + 2
        ):
            fname = self.attr_stack[-2].get("name", "")
            kind = self.kinds[frame.key]
            kind.value_types[f"{fname}: {attrs.get('type', '')}"] += 1
            kind.value_attributes.update(attrs.keys())
            if fname.lower() not in frame.fields and self._capture is None:
                self._capture = (frame, fname, [])
            return
        if frame is not None:
            return

        if local == "extractionInfo":
            self.extraction_types[attrs.get("type", "")] += 1
            if (attrs.get("IsPartialData") or "").lower() in _TRUE:
                self.partial_extractions += 1
        elif local == "file" and parent == "taggedFiles":
            self.tagged_files += 1
            self._tagged_id = attrs.get("id") or None
        elif local == "item" and "taggedFiles" in self.path:
            if self._tagged_id and ufdr._key(attrs.get("name", "")) == "localpath":
                self._tagged = (self._tagged_id, [])
        elif local == "item" and "decodedData" not in self.path and "taggedFiles" not in self.path:
            self.metadata_items += 1
            self._item, self._item_name = [], attrs.get("name", "")

    def end(self, name: str) -> None:
        local = self.path.pop()
        self.attr_stack.pop()
        if self._capture is not None and local == "value":
            frame, fname, parts = self._capture
            if len(self.path) == frame.depth + 1:
                frame.fields.setdefault(fname.lower(), "".join(parts))
                self._observe(frame, fname, "".join(parts))
                self._capture = None
            return
        if local == "item" and self._tagged is not None:
            fid, parts = self._tagged
            if path := "".join(parts).strip():
                ufdr._add_tagged(self.tagged_paths, self.tagged_conflicts, fid, path)
            self._tagged = None
            return
        if local == "file" and self._tagged_id is not None and "taggedFiles" in self.path[-1:]:
            self._tagged_id = None
            return
        if local == "item" and self._item is not None:
            key = ufdr._key(self._item_name)
            self.metadata_names.add(key)
            self.meta_values.setdefault(key, "".join(self._item).strip())
            self._item = None
            return
        if local == "model" and self.frames and len(self.path) + 1 == self.frames[-1].depth:
            f = self.frames.pop()
            holder = self.attr_stack[-1].get("name", "") if self.path else ""
            self._close(f, holder.lower())

    def chars(self, data: str) -> None:
        if self._capture is not None:
            self._capture[2].append(data)
        elif self._item is not None:
            self._item.append(data)
        elif self._tagged is not None:
            self._tagged[1].append(data)

    # records -------------------------------------------------------------

    def _observe(self, frame: _Frame, fname: str, value: str) -> None:
        low = fname.lower()
        label = f"{frame.key}.{fname}"
        if low in (*CALL_TS, "duration", "dateread", "datedelivered", "lastactivity"):
            self.shapes.setdefault(label, Counter())[shape(value)] += 1
        elif low in ENUM_FIELDS and frame.type != "Attachment":
            self.enums.setdefault(label, Counter())[_enum_value(value)] += 1

    def _close(self, f: _Frame, holder: str) -> None:
        parent = self.frames[-1] if self.frames else None
        if parent is not None and holder in ("attachments", "attachment"):
            name = _first(f.fields, ATT_NAME)
            path = _first(f.fields, ATT_PATH)
            parent.attachments.append((bool(name) or bool(path), path, f.attrs.get("file_id")))
            return
        if parent is not None and holder == "entries":
            if ufdr.PICTURE_TYPE_RE.search(f.type):  # an image link, not an identifier
                return
            v = _first(f.fields, ("value", "identifier", "number", "address"))
            if v and v not in parent.entries:
                parent.entries.append(v)
            if v and ufdr._key(f.type) == "userid":
                parent.user_ids.append(v)
            return
        if parent is not None and (f.type == "Party" or holder in PARTY_HOLDERS):
            ident = _text(f.fields.get("identifier"))
            name = _text(f.fields.get("name"))
            if ident is not None or name is not None:
                role = (_text(f.fields.get("role")) or "").lower()
                owner = (_text(f.fields.get("isphoneowner")) or "").lower() in _TRUE
                parent.parties.setdefault(holder, []).append((ident, name, role, owner))
            return
        if f.locator is None:
            return
        if f.top and f.type == "UserAccount":
            u = _text(f.fields.get("username"))
            ident = u or next(iter(f.user_ids), None) or next(iter(f.entries), None)
            if ident is not None:  # one with no identifier is skipped, and listed
                self.user_accounts[f.locator] = ident
                self.owner_ids.add(ident)  # the importer marks this identifier as the owner's
        elif (f.top and f.type in TOP_MESSAGE_TYPES) or not f.top:
            self._message(f)
        elif f.type == "Call":
            self._call(f)
        elif f.type == "Contact":
            self.contacts[f.locator] = ContactRec(
                f.locator, _digest(_text(f.fields.get("name"))), len(f.entries)
            )

    def _repeat(self, f: _Frame) -> None:
        mid = f.attrs.get("id")
        if mid:
            self.ids[mid] += 1
            if self.ids[mid] > 1 and f.locator:
                self.repeats.add(f.locator)

    def _message(self, f: _Frame) -> None:
        if f.locator is None:
            return
        self._repeat(f)
        senders = list(f.parties.get("from", []))
        recips = list(f.parties.get("to", []))
        for p in f.parties.get("parties", []) + f.parties.get("participants", []):
            if p[2] == "from":
                senders.append(p)
            elif p[2] in ("to", "cc", "bcc"):
                recips.append(p)
        body = _first_raw(f.fields, BODY)
        s = senders[0] if senders else None
        self.messages[f.locator] = MessageRec(
            locator=f.locator,
            type=f.type,
            model_id=f.attrs.get("id"),
            body=_digest(body),
            body_present=body is not None and body != "",
            ts_raw=_first_raw(f.fields, TS),
            sender=(s[0] or s[1]) if s else None,
            sender_owner=bool(s and s[3]),
            recipient_owner=any(p[3] for p in recips),
            recipients=[p[0] or p[1] or "" for p in recips],
            direction=_text(f.fields.get("direction")),
            folder=_text(f.fields.get("folder")),
            status=_text(f.fields.get("status")),
            state=_state(f),
            att_refs=list(f.attachments),
        )

    def _finish(self) -> None:
        """Count each message's attachments once taggedFiles (which may follow the records)
        has been read: an attachment may name its file only through file_id."""
        for x in self.messages.values():
            paths = [
                p or (self.tagged_paths.get(fid) if fid else None) for _n, p, fid in x.att_refs
            ]
            x.attachments = sum(
                1 for (named, _p, _f), p in zip(x.att_refs, paths, strict=True) if named or p
            )
            x.attachment_files = sum(1 for p in paths if p and _member(p) in self.members)

    def _call(self, f: _Frame) -> None:
        if f.locator is None:
            return
        self._repeat(f)
        frm = list(f.parties.get("from", []))
        to = list(f.parties.get("to", []))
        for p in f.parties.get("parties", []):
            if p[2] == "from":
                frm.append(p)
            elif p[2] == "to":
                to.append(p)
        self.calls[f.locator] = CallRec(
            locator=f.locator,
            model_id=f.attrs.get("id"),
            ts_raw=_first_raw(f.fields, CALL_TS),
            duration_raw=_text(f.fields.get("duration")),
            direction=_text(f.fields.get("direction")) or _text(f.fields.get("type")),
            sender=(frm[0][0] or frm[0][1]) if frm else None,
            recipient=(to[0][0] or to[0][1]) if to else None,
            state=_state(f),
        )

    # driving -------------------------------------------------------------

    def read(self, stream: IO[bytes]) -> None:
        p = expat.ParserCreate(namespace_separator=" ")
        p.buffer_text = True
        p.StartElementHandler = self.start
        p.EndElementHandler = self.end
        p.CharacterDataHandler = self.chars
        p.StartDoctypeDeclHandler = ufdr._refuse_doctype
        p.EntityDeclHandler = ufdr._refuse_entity
        p.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        try:
            while chunk := stream.read(ufdr.CHUNK):
                p.Parse(chunk, False)
            p.Parse(b"", True)
        except expat.ExpatError as err:
            raise ValueError(f"report.xml is not well-formed XML ({err})") from err
        self._finish()


def _state(f: _Frame) -> str | None:
    """The record state as the package writes it: an attribute, else a field."""
    for a in ("deleted_state", "deleted"):
        if a in f.attrs:
            return f.attrs[a]
    return _first(f.fields, ("deleted_state", "deletedstate", "recordstatus"))


def _text(v: str | None) -> str | None:
    return v.strip() if v is not None and v.strip() else None


def _first(fields: dict[str, str], names: tuple[str, ...]) -> str | None:
    for n in names:
        v = _text(fields.get(n))
        if v is not None:
            return v
    return None


def _first_raw(fields: dict[str, str], names: tuple[str, ...]) -> str | None:
    for n in names:
        if n in fields:
            return fields[n]
    return None


def _member(path: str) -> str:
    return re.sub(r"^(?:\./|/)+", "", path.strip().replace("\\", "/")).lower()


# ---------------------------------------------------------------- independent value readings


def iso_utc(raw: str | None) -> str | None:
    """UTC for an ISO 8601 value with an offset, read independently of the importer."""
    if raw is None or not _ISO.fullmatch(raw):
        return None
    s = raw.strip().replace(" ", "T", 1)
    s = re.sub(r"[Zz]$", "+00:00", s)
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    s = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), s)
    try:
        dt = datetime.fromisoformat(s).astimezone(UTC)
    except ValueError:  # '2026-02-30T...': not a real time; the importer lists it, unread
        return None
    return dt.isoformat().replace("+00:00", "Z")


# Stated message directions, read separately from the importer: Direction, then Folder, then
# Status, the first word of each.
_DIRECTION_WORDS = {"incoming": "incoming", "outgoing": "outgoing"}
_FOLDER_WORDS = {"inbox": "incoming", "sent": "outgoing", "outbox": "outgoing"}
_STATUS_WORDS = {"received": "incoming", "sent": "outgoing"}


def message_direction(x: MessageRec) -> str | None:
    for value, words in (
        (x.direction, _DIRECTION_WORDS),
        (x.folder, _FOLDER_WORDS),
        (x.status, _STATUS_WORDS),
    ):
        first = (value or "").strip().lower().split(" ")[0]
        if first in words:
            return words[first]
    return None


def seconds(raw: str | None) -> int | None:
    if raw is None:
        return None
    t = raw.strip()
    if re.fullmatch(r"\d+", t):
        return int(t)
    m = _TIMESPAN.fullmatch(t)
    if not m:
        return None
    d, h, mi, s = m.groups()
    return int(d or 0) * 86400 + int(h) * 3600 + int(mi) * 60 + int(s)


def state_flag(state: str | None) -> int | None:
    s = (state or "").strip().lower()
    return 0 if s == "intact" else 1 if s in ("deleted", "trash") else None


def _same_raw(stored: str | None, written: str | None) -> bool:
    """The importer keeps a time as written; a blank one is stored as no time."""
    if not (written or "").strip():
        return stored is None or not stored.strip()
    return stored == written


def _same_utc(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a == b
    pa = datetime.fromisoformat(a.replace("Z", "+00:00"))
    pb = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return pa == pb


# ---------------------------------------------------------------- comparison


@dataclass
class Check:
    """One comparison over many records: how many were compared and which differed."""

    record: str
    name: str
    what: str
    compared: int = 0
    differ: int = 0
    not_checked: int = 0
    locators: list[str] = field(default_factory=list)

    def see(self, same: bool, locator: str) -> None:
        self.compared += 1
        if not same:
            self.differ += 1
            if len(self.locators) < MAX_LOCATORS:
                self.locators.append(locator)

    def as_dict(self) -> dict[str, object]:
        return {
            "record": self.record,
            "check": self.name,
            "what": self.what,
            "compared": self.compared,
            "differ": self.differ,
            "not_checked": self.not_checked,
            "first_differing_locators": [safe_locator(x) for x in self.locators],
        }


@dataclass
class Count:
    record: str
    in_report: int
    imported: int
    expected_not_imported: int  # same model id as an earlier record (imported once)
    missing: list[str]  # locators in report.xml Mabillon has no record for
    extra: list[str]  # Mabillon records with no model at that locator

    def as_dict(self) -> dict[str, object]:
        return {
            "record": self.record,
            "in_report_xml": self.in_report,
            "imported_by_baker": self.imported,
            "repeats_imported_once": self.expected_not_imported,
            "missing": len(self.missing),
            "first_missing_locators": [safe_locator(x) for x in self.missing[:MAX_LOCATORS]],
            "extra": len(self.extra),
            "first_extra_locators": [safe_locator(x) for x in self.extra[:MAX_LOCATORS]],
        }


@dataclass
class Result:
    shareable: dict[str, object]
    sample: list[dict[str, object]]  # private: records to compare in Cellebrite Reader
    import_error: str | None


def _counts(record: str, xml: dict, db: set[str], repeats: set[str]) -> Count:
    want = set(xml)
    rep = want & repeats
    missing = sorted(want - db - rep, key=_loc_key)
    extra = sorted(db - want, key=_loc_key)
    return Count(record, len(want), len(db), len(rep - db), missing, extra)


def _loc_key(loc: str) -> tuple[object, ...]:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", loc))


def compare(t: Tally, conn: sqlite3.Connection, src: str) -> tuple[list[Count], list[Check]]:
    checks: list[Check] = []

    def check(record: str, name: str, what: str) -> Check:
        c = Check(record, name, what)
        checks.append(c)
        return c

    # messages --------------------------------------------------------------
    rows = conn.execute(
        "SELECT m.id, m.locator, m.body, m.ts_raw, m.ts_utc, m.deleted_flag, m.direction,"
        " a.identifier, a.device_id FROM messages m"
        " LEFT JOIN accounts a ON a.id = m.sender_account_id WHERE m.source_id = ?",
        (src,),
    ).fetchall()
    recips: dict[str, list[str]] = {}
    for mid, ident in conn.execute(
        "SELECT r.message_id, a.identifier FROM message_recipients r"
        " JOIN accounts a ON a.id = r.account_id JOIN messages m ON m.id = r.message_id"
        " WHERE m.source_id = ?",
        (src,),
    ):
        recips.setdefault(mid, []).append(ident)
    atts: dict[str, tuple[int, int]] = {}
    for mid, n, hashed in conn.execute(
        "SELECT message_id, COUNT(*), COUNT(sha256) FROM attachments WHERE source_id = ?"
        " GROUP BY message_id",
        (src,),
    ):
        atts[mid] = (n, hashed)

    body = check("messages", "body", "message text, exactly as written in report.xml")
    ts_raw = check("messages", "time_as_written", "time value kept exactly as written")
    ts_utc = check(
        "messages", "time_utc", "UTC time, for ISO 8601 times with an offset (read separately)"
    )
    sender = check("messages", "sender", "stated sender's identifier (else name)")
    to = check("messages", "recipients", "every stated recipient is among Mabillon's recipients")
    direction = check(
        "messages",
        "direction",
        "stated Direction, else outgoing from the phone's owner and incoming to them",
    )
    state = check("messages", "record_state", "deleted_state Intact or Deleted/Trash")
    att = check("messages", "attachments", "number of attachments with a name or a file")
    att_files = check("messages", "attachment_files_hashed", "attachment files in the package")
    db_msgs: set[str] = set()
    for mid, loc, b, raw, utc, flag, dirn, ident, _dev in rows:
        if ufdr.EMBEDDED_STEP in loc:
            # a message embedded in another, imported as its own record: not one of the
            # package's own records, so not compared here (the coverage count
            # embedded_messages_imported lists how many)
            continue
        db_msgs.add(loc)
        x = t.messages.get(loc)
        if x is None:
            continue
        body.see(_digest(b) == x.body, loc)
        ts_raw.see(_same_raw(raw, x.ts_raw), loc)
        want = iso_utc(x.ts_raw)
        if want is not None:
            ts_utc.see(_same_utc(want, utc), loc)
        else:
            ts_utc.not_checked += 1
        if x.sender is not None:
            sender.see(ident == x.sender, loc)
        else:
            sender.not_checked += 1
        if x.recipients:
            got = set(recips.get(mid, []))
            to.see(all(r in got for r in x.recipients), loc)
        else:
            to.not_checked += 1
        stated = message_direction(x)
        if stated is not None:
            direction.see(dirn == stated, loc)
        elif x.sender is not None and (x.sender_owner or x.sender in t.owner_ids):
            direction.see(dirn == "outgoing", loc)
        elif x.sender is not None and (
            x.recipient_owner or any(r in t.owner_ids for r in x.recipients)
        ):
            direction.see(dirn == "incoming", loc)
        else:
            direction.not_checked += 1
        f = state_flag(x.state)
        if f is not None:
            state.see(flag == f, loc)
        else:
            state.not_checked += 1
        n, hashed = atts.get(mid, (0, 0))
        att.see(n == x.attachments, loc)
        if x.attachment_files:
            att_files.see(hashed == x.attachment_files, loc)
        else:
            att_files.not_checked += 1

    # calls -----------------------------------------------------------------
    crow = conn.execute(
        "SELECT c.locator, c.ts_raw, c.ts_utc, c.duration_s, c.direction, c.deleted_flag,"
        " f.identifier, t.identifier FROM calls c"
        " LEFT JOIN accounts f ON f.id = c.from_account_id"
        " LEFT JOIN accounts t ON t.id = c.to_account_id WHERE c.source_id = ?",
        (src,),
    ).fetchall()
    c_raw = check("calls", "time_as_written", "time value kept exactly as written")
    c_utc = check("calls", "time_utc", "UTC time, for ISO 8601 times with an offset")
    c_dur = check("calls", "duration", "duration in seconds (whole seconds, or [d.]hh:mm:ss)")
    c_dir = check("calls", "direction", "stated Direction or Type: Incoming, Outgoing, Missed")
    c_from = check("calls", "caller", "stated caller's identifier (else name)")
    c_to = check("calls", "callee", "stated callee's identifier (else name)")
    c_state = check("calls", "record_state", "deleted_state Intact or Deleted/Trash")
    db_calls: set[str] = set()
    for loc, raw, utc, dur, dirn, flag, fid, tid in crow:
        db_calls.add(loc)
        x = t.calls.get(loc)
        if x is None:
            continue
        c_raw.see(_same_raw(raw, x.ts_raw), loc)
        want = iso_utc(x.ts_raw)
        if want is not None:
            c_utc.see(_same_utc(want, utc), loc)
        else:
            c_utc.not_checked += 1
        secs = seconds(x.duration_raw)
        if secs is not None:
            c_dur.see(dur == secs, loc)
        else:
            c_dur.not_checked += 1
        stated = (x.direction or "").lower().split(" ")[0]
        if stated in ("incoming", "outgoing", "missed"):
            c_dir.see(dirn == stated, loc)
        else:
            c_dir.not_checked += 1
        for chk, want_id, got in ((c_from, x.sender, fid), (c_to, x.recipient, tid)):
            if want_id is not None:
                chk.see(got == want_id, loc)
            else:
                chk.not_checked += 1
        f = state_flag(x.state)
        if f is not None:
            c_state.see(flag == f, loc)
        else:
            c_state.not_checked += 1

    # contacts --------------------------------------------------------------
    k_entries = check("contacts", "entries", "one Mabillon row per distinct entry value")
    k_name = check("contacts", "name", "contact name")
    db_contacts: set[str] = set()
    names: dict[str, list[str | None]] = {}
    for loc, name in conn.execute("SELECT locator, name FROM contacts WHERE source_id = ?", (src,)):
        names.setdefault(loc, []).append(name)
    for loc, stored in names.items():
        db_contacts.add(loc)
        x = t.contacts.get(loc)
        if x is None:
            continue
        k_entries.see(len(stored) == max(1, x.entries), loc)
        k_name.see(all(_digest(n) == x.name for n in stored), loc)

    accounts: set[str] = set()
    acct_ident = check(
        "phone's own accounts",
        "identifier",
        "Username, else the first UserID entry, else the first entry that is not a picture",
    )
    for loc, ident in conn.execute(
        "SELECT locator, identifier FROM accounts WHERE source_id = ? AND locator LIKE"
        " 'UserAccount[%'",
        (src,),
    ):
        accounts.add(loc)
        if (want := t.user_accounts.get(loc)) is not None:
            acct_ident.see(ident == want, loc)
    counts = [
        _counts("messages", t.messages, db_msgs, t.repeats),
        _counts("calls", t.calls, db_calls, t.repeats),
        _counts("contacts", t.contacts, db_contacts, set()),
        _counts("phone's own accounts (UserAccount)", t.user_accounts, accounts, set()),
    ]
    xml_atts = sum(m.attachments for m in t.messages.values() if m.locator in db_msgs)
    (db_atts,) = conn.execute(
        "SELECT COUNT(*) FROM attachments WHERE source_id = ?", (src,)
    ).fetchone()
    counts.append(Count("attachments", xml_atts, db_atts, 0, [], []))
    return counts, checks


# ---------------------------------------------------------------- running it


def run(package: Path, sample_size: int = 20, date_order: str | None = None) -> Result:
    """Check one UFDR package. Raises ValueError only when it is not a readable UFDR at all."""
    with open_input(package) as raw:
        if not zipfile.is_zipfile(raw):
            raise ValueError(f"{package.name} is not a zip package, so it is not a UFDR")
    with open_input(package) as raw, zipfile.ZipFile(raw) as z:
        report = ufdr.find_report(z)
        members = {_member(i.filename) for i in z.infolist() if not i.is_dir() and i is not report}
        tally = Tally(members)
        with z.open(report) as f:
            tally.read(f)
        n_files, report_bytes = len(members), report.file_size

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    import_error = None
    coverage: dict[str, object] = {}
    try:
        ufdr.UfdrImporter(source_id=SOURCE_ID, date_order=date_order).import_source(package, conn)
        row = conn.execute(
            "SELECT payload_json FROM source_coverage WHERE source_id = ?", (SOURCE_ID,)
        ).fetchone()
        coverage = json.loads(row[0]) if row else {}
    except ValueError as e:
        import_error = str(e)
    counts, checks = compare(tally, conn, SOURCE_ID)
    sample = _sample(tally, conn, SOURCE_ID, sample_size)
    conn.close()
    shareable = _shareable(tally, counts, checks, coverage, import_error, n_files, report_bytes)
    return Result(shareable, sample, import_error)


_REFUSALS = (
    ("not well-formed", "report.xml is not well-formed XML"),
    ("root element", "report.xml's root element is not 'project'"),
    ("document type", "report.xml declares a document type"),
    ("entity", "report.xml declares an entity"),
    ("more than one device", "the package holds extractions from more than one device"),
    ("on the first read", "the two reads of report.xml counted different records"),
    ("changed while", "the package changed while it was read"),
)


def _refusal(msg: str) -> str:
    """The importer's refusal without its details (which can name the device)."""
    for needle, text in _REFUSALS:
        if needle in msg:
            return text
    return "Mabillon's importer refused the package (the reason is in the private file)"


def _shareable(
    t: Tally,
    counts: list[Count],
    checks: list[Check],
    cov: dict[str, object],
    import_error: str | None,
    n_files: int,
    report_bytes: int,
) -> dict[str, object]:
    differences = sum(c.differ for c in checks) + sum(len(c.missing) + len(c.extra) for c in counts)
    tables = cov.get("tables", []) if isinstance(cov.get("tables"), list) else []
    unread = {
        _safe_name(tb.get("record_type")): sorted(_safe_name(n) for n in tb["unknown_columns"])
        for tb in tables
        if isinstance(tb, dict) and tb.get("unknown_columns")
    }
    flags = {
        _safe_name(tb.get("record_type")): {_safe_name(k): v for k, v in tb["flag_counts"].items()}
        for tb in tables
        if isinstance(tb, dict) and tb.get("flag_counts")
    }
    time_problems = {
        _safe_name(tb.get("record_type")): dict(tb["time_problems"])
        for tb in tables
        if isinstance(tb, dict) and tb.get("time_problems")
    }
    not_imported = [
        {"type": _safe_name(str(x.get("name"))), "records": x.get("records"),
         "reason": str(x.get("reason"))}
        for x in cov.get("not_imported", []) or []
        if isinstance(x, dict)
    ]  # fmt: skip
    counters = cov.get("counts", {}) if isinstance(cov.get("counts"), dict) else {}
    tool = t.meta_values.get("ufedphysicalanalyzerversion") or t.meta_values.get(
        "physicalanalyzerversion"
    )
    version = t.project_attrs.get("reportVersion")
    return {
        "baker_ufdr_check": CHECK_VERSION,
        "importer": f"{ufdr.IMPORTER_NAME} {ufdr.IMPORTER_VERSION}",
        "format_support": ufdr.FORMAT_SUPPORT,
        "checked_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "differences": differences,
        "imported": import_error is None,
        "import_refused_because": _refusal(import_error) if import_error else None,
        "package": {
            "files_besides_report": n_files,
            "report_xml_bytes": report_bytes,
            "root_element": _safe_name(t.root),
            "namespace_known": t.namespace == ufdr.KNOWN_NAMESPACE,
            "report_version": version
            if version and _VERSION.fullmatch(version)
            else (f"(shape {shape(version)})" if version else None),
            "physical_analyzer_version": tool
            if tool and _VERSION.fullmatch(tool)
            else (f"(shape {shape(tool)})" if tool else None),
            "extraction_types": {
                _enum_value(k) if k else "(none)": v for k, v in sorted(t.extraction_types.items())
            },
            "partial_extractions": t.partial_extractions,
            "metadata_items": t.metadata_items,
            "metadata_baker_reads_found": sorted(
                k
                for k, aliases in ufdr.META_KEYS.items()
                if any(a in t.metadata_names for a in aliases)
            ),
            "tagged_files": t.tagged_files,
        },  # fmt: skip
        "records": [c.as_dict() for c in counts],
        "checks": [c.as_dict() for c in checks],
        "value_shapes": {
            _safe_label(k): dict(v.most_common(MAX_SHAPES)) for k, v in sorted(t.shapes.items())
        },
        "values": {
            _safe_label(k): dict(v.most_common(MAX_SHAPES)) for k, v in sorted(t.enums.items())
        },
        "model_kinds": {
            _safe_label(k): {
                "count": kd.count,
                "fields": {_safe_field(n): c for n, c in kd.fields.most_common(MAX_SCHEMA_FIELDS)},
                "attributes": {_safe_name(n): c for n, c in sorted(kd.attributes.items())},
                "other_elements": {_safe_name(n): c for n, c in sorted(kd.other_elements.items())},
                "value_types": {
                    _safe_field(n): c for n, c in kd.value_types.most_common(MAX_SCHEMA_FIELDS)
                },
                "value_attributes": {
                    _safe_name(n): c for n, c in sorted(kd.value_attributes.items())
                },
            }
            for k, kd in sorted(t.kinds.items())
        },
        "baker_coverage": {
            "types_not_imported": not_imported,
            "fields_baker_does_not_read": unread,
            "records_listed_for_review": flags,
            "time_problems": time_problems,
            "counters": {
                _safe_name(k): v for k, v in sorted(counters.items()) if isinstance(v, int)
            },
            "record_states_seen": {
                _enum_value(k): v
                for k, v in (cov.get("ufdr", {}) or {}).get("deleted_state_values", {}).items()
            }
            if isinstance(cov.get("ufdr"), dict)
            else {},
        },  # fmt: skip
    }


def safe_locator(loc: str) -> str:
    """'Chat[3]/Messages[17]' as written; a model type or field name in it that does not look
    like a schema name becomes its shape."""
    return re.sub(r"[^/\[\]]+(?=\[)", lambda m: _safe_name(m.group(0)), loc)


def _safe_label(label: str) -> str:
    """'Chat.Messages>InstantMessage.TimeStamp@deleted_state': each name part made safe."""
    return re.sub(r"[^.>@]+", lambda m: _safe_name(m.group(0)), label)


def _safe_field(label: str) -> str:
    """'Body (field)' or 'TimeStamp: TimeStamp': each name part made safe."""
    m = re.fullmatch(r"(.*) \((\w+)\)", label)
    if m:
        return f"{_safe_name(m.group(1))} ({m.group(2)})"
    a, sep, b = label.partition(": ")
    return f"{_safe_name(a)}{sep}{_safe_name(b) if b else ''}"


# ---------------------------------------------------------------- the private sample


def _sample(t: Tally, conn: sqlite3.Connection, src: str, n: int) -> list[dict[str, object]]:
    """Up to n records of each kind, picked with a fixed seed, with what Mabillon stored."""
    rng = random.Random(20261014)  # noqa: S311 - a reproducible sample, not a secret
    out: list[dict[str, object]] = []
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM messages WHERE source_id = ? ORDER BY id", (src,)
    )]  # fmt: skip
    picked = [
        conn.execute(
            "SELECT m.id, m.locator, m.ts_utc, m.ts_offset_min, m.ts_raw, m.direction,"
            " m.deleted_flag, m.body, a.identifier, a.display_name, th.app FROM messages m"
            " LEFT JOIN accounts a ON a.id = m.sender_account_id"
            " LEFT JOIN threads th ON th.id = m.thread_id WHERE m.id = ?",
            (i,),
        ).fetchone()
        for i in rng.sample(ids, min(n, len(ids)))
    ]
    for row in sorted(picked, key=lambda r: _loc_key(r[1])):
        mid, loc, utc, off, raw, dirn, flag, body, ident, name, app = row
        to = [
            r[0] or r[1]
            for r in conn.execute(
                "SELECT a.identifier, a.display_name FROM message_recipients r"
                " JOIN accounts a ON a.id = r.account_id WHERE r.message_id = ?",
                (mid,),
            )
        ]
        files = [
            r[0]
            for r in conn.execute("SELECT file_name FROM attachments WHERE message_id = ?", (mid,))
        ]
        x = t.messages.get(loc)
        out.append(
            {
                "kind": "message",
                "locator": loc,
                "model_id": x.model_id if x else None,
                "app": app,
                "time_utc": utc,
                "offset_min": off,
                "time_as_written": raw,
                "from": " ".join(v for v in (ident, name) if v) or None,
                "to": ", ".join(to) or None,
                "direction": dirn,
                "deleted_flag": flag,
                "text": (body or "")[:80],
                "attachments": ", ".join(files) or None,
            }
        )
    calls = conn.execute(
        "SELECT c.locator, c.app, c.ts_utc, c.ts_offset_min, c.ts_raw, c.direction,"
        " c.duration_s, c.deleted_flag, f.identifier, t.identifier FROM calls c"
        " LEFT JOIN accounts f ON f.id = c.from_account_id"
        " LEFT JOIN accounts t ON t.id = c.to_account_id WHERE c.source_id = ? ORDER BY c.id",
        (src,),
    ).fetchall()
    for row in sorted(rng.sample(calls, min(n, len(calls))), key=lambda r: _loc_key(r[0])):
        loc, app, utc, off, raw, dirn, dur, flag, frm, to_ = row
        x = t.calls.get(loc)
        out.append(
            {
                "kind": "call",
                "locator": loc,
                "model_id": x.model_id if x else None,
                "app": app,
                "time_utc": utc,
                "offset_min": off,
                "time_as_written": raw,
                "from": frm,
                "to": to_,
                "direction": dirn,
                "duration_s": dur,
                "deleted_flag": flag,
            }
        )
    contacts = conn.execute(
        "SELECT locator, MIN(name), GROUP_CONCAT(identifier, ', ') FROM contacts"
        " WHERE source_id = ? GROUP BY locator ORDER BY locator",
        (src,),
    ).fetchall()
    for loc, name, idents in sorted(
        rng.sample(contacts, min(n, len(contacts))), key=lambda r: _loc_key(r[0])
    ):
        out.append({"kind": "contact", "locator": loc, "name": name, "entries": idents})
    return out


# ---------------------------------------------------------------- writing


def write(result: Result, out_dir: Path) -> list[Path]:
    """The shareable Markdown and JSON, and the private sample. Never overwrites a file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / SHAREABLE_MD, out_dir / SHAREABLE_JSON, out_dir / PRIVATE_MD]
    for p in paths:
        if p.exists():
            raise ValueError(f"{p} already exists; choose an empty folder for the check")
    paths[0].write_text(shareable_markdown(result.shareable), encoding="utf-8")
    paths[1].write_text(json.dumps(result.shareable, indent=2, sort_keys=True), encoding="utf-8")
    paths[2].write_text(private_markdown(result), encoding="utf-8")
    return paths


def _cell(v: object) -> str:
    s = "" if v is None else str(v)
    return s.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def shareable_markdown(d: dict) -> str:
    pkg = d["package"]
    lines = [
        "# Mabillon UFDR self-check",
        "",
        "**Shareable.** This file holds counts, field names, record positions and value shapes "
        "only: no message text, names, numbers, file names or device details. Read it before "
        "you send it.",
        "",
        f"- Check {d['baker_ufdr_check']}, importer {d['importer']} "
        f"(format support: {d['format_support']}), run {d['checked_at_utc']}",
        f"- Differences found: **{d['differences']}**"
        + (
            ""
            if d["imported"]
            else f" (Mabillon refused the package: {d['import_refused_because']})"
        ),
        f"- Package: {pkg['files_besides_report']} files besides report.xml, report.xml "
        f"{pkg['report_xml_bytes']} bytes, report version {pkg['report_version']}, "
        f"Physical Analyzer {pkg['physical_analyzer_version']}, "
        f"namespace {'known' if pkg['namespace_known'] else 'NOT the one Mabillon expects'}",
        f"- Extractions: {_inline(pkg['extraction_types'])}; partial: "
        f"{pkg['partial_extractions']}; tagged files: {pkg['tagged_files']}",
        "",
        "## Records: report.xml against Mabillon",
        "",
        "| Record | In report.xml | Imported by Mabillon | Repeats imported once | Missing "
        "| Extra |",
        "|---|---|---|---|---|---|",
    ]
    for r in d["records"]:
        lines.append(
            f"| {r['record']} | {r['in_report_xml']} | {r['imported_by_baker']} | "
            f"{r['repeats_imported_once']} | {r['missing']} | {r['extra']} |"
        )
    for r in d["records"]:
        for key, label in (("first_missing_locators", "missing"), ("first_extra_locators",
                                                                     "extra")):  # fmt: skip
            if r[key]:
                lines.append(f"\nFirst {label} {r['record']}: {', '.join(r[key])}")
    lines += [
        "",
        "## Field checks, record by record",
        "",
        "| Record | Check | Compared | Differ | Not checked | First differing |",
        "|---|---|---|---|---|---|",
    ]
    for c in d["checks"]:
        lines.append(
            f"| {c['record']} | {c['what']} | {c['compared']} | {c['differ']} | "
            f"{c['not_checked']} | {', '.join(c['first_differing_locators'])} |"
        )
    lines += [
        "",
        "## Compared in Cellebrite Reader (fill in)",
        "",
        "Copy the totals from ufdr-check-private.md.",
        "",
        "| Record | Count Cellebrite Reader shows | Records opened | Matched | Differed |",
        "|---|---|---|---|---|",
        "| Chats (messages) |  |  |  |  |",
        "| SMS / MMS |  |  |  |  |",
        "| Calls |  |  |  |  |",
        "| Contacts |  |  |  |  |",
        "",
        "What differed, in your words (no case content):",
        "",
        "",
        "## What Mabillon did not read",
        "",
    ]
    cov = d["baker_coverage"]
    for x in cov["types_not_imported"]:
        lines.append(f"- {x['type']}: {x['records']} records ({x['reason']})")
    for k, names in cov["fields_baker_does_not_read"].items():
        lines.append(f"- {k} fields not read: {', '.join(names)}")
    for k, v in cov["records_listed_for_review"].items():
        lines.append(f"- {k} records listed for review: {_inline(v)}")
    for k, v in cov["time_problems"].items():
        lines.append(f"- {k} times without a UTC instant: {_inline(v)}")
    if cov["record_states_seen"]:
        lines.append(f"- Record states seen: {_inline(cov['record_states_seen'])}")
    lines += ["", "## Value shapes", ""]
    for k, v in d["value_shapes"].items():
        lines.append(f"- {k}: {_inline(v)}")
    lines += ["", "## Values of fixed-vocabulary fields", ""]
    for k, v in d["values"].items():
        lines.append(f"- {k}: {_inline(v)}")
    lines += ["", "## Model kinds in report.xml", ""]
    for k, kd in d["model_kinds"].items():
        lines.append(f"### {k} ({kd['count']})")
        lines.append(f"- fields: {_inline(kd['fields'])}")
        if kd["other_elements"]:
            lines.append(f"- other elements: {_inline(kd['other_elements'])}")
        lines.append(f"- attributes: {_inline(kd['attributes'])}")
        lines.append(f"- value types: {_inline(kd['value_types'])}")
        lines.append("")
    lines.append("The same content, for a program, is in ufdr-check.json.")
    return "\n".join(lines) + "\n"


def _inline(d: dict) -> str:
    return ", ".join(f"{_cell(k)} {v}" for k, v in d.items()) or "none"


def private_markdown(result: Result) -> str:
    lines = [
        "# Mabillon UFDR self-check: records to compare in Cellebrite Reader",
        "",
        "**PRIVATE. This file holds case content. Keep it on this computer; do not send it.**",
        "",
        "1. Open the same UFDR in Cellebrite Reader.",
        "2. For each record below, find it in Reader (by time and party) and compare sender, "
        "recipients, time and offset, text, deleted state and attachments.",
        "3. Mark each row yes or no, and note what differed.",
        "4. Copy the totals, and the counts Reader shows per category, into ufdr-check.md.",
        "",
        "The locator is the record's position in report.xml: `Chat[3]/Messages[17]` is the 17th "
        "message of the 3rd chat.",
        "",
    ]
    if result.import_error:
        lines += [f"Mabillon refused the package: {result.import_error}", ""]
    groups: dict[str, list[dict[str, object]]] = {}
    for rec in result.sample:
        groups.setdefault(str(rec["kind"]), []).append(rec)
    for kind, recs in groups.items():
        keys = [k for k in recs[0] if k != "kind"]
        lines += [f"## {kind.capitalize()}s ({len(recs)})", ""]
        lines.append("| " + " | ".join(keys) + " | Matches Reader? | What differed |")
        lines.append("|" + "---|" * (len(keys) + 2))
        for rec in recs:
            lines.append("| " + " | ".join(_cell(rec[k]) for k in keys) + " |  |  |")
        lines.append("")
    if not groups:
        lines.append("Mabillon imported no records to sample.")
    return "\n".join(lines) + "\n"
