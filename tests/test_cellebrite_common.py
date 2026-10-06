from datetime import UTC, datetime

import pytest

from core.ingest.cellebrite_common import (
    DateOrder,
    Party,
    RawTable,
    RecordKind,
    find_header,
    fixed_report_offset,
    parse_deleted,
    parse_duration,
    parse_offset,
    parse_parties,
    parse_time,
)


def order(*values: str) -> DateOrder:
    o = DateOrder()
    for v in values:
        o.observe(v)
    return o


@pytest.mark.parametrize(
    ("raw", "utc", "offset"),
    [
        ("3/5/2026 9:31:00 PM(UTC-5)", datetime(2026, 3, 6, 2, 31, tzinfo=UTC), -300),
        ("3/5/2026 12:05:00 AM(UTC+0)", datetime(2026, 3, 5, 0, 5, tzinfo=UTC), 0),
        ("3/5/2026 21:31(UTC+05:30)", datetime(2026, 3, 5, 16, 1, tzinfo=UTC), 330),
        ("2026-03-05 21:31:00 (UTC)", datetime(2026, 3, 5, 21, 31, tzinfo=UTC), 0),
        ("2026-03-05T21:31:00-04:00", datetime(2026, 3, 6, 1, 31, tzinfo=UTC), -240),
        ("2026-03-05T21:31:00Z", datetime(2026, 3, 5, 21, 31, tzinfo=UTC), 0),
    ],
)
def test_parse_time_with_offset(raw, utc, offset):
    ts = parse_time(raw, DateOrder(), None).ts
    assert (ts.utc, ts.offset_min, ts.raw) == (utc, offset, raw)


@pytest.mark.parametrize(
    "raw",
    ["3/5/2026", "2026-03-05", "3/5/26 9:00 PM(UTC-5)", "13/13/2026 1:00:00", "yesterday",
     "3/5/2026 13:00 PM(UTC-5)"],
)  # fmt: skip
def test_unparseable_or_partial_times_have_no_utc(raw):
    ts = parse_time(raw, DateOrder(), 0).ts
    assert ts.utc is None and ts.offset_min is None and ts.raw == raw


def test_date_order_from_disambiguating_rows():
    assert order("13/3/2026 1:00", "3/4/2026 1:00").label == "dmy"
    assert order("3/13/2026 1:00", "3/4/2026 1:00").label == "mdy"
    assert order("3/4/2026 1:00").label == "mdy_assumed"
    assert order("13/3/2026 1:00", "3/13/2026 1:00").label == "conflict"
    dmy = parse_time("3/4/2026 1:00(UTC+0)", order("13/3/2026 1:00"), None).ts
    assert dmy.utc == datetime(2026, 4, 3, 1, 0, tzinfo=UTC)


def test_conflicting_date_order_leaves_ambiguous_values_unparsed():
    o = order("13/3/2026 1:00", "3/13/2026 1:00")
    assert parse_time("3/4/2026 1:00(UTC+0)", o, None).ts.utc is None
    assert parse_time("13/3/2026 1:00(UTC+0)", o, None).ts.utc == datetime(
        2026, 3, 13, 1, 0, tzinfo=UTC
    )


def test_report_offset_only_when_fixed():
    assert fixed_report_offset("UTC-5") == -300
    assert fixed_report_offset("(UTC+03:00)") == 180
    assert fixed_report_offset("GMT") == 0
    assert fixed_report_offset("(UTC-05:00) Eastern Time (US & Canada)") is None
    assert fixed_report_offset("America/New_York") is None
    assert fixed_report_offset(None) is None


def test_parse_offset():
    assert [parse_offset(x) for x in ("+5", "-05:00", "+0530", None, "- 3")] == [
        300, -300, 330, 0, -180,
    ]  # fmt: skip


def test_parse_parties():
    got = parse_parties("+15550000001 Dana (owner)\n alex92@s.whatsapp.net Alex B ;@northstar\nSam")
    assert got == [
        Party("+15550000001", "Dana", True, None),
        Party("alex92@s.whatsapp.net", "Alex B", False, None),
        Party("@northstar", None, False, None),
        Party(None, "Sam", False, None),
    ]
    assert parse_parties("From: +15550000002 Alex\nTo: +15550000001")[1] == Party(
        "+15550000001", None, False, "to"
    )
    assert parse_parties(None) == [] and parse_parties("  ") == []


def test_parse_deleted():
    assert [parse_deleted(v) for v in ("Deleted", "Trash", "Intact", "No", None, "", "?")] == [
        True, True, False, False, None, None, None,
    ]  # fmt: skip


def test_parse_duration():
    assert [parse_duration(v) for v in ("00:01:05", "1:05", "65", 65, 65.0, "", None, "1m")] == [
        65, 65, 65, 65, 65, None, None, None,
    ]  # fmt: skip


def test_header_found_below_title_rows_and_by_columns():
    rows = [("S!1", ["Chats (2)"]), ("S!2", ["filter: all"]), ("S!3", ["#", "From", "Body"])]
    assert find_header(RawTable("S", RecordKind.CHATS, rows)) == (RecordKind.CHATS, 2)
    calls = [("p1:t1:r1", ["Type", "Parties", "Duration"])]
    assert find_header(RawTable("p1:t1", None, calls)) == (RecordKind.CALLS, 0)
    assert find_header(RawTable("x", None, [("x!1", ["Latitude", "Longitude"])])) is None


def test_parse_parties_reflowed_pdf_cell_joins_wrapped_lines():
    cell = "+15550000001 Dana\n(owner)\n+15550000002 Alex\nJohnson"
    assert parse_parties(cell, reflowed=True) == [
        Party("+15550000001", "Dana", True, None),
        Party("+15550000002", "Alex Johnson", False, None),
    ]
    # Without reflow (Excel), each line is its own party.
    assert len(parse_parties(cell)) == 3


def test_parse_parties_comma_separated_and_bare_handles():
    got = parse_parties("+12125550122 (owner), +12125550188 Jenna, m.reyes.auto")
    assert got == [
        Party("+12125550122", None, True, None),
        Party("+12125550188", "Jenna", False, None),
        Party("m.reyes.auto", None, False, None),
    ]
    # A comma inside a display name does not split it.
    assert parse_parties("+12125550188 Smith, John") == [
        Party("+12125550188", "Smith, John", False, None)
    ]
    assert parse_parties("Sam") == [Party(None, "Sam", False, None)]
    assert len(parse_parties("d.petrov (owner), m.reyes.auto")) == 2
