"""Synthetic Cellebrite-style report builders. Every value here is invented."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from openpyxl import Workbook

from core.db import apply_schema, connect

Sheet = list[list[object]]

SUMMARY: Sheet = [
    ["Extraction Summary"],
    ["Extraction start date/time", "3/1/2026 10:00:00 AM(UTC-5)"],
    ["Extraction type", "Advanced Logical"],
    ["Device", "SyntheticPhone X1"],
    ["OS version", "14.1"],
    ["UFED Physical Analyzer version", "7.70.0.1"],
    ["Time zone", "(UTC-05:00) Eastern Time (US & Canada)"],
]

CHATS: Sheet = [
    ["Chats (4)"],
    ["#", "Chat #", "Name", "Source", "Participants", "From", "To", "Body", "Timestamp",
     "Direction", "Deleted", "Attachment #1", "Tags", "Mood"],
    [1, "c1", "Weekend", "WhatsApp",
     "+15550000001 Dana (owner)\n+15550000002 Alex", "+15550000002 Alex",
     "+15550000001 Dana (owner)", "Got the tickets?", "3/5/2026 9:31:00 PM(UTC-5)",
     "Incoming", "Intact", None, None, "x"],
    [2, "c1", "Weekend", "WhatsApp",
     "+15550000001 Dana (owner)\n+15550000002 Alex", "+15550000001 Dana (owner)",
     "+15550000002 Alex", "  yes, two  ", "3/5/2026 9:32:10 PM(UTC-5)",
     None, "Deleted", "IMG_0001.jpg", None, None],
    [3, "c2", None, "WhatsApp",
     "+15550000001 Dana (owner)\n+15550000003 Alex", "+15550000003 Alex",
     None, "different Alex", "3/13/2026 8:00:00 AM", None, None, None, None, None],
    [None] * 14,
    [4, "c3", None, "Telegram", None, "Sam", "Dana (owner)", "name only", "3/14/2026 1:00:00 PM",
     None, None, None, None, None],
]  # fmt: skip

SMS: Sheet = [
    ["#", "Parties", "Body", "Timestamp", "Type", "Deleted"],
    [1, "+15550000009 Pat", "call me", "2026-03-06T10:00:00Z", "Incoming", None],
    [2, "+15550000009 Pat", "ok", "2026-03-06T10:05:00+03:00", "Sent", None],
]

CALLS: Sheet = [
    ["#", "Source", "Type", "Parties", "Timestamp", "Duration", "Deleted"],
    [1, "Phone", "Outgoing", "+15550000002 Alex", "3/5/2026 9:40:00 PM(UTC-5)", "00:01:05", None],
    [2, "Phone", "Missed", "+15550000004", "3/6/2026 7:00:00 AM(UTC-5)", "00:00:00", "Deleted"],
    [3, "Phone", "Rejected", "+15550000005", "3/6/2026 7:30:00 AM(UTC-5)", "0", None],
]

CONTACTS: Sheet = [
    ["#", "Name", "Entries", "Source"],
    [1, "Alex", "Phone-Mobile: +15550000002\nEmail-Home: alex@example.invalid", "Phone"],
    [2, "Alex Work", "Phone-Mobile: +15550000003", "Phone"],
    [3, "No Number", None, "Phone"],
]

ACCOUNTS: Sheet = [
    ["#", "Source", "Username", "Name"],
    [1, "WhatsApp", "+15550000001", "Dana"],
    [2, "Telegram", "@dana_t", "Dana"],
]

LOCATIONS: Sheet = [["#", "Latitude", "Longitude", "Timestamp"], [1, 40.0, -73.0, "3/5/2026"]]

DEFAULT_SHEETS: dict[str, Sheet] = {
    "Summary": SUMMARY,
    "Chats": CHATS,
    "SMS Messages": SMS,
    "Call Log": CALLS,
    "Contacts": CONTACTS,
    "User Accounts": ACCOUNTS,
    "Locations": LOCATIONS,
}


def write_xlsx(path: Path, sheets: dict[str, Sheet]) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(list(r))
    wb.save(path)
    return path


@pytest.fixture
def make_xlsx(tmp_path: Path) -> Callable[..., Path]:
    def _make(sheets: dict[str, Sheet] | None = None, name: str = "report.xlsx") -> Path:
        return write_xlsx(tmp_path / name, sheets if sheets is not None else DEFAULT_SHEETS)

    return _make


@pytest.fixture
def case_db() -> sqlite3.Connection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn
