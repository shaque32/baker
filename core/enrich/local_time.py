"""Device-local time for display. Derived from the stored UTC time and the device's zone.

The phone's zone is devices.timezone. The offset printed in a report can be a display setting
(case01 item1 prints UTC+0 for a phone set to America/New_York), so it is never used here.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.utcoffset() is None:
        return None  # stored times are always aware; refuse to guess
    return dt.astimezone(UTC)


def device_zone(conn: sqlite3.Connection, device_id: str | None) -> ZoneInfo | None:
    if device_id is None:
        return None
    row = conn.execute("SELECT timezone FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None or not row[0]:
        return None
    try:
        return ZoneInfo(row[0])
    except (ZoneInfoNotFoundError, ValueError):
        return None


def format_local(utc: datetime | None, zone: ZoneInfo | None, raw: str | None) -> str:
    """'2026-02-20 19:02:11 EST (UTC-05:00)', or UTC with a note when the zone is unknown."""
    if utc is None:
        return f"time unknown (source shows {raw!r})" if raw else "time unknown"
    if zone is None:
        return f"{utc:%Y-%m-%d %H:%M:%S} UTC (device zone unknown)"
    local = utc.astimezone(zone)
    off = local.strftime("%z")
    return f"{local:%Y-%m-%d %H:%M:%S} {local.tzname()} (UTC{off[:3]}:{off[3:]})"
