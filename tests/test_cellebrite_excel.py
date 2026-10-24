import hashlib
import json
import sqlite3
from datetime import UTC, datetime

import pytest

from core.contracts import ExtractionType, Fidelity, SourceKind
from core.db import apply_schema, connect
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.review.audit_log import verify_chain

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def run(conn: sqlite3.Connection, path, source_id: str = "src1"):
    return CellebriteExcelImporter(source_id=source_id, now=NOW).import_source(path, conn)


def one(conn: sqlite3.Connection, sql: str, *args):
    return conn.execute(sql, args).fetchone()


def coverage(conn: sqlite3.Connection) -> dict:
    row = one(conn, "SELECT payload_json FROM audit_log WHERE action = 'import'")
    return json.loads(row[0])


def test_source_metadata_hash_and_fidelity(make_xlsx, case_db):
    path = make_xlsx()
    src = run(case_db, path)
    assert src.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert src.kind is SourceKind.CELLEBRITE_EXCEL
    assert src.fidelity is Fidelity.CURATED_REPORT
    assert src.extraction_type is ExtractionType.LOGICAL
    assert src.tool_version == "7.70.0.1"
    assert src.extracted_at_utc == datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    row = one(case_db, "SELECT kind, fidelity, sha256 FROM sources WHERE id = 'src1'")
    assert row == ("cellebrite_excel", "curated_report", src.sha256)
    dev = one(case_db, "SELECT label, os_version, timezone FROM devices WHERE id = 'dev:src1'")
    assert dev == ("SyntheticPhone X1", "14.1", "(UTC-05:00) Eastern Time (US & Canada)")


def test_input_file_is_not_modified(make_xlsx, case_db):
    path = make_xlsx()
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    run(case_db, path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_message_ids_and_source_refs(make_xlsx, case_db):
    run(case_db, make_xlsx())
    ids = [r[0] for r in case_db.execute("SELECT id FROM messages ORDER BY id")]
    assert "msg:src1:Chats!3" in ids  # header is row 2, first record row 3
    assert "msg:src1:Chats!6" not in ids  # blank row skipped
    row = one(case_db, "SELECT source_id, locator FROM messages WHERE id = 'msg:src1:Chats!7'")
    assert row == ("src1", "Chats!7")


def test_body_is_verbatim(make_xlsx, case_db):
    run(case_db, make_xlsx())
    body = one(case_db, "SELECT body FROM messages WHERE id = 'msg:src1:Chats!4'")[0]
    assert body == "  yes, two  "


def test_times_with_explicit_offset_convert_to_utc(make_xlsx, case_db):
    run(case_db, make_xlsx())
    row = one(
        case_db,
        "SELECT ts_utc, ts_offset_min, ts_raw FROM messages WHERE id = 'msg:src1:Chats!3'",
    )
    assert row == ("2026-03-06T02:31:00Z", -300, "3/5/2026 9:31:00 PM(UTC-5)")
    iso = one(
        case_db, "SELECT ts_utc, ts_offset_min FROM messages WHERE locator = 'SMS Messages!3'"
    )
    assert iso == ("2026-03-06T07:05:00Z", 180)


def test_time_without_offset_is_not_guessed(make_xlsx, case_db):
    # Report time zone is a named zone with DST, so it is not applied.
    run(case_db, make_xlsx())
    row = one(
        case_db,
        "SELECT ts_utc, ts_offset_min, ts_raw FROM messages WHERE id = 'msg:src1:Chats!5'",
    )
    assert row == (None, None, "3/13/2026 8:00:00 AM")
    cov = coverage(case_db)
    assert cov["counts"]["times_without_offset"] == 2
    assert any("not a fixed UTC offset" in n for n in cov["notes"])


def test_fixed_report_offset_is_applied_and_recorded(make_xlsx, case_db):
    from conftest import DEFAULT_SHEETS, SUMMARY

    summary = [r if r[0] != "Time zone" else ["Time zone", "UTC+3"] for r in SUMMARY]
    run(case_db, make_xlsx({**DEFAULT_SHEETS, "Summary": summary}))
    row = one(case_db, "SELECT ts_utc, ts_offset_min FROM messages WHERE id = 'msg:src1:Chats!5'")
    assert row == ("2026-03-13T05:00:00Z", 180)
    assert coverage(case_db)["counts"]["times_offset_from_report_settings"] == 2


def test_deleted_flag_only_when_stated(make_xlsx, case_db):
    run(case_db, make_xlsx())
    flags = dict(case_db.execute("SELECT locator, deleted_flag FROM messages"))
    assert flags["Chats!3"] == 0  # 'Intact'
    assert flags["Chats!4"] == 1  # 'Deleted'
    assert flags["Chats!5"] is None  # blank: source did not say


def test_direction_stated_and_derived(make_xlsx, case_db):
    run(case_db, make_xlsx())
    d = dict(case_db.execute("SELECT locator, direction FROM messages"))
    assert d["Chats!3"] == "incoming"  # stated
    assert d["Chats!4"] == "outgoing"  # derived: sender marked (owner)
    assert d["Chats!5"] == "incoming"  # derived: owner is among the other participants
    assert d["Chats!7"] == "incoming"  # derived: recipient marked (owner)
    assert coverage(case_db)["counts"]["direction_derived_from_owner"] == 3
    assert d["SMS Messages!2"] == "incoming"
    assert d["SMS Messages!3"] == "outgoing"


def test_same_name_different_numbers_are_different_accounts(make_xlsx, case_db):
    run(case_db, make_xlsx())
    s1 = one(case_db, "SELECT sender_account_id FROM messages WHERE id = 'msg:src1:Chats!3'")[0]
    s2 = one(case_db, "SELECT sender_account_id FROM messages WHERE id = 'msg:src1:Chats!5'")[0]
    assert s1 == "acct:src1:WhatsApp:+15550000002"
    assert s2 == "acct:src1:WhatsApp:+15550000003"
    names = case_db.execute("SELECT display_name FROM accounts WHERE id IN (?, ?)", (s1, s2))
    assert {r[0] for r in names} == {"Alex"}


def test_name_only_party_is_scoped_to_its_thread(make_xlsx, case_db):
    run(case_db, make_xlsx())
    sender = one(case_db, "SELECT sender_account_id FROM messages WHERE id = 'msg:src1:Chats!7'")
    assert sender[0] == "acct:src1:Telegram:name:c3:Sam"
    assert coverage(case_db)["counts"]["parties_name_only"] >= 1


def test_owner_accounts_from_user_accounts_sheet(make_xlsx, case_db):
    run(case_db, make_xlsx())
    row = one(
        case_db,
        "SELECT device_id, locator, display_name FROM accounts"
        " WHERE id = 'acct:src1:WhatsApp:+15550000001'",
    )
    assert row == ("dev:src1", "User Accounts!2", "Dana")
    other = one(
        case_db, "SELECT device_id FROM accounts WHERE id = 'acct:src1:WhatsApp:+15550000002'"
    )
    assert other == (None,)


def test_threads_recipients_and_attachments(make_xlsx, case_db):
    run(case_db, make_xlsx())
    thr = one(case_db, "SELECT thread_id FROM messages WHERE id = 'msg:src1:Chats!3'")[0]
    assert thr == "thr:src1:WhatsApp:c1"
    assert one(case_db, "SELECT title FROM threads WHERE id = ?", thr) == ("Weekend",)
    rec = case_db.execute(
        "SELECT account_id FROM message_recipients WHERE message_id = 'msg:src1:Chats!4'"
    ).fetchall()
    assert rec == [("acct:src1:WhatsApp:+15550000002",)]
    att = one(case_db, "SELECT id, message_id, file_name FROM attachments")
    assert att == ("att:src1:Chats!4:1", "msg:src1:Chats!4", "IMG_0001.jpg")
    sms_thr = one(case_db, "SELECT thread_id FROM messages WHERE locator = 'SMS Messages!2'")[0]
    assert sms_thr == "thr:src1:SMS:sms:+15550000009"
    same = one(case_db, "SELECT thread_id FROM messages WHERE locator = 'SMS Messages!3'")[0]
    assert same == sms_thr


def test_calls(make_xlsx, case_db):
    run(case_db, make_xlsx())
    rows = {
        r[0]: r[1:]
        for r in case_db.execute(
            "SELECT locator, from_account_id, to_account_id, direction, ts_utc, duration_s,"
            " deleted_flag FROM calls"
        )
    }
    assert rows["Call Log!2"] == (
        None, "acct:src1:Phone:+15550000002", "outgoing", "2026-03-06T02:40:00Z", 65, None,
    )  # fmt: skip
    assert rows["Call Log!3"][0] == "acct:src1:Phone:+15550000004"
    assert rows["Call Log!3"][2:] == ("missed", "2026-03-06T12:00:00Z", 0, 1)
    assert rows["Call Log!4"][:3] == (None, None, "unknown")  # 'Rejected' is not mapped
    cov = coverage(case_db)
    assert cov["unmapped_direction_values"] == {"Rejected": 1}
    assert cov["counts"]["calls_party_unattributed"] == 1


def test_contacts_one_row_per_identifier(make_xlsx, case_db):
    run(case_db, make_xlsx())
    rows = case_db.execute("SELECT id, name, identifier FROM contacts ORDER BY id").fetchall()
    assert rows == [
        ("contact:src1:Contacts!2#1", "Alex", "+15550000002"),
        ("contact:src1:Contacts!2#2", "Alex", "alex@example.invalid"),
        ("contact:src1:Contacts!3#1", "Alex Work", "+15550000003"),
        ("contact:src1:Contacts!4#1", "No Number", ""),
    ]


def test_coverage_entry(make_xlsx, case_db):
    run(case_db, make_xlsx())
    cov = coverage(case_db)
    assert cov["fidelity"] == "curated_report"
    assert {
        "name": "Locations",
        "reason": "category not imported",
        "rows": 2,
        "columns": ["#", "Latitude", "Longitude", "Timestamp"],
    } in cov["not_imported"]
    chats = next(t for t in cov["tables"] if t["name"] == "Chats")
    assert chats["header_locator"] == "Chats!2"
    assert chats["unknown_columns"] == ["Mood"]
    assert chats["rows_skipped"] == {"empty": 1}
    assert chats["date_order"] == "mdy"
    sms = next(t for t in cov["tables"] if t["name"] == "SMS Messages")
    assert sms["absent_fields"] == ["app"]
    assert cov["counts"]["messages"] == 6
    assert verify_chain(case_db)


def test_reimport_gives_identical_ids(make_xlsx, tmp_path):
    path = make_xlsx()
    dumps = []
    for i in range(2):
        conn = connect(tmp_path / f"case{i}.db")
        apply_schema(conn)
        run(conn, path)
        dumps.append(
            [
                conn.execute(f"SELECT id FROM {t} ORDER BY id").fetchall()  # noqa: S608
                for t in ("messages", "accounts", "threads", "calls", "contacts", "attachments")
            ]
        )
    assert dumps[0] == dumps[1]


def test_same_source_twice_is_refused(make_xlsx, case_db):
    path = make_xlsx()
    run(case_db, path)
    with pytest.raises(ValueError, match="already in this case database"):
        run(case_db, path)


def test_default_source_id_from_file_stem_else_hash(make_xlsx, case_db):
    src = CellebriteExcelImporter(now=NOW).import_source(make_xlsx(name="item1.xlsx"), case_db)
    assert src.id == "item1"
    odd = make_xlsx(name="phone report (final).xlsx")
    src2 = CellebriteExcelImporter(now=NOW).import_source(odd, case_db)
    assert src2.id == "src_" + src2.sha256[:12]


def test_two_devices_never_share_accounts(make_xlsx, case_db):
    run(case_db, make_xlsx(name="a.xlsx"), "phone_a")
    run(case_db, make_xlsx(name="b.xlsx"), "phone_b")
    rows = case_db.execute(
        "SELECT id FROM accounts WHERE identifier = '+15550000002' AND app = 'WhatsApp' ORDER BY id"
    ).fetchall()
    assert rows == [
        ("acct:phone_a:WhatsApp:+15550000002",),
        ("acct:phone_b:WhatsApp:+15550000002",),
    ]
    assert case_db.execute("SELECT count(*) FROM identity_links").fetchone() == (0,)


def test_failed_import_writes_nothing(make_xlsx, case_db, monkeypatch):
    from core.review import audit_log

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(audit_log, "append", boom)
    with pytest.raises(RuntimeError):
        run(case_db, make_xlsx())
    for table in ("sources", "devices", "accounts", "messages", "calls", "contacts"):
        assert case_db.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)  # noqa: S608


def test_split_date_time_columns_and_excel_datetime_cells(make_xlsx, case_db):
    chats = [
        ["#", "Chat #", "Source", "From", "Body", "Timestamp: Date", "Timestamp: Time"],
        [1, "c", "Signal", "+15550000002 Alex", "a", "13/03/2026", "21:00:00(UTC+1)"],
        [2, "c", "Signal", "+15550000002 Alex", "b", datetime(2026, 3, 14), "07:15:00(UTC+1)"],
    ]
    sms = [["#", "Parties", "Body", "Timestamp"], [1, "+15550000009", "c", datetime(2026, 3, 6, 9)]]
    run(case_db, make_xlsx({"Chats": chats, "SMS Messages": sms}))
    rows = dict(
        (r[0], r[1:])
        for r in case_db.execute("SELECT locator, ts_utc, ts_offset_min, ts_raw FROM messages")
    )
    assert rows["Chats!2"] == ("2026-03-13T20:00:00Z", 60, "13/03/2026 21:00:00(UTC+1)")
    assert rows["Chats!3"] == ("2026-03-14T06:15:00Z", 60, "2026-03-14 07:15:00(UTC+1)")
    # Excel datetime cell, no report time zone: raw kept, no UTC guessed.
    assert rows["SMS Messages!2"] == (None, None, "2026-03-06 09:00:00")


def test_a_forwarded_label_lists_the_message_for_the_fail_closed_path(make_xlsx, case_db):
    from core.ingest import forwarded
    from tests.conftest import SUMMARY

    chats = [
        ["#", "Chat #", "Source", "From", "To", "Body", "Timestamp", "Label"],
        [1, "c1", "WhatsApp", "+15550000002 Alex", "+15550000001 Dana (owner)", "SYNTHETIC a",
         "3/5/2026 9:31:00 PM(UTC-5)", "Forwarded"],
        [2, "c1", "WhatsApp", "+15550000002 Alex", "+15550000001 Dana (owner)", "SYNTHETIC b",
         "3/5/2026 9:32:00 PM(UTC-5)", "Reply"],
    ]  # fmt: skip
    run(case_db, make_xlsx({"Summary": SUMMARY, "Chats": chats}))
    ids = dict(case_db.execute("SELECT body, id FROM messages"))
    assert forwarded.affected(case_db) == {ids["SYNTHETIC a"]: "forwarded"}
    assert coverage(case_db)["counts"]["messages_marked_forwarded"] == 1
    marked = case_db.execute(
        "SELECT body, forwarded, forwarded_from_raw FROM messages ORDER BY body"
    ).fetchall()
    assert marked == [("SYNTHETIC a", 1, None), ("SYNTHETIC b", None, None)]


# The layout of Physical Analyzer's per-category Excel export (one 'SMS Messages (N)' sheet, a
# title row over the header, 'Date' as an Excel serial number, 'Time' as the full value, and
# each record of a rooted extraction listed twice, '1' and '1(1)'). Synthetic values only.
PA_SMS_HEADER = [
    "#", "Party", "Date", "Time", "All timestamps", "Direction", "Delivered-Date",
    "Delivered-Time", "Read-Date", "Read-Time", "Folder", "Status", "Source", "SMSC", "Message",
    "Deleted", "Tag Note", "Source file information", "Carved", "Manually decoded",
]  # fmt: skip


def _pa_row(number, party, serial, time, direction, body, path):
    return [
        number, party, serial, time, "", direction, "", "", "", "", "Inbox", "Read", "", "",
        body, "", "", f"Phone.zip/{path}/mmssms.db : 0x1F00 (Table: sms, Size: 4096 bytes)",
        "", "",
    ]  # fmt: skip


def _pa_sheet(rows):
    return {"SMS Messages (4)": [["", "SMS Messages (4)"], PA_SMS_HEADER, *rows]}


def test_physical_analyzer_sms_export_reads_time_column_and_flags_copies(make_xlsx, case_db):
    mirror = "sbin/.magisk/mirror/data/data/com.android.providers.telephony/databases"
    own = "data/data/com.android.providers.telephony/databases"
    t1, s1 = "2/14/2020 1:09:03 PM(UTC+0)", 43875.547951388886  # 2020-02-14 13:09:03
    t2, s2 = "1/29/2020 6:20:45 PM(UTC-5)", 43859.764409722222  # 2020-01-29 18:20:45 local
    party_in = "From:  +15550100001 Sam\r\nTo:  "
    rows = [
        _pa_row(1, party_in, s1, t1, "Incoming", "first", mirror),
        _pa_row("1(1)", party_in, s1, t1, "Incoming", "first", own),
        _pa_row(2, "From:  \r\nTo:  +15550100002", s2, t2, "Outgoing", "second", mirror),
        _pa_row("2(1)", "From:  \r\nTo:  +15550100002", s2, t2, "Outgoing", "second", own),
    ]
    run(case_db, make_xlsx(_pa_sheet(rows)))
    got = case_db.execute(
        "SELECT locator, ts_utc, ts_offset_min, ts_raw, direction FROM messages ORDER BY locator"
    ).fetchall()
    assert got == [
        ("SMS Messages (4)!3", "2020-02-14T13:09:03Z", 0, t1, "incoming"),
        ("SMS Messages (4)!4", "2020-02-14T13:09:03Z", 0, t1, "incoming"),
        ("SMS Messages (4)!5", "2020-01-29T23:20:45Z", -300, t2, "outgoing"),
        ("SMS Messages (4)!6", "2020-01-29T23:20:45Z", -300, t2, "outgoing"),
    ]
    senders = case_db.execute(
        "SELECT a.identifier FROM messages m JOIN accounts a ON a.id = m.sender_account_id"
    ).fetchall()
    assert senders == [("+15550100001",), ("+15550100001",)]
    (table,) = coverage(case_db)["tables"]
    # Copies stay records of their own and are listed for the expert, never merged.
    assert table["flag_counts"] == {"numbered_as_copy": 2}
    assert table["flagged_locators"]["numbered_as_copy"] == [
        "SMS Messages (4)!4",
        "SMS Messages (4)!6",
    ]
    assert table["time_problems"] == {}


def test_a_date_column_that_disagrees_with_the_full_time_sets_no_time(make_xlsx, case_db):
    t = "2/14/2020 1:09:03 PM(UTC+0)"
    rows = [
        _pa_row(1, "From:  +15550100001", 43876.0, t, "Incoming", "a", "data"),  # 2020-02-15
        _pa_row(2, "From:  +15550100001", "not a date", t, "Incoming", "b", "data"),
        _pa_row(3, "From:  +15550100001", "2/14/2020", t, "Incoming", "c", "data"),
        _pa_row(4, "From:  +15550100001", None, t, "Incoming", "d", "data"),
    ]
    run(case_db, make_xlsx(_pa_sheet(rows)))
    got = dict(case_db.execute("SELECT body, ts_utc FROM messages"))
    assert got == {"a": None, "b": None, "c": "2020-02-14T13:09:03Z", "d": "2020-02-14T13:09:03Z"}
    (table,) = coverage(case_db)["tables"]
    assert table["time_problems"] == {"date_column_disagrees": 2}
