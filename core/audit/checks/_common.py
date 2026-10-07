"""Shared plumbing for the deterministic checks: parties, records, sources and local time.

Nothing here decides an outcome. It finds rows and converts times; each check states what it
searched and decides pass, fail or inconclusive on its own terms.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.audit.quotes import find_quote
from core.contracts import (
    AssumptionParams,
    CheckOutcome,
    CheckResult,
    Fidelity,
    TimeWindow,
    check_id,
)

# Accounts are matched across phones by (namespace, identifier). SMS and phone calls share a
# number space; every other app is its own.
_TEL_APPS = {"sms", "mms", "phone", "call", "calls", "imessage", "rcs"}
CALL_CHANNEL = "call"

type Key = tuple[str, str]


def namespace(app: str) -> str:
    a = app.strip().lower()
    return "tel" if a in _TEL_APPS else a


def norm_identifier(ns: str, identifier: str) -> str:
    ident = unicodedata.normalize("NFC", identifier.strip())
    if ns == "tel":
        return re.sub(r"[\s().\-]", "", ident)
    return ident.lower() if ns in {"instagram", "email"} else ident


def key(app: str, identifier: str) -> Key:
    ns = namespace(app)
    return ns, norm_identifier(ns, identifier)


def fmt_key(k: Key) -> str:
    return f"{k[0]} {k[1]}"


def _same_text(a: str | None, b: str) -> bool:
    if a is None:
        return False
    return unicodedata.normalize("NFC", a.strip()) == unicodedata.normalize("NFC", b.strip())


# ---------------------------------------------------------------- case data


@dataclass(frozen=True)
class SourceInfo:
    id: str
    fidelity: Fidelity
    tz: str | None  # the phone's zone (devices.timezone), if the source said
    device_ids: tuple[str, ...]


@dataclass(frozen=True)
class Account:
    id: str
    source_id: str
    device_id: str | None  # set only on the phone's own accounts
    app: str
    identifier: str
    display_name: str | None

    @property
    def key(self) -> Key:
        return key(self.app, self.identifier)

    @property
    def is_owner(self) -> bool:
        return self.device_id is not None


class CaseData:
    """Small lookups, loaded once per check run. Read-only."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        devices: dict[str, list[tuple[str, str | None]]] = {}
        for did, sid, tz in conn.execute("SELECT id, source_id, timezone FROM devices ORDER BY id"):
            devices.setdefault(sid, []).append((did, tz))
        self.sources: dict[str, SourceInfo] = {}
        for sid, fidelity in conn.execute(
            "SELECT id, fidelity FROM sources WHERE kind != 'govdoc' ORDER BY id"
        ):
            devs = devices.get(sid, [])
            tz = next((t for _, t in devs if t), None)
            self.sources[sid] = SourceInfo(sid, Fidelity(fidelity), tz, tuple(d for d, _ in devs))
        self.accounts: dict[str, Account] = {
            r[0]: Account(*r)
            for r in conn.execute(
                "SELECT id, source_id, device_id, app, identifier, display_name FROM accounts"
            )
        }
        self.has_sender_raw = any(
            r[1] == "sender_raw" for r in conn.execute("PRAGMA table_info(messages)")
        )
        self.stipulations: list[tuple[str, str, str, str]] = []  # (id, device, person, status)
        if "stipulations" in tables:
            self.stipulations = list(
                conn.execute(
                    "SELECT id, subject_id, person_id, status FROM stipulations"
                    " WHERE kind = 'device_owner' ORDER BY id"
                )
            )
        self.links: list[tuple[str, str, str]] = list(  # (link id, account, person)
            conn.execute(
                "SELECT id, account_id, person_id FROM identity_links WHERE status = 'confirmed'"
                " ORDER BY id"
            )
        )

    def account_ids(self, keys: Iterable[Key]) -> set[str]:
        wanted = set(keys)
        return {a.id for a in self.accounts.values() if a.key in wanted}

    def sources_for(self, device_ids: Iterable[str]) -> list[str]:
        """Sources holding these devices; every evidence source if none are named."""
        wanted = set(device_ids)
        if not wanted:
            return list(self.sources)
        return [s.id for s in self.sources.values() if wanted & set(s.device_ids)]

    def tz_for(self, source_id: str) -> ZoneInfo | None:
        source = self.sources.get(source_id)
        if source is None or source.tz is None:
            return None
        try:
            return ZoneInfo(source.tz)
        except (ZoneInfoNotFoundError, ValueError):
            return None


# ---------------------------------------------------------------- parties


@dataclass
class Party:
    label: str
    keys: set[Key] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)  # how each key was found
    record_ids: list[str] = field(default_factory=list)  # rows a handle resolution relied on

    def describe(self) -> str:
        ids = ", ".join(sorted(fmt_key(k) for k in self.keys)) or "no accounts"
        return f"{self.label} ({ids})"


def person_party(data: CaseData, person_id: str) -> Party:
    """A person's accounts: the owner accounts of each phone an expert-confirmed device_owner
    stipulation gives them, plus accounts an expert confirmed as theirs. A proposed
    stipulation is not ownership yet: it is named in the notes and never used."""
    out = Party(person_id)
    for stip_id, device_id, pid, status in data.stipulations:
        if pid != person_id:
            continue
        if status != "confirmed":
            out.notes.append(
                f"stipulation {stip_id} ({device_id}) is {status}, not confirmed, so it is not used"
            )
            continue
        owned = [a for a in data.accounts.values() if a.device_id == device_id]
        out.keys.update(a.key for a in owned)
        out.notes.append(
            f"{person_id} = owner accounts of {device_id}, per confirmed stipulation {stip_id}"
        )
    for link_id, account_id, pid in data.links:
        acc = data.accounts.get(account_id)
        if pid == person_id and acc is not None:
            out.keys.add(acc.key)
            out.notes.append(f"{person_id} uses {fmt_key(acc.key)}, per confirmed link {link_id}")
    if not out.keys:
        out.notes.append(
            f"no confirmed stipulation or confirmed link ties {person_id} to any account"
        )
    return out


def account_party(data: CaseData, account_ids: Iterable[str]) -> Party:
    ids = list(account_ids)
    out = Party("/".join(ids))
    for aid in ids:
        acc = data.accounts.get(aid)
        if acc is None:
            out.notes.append(f"account {aid} is not in this case")
        else:
            out.keys.add(acc.key)
    return out


def parties(data: CaseData, p: AssumptionParams) -> list[Party]:
    """Each person is one party; all account ids and handles together are one more.

    A handle joins the party only if the data resolves it to exactly one account, on the one
    app named in channels if there is one. Otherwise the whole party is left without accounts,
    so the check comes out inconclusive rather than searching the wrong account.
    """
    out = [person_party(data, pid) for pid in p.person_ids]
    if p.account_ids or p.handles:
        party = account_party(data, p.account_ids)
        apps = [c for c in p.channels if c.strip().lower() != CALL_CHANNEL]
        app = apps[0] if len(apps) == 1 else None
        unresolved = False
        for h in p.handles:
            r = resolve_handle(data, h, app)
            party.notes += r.notes
            party.record_ids += r.record_ids
            if len(r.keys) == 1:
                party.keys |= r.keys
            else:
                unresolved = True
                party.notes.append(f'"{h}" does not resolve to exactly one account')
        if unresolved:
            party.keys.clear()
        party.label = "/".join((*p.account_ids, *p.handles))
        out.append(party)
    return out


def resolve_handle(data: CaseData, handle: str, app: str | None) -> Party:
    """Accounts a display name was seen on, and where. A handle is a name, not an identity:
    this reports every account it was seen on, and how."""
    out = Party(handle)
    ns_wanted = namespace(app) if app else None

    def take(acc: Account, how: str, rid: str) -> None:
        if acc.is_owner or (ns_wanted is not None and namespace(acc.app) != ns_wanted):
            return
        if acc.key not in out.keys:
            out.notes.append(f'"{handle}" -> {fmt_key(acc.key)} ({how})')
        out.keys.add(acc.key)
        out.record_ids.append(rid)

    for acc in data.accounts.values():
        if _same_text(acc.display_name, handle):
            take(acc, f"account name in {acc.source_id}", acc.id)
    # A thread titled with the handle: its non-owner participants carry that name.
    for tid, title in data.conn.execute(
        "SELECT id, title FROM threads WHERE title IS NOT NULL ORDER BY id"
    ):
        if not _same_text(title, handle):
            continue
        for (aid,) in data.conn.execute(
            "SELECT sender_account_id FROM messages WHERE thread_id = ?"
            " AND sender_account_id IS NOT NULL"
            " UNION SELECT r.account_id FROM message_recipients r"
            " JOIN messages m ON m.id = r.message_id WHERE m.thread_id = ? ORDER BY 1",
            (tid, tid),
        ):
            acc = data.accounts.get(aid)
            if acc is not None:
                take(acc, f"participant of thread {tid}, titled {title!r}", tid)
    # The sender text a report printed on each row, where the importer kept it.
    if data.has_sender_raw:
        for mid, aid, raw in data.conn.execute(
            "SELECT id, sender_account_id, sender_raw FROM messages"
            " WHERE sender_raw IS NOT NULL AND sender_account_id IS NOT NULL ORDER BY id"
        ):
            acc = data.accounts.get(aid)
            if acc is not None and _ends_with_name(raw, handle):
                take(acc, f"sender shown as {raw!r}", mid)
    # A saved contact with that name. Contact lists do not say which app an entry is for, so
    # only phone numbers are taken, and only into the phone-number space.
    for cid, name, ident in data.conn.execute(
        "SELECT id, name, identifier FROM contacts ORDER BY id"
    ):
        if _same_text(name, handle) and ident.strip().startswith("+"):
            k = key("Phone", ident)
            if ns_wanted is None or k[0] == ns_wanted:
                if k not in out.keys:
                    out.notes.append(f'"{handle}" -> {fmt_key(k)} (saved contact {cid})')
                out.keys.add(k)
                out.record_ids.append(cid)
    if not out.keys:
        out.notes.append(f'"{handle}" matched no account, thread, sender or contact')
    return out


def _ends_with_name(raw: str, handle: str) -> bool:
    raw_n = unicodedata.normalize("NFC", raw.strip())
    h = unicodedata.normalize("NFC", handle.strip())
    return raw_n == h or raw_n.endswith(" " + h)


# ---------------------------------------------------------------- records


@dataclass(frozen=True)
class Row:
    """A message or call, reduced to what the checks compare."""

    id: str
    kind: str  # 'message' or 'call'
    source_id: str
    app: str
    sender: str | None  # account id (calls: the calling side)
    recipients: tuple[str, ...]
    ts_utc: datetime | None
    ts_raw: str | None
    text: str | None
    duration_s: int | None = None
    deleted: bool | None = None

    @property
    def accounts(self) -> set[str]:
        return {a for a in (self.sender, *self.recipients) if a}


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


_MSG_SQL = (
    "SELECT m.id, m.source_id, t.app, m.sender_account_id, m.ts_utc, m.ts_raw, m.body,"
    " m.deleted_flag, (SELECT json_group_array(r.account_id) FROM message_recipients r"
    " WHERE r.message_id = m.id)"
    " FROM messages m JOIN threads t ON t.id = m.thread_id"
)


def _message_row(r: tuple) -> Row:
    mid, sid, app, sender, ts, raw, body, deleted, recips = r
    return Row(
        id=mid,
        kind="message",
        source_id=sid,
        app=app,
        sender=sender,
        recipients=tuple(json.loads(recips or "[]")),
        ts_utc=_ts(ts),
        ts_raw=raw,
        text=body,
        deleted=None if deleted is None else bool(deleted),
    )


def messages_for_accounts(data: CaseData, account_ids: set[str]) -> list[Row]:
    """Every message an account in the set sent or received, across all sources."""
    if not account_ids:
        return []
    ids = json.dumps(sorted(account_ids))
    rows = data.conn.execute(
        _MSG_SQL  # noqa: S608  (constant SQL; values are bound)
        + " WHERE m.sender_account_id IN (SELECT value FROM json_each(?))"
        " OR m.id IN (SELECT r.message_id FROM message_recipients r"
        "  WHERE r.account_id IN (SELECT value FROM json_each(?))) ORDER BY m.id",
        (ids, ids),
    )
    return [_message_row(r) for r in rows]


def messages_with_text(data: CaseData, text: str) -> list[Row]:
    """Messages whose original body contains the text verbatim and word-aligned."""
    rows = data.conn.execute(_MSG_SQL + " WHERE instr(m.body, ?) > 0 ORDER BY m.id", (text,))
    return [row for row in map(_message_row, rows) if find_quote(text, row.text or "")]


def calls_for_accounts(data: CaseData, account_ids: set[str]) -> list[Row]:
    if not account_ids:
        return []
    ids = json.dumps(sorted(account_ids))
    rows = data.conn.execute(
        "SELECT id, source_id, app, from_account_id, to_account_id, ts_utc, ts_raw, duration_s,"
        " deleted_flag FROM calls"
        " WHERE from_account_id IN (SELECT value FROM json_each(?))"
        " OR to_account_id IN (SELECT value FROM json_each(?)) ORDER BY id",
        (ids, ids),
    )
    return [
        Row(
            id=cid,
            kind="call",
            source_id=sid,
            app=app,
            sender=frm,
            recipients=(to,) if to else (),
            ts_utc=_ts(ts),
            ts_raw=raw,
            text=None,
            duration_s=dur,
            deleted=None if deleted is None else bool(deleted),
        )
        for cid, sid, app, frm, to, ts, raw, dur, deleted in rows
    ]


def involves_all(row: Row, party_accounts: list[set[str]]) -> bool:
    """True if every party has an account on the row. Two parties must be on opposite sides
    (one sends, the other receives), so a group message between two others does not count."""
    if len(party_accounts) == 2:
        a, b = party_accounts
        recips = set(row.recipients)
        if row.sender is None:
            return False
        return (row.sender in a and bool(recips & b)) or (row.sender in b and bool(recips & a))
    return all(row.accounts & p for p in party_accounts)


def channel_ok(row: Row, channels: Iterable[str]) -> bool:
    """Empty channels means every channel. 'call' admits every call; an app name admits that
    app's messages and calls."""
    wanted = {c.strip().lower() for c in channels}
    if not wanted:
        return True
    if row.kind == "call" and CALL_CHANNEL in wanted:
        return True
    return row.app.strip().lower() in wanted


# ---------------------------------------------------------------- time


def in_window(ts: datetime, window: TimeWindow) -> bool:
    """The contract's windows are inclusive at both ends."""
    return window.start_utc <= ts <= window.end_utc


def local_str(data: CaseData, row: Row) -> str:
    """'2026-03-04 21:31:00 EST (printed 3/5/2026 2:31:00 AM(UTC+0))', in the phone's zone."""
    printed = f" (printed {row.ts_raw})" if row.ts_raw else ""
    if row.ts_utc is None:
        return f"no usable time{printed}"
    tz = data.tz_for(row.source_id)
    if tz is None:
        return f"{row.ts_utc:%Y-%m-%d %H:%M:%S} UTC, phone zone unknown{printed}"
    local = row.ts_utc.astimezone(tz)
    return f"{local:%Y-%m-%d %H:%M:%S} {local.tzname()}{printed}"


def window_str(window: TimeWindow) -> str:
    try:
        zone = ZoneInfo(window.tz)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")  # the UTC bounds below are what the checks compare anyway
    start = window.start_utc.astimezone(zone)
    end = window.end_utc.astimezone(zone)
    return (
        f'"{window.raw}" = {start:%Y-%m-%d %H:%M:%S} to {end:%Y-%m-%d %H:%M:%S} {window.tz}'
        f" ({window.start_utc:%Y-%m-%d %H:%M:%S} to {window.end_utc:%Y-%m-%d %H:%M:%S} UTC)"
    )


def zone_notes(data: CaseData, window: TimeWindow, source_ids: Iterable[str]) -> list[str]:
    """Flag a phone whose own zone differs from the zone the window was stated in."""
    out = []
    for sid in source_ids:
        src = data.sources.get(sid)
        if src is None:
            continue
        if src.tz is None:
            out.append(f"{sid} does not say its phone's time zone")
        elif src.tz != window.tz:
            out.append(f"{sid}'s phone is set to {src.tz}, not {window.tz}")
    return out


# ---------------------------------------------------------------- results


def result(
    assumption_id: str,
    name: str,
    version: str,
    outcome: CheckOutcome,
    searched: str,
    detail: str,
    record_ids: Iterable[str] = (),
    source_ids: Iterable[str] = (),
) -> CheckResult:
    return CheckResult(
        id=check_id(assumption_id, name, version),
        assumption_id=assumption_id,
        check_name=name,
        check_version=version,
        outcome=outcome,
        searched=searched,
        record_ids=tuple(dict.fromkeys(record_ids)),
        source_ids=tuple(dict.fromkeys(source_ids)),
        detail=detail,
    )


def sentences(*parts: str | Iterable[str]) -> str:
    """Join fragments into sentences, each ending in one full stop."""
    out: list[str] = []
    for part in parts:
        for s in [part] if isinstance(part, str) else part:
            s = s.strip()
            if s:
                out.append(s if s.endswith((".", "?", "!")) else s + ".")
    return " ".join(out)
