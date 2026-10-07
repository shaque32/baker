"""Surrounding messages for one record, as the stance labeler and AI reviewer see them.

Each context line shows the sender's account (app and identifier, and whether it is one of the
phone's own accounts), the direction and the device-local time. The reviewer prompt tells the
model to dismiss when "the timing or sender in the context does not match", which it can only do
if those are on the line.

Device-local time is derived from the stored UTC time and the device's zone (devices.timezone),
never from the offset a report printed. Display names are not shown: the accounts table keeps only
the first name seen, so a renamed handle (case01 handle_change) would show the wrong name on later
messages. Once the schema keeps the sender text per message (sender_raw), it is shown as written.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from core.enrich.local_time import device_zone, format_local, parse_utc
from core.enrich.records import get_record

DEFAULT_WINDOW = 20  # messages on either side of the target
HEADER = (
    "(One line per record, in time order. '>>' marks the record under review. Times are the"
    " phone's local time. Sender is app and account id; '(this phone)' is the phone's own account.)"
)


@dataclass(frozen=True)
class ContextLine:
    record_id: str
    locator: str
    sender: str  # "Telegram 5551234", "SMS +12125550111 (this phone)" or "unknown sender"
    shown_as: str | None  # sender text as the source printed it, when the schema keeps it
    direction: str
    local_time: str
    body: str
    is_target: bool


def _natural(locator: str) -> tuple[object, ...]:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", locator))


def _order_key(ts_utc: str | None, locator: str, rec_id: str) -> tuple[object, ...]:
    # Known times first in UTC order; rows with no time keep source order after them.
    return (ts_utc is None, ts_utc or "", _natural(locator), rec_id)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))  # noqa: S608


def _window(ordered: list[str], target: str, window: int, include_target: bool) -> list[str]:
    i = ordered.index(target)
    before = ordered[max(0, i - window) : i]
    after = ordered[i + 1 : i + 1 + window]
    return before + ([target] if include_target else []) + after


def _thread_message_ids(conn: sqlite3.Connection, thread_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT id, ts_utc, locator FROM messages WHERE thread_id = ?", (thread_id,)
    ).fetchall()
    rows.sort(key=lambda r: _order_key(r[1], r[2], r[0]))
    return [r[0] for r in rows]


def _source_messages_around(
    conn: sqlite3.Connection, source_id: str, ts_utc: str | None, window: int
) -> list[str]:
    """Messages on the same source nearest a call's time: `window` before and `window` after."""
    if ts_utc is None:
        return []
    before = conn.execute(
        "SELECT id FROM messages WHERE source_id = ? AND ts_utc IS NOT NULL AND ts_utc < ?"
        " ORDER BY ts_utc DESC, id DESC LIMIT ?",
        (source_id, ts_utc, window),
    ).fetchall()
    after = conn.execute(
        "SELECT id FROM messages WHERE source_id = ? AND ts_utc IS NOT NULL AND ts_utc >= ?"
        " ORDER BY ts_utc, id LIMIT ?",
        (source_id, ts_utc, window),
    ).fetchall()
    return [r[0] for r in reversed(before)] + [r[0] for r in after]


def context_ids(
    conn: sqlite3.Connection,
    record_id: str,
    window: int = DEFAULT_WINDOW,
    include_target: bool = False,
) -> tuple[str, ...]:
    """Ids of the surrounding messages, in time order.

    message: up to `window` messages either side in the same thread.
    attachment: the same, around the message it is attached to (that message included).
    call: up to `window` messages either side on the same source, by time.
    contact or anything else: none.
    """
    if record_id.startswith("msg:"):
        row = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return ()
        return tuple(_window(_thread_message_ids(conn, row[0]), record_id, window, include_target))
    if record_id.startswith("att:"):
        row = conn.execute(
            "SELECT message_id FROM attachments WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None or row[0] is None:
            return ()
        return context_ids(conn, row[0], window, include_target=True)
    if record_id.startswith("call:"):
        row = conn.execute(
            "SELECT source_id, ts_utc FROM calls WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            return ()
        return tuple(_source_messages_around(conn, row[0], row[1], window))
    return ()


def _sender(conn: sqlite3.Connection, account_id: str | None) -> str:
    if account_id is None:
        return "unknown sender"
    row = conn.execute(
        "SELECT app, identifier, device_id FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        return f"account {account_id}"
    app, identifier, device_id = row
    return f"{app} {identifier}" + (" (this phone)" if device_id else "")


def build_context(
    conn: sqlite3.Connection, record_id: str, window: int = DEFAULT_WINDOW
) -> list[ContextLine]:
    """Context lines around a record, the target marked. Messages only; empty for a contact."""
    if record_id.startswith("contact:"):
        return _contact_line(conn, record_id)
    ids = list(context_ids(conn, record_id, window, include_target=True))
    if not ids:
        return []
    target = record_id
    if record_id.startswith("att:"):
        target = conn.execute(
            "SELECT message_id FROM attachments WHERE id = ?", (record_id,)
        ).fetchone()[0]
    shown_col = "m.sender_raw" if _has_column(conn, "messages", "sender_raw") else "NULL"
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT m.id, m.locator, m.sender_account_id, {shown_col}, m.direction, m.ts_utc,"  # noqa: S608
        f" m.ts_raw, m.body, t.device_id FROM messages m JOIN threads t ON t.id = m.thread_id"
        f" WHERE m.id IN ({marks})",
        ids,
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    zones: dict[str | None, object] = {}
    lines = []
    for rid in ids:
        _, locator, sender_id, shown, direction, ts_utc, ts_raw, body, device_id = by_id[rid]
        if device_id not in zones:
            zones[device_id] = device_zone(conn, device_id)
        lines.append(
            ContextLine(
                record_id=rid,
                locator=locator,
                sender=_sender(conn, sender_id),
                shown_as=shown,
                direction=direction,
                local_time=format_local(parse_utc(ts_utc), zones[device_id], ts_raw),  # type: ignore[arg-type]
                body=body,
                is_target=rid == target,
            )
        )
    if record_id.startswith("call:"):
        lines = _with_call_line(conn, record_id, lines, by_id)
    return lines


def _contact_line(conn: sqlite3.Connection, contact_id: str) -> list[ContextLine]:
    rec = get_record(conn, contact_id)
    if rec is None:
        return []
    return [
        ContextLine(
            record_id=contact_id,
            locator=rec.ref.locator,
            sender="contact list",
            shown_as=None,
            direction="none",
            local_time="no time in source",
            body=f"[contact] {rec.text}",
            is_target=True,
        )
    ]


def _with_call_line(
    conn: sqlite3.Connection,
    call_id: str,
    lines: list[ContextLine],
    by_id: dict[str, tuple[object, ...]],
) -> list[ContextLine]:
    """Put the call itself, marked as the target, at its place in time among the messages."""
    rec = get_record(conn, call_id)
    row = conn.execute(
        "SELECT from_account_id, direction, ts_raw, device_id FROM calls WHERE id = ?", (call_id,)
    ).fetchone()
    if rec is None or row is None:
        return lines
    call_line = ContextLine(
        record_id=call_id,
        locator=rec.ref.locator,
        sender=_sender(conn, row[0]),
        shown_as=None,
        direction=row[1],
        local_time=format_local(parse_utc(rec.ts_utc), device_zone(conn, row[3]), row[2]),
        body=f"[call] {rec.text}",
        is_target=True,
    )
    # context_ids put messages strictly before the call first, then those at or after it.
    i = sum(1 for ln in lines if (by_id[ln.record_id][5] or "") < (rec.ts_utc or ""))
    return lines[:i] + [call_line] + lines[i:]


def _one_line(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " \\n ")


def render_context(lines: list[ContextLine]) -> str:
    """Plain text for the {context} slot of the prompts. The target line starts with '>>'."""
    if not lines:
        return "(no surrounding messages)"
    out = [HEADER]
    for ln in lines:
        mark = ">>" if ln.is_target else "  "
        who = ln.sender + (f' shown as "{ln.shown_as}"' if ln.shown_as else "")
        out.append(f"{mark} [{ln.local_time}] {who}, {ln.direction}: {_one_line(ln.body)}")
    return "\n".join(out)


def render_for(conn: sqlite3.Connection, record_id: str, window: int = DEFAULT_WINDOW) -> str:
    return render_context(build_context(conn, record_id, window))


class ReviewContext:
    """The pipeline's context builder: the {context} text for one evidence item's record."""

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self.window = window

    def __call__(self, conn: sqlite3.Connection, assumption: object, item: object) -> str:
        return render_for(conn, item.record_id, self.window)  # type: ignore[attr-defined]


def create(conn: sqlite3.Connection) -> ReviewContext:
    """Pipeline entry point (core.pipeline.real_components)."""
    return ReviewContext()
