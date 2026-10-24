"""What the expert sees for one match (or any message): the message in its own conversation,
about 20 messages either side, and the related threads between the same participants.

Every line carries its tier. Message text, sender, direction and the UTC time are observed (as
the source recorded them, the time normalized to UTC). The phone's local time is derived from the
UTC time and the phone's time zone (devices.timezone), never from the offset a report printed.
The match itself is derived: deterministic code found and verified it.

Related threads are matched by identifier as the sources show it (a phone number compared by its
digits, a handle or user id compared as written, ignoring case), plus identity links an expert
confirmed. Mabillon never links two different identifiers on its own: proposed identity links do
not count here.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from core.audit.context import context_ids
from core.contracts import ExhibitMatch, ProvenanceTier
from core.enrich.local_time import device_zone, format_local, parse_utc

WINDOW = 20  # messages either side of the matched message
RELATED_CAP = 40  # messages shown per related thread
_PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,}$")


@dataclass(frozen=True)
class Line:
    record_id: str
    source_id: str
    locator: str
    sender: str  # account as the source shows it, "(this phone)" for the phone's own account
    shown_as: str | None  # sender text exactly as the source printed it, when kept
    direction: str
    utc: str  # "2026-03-12 16:15:02 UTC", or "time unknown"
    local: str  # the phone's local time (derived)
    raw: str | None  # the time exactly as the source printed it
    body: str
    tier: ProvenanceTier  # observed for every message line
    is_target: bool = False


@dataclass(frozen=True)
class ThreadInfo:
    id: str
    source_id: str
    file_name: str
    device: str
    app: str
    title: str | None
    messages: int
    first_utc: str | None
    last_utc: str | None


@dataclass(frozen=True)
class Related:
    thread: ThreadInfo
    shared: tuple[str, ...]  # identifiers (or confirmed persons) the two threads share
    lines: tuple[Line, ...]  # messages in the same period as the main context
    nearest: bool  # True if no message fell in that period and the nearest ones are shown
    more: int  # messages in the period beyond RELATED_CAP


@dataclass(frozen=True)
class ContextView:
    record_id: str  # the message shown in context
    thread: ThreadInfo
    lines: tuple[Line, ...]
    before: int  # thread messages before the first line shown
    after: int  # thread messages after the last line shown
    related: tuple[Related, ...]


@dataclass(frozen=True)
class MatchView(ContextView):
    match: ExhibitMatch


def _utc_text(ts_utc: str | None) -> str:
    dt = parse_utc(ts_utc)
    return f"{dt:%Y-%m-%d %H:%M:%S} UTC" if dt else "time unknown"


def message_lines(conn: sqlite3.Connection, ids: list[str], target: str | None) -> list[Line]:
    """One display line per message id, in the order given; target marks one of them."""
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        "SELECT m.id, m.source_id, m.locator, a.app, a.identifier, a.device_id, m.sender_raw,"  # noqa: S608
        " m.direction, m.ts_utc, m.ts_raw, m.body, t.device_id FROM messages m"
        " JOIN threads t ON t.id = m.thread_id"
        " LEFT JOIN accounts a ON a.id = m.sender_account_id"
        f" WHERE m.id IN ({marks})",
        ids,
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    zones: dict[str | None, object] = {}
    out = []
    for rid in ids:
        r = by_id[rid]
        _, src, loc, app, ident, own_dev, shown, direction, ts_utc, ts_raw, body, dev = r
        if dev not in zones:
            zones[dev] = device_zone(conn, dev)
        sender = f"{app} {ident}" + (" (this phone)" if own_dev else "") if ident else "unknown"
        out.append(
            Line(
                record_id=rid,
                source_id=src,
                locator=loc,
                sender=sender,
                shown_as=shown,
                direction=direction,
                utc=_utc_text(ts_utc),
                local=format_local(parse_utc(ts_utc), zones[dev], ts_raw),  # type: ignore[arg-type]
                raw=ts_raw,
                body=body,
                tier=ProvenanceTier.OBSERVED,
                is_target=rid == target,
            )
        )
    return out


def thread_info(conn: sqlite3.Connection, thread_id: str) -> ThreadInfo | None:
    r = conn.execute(
        "SELECT t.id, t.source_id, s.file_name, coalesce(d.label, t.device_id, '?'), t.app,"
        " t.title, (SELECT COUNT(*) FROM messages m WHERE m.thread_id = t.id),"
        " (SELECT MIN(ts_utc) FROM messages m WHERE m.thread_id = t.id),"
        " (SELECT MAX(ts_utc) FROM messages m WHERE m.thread_id = t.id)"
        " FROM threads t JOIN sources s ON s.id = t.source_id"
        " LEFT JOIN devices d ON d.id = t.device_id WHERE t.id = ?",
        (thread_id,),
    ).fetchone()
    return ThreadInfo(*r) if r else None


# ---------------------------------------------------------------- related threads


def identifier_key(identifier: str) -> str:
    """How an identifier is compared across sources: a phone number (or a WhatsApp id built
    from one) by its digits, anything else as written, ignoring case and a leading '@'."""
    head = identifier.split("@", 1)[0] if identifier.endswith("whatsapp.net") else identifier
    if _PHONE_RE.match(head):
        return "tel:" + re.sub(r"\D", "", head)
    return "id:" + identifier.strip().lstrip("@").casefold()


def _participants(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Thread id -> identifier keys of everyone who sent or received a message in it, plus
    'person:<id>' for accounts an expert linked to a person."""
    people: dict[str, str] = {
        a: p
        for a, p in conn.execute(
            "SELECT account_id, person_id FROM identity_links WHERE status = 'confirmed'"
        )
    }
    keys: dict[str, set[str]] = {}
    rows = conn.execute(
        "SELECT m.thread_id, a.id, a.identifier FROM messages m"
        " JOIN accounts a ON a.id = m.sender_account_id"
        " UNION SELECT m.thread_id, a.id, a.identifier FROM message_recipients r"
        " JOIN messages m ON m.id = r.message_id JOIN accounts a ON a.id = r.account_id"
    )
    for thread_id, account_id, identifier in rows:
        k = keys.setdefault(thread_id, set())
        k.add(identifier_key(identifier))
        if account_id in people:
            k.add(f"person:{people[account_id]}")
    return keys


def _own_keys(conn: sqlite3.Connection, device_id: str | None) -> set[str]:
    if device_id is None:
        return set()
    return {
        identifier_key(i)
        for (i,) in conn.execute(
            "SELECT identifier FROM accounts WHERE device_id = ?", (device_id,)
        )
    }


def related_threads(
    conn: sqlite3.Connection, thread_id: str, first_utc: str | None, last_utc: str | None
) -> list[Related]:
    """Other threads, on any source, between the same participants.

    A thread on the same phone is related when it shares an identifier other than the phone's
    own accounts. A thread on another source is related when it shares at least two
    identifiers, one of them not this phone's own, so that every thread on the other phone does
    not count merely because the other phone's owner is in this one.
    """
    keys = _participants(conn)
    mine = keys.get(thread_id, set())
    devices = dict(conn.execute("SELECT id, device_id FROM threads"))
    own = _own_keys(conn, devices.get(thread_id))
    counterparts = mine - own
    out: list[Related] = []
    for other, theirs in sorted(keys.items()):
        if other == thread_id:
            continue
        shared = mine & theirs
        if not shared & counterparts:
            continue
        here = devices.get(thread_id)
        same_device = here is not None and devices.get(other) == here
        if not same_device and len(shared) < 2:
            continue
        info = thread_info(conn, other)
        if info is None:
            continue
        lines, nearest, more = _period(conn, other, first_utc, last_utc)
        out.append(Related(info, tuple(sorted(shared)), tuple(lines), nearest, more))
    return out


def _period(
    conn: sqlite3.Connection, thread_id: str, first: str | None, last: str | None
) -> tuple[list[Line], bool, int]:
    """Messages of a thread in [first, last]; if none, the nearest one before and after."""
    if first is None or last is None:
        return [], True, 0
    ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM messages WHERE thread_id = ? AND ts_utc >= ? AND ts_utc <= ?"
            " ORDER BY ts_utc, id",
            (thread_id, first, last),
        )
    ]
    if ids:
        return message_lines(conn, ids[:RELATED_CAP], None), False, max(0, len(ids) - RELATED_CAP)
    before = conn.execute(
        "SELECT id FROM messages WHERE thread_id = ? AND ts_utc < ? ORDER BY ts_utc DESC, id DESC"
        " LIMIT 1",
        (thread_id, first),
    ).fetchone()
    after = conn.execute(
        "SELECT id FROM messages WHERE thread_id = ? AND ts_utc > ? ORDER BY ts_utc, id LIMIT 1",
        (thread_id, last),
    ).fetchone()
    return message_lines(conn, [r[0] for r in (before, after) if r], None), True, 0


# ---------------------------------------------------------------- the view


def context_view(conn: sqlite3.Connection, record_id: str, window: int = WINDOW) -> ContextView:
    """A message in its own conversation: `window` messages either side, and related threads."""
    row = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise LookupError(f"message {record_id} is not in this case")
    thread_id = row[0]
    info = thread_info(conn, thread_id)
    assert info is not None  # noqa: S101 - messages.thread_id is a foreign key
    # The whole thread in time order (context_ids' own ordering), then the window around it.
    order = list(context_ids(conn, record_id, 10**9, include_target=True))
    i = order.index(record_id)
    lo, hi = max(0, i - window), min(len(order), i + window + 1)
    ids = order[lo:hi]
    lines = message_lines(conn, ids, record_id)
    times = [
        r[0]
        for r in conn.execute(
            f"SELECT ts_utc FROM messages WHERE id IN ({','.join('?' * len(ids))})"  # noqa: S608
            " AND ts_utc IS NOT NULL",
            ids,
        )
    ]
    first, last = (min(times), max(times)) if times else (None, None)
    return ContextView(
        record_id=record_id,
        thread=info,
        lines=tuple(lines),
        before=lo,
        after=len(order) - hi,
        related=tuple(related_threads(conn, thread_id, first, last)),
    )


def match_view(conn: sqlite3.Connection, match: ExhibitMatch, window: int = WINDOW) -> MatchView:
    v = context_view(conn, match.record_id, window)
    return MatchView(
        record_id=v.record_id,
        thread=v.thread,
        lines=v.lines,
        before=v.before,
        after=v.after,
        related=v.related,
        match=match,
    )
