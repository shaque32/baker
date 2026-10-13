"""Messages and calls with their times, read once from the case database for the timeline
check and the gaps view. Read-only.

Times are the stored UTC value. A record's local time is in its phone's own zone
(devices.timezone), never the offset a report printed, which can be a display setting.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.utcoffset() is None:
        return None  # stored times are always aware; never guess
    return t.astimezone(UTC)


@dataclass(frozen=True)
class Phone:
    source_id: str
    file_name: str
    label: str  # the device as the report named it; the file name if it named none
    tz: str | None  # the phone's own zone, if the source said
    fidelity: str  # sources.fidelity

    @property
    def name(self) -> str:
        return self.file_name if self.label == self.file_name else f"{self.file_name}, {self.label}"


@dataclass(frozen=True)
class Record:
    id: str
    kind: str  # 'message' or 'call'
    source_id: str
    locator: str
    app: str
    thread_id: str | None
    thread: str | None  # thread title as the source showed it
    what: str  # the message body, or the call's fields
    ts_utc: datetime | None
    ts_raw: str | None
    offset_min: int | None
    tz: str | None  # the phone's zone
    parties: tuple[str, ...] = ()  # calls: both numbers as the source gave them

    def local(self) -> datetime | None:
        z = zone(self.tz)
        if self.ts_utc is None or z is None:
            return None
        return self.ts_utc.astimezone(z)

    def when(self) -> str:
        """'2026-03-04 21:31:00 EST', or UTC with a note when the phone's zone is unknown."""
        if self.ts_utc is None:
            return "no usable time"
        loc = self.local()
        if loc is None:
            return f"{self.ts_utc:%Y-%m-%d %H:%M:%S} UTC (phone zone unknown)"
        return f"{loc:%Y-%m-%d %H:%M:%S} {loc.tzname()}"


class CaseRecords:
    """Every message and call in the case, with each source's phone. Loaded once."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        labels: dict[str, tuple[str, str | None]] = {}
        for sid, label, tz in conn.execute(
            "SELECT source_id, label, timezone FROM devices ORDER BY id"
        ):
            if sid not in labels:
                labels[sid] = (label, tz)
        self.phones: dict[str, Phone] = {}
        for sid, file_name, fidelity in conn.execute(
            "SELECT id, file_name, fidelity FROM sources WHERE kind != 'govdoc' ORDER BY id"
        ):
            label, tz = labels.get(sid, (file_name, None))
            self.phones[sid] = Phone(sid, file_name, label or file_name, tz, fidelity)
        self.records: list[Record] = []
        for r in conn.execute(
            "SELECT m.id, m.source_id, m.locator, t.app, m.thread_id, t.title, m.body, m.ts_utc,"
            " m.ts_raw, m.ts_offset_min FROM messages m JOIN threads t ON t.id = m.thread_id"
            " ORDER BY m.id"
        ):
            mid, sid, loc, app, tid, title, body, ts, raw, off = r
            self.records.append(
                Record(
                    mid,
                    "message",
                    sid,
                    loc,
                    app,
                    tid,
                    title,
                    body,
                    parse_utc(ts),
                    raw,
                    off,
                    self._tz(sid),
                )  # fmt: skip
            )
        for r in conn.execute(
            "SELECT c.id, c.source_id, c.locator, c.app, c.direction, c.duration_s, c.ts_utc,"
            " c.ts_raw, c.ts_offset_min, fa.identifier, fa.display_name, ta.identifier,"
            " ta.display_name FROM calls c"
            " LEFT JOIN accounts fa ON fa.id = c.from_account_id"
            " LEFT JOIN accounts ta ON ta.id = c.to_account_id ORDER BY c.id"
        ):
            cid, sid, loc, app, direction, dur, ts, raw, off, fi, fn, ti, tn = r
            what = f"{direction} call from {_who(fi, fn)} to {_who(ti, tn)}" + (
                f", {dur} s" if dur is not None else ", duration not given"
            )
            self.records.append(
                Record(
                    cid,
                    "call",
                    sid,
                    loc,
                    app,
                    None,
                    None,
                    what,
                    parse_utc(ts),
                    raw,
                    off,
                    self._tz(sid),
                    tuple(x for x in (fi, ti) if x),
                )  # fmt: skip
            )
        self.by_id = {r.id: r for r in self.records}
        self.timed = sorted((r for r in self.records if r.ts_utc), key=lambda r: (r.ts_utc, r.id))
        self._keys = [r.ts_utc for r in self.timed]

    def between(
        self, start: datetime | None, end: datetime | None, closed: bool = True
    ) -> list[Record]:
        """Timed records from start to end (either may be None for open). closed=False leaves
        out records exactly at either end."""
        lo = 0 if start is None else (bisect_left if closed else bisect_right)(self._keys, start)
        hi = (
            len(self._keys)
            if end is None
            else (bisect_right if closed else bisect_left)(self._keys, end)
        )
        return self.timed[lo:hi]

    def zones(self) -> set[str]:
        """Every usable zone a phone states."""
        return {p.tz for p in self.phones.values() if p.tz and zone(p.tz) is not None}

    def _tz(self, source_id: str) -> str | None:
        p = self.phones.get(source_id)
        return None if p is None else p.tz

    def phone(self, source_id: str) -> Phone:
        return self.phones.get(source_id) or Phone(source_id, source_id, source_id, None, "unknown")

    def shared_zone(self) -> str | None:
        """The one zone every phone states, or None if any phone has none or they differ."""
        zones = {p.tz for p in self.phones.values()}
        if len(zones) != 1:
            return None
        (z,) = zones
        return z if zone(z) is not None else None


def _who(identifier: str | None, name: str | None) -> str:
    if identifier and name and name != identifier:
        return f"{identifier} ({name})"
    return identifier or name or "unknown"
