"""A phone's time zone text, as real extractions write it, read as an IANA zone (core/zones.py).
The strings are the shapes real exports use; no case data."""

from __future__ import annotations

import pytest

from core.zones import resolve_zone


@pytest.mark.parametrize(
    ("raw", "zone"),
    [
        ("America/New_York", "America/New_York"),
        # Cellebrite Reader 7.48 UFDR device info (the public iOS 15 package's shape)
        ("(UTC-05:00)  New_York  (America)", "America/New_York"),
        ("(UTC+05:30) Kolkata (Asia)", "Asia/Kolkata"),
        ("(UTC+01:00) Berlin (Europe)", "Europe/Berlin"),
        # Cellebrite Excel summary: Windows display names
        ("(UTC-05:00) Eastern Time (US & Canada)", "America/New_York"),
        ("(UTC-08:00) Pacific Time (US & Canada)", "America/Los_Angeles"),
        ("(UTC) Coordinated Universal Time", "UTC"),
    ],
)
def test_real_export_shapes_read_as_the_zone_they_name(raw, zone):
    assert resolve_zone(raw) == zone


@pytest.mark.parametrize(
    "raw",
    [
        "(UTC+03:00)  New_York  (America)",  # the offset is not the zone's, winter or summer
        "(UTC-05:00) Nowhere (America)",
        "(UTC-06:00) Eastern Time (US & Canada)",  # neither New York's winter nor summer offset
        "(UTC+10:00) Canberra, Melbourne, Sydney",  # a display name not in the checked table
        "Device local (offset shown per row)",
        "UTC+0",
    ],
)
def test_text_that_names_no_zone_comes_back_as_given(raw):
    assert resolve_zone(raw) == raw


def test_nothing_stays_nothing():
    assert resolve_zone(None) is None


def test_checks_and_local_time_read_the_phone_zone_through_it():
    import sqlite3

    from core.audit.checks._common import CaseData
    from core.db import apply_schema
    from core.enrich.local_time import device_zone

    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO sources (id, kind, fidelity, extraction_type, file_name, sha256,"
        " imported_at_utc) VALUES"
        " ('s1', 'ufdr', 'full_extraction', 'logical', 'p.ufdr', 'x', 'now')"
    )
    conn.execute(
        "INSERT INTO devices (id, source_id, locator, label, timezone) VALUES"
        " ('dev:s1', 's1', 'metadata[1]', 'Phone', '(UTC-05:00)  New_York  (America)')"
    )
    assert str(CaseData(conn).tz_for("s1")) == "America/New_York"
    assert str(device_zone(conn, "dev:s1")) == "America/New_York"
