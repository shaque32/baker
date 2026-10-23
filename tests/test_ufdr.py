"""Cellebrite UFDR import (core/ingest/ufdr.py). UNVERIFIED format support: every package here
is synthetic (eval/synthetic/ufdr.py), built from public descriptions of the format.

The anchor: synthetic case01 rendered as a UFDR imports to exactly the canonical records its
Excel report gives, so everything after import (retrieval, checks, rules) works unchanged."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tracemalloc
import zipfile
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core.audit.invariants import FORBIDDEN_WORDS, check_report_text
from core.db import apply_schema
from core.ingest import coverage, forwarded, ufdr, ufdr_check
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.ufdr import UfdrImporter
from core.report.html import render_report
from eval.synthetic.generate import generate
from eval.synthetic.ufdr import (
    UNKNOWN_TYPES,
    field,
    iso_local,
    many,
    model,
    one,
    party,
    related,
    related_package,
    report_xml,
    ts_field,
    write_case01,
    write_package,
)
from tests.test_coverage_display import _screen, _send, _setup

OWNER = ("+15550100001", None, True)
JO = ("+15550100002", "Jo", False)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


def _import(
    path: Path, sid: str = "u1", **kw
) -> tuple[sqlite3.Connection, coverage.CoverageSummary]:
    conn = _db()
    UfdrImporter(source_id=sid, **kw).import_source(path, conn)
    s = coverage.summary(conn, sid)
    assert s is not None
    return conn, s


def _codes(s: coverage.CoverageSummary) -> dict[str, str]:
    return {i.code: i.level for i in s.items}


def _msg(body: str, ts: str | None, frm=JO, to=(OWNER,), **attrs) -> str:
    parts = [
        field("Source", "WhatsApp"),
        one("From", party(*frm)),
        many("To", [party(*p) for p in to]),
        field("Body", body),
        ts_field("TimeStamp", ts),
    ]
    return model("InstantMessage", *parts, **attrs)


def _chat(key: str, *messages: str, extra: tuple[str, ...] = ()) -> str:
    return model(
        "Chat",
        field("Source", "WhatsApp"),
        field("Id", key),
        field("Name", f"Chat {key}"),
        many("Participants", [party(*OWNER), party(*JO)]),
        many("Messages", messages, "InstantMessage"),
        *extra,
    )


# ---------------------------------------------------------------- case01 parity


@pytest.fixture(scope="module")
def case01(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("case01")
    generate(out)
    write_case01(out)
    return out


PARITY = {
    "accounts": "SELECT id, app, identifier, display_name, device_id IS NOT NULL FROM accounts",
    "threads": "SELECT id, app, title FROM threads",
    "messages": "SELECT thread_id, sender_account_id, direction, ts_utc, ts_offset_min, body,"
    " deleted_flag FROM messages",
    "recipients": "SELECT m.thread_id, m.ts_utc, m.body, r.account_id FROM message_recipients r"
    " JOIN messages m ON m.id = r.message_id",
    "calls": "SELECT app, from_account_id, to_account_id, direction, ts_utc, ts_offset_min,"
    " duration_s, deleted_flag FROM calls",
    "contacts": "SELECT name, identifier FROM contacts",
    "attachments": "SELECT m.thread_id, m.ts_utc, a.file_name FROM attachments a"
    " JOIN messages m ON m.id = a.message_id",
    "devices": "SELECT id, label, model, os_version, timezone FROM devices",
    "sources": "SELECT id, extraction_type, extracted_at_utc FROM sources",
}


@pytest.mark.parametrize("device", ["item1", "item2"])
def test_case01_as_ufdr_gives_the_same_records_as_its_excel_report(case01, device):
    xl = _db()
    CellebriteExcelImporter(source_id=device).import_source(case01 / f"{device}.xlsx", xl)
    uf = _db()
    UfdrImporter(source_id=device).import_source(case01 / f"{device}.ufdr", uf)
    for name, sql in PARITY.items():
        a = sorted(map(repr, xl.execute(sql)))
        b = sorted(map(repr, uf.execute(sql)))
        assert a == b, name
        assert a or name == "attachments", name  # item2 has no attachments


def test_case01_ufdr_source_ids_locators_and_hashes(case01):
    path = case01 / "item1.ufdr"
    conn, s = _import(path, "item1")
    kind, fidelity, sha = conn.execute("SELECT kind, fidelity, sha256 FROM sources").fetchone()
    assert (kind, fidelity) == ("ufdr", "unknown")  # never a full extraction while unverified
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()
    mid, loc = conn.execute("SELECT id, locator FROM messages ORDER BY rowid LIMIT 1").fetchone()
    assert (mid, loc) == ("msg:item1:Chat[1]/Messages[1]", "Chat[1]/Messages[1]")
    assert conn.execute("SELECT id FROM calls ORDER BY rowid LIMIT 1").fetchone() == (
        "call:item1:Call[1]",
    )
    assert conn.execute("SELECT id FROM contacts ORDER BY rowid LIMIT 1").fetchone() == (
        "contact:item1:Contact[1]#1",
    )
    # the attachment file inside the package is hashed; its name and type come from report.xml
    att_id, mid, name, mime, att_sha = conn.execute(
        "SELECT id, message_id, file_name, mime_type, sha256 FROM attachments"
    ).fetchone()
    assert att_id == f"att:item1:{mid.removeprefix('msg:item1:')}:1" and mime == "application/pdf"
    with zipfile.ZipFile(path) as z:
        member = next(n for n in z.namelist() if n.endswith(name))
        assert att_sha == hashlib.sha256(z.read(member)).hexdigest()
    payload = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    assert payload["importer"] == "ufdr" and payload["importer_version"] == ufdr.IMPORTER_VERSION
    assert payload["format_support"] == "unverified"
    with zipfile.ZipFile(path) as z:
        assert payload["ufdr"]["report_sha256"] == hashlib.sha256(z.read("report.xml")).hexdigest()
    (logged,) = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'import'"
    ).fetchone()
    assert json.loads(logged) == payload
    assert s.status == "needs_review" and s.format_unverified
    assert s.headline.startswith("Unverified format. Imported all ")


def test_case01_packages_are_deterministic(tmp_path):
    a = write_case01(tmp_path / "a")
    b = write_case01(tmp_path / "b")
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]


# ---------------------------------------------------------------- record flags and times


@pytest.fixture(scope="module")
def edge(tmp_path_factory) -> Path:
    t = "2026-03-05T21:31:00.000-05:00"
    files = {"files/Image/a.jpg": b"SYNTHETIC jpeg bytes"}
    good = hashlib.sha256(files["files/Image/a.jpg"]).hexdigest()
    att = [
        model(
            "Attachment",
            field("Filename", "a.jpg"),
            field("ContentType", "image/jpeg"),
            field("attachment_extracted_path", "files\\Image\\a.jpg"),
            field("SHA256", good),
        ),
        model("Attachment", field("Filename", "gone.jpg"), field("LocalPath", "files/gone.jpg")),
        model("Attachment", field("Filename", "b.jpg"), field("LocalPath", "files/Image/a.jpg"),
              field("SHA256", "0" * 64)),
    ]  # fmt: skip
    chat = _chat(
        "c1",
        _msg("hello from Jo", t, deleted_state="Intact"),
        _msg("reply", "2026-03-05T21:32:00.000-05:00", frm=OWNER, to=(JO,)),
        _msg("in the trash", t, deleted_state="Trash"),
        _msg("marked", t, deleted_state="Deleted"),
        _msg("rebuilt", t, carved="True"),
        _msg("unsure", t, decoding_confidence="Low"),
        _msg("no state", t, deleted_state=None),
        _msg("no offset", "2026-03-05T21:31:00"),
        _msg("day or month", "3/4/2026 9:31:00 PM(UTC-5)"),
        _msg("no time at all", None),
        model(
            "InstantMessage",
            field("Source", "WhatsApp"),
            one("From", party(*JO)),
            field("Body", "with files"),
            ts_field("TimeStamp", t),
            field("Mood", "calm"),
            many("Attachments", att, "Attachment"),
        ),
    )
    sms = [
        model(
            "SMS",
            field("Folder", "Inbox"),
            many("Parties", [party("+15550100003", "Sam", role="From")]),
            field("Body", "sms in"),
            ts_field("TimeStamp", t),
        ),
        model(
            "SMS",
            field("Folder", "Sent"),
            many("Parties", [party("+15550100003", "Sam", role="To")]),
            field("Body", "sms out\r\nsecond line"),
            ts_field("TimeStamp", t),
        ),
    ]
    calls = [
        model(
            "Call",
            field("Type", "Missed"),
            ts_field("TimeStamp", t),
            field("Duration", "1.00:00:05", "TimeSpan"),
            many("Parties", [party("+15550100003", "Sam", role="From")]),
        ),
        model(
            "Call",
            field("Type", "Outgoing"),
            ts_field("TimeStamp", t),
            field("Duration", "about a minute", "TimeSpan"),
            many("Parties", [party("+15550100003", "Sam", role="To")]),
        ),
    ]
    loose = [_msg("not in a chat", t, frm=OWNER, to=(JO,))]
    xml = report_xml(
        {
            "Location": [model("Location", field("Name", "x"))] * 3,
            "MysteryThing": [model("MysteryThing", field("Name", "y"))],
            "Chat": [chat],
            "InstantMessage": loose,
            "SMS": sms,
            "Call": calls,
            "UserAccount": [
                model("UserAccount", field("Source", "WhatsApp"), field("Username", OWNER[0]))
            ],
        },
        [("DeviceInfoSelectedDeviceName", "SyntheticPhone X1")],
        [
            {"type": "Logical", "deviceName": "SyntheticPhone X1"},
            {"type": "File System", "deviceName": "SyntheticPhone X1", "IsPartialData": "True"},
        ],
        extra='<taggedFiles><file id="f1" path="files/Image/a.jpg" /></taggedFiles>',
    )
    return write_package(tmp_path_factory.mktemp("edge") / "edge.ufdr", xml, files)


def test_record_states_and_recovery_flags_are_kept_never_guessed(edge):
    conn, s = _import(edge)
    flags = dict(conn.execute("SELECT body, deleted_flag FROM messages"))
    assert flags["hello from Jo"] == 0
    assert flags["in the trash"] == 1 and flags["marked"] == 1  # what the package states
    assert flags["no state"] is None  # not stated: never read as either
    codes = _codes(s)
    assert codes["carved"] == "attention" and codes["decoding_confidence_not_high"] == "attention"
    carved = next(i for i in s.items if i.code == "carved")
    assert carved.locators == ("Chat[1]/Messages[5]",)
    assert codes["record_states"] == "info"
    states = next(i for i in s.items if i.code == "record_states")
    assert ("Trash", True) in states.parts and ("Deleted", True) in states.parts


def test_times_keep_their_offset_and_are_never_guessed(edge):
    conn, s = _import(edge)
    rows = {b: (u, o, r) for b, u, o, r in conn.execute(
        "SELECT body, ts_utc, ts_offset_min, ts_raw FROM messages")}  # fmt: skip
    assert rows["hello from Jo"] == ("2026-03-06T02:31:00Z", -300, "2026-03-05T21:31:00.000-05:00")
    assert rows["no offset"] == (None, None, "2026-03-05T21:31:00")
    assert rows["day or month"][0] is None  # 3/4/2026: nothing in the package decides
    codes = _codes(s)
    assert codes["times_no_offset"] == "attention"
    assert codes["times_ambiguous_day_month"] == "attention"
    no_time = next(i for i in s.items if i.code == "no_time")
    assert no_time.level == "attention" and no_time.locators == ("Chat[1]/Messages[10]",)
    assert rows["no time at all"] == (None, None, None)

    conn2, s2 = _import(edge, date_order="dmy")
    (utc,) = conn2.execute("SELECT ts_utc FROM messages WHERE body = 'day or month'").fetchone()
    assert utc == "2026-04-04T02:31:00Z"  # 3 April, 21:31 at UTC-5
    assert "times_ambiguous_day_month" not in _codes(s2)


def test_direction_parties_and_threads_follow_the_shared_mapping(edge):
    conn, _ = _import(edge)
    d = dict(conn.execute("SELECT body, direction FROM messages"))
    assert d["hello from Jo"] == "incoming" and d["reply"] == "outgoing"  # from the owner flag
    assert d["not in a chat"] == "outgoing"
    assert d["sms in"] == "incoming" and d["sms out\r\nsecond line"] == "outgoing"  # CR kept
    threads = {r[0] for r in conn.execute("SELECT id FROM threads")}
    assert "thr:u1:WhatsApp:c1" in threads and "thr:u1:SMS:sms:+15550100003" in threads
    owner = conn.execute(
        "SELECT device_id FROM accounts WHERE id = 'acct:u1:WhatsApp:+15550100001'"
    ).fetchone()
    assert owner == ("dev:u1",)
    calls = conn.execute("SELECT direction, duration_s, from_account_id FROM calls").fetchall()
    assert ("missed", 86405, "acct:u1:unknown:+15550100003") in calls
    assert ("outgoing", None, None) in calls


def test_attachments_are_hashed_from_the_package_and_mismatches_listed(edge):
    conn, s = _import(edge)
    atts = {n: (m, h) for n, m, h in conn.execute(
        "SELECT file_name, mime_type, sha256 FROM attachments")}  # fmt: skip
    good = hashlib.sha256(b"SYNTHETIC jpeg bytes").hexdigest()
    assert atts["a.jpg"] == ("image/jpeg", good)
    assert atts["gone.jpg"] == (None, None)
    assert atts["b.jpg"] == (None, good)  # hashed from the package, not taken from report.xml
    codes = _codes(s)
    assert codes["attachment_file_not_in_package"] == "attention"
    assert codes["attachment_hash_differs"] == "attention"


def test_coverage_lists_what_the_package_held_and_baker_did_not_read(edge):
    _conn, s = _import(edge)
    codes = _codes(s)
    assert codes["format_unverified"] == "attention" and s.items[0].code == "format_unverified"
    assert codes["category_not_imported"] == "info"  # Location: known, not imported yet
    assert codes["not_imported"] == "attention"  # MysteryThing: not recognised
    mystery = next(i for i in s.items if i.code == "not_imported")
    assert mystery.plain.startswith("MysteryThing was not imported (1 record)")
    assert codes["partial_extraction"] == "attention"
    assert codes["several_extractions"] == "info"
    assert codes["tagged_files"] == "info" and codes["package_files"] == "info"
    assert codes["duration_unread"] == "attention"
    unknown = next(i for i in s.items if i.code == "unknown_columns")
    assert "fields Baker does not read" in unknown.plain and ("Mood", True) in unknown.parts


def test_coverage_own_words_never_use_forbidden_words(edge):
    _conn, s = _import(edge)
    for item in s.items:
        own = "".join(t for t, quoted in item.parts if not quoted)
        assert not FORBIDDEN_WORDS.search(own), item.plain
    assert not FORBIDDEN_WORDS.search(s.headline)


def test_rows_read_balance_for_every_record_type(edge):
    conn, _ = _import(edge)
    (payload,) = conn.execute("SELECT payload_json FROM source_coverage").fetchone()
    for t in json.loads(payload)["tables"]:
        skipped = sum(t["rows_skipped"].values())
        assert t["rows_read"] == t["rows_imported"] + skipped, t["name"]
    p = json.loads(payload)
    assert p["ufdr"]["model_counts"]["Location"] == 3


def test_no_message_is_left_inside_a_chat_and_a_record_listed_twice_is_imported_once(tmp_path):
    t = "2026-03-05T21:31:00.000-05:00"
    chat = model(
        "Chat",
        field("Source", "WhatsApp"),
        field("Id", "c9"),
        many("InstantMessages", [_msg("other field name", t, id="m1")], "InstantMessage"),
        many("Messages", [_msg("usual field", t, id="m2")], "InstantMessage"),
    )
    loose = [_msg("usual field", t, id="m2")]  # the same record again, on its own
    xml = report_xml({"Chat": [chat], "InstantMessage": loose})
    conn, s = _import(write_package(tmp_path / "twice.ufdr", xml))
    got = dict(conn.execute("SELECT locator, body FROM messages"))
    assert got == {
        "Chat[1]/InstantMessages[1]": "other field name",
        "Chat[1]/Messages[1]": "usual field",
    }
    item = next(i for i in s.items if i.code == "rows_skipped_same_id_as_an_earlier_record")
    assert item.level == "attention" and item.locators == ("InstantMessage[1]",)
    assert item.plain.startswith("In InstantMessage, 1 record was not imported")


# ---------------------------------------------------------------- refusals


def _refused(path: Path, match: str) -> None:
    conn = _db()
    with pytest.raises(ValueError, match=match):
        UfdrImporter(source_id="bad").import_source(path, conn)
    assert conn.execute("SELECT COUNT(*) FROM sources").fetchone() == (0,)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (0,)


def test_a_document_type_or_entity_is_refused(tmp_path):
    xml = (
        '<?xml version="1.0"?><!DOCTYPE project [<!ENTITY a "aaaa">]>'
        '<project xmlns="http://pa.cellebrite.com/report/2.0"><decodedData/></project>'
    )
    _refused(write_package(tmp_path / "dtd.ufdr", xml), "document type")


def test_broken_xml_stores_nothing(tmp_path):
    xml = report_xml({"Chat": [_chat("c1", _msg("x", "2026-03-05T21:31:00Z"))]})
    _refused(write_package(tmp_path / "cut.ufdr", xml[: len(xml) // 2]), "not well-formed")


def test_not_a_ufdr_is_refused(tmp_path):
    (tmp_path / "plain.ufdr").write_bytes(b"not a zip")
    _refused(tmp_path / "plain.ufdr", "not a zip")
    write_package(tmp_path / "noreport.zip", "<x/>", member="other.xml")
    _refused(tmp_path / "noreport.zip", "no report.xml")
    two = tmp_path / "two.zip"
    with zipfile.ZipFile(two, "w") as z:
        z.writestr("a/report.xml", "<project/>")
        z.writestr("b/report.xml", "<project/>")
    _refused(two, "more than one report.xml")
    write_package(tmp_path / "root.zip", "<html/>")
    _refused(tmp_path / "root.zip", "root element 'html'")


def test_two_devices_in_one_package_are_refused(tmp_path):
    xml = report_xml(
        {"Chat": [_chat("c1", _msg("x", "2026-03-05T21:31:00Z"))]},
        extractions=[
            {"type": "Logical", "deviceName": "A"},
            {"type": "Logical", "deviceName": "B"},
        ],
    )
    _refused(write_package(tmp_path / "two.ufdr", xml), "more than one device")


# ---------------------------------------------------------------- streaming


def test_large_packages_stream_in_batches_with_bounded_memory(tmp_path, monkeypatch):
    """Many chats, written in many batches: memory follows one chat, not the package."""
    monkeypatch.setattr(ufdr, "BATCH", 500)
    chats = []
    for c in range(400):
        msgs = [
            _msg(f"synthetic message {c}-{i} " + "x" * 200, iso_local_ts(c, i)) for i in range(50)
        ]
        chats.append(_chat(f"c{c}", *msgs))
    xml = report_xml({"Chat": chats})
    path = write_package(tmp_path / "big.ufdr", xml)
    writes = []
    real = ufdr._StreamWriter.write_pending
    monkeypatch.setattr(
        ufdr._StreamWriter, "write_pending", lambda self: (writes.append(1), real(self))[1]
    )
    tracemalloc.start()
    try:
        conn, s = _import(path)
        _cur, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (20000,)
    assert len(writes) >= 20  # rows went to the database as the file was read
    assert peak < len(xml) / 2, (peak, len(xml))  # the XML was never held whole
    assert "Imported all 20,000 records read from 1 record type" in s.headline


def iso_local_ts(c: int, i: int) -> str:
    from datetime import UTC, datetime, timedelta

    return iso_local(datetime(2026, 3, 1, tzinfo=UTC) + timedelta(minutes=c * 60 + i), -300)


# ---------------------------------------------------------------- where the expert sees it


def test_baker_import_reads_a_ufdr_and_says_it_is_unverified(case01, tmp_path, capsys):
    db = tmp_path / "c.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    assert cli_main(["import", "--db", str(db), "--report", str(case01 / "item2.ufdr")]) == 0
    out = capsys.readouterr().out
    assert "(unknown)" in out and "Unverified format." in out
    assert "UFDR reader is not yet verified" in out


def test_case_screen_imports_a_ufdr_and_shows_it_unverified(case01, tmp_path):
    app = _screen(tmp_path)
    assert _send(app, case01 / "item2.ufdr").status == 303
    page = _setup(app)
    assert "Imported item2.ufdr" in page and "Unverified format." in page
    assert "UFDR reader is not yet verified" in page
    assert ".ufdr" in page  # the upload form takes UFDR packages
    check_report_text(page)


def test_report_limitations_say_the_ufdr_reader_is_unverified(case01, edge):
    conn = _db()
    UfdrImporter(source_id="item2").import_source(case01 / "item2.ufdr", conn)
    UfdrImporter(source_id="edge").import_source(edge, conn)
    html = render_report(conn)
    limits = html.split("<h2>Limitations</h2>", 1)[1].split("<h2>", 1)[0]
    assert limits.count("UFDR reader, which is not yet verified") == 2
    assert "The coverage of" in limits  # fidelity not known: no absence finding rests on it
    # item2 has nothing else to review; the edge package lists what it did not read
    assert 'Baker did not read all of <span class="q">item2.ufdr' not in limits
    assert 'Baker did not read all of <span class="q">edge.ufdr' in limits
    check_report_text(html)


def test_the_upload_rejects_other_suffixes_with_the_ufdr_named(tmp_path):
    app = _screen(tmp_path)
    p = tmp_path / "x.txt"
    p.write_bytes(b"x")
    _send(app, p)
    assert "UFDR (.ufdr or .zip)" in _setup(app)


def test_hashing_reader_hashes_what_it_reads():
    r = ufdr._HashingReader(io.BytesIO(b"abc" * 1000))
    while r.read(7):
        pass
    assert r.h.hexdigest() == hashlib.sha256(b"abc" * 1000).hexdigest() and r.size == 3000


def test_an_encrypted_case_imports_a_ufdr_through_decryption(case01, tmp_path):
    """The copy is encrypted as it is uploaded; the importer reads the zip through the
    decrypting reader, hashes the plain bytes and stores the same records as a plain import."""
    from core import encryption
    from core.db import connect
    from tests.test_coverage_display import HOST
    from ui.app import Request

    app = _screen(tmp_path / "plain")
    pkg = case01 / "item2.ufdr"
    app.handle(
        Request(
            "POST",
            "/case/new",
            {},
            dict(HOST),
            {"token": app.token, "name": "Synth encrypted", "encrypt": "1",
             "passphrase": "correct horse battery staple",
             "passphrase2": "correct horse battery staple"},
        )
    )  # fmt: skip
    case = app.case
    assert case is not None and encryption.is_encrypted_case(case.db)
    assert _send(app, pkg).status == 303
    assert "Imported item2.ufdr" in _setup(app)
    copy = case.inputs / "item2.ufdr"
    assert encryption.is_encrypted_file(copy) and not zipfile.is_zipfile(copy)
    conn = connect(case.db)
    plain = _db()
    UfdrImporter(source_id="item2").import_source(pkg, plain)
    sha = hashlib.sha256(pkg.read_bytes()).hexdigest()
    assert conn.execute("SELECT sha256 FROM sources WHERE id = 'item2'").fetchone() == (sha,)
    for name, sql in PARITY.items():
        if name == "sources":
            continue
        assert sorted(map(repr, conn.execute(sql))) == sorted(map(repr, plain.execute(sql))), name
    conn.close()


# ---------------------------------------------------------------- shapes from third-party samples
# Both shapes below were found by running ufdr-check on public third-party UFDR samples
# (docs/ingest/ufdr.md, "Checked against public samples"). The samples are not in the repo.


BACKSLASH_PATH = "files\\Image\\goat.jpg"  # as Physical Analyzer writes it on Windows


def _tagged_file(fid: str, local_path: str) -> str:
    return (
        f'<file fs="Phone" path="/data/goat.jpg" id="{fid}">'
        '<metadata section="File">'
        f'<item name="Local Path"><![CDATA[{local_path}]]></item>'
        '<item name="SHA256"><![CDATA[]]></item>'
        "</metadata></file>"
    )


def test_an_attachment_that_names_its_file_only_through_file_id_is_hashed(tmp_path):
    att = model(
        "Attachment",
        field("Filename", "goat.jpg"),
        field("ContentType", "image/jpeg"),
        file_id="tf-1",
    )
    msg = model(
        "InstantMessage",
        field("Source", "WhatsApp"),
        one("From", party(*JO)),
        field("Body", "look"),
        ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00"),
        many("Attachments", [att], "Attachment"),
    )
    body = b"SYNTHETIC goat bytes"
    xml = report_xml(
        {"Chat": [_chat("c1", msg)]},
        # taggedFiles after the records: the link must not depend on document order
        extra=f"<taggedFiles>{_tagged_file('tf-1', BACKSLASH_PATH)}</taggedFiles>",
    )
    path = write_package(tmp_path / "p.ufdr", xml, {"files/Image/goat.jpg": body})
    conn, s = _import(path)
    rows = conn.execute("SELECT file_name, sha256 FROM attachments").fetchall()
    assert rows == [("goat.jpg", hashlib.sha256(body).hexdigest())]
    assert "attachment_file_not_in_package" not in _codes(s)


def test_an_account_or_contact_never_takes_a_picture_link_as_an_identifier(tmp_path):
    pic = "https://cdn.example.invalid/SYNTHETIC/pic.jpg"
    acct = model(
        "UserAccount",
        field("Source", "Instagram"),
        field("Name", "Sam"),
        many(
            "Entries",
            [
                model("ProfilePicture", field("Value", pic)),
                model("UserID", field("Value", "1212121212")),
            ],
            "ContactEntry",
        ),
    )
    contact = model(
        "Contact",
        field("Name", "Jo"),
        many(
            "Entries",
            [
                model("ContactPhoto", field("Value", pic)),
                model("PhoneNumber", field("Value", "+15550100002")),
            ],
            "ContactEntry",
        ),
    )
    path = write_package(
        tmp_path / "p.ufdr", report_xml({"UserAccount": [acct], "Contact": [contact]})
    )
    conn, _s = _import(path)
    assert conn.execute(
        "SELECT app, identifier FROM accounts WHERE locator = 'UserAccount[1]'"
    ).fetchall() == [("Instagram", "1212121212")]
    assert conn.execute("SELECT name, identifier FROM contacts").fetchall() == [
        ("Jo", "+15550100002")
    ]


def test_a_forwarded_message_is_listed_and_never_shown_as_quietly_authored(tmp_path):
    def labels(*vals: str) -> str:
        inner = "".join(f'<value type="Label"><![CDATA[{v}]]></value>' for v in vals)
        return f'<multiField name="Labels" type="Label">{inner}</multiField>'

    embedded = model("InstantMessage", field("Body", "SYNTHETIC original words"))
    base = [field("Source", "WhatsApp"), one("From", party(*OWNER)),
            ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00")]  # fmt: skip
    by_labels = model("InstantMessage", *base, field("Body", "SYNTHETIC passed on"),
                      labels("Forwarded", "Edited"))  # fmt: skip
    by_extra = model(
        "InstantMessage",
        *base,
        many("MessageExtraData",
             [model("MessageLabel", field("Label", "Forwarded", "Label"))],
             "InstantMessageExtraData"),
        many("EmbeddedInstantMessage", [embedded], "InstantMessage"),
    )  # fmt: skip
    plain = model("InstantMessage", *base, field("Body", "SYNTHETIC own words"), labels("Edited"))
    path = write_package(
        tmp_path / "p.ufdr", report_xml({"Chat": [_chat("c1", by_labels, by_extra, plain)]})
    )
    conn, s = _import(path)
    item = next(i for i in s.items if i.code == "forwarded")
    assert item.level == "attention"
    assert item.locators == ("Chat[1]/Messages[1]", "Chat[1]/Messages[2]")
    assert "has not verified who first wrote" in item.plain
    emb = next(i for i in s.items if i.code == "embedded_message_imported_separately")
    assert emb.locators == ("Chat[1]/Messages[2]",)
    # the embedded original is its own record, never the forwarder's words
    rows = dict(conn.execute("SELECT locator, body FROM messages"))
    assert rows["Chat[1]/Messages[2]/Embedded[1]"] == "SYNTHETIC original words"
    assert rows["Chat[1]/Messages[2]"] != "SYNTHETIC original words"


def _extra(label: str, type_: str = "MessageLabel") -> str:
    return many(
        "MessageExtraData",
        [model(type_, field("Label", label, "Label"))],
        "InstantMessageExtraData",
    )


def _embedded(*models: str) -> str:
    return many("EmbeddedInstantMessage", list(models), "InstantMessage")


def test_quoted_and_nested_forwards_are_listed_in_full_and_one_level_is_imported_separately(
    tmp_path,
):
    base = [field("Source", "WhatsApp"), one("From", party(*OWNER)),
            ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00")]  # fmt: skip
    # a reply quoting Jo's message: not forwarded, but it carries someone else's words
    quoted = model(
        "InstantMessage",
        *base,
        field("Body", "SYNTHETIC my answer"),
        _extra("Reply", "QuotedMessageData"),
        _embedded(model("InstantMessage", field("Body", "SYNTHETIC Jo's question"))),
    )
    # a forward of a forward: the inner original is itself marked forwarded
    inner = model(
        "InstantMessage",
        field("Body", "SYNTHETIC passed along twice"),
        _extra("Forwarded"),
        _embedded(model("InstantMessage", field("Body", "SYNTHETIC first author's words"))),
    )
    nested = model("InstantMessage", *base, _extra("Forwarded"), _embedded(inner))
    plain = model("InstantMessage", *base, field("Body", "SYNTHETIC own words"))
    path = write_package(
        tmp_path / "p.ufdr", report_xml({"Chat": [_chat("c1", quoted, nested, plain)]})
    )
    conn, s = _import(path)
    fwd = next(i for i in s.items if i.code == "forwarded")
    assert fwd.locators == ("Chat[1]/Messages[2]",)
    sep = next(i for i in s.items if i.code == "embedded_message_imported_separately")
    assert sep.locators == ("Chat[1]/Messages[1]", "Chat[1]/Messages[2]")
    got = next(i for i in s.items if i.code == "embedded_original_imported")
    assert got.locators == ("Chat[1]/Messages[1]/Embedded[1]", "Chat[1]/Messages[2]/Embedded[1]")
    # the second level, nested inside an embedded message, is not imported
    nested_item = next(i for i in s.items if i.code == "embedded_message_not_imported")
    assert nested_item.locators == ("Chat[1]/Messages[2]/Embedded[1]",)
    bodies = dict(conn.execute("SELECT locator, body FROM messages"))
    assert bodies == {
        "Chat[1]/Messages[1]": "SYNTHETIC my answer",
        "Chat[1]/Messages[1]/Embedded[1]": "SYNTHETIC Jo's question",
        "Chat[1]/Messages[2]": "",
        "Chat[1]/Messages[2]/Embedded[1]": "SYNTHETIC passed along twice",
        "Chat[1]/Messages[3]": "SYNTHETIC own words",
    }
    # the embedded originals are never the phone owner's words, and share the parent's thread
    rows = conn.execute(
        "SELECT direction, sender_raw, forwarded, forwarded_from_raw, thread_id FROM messages"
        " WHERE locator LIKE '%/Embedded[%' ORDER BY locator"
    ).fetchall()
    tid = conn.execute("SELECT thread_id FROM messages WHERE locator = 'Chat[1]/Messages[1]'")
    t = tid.fetchone()[0]
    assert rows == [("unknown", None, 1, None, t), ("unknown", None, 1, None, t)]
    # every affected message is listed by id for the fail-closed path downstream
    found = forwarded.affected(conn)
    ids = dict(conn.execute("SELECT locator, id FROM messages"))
    assert found == {
        ids["Chat[1]/Messages[1]"]: "embedded",
        ids["Chat[1]/Messages[1]/Embedded[1]"]: "embedded_copy",
        ids["Chat[1]/Messages[2]"]: "forwarded",
        ids["Chat[1]/Messages[2]/Embedded[1]"]: "embedded_copy",
    }


def test_picture_entries_are_counted_in_coverage(tmp_path):
    pic = "https://cdn.example.invalid/SYNTHETIC/pic.jpg"
    contact = model(
        "Contact",
        field("Name", "Jo"),
        many(
            "Entries",
            [
                model("ContactPhoto", field("Value", pic)),
                model("PhoneNumber", field("Value", "+15550100002")),
            ],
            "ContactEntry",
        ),
    )
    path = write_package(tmp_path / "p.ufdr", report_xml({"Contact": [contact]}))
    _conn, s = _import(path)
    item = next(i for i in s.items if i.code == "picture_entries_not_identifiers")
    assert item.level == "info"
    assert item.plain.endswith("identifiers: 1.")


def test_a_tagged_file_id_with_two_paths_links_to_neither(tmp_path):
    att = model("Attachment", field("Filename", "goat.jpg"), file_id="tf-1")
    msg = model(
        "InstantMessage",
        field("Source", "WhatsApp"),
        one("From", party(*JO)),
        field("Body", "look"),
        ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00"),
        many("Attachments", [att], "Attachment"),
    )
    tagged = _tagged_file("tf-1", BACKSLASH_PATH) + _tagged_file("tf-1", "files/Image/other.jpg")
    xml = report_xml({"Chat": [_chat("c1", msg)]}, extra=f"<taggedFiles>{tagged}</taggedFiles>")
    path = write_package(
        tmp_path / "p.ufdr", xml, {"files/Image/goat.jpg": b"a", "files/Image/other.jpg": b"b"}
    )
    conn, s = _import(path)
    assert conn.execute("SELECT sha256 FROM attachments").fetchall() == [(None,)]
    codes = _codes(s)
    assert codes["tagged_file_ids_repeated"] == "attention"
    assert codes["attachment_file_ambiguous"] == "attention"


def test_a_forwarded_message_is_marked_on_the_record_with_its_original_author(tmp_path):
    base = [field("Source", "WhatsApp"), one("From", party(*OWNER)),
            ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00")]  # fmt: skip
    original = model(
        "InstantMessage", one("From", party(*JO)), field("Body", "SYNTHETIC Jo's words")
    )
    named = model("InstantMessage", *base, field("Body", "SYNTHETIC passed on"),
                  _extra("Forwarded"), _embedded(original))  # fmt: skip
    unnamed = model("InstantMessage", *base, field("Body", "SYNTHETIC passed on too"),
                    _extra("Forwarded"))  # fmt: skip
    quoted = model("InstantMessage", *base, field("Body", "SYNTHETIC my answer"),
                   _embedded(original))  # fmt: skip
    plain = model("InstantMessage", *base, field("Body", "SYNTHETIC own words"))
    # a forward of a forward: the embedded sender is only an intermediate forwarder
    relayed = model("InstantMessage", one("From", party(*JO)), field("Body", "SYNTHETIC relayed"),
                    _extra("Forwarded"))  # fmt: skip
    nested = model("InstantMessage", *base, field("Body", "SYNTHETIC passed on again"),
                   _extra("Forwarded"), _embedded(relayed))  # fmt: skip
    chat = _chat("c1", named, unnamed, quoted, plain, nested)
    path = write_package(tmp_path / "p.ufdr", report_xml({"Chat": [chat]}))
    conn, _s = _import(path)
    rows = conn.execute(
        "SELECT locator, forwarded, forwarded_from_raw FROM messages ORDER BY locator"
    ).fetchall()
    assert rows == [
        ("Chat[1]/Messages[1]", 1, "+15550100002 Jo"),
        ("Chat[1]/Messages[1]/Embedded[1]", 1, "+15550100002 Jo"),  # the original, own record
        ("Chat[1]/Messages[2]", 1, None),  # the package names no original author
        ("Chat[1]/Messages[3]", None, None),  # a quote is not a forward
        ("Chat[1]/Messages[3]/Embedded[1]", 1, "+15550100002 Jo"),  # the quoted words
        ("Chat[1]/Messages[4]", None, None),
        ("Chat[1]/Messages[5]", 1, None),  # never the intermediate forwarder
        ("Chat[1]/Messages[5]/Embedded[1]", 1, None),  # itself forwarded: author unknown
    ]
    from core.report.html import record_line

    mid = conn.execute("SELECT id FROM messages WHERE locator = 'Chat[1]/Messages[1]'").fetchone()
    line = record_line(conn, mid[0], forwarded.affected(conn))
    assert 'names <span class="q">+15550100002 Jo</span> as the original author' in line


def test_a_case_made_before_the_forwarded_columns_still_fails_closed(tmp_path):
    msg = model("InstantMessage", field("Source", "WhatsApp"), one("From", party(*OWNER)),
                field("Body", "SYNTHETIC passed on"), _extra("Forwarded"))  # fmt: skip
    path = write_package(tmp_path / "p.ufdr", report_xml({"Chat": [_chat("c1", msg)]}))
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    schema = (Path(__file__).parents[1] / "core" / "schema.sql").read_text(encoding="utf-8")
    old = schema.replace(
        "    bookmarked      INTEGER CHECK (bookmarked IN (0, 1)),",
        "    bookmarked      INTEGER CHECK (bookmarked IN (0, 1))",
    )
    old = old.replace(
        "    forwarded       INTEGER CHECK (forwarded IN (0, 1)),"
        "     -- NULL = source did not say\n",
        "",
    ).replace(
        "    forwarded_from_raw TEXT          -- the original author as the source wrote it, "
        "when it says\n",
        "",
    )
    conn.executescript(old)
    assert not forwarded.has_columns(conn)
    UfdrImporter(source_id="u1").import_source(path, conn)
    (mid,) = conn.execute("SELECT id FROM messages").fetchone()
    assert forwarded.affected(conn) == {mid: "forwarded"}
    assert forwarded.original_author(conn, mid) is None
    # the report says which mode the case is in, so the weaker one is never silent
    from core.report.html import forwarded_label

    label = forwarded_label(conn)
    assert label.startswith("coverage list only (case made before contracts")
    # an import from before the list existed is not promised the fail-closed path
    assert "imported before Baker listed forwarded messages (#73)" in label
    new_case = sqlite3.connect(":memory:")
    new_case.executescript(schema)
    assert forwarded_label(new_case).startswith("on the record")


def test_an_embedded_original_is_its_own_record_with_its_author_as_written(tmp_path):
    original = model(
        "InstantMessage",
        one("From", party(*JO)),
        field("Body", "  SYNTHETIC Jo's exact words\n"),
        ts_field("TimeStamp", "2026-03-01T10:00:00.000-05:00"),
    )
    fwd = model(
        "InstantMessage",
        field("Source", "WhatsApp"),
        one("From", party(*OWNER)),
        one("To", party(*JO)),
        field("Body", "SYNTHETIC look at this"),
        field("Direction", "Outgoing"),
        ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00"),
        _extra("Forwarded"),
        _embedded(original),
    )
    path = write_package(tmp_path / "p.ufdr", report_xml({"InstantMessage": [fwd]}))
    conn, s = _import(path)
    rows = conn.execute(
        "SELECT locator, body, sender_raw, direction, ts_raw, forwarded, forwarded_from_raw,"
        " thread_id FROM messages ORDER BY locator"
    ).fetchall()
    assert len(rows) == 2
    parent, emb = rows
    assert parent[0] == "InstantMessage[1]" and parent[3] == "outgoing"
    assert emb[0] == "InstantMessage[1]/Embedded[1]"
    assert emb[1] == "  SYNTHETIC Jo's exact words\n"  # verbatim
    sender = conn.execute(
        "SELECT a.identifier FROM messages m JOIN accounts a ON a.id = m.sender_account_id"
        " WHERE m.locator = ?",
        (emb[0],),
    ).fetchone()
    assert sender == ("+15550100002",)  # Jo, never the forwarder or the phone owner
    assert emb[3] != "outgoing"  # never the phone owner's words
    assert emb[4] is None  # the original's time is kept off the record and the timeline
    assert emb[5:7] == (1, "+15550100002 Jo")
    assert emb[7] == parent[7]  # same thread
    assert _codes(s)["embedded_messages_imported"] == "info"


def test_an_embedded_original_already_imported_by_id_is_not_duplicated(tmp_path):
    original = model(
        "InstantMessage",
        one("From", party(*JO)),
        field("Body", "SYNTHETIC said once"),
        ts_field("TimeStamp", "2026-03-01T10:00:00.000-05:00"),
        id="m-1",
    )
    fwd = model(
        "InstantMessage",
        field("Source", "WhatsApp"),
        one("From", party(*OWNER)),
        field("Body", "SYNTHETIC passing it on"),
        ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00"),
        _extra("Forwarded"),
        _embedded(original),
    )
    path = write_package(tmp_path / "p.ufdr", report_xml({"Chat": [_chat("c1", original, fwd)]}))
    conn, _s = _import(path)
    bodies = [b for (b,) in conn.execute("SELECT body FROM messages")]
    assert bodies.count("SYNTHETIC said once") == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM messages WHERE locator LIKE '%Embedded%'"
    ).fetchone() == (0,)


def test_an_embedded_copy_before_its_standalone_record_never_takes_its_id(tmp_path):
    original = model(
        "InstantMessage",
        one("From", party(*JO)),
        field("Body", "SYNTHETIC said first"),
        ts_field("TimeStamp", "2026-03-01T10:00:00.000-05:00"),
        id="m-2",
    )
    fwd = model(
        "InstantMessage",
        field("Source", "WhatsApp"),
        one("From", party(*OWNER)),
        field("Body", "SYNTHETIC passing it on"),
        ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00"),
        _extra("Forwarded"),
        _embedded(original),
    )
    path = write_package(
        tmp_path / "p.ufdr", report_xml({"Chat": [_chat("c1", fwd), _chat("c2", original)]})
    )
    conn, _s = _import(path)
    rows = conn.execute(
        "SELECT locator, forwarded FROM messages WHERE body = 'SYNTHETIC said first'"
        " ORDER BY locator"
    ).fetchall()
    # the standalone record imports normally, not marked forwarded
    assert rows == [("Chat[1]/Messages[1]/Embedded[1]", 1), ("Chat[2]/Messages[1]", None)]


def _copy_case(tmp_path, *embedded: str):
    fwd = model(
        "InstantMessage",
        field("Source", "WhatsApp"),
        one("From", party(*OWNER)),
        field("Body", "SYNTHETIC look at this"),
        ts_field("TimeStamp", "2026-03-05T21:31:00.000-05:00"),
        _extra("Forwarded"),
        _embedded(*embedded),
    )
    path = write_package(tmp_path / "p.ufdr", report_xml({"Chat": [_chat("c1", fwd)]}))
    conn, _s = _import(path)
    ids = dict(conn.execute("SELECT locator, id FROM messages"))
    return conn, ids


def test_the_note_on_an_embedded_copy_with_a_named_sender_is_true(tmp_path):
    from core.report.html import record_line

    original = model("InstantMessage", one("From", party(*JO)), field("Body", "SYNTHETIC hi"))
    conn, ids = _copy_case(tmp_path, original)
    parent, copy = ids["Chat[1]/Messages[1]"], ids["Chat[1]/Messages[1]/Embedded[1]"]
    found = forwarded.affected(conn)
    assert found[copy] == "embedded_copy" and found[parent] == "forwarded"
    assert forwarded.record_note_text(conn, copy, found[copy]) == (
        f"Forwarded or quoted copy carried inside record {parent}, imported as its own record. "
        'The sender shown, "+15550100002 (Jo)", is the one the extraction names for the embedded '
        'message, not verified; the message that carried it was sent by "+15550100001".'
    )
    line = record_line(conn, copy, found)
    assert "whoever forwarded" not in line
    assert '<span class="q">+15550100002 (Jo)</span>' in line


def test_the_note_on_an_embedded_copy_with_no_sender_is_true(tmp_path):
    original = model("InstantMessage", field("Body", "SYNTHETIC no one named"))
    conn, ids = _copy_case(tmp_path, original)
    parent, copy = ids["Chat[1]/Messages[1]"], ids["Chat[1]/Messages[1]/Embedded[1]"]
    assert forwarded.record_note_text(conn, copy, "embedded_copy") == (
        f"Forwarded or quoted copy carried inside record {parent}, imported as its own record. "
        "The extraction names no sender for the embedded message; the message that carried it "
        'was sent by "+15550100001".'
    )


def test_a_claim_warning_over_a_forward_and_an_embedded_copy_names_each_kind():
    found = {"msg:s:a": "forwarded", "msg:s:a/Embedded[1]": "embedded_copy"}
    assert forwarded.claim_warning(found, ["msg:s:a", "msg:s:a/Embedded[1]", "msg:s:z"]) == (
        "2 records this claim's evidence or checks rest on are affected. 1 is a message the "
        "extraction marks as forwarded or as carrying a forwarded or quoted message, which "
        "Baker shows as sent by whoever forwarded or quoted; 1 is a forwarded or quoted copy "
        "carried inside another message, imported as its own record, shown with the sender the "
        "extraction names for the embedded message. Baker has not verified who first wrote any "
        "of these words, even where the extraction names an original author, so they cannot "
        "support or contradict this claim. Check each in the extraction tool."
    )
    assert forwarded.claim_warning(
        {"msg:s:a/Embedded[1]": "embedded_copy"}, ["msg:s:a/Embedded[1]"]
    ) == (
        "1 record this claim's evidence or checks rest on is a forwarded or quoted copy carried "
        "inside another message, imported as its own record. Baker shows the sender the "
        "extraction names for it, which it has not verified, so it cannot support or contradict "
        "this claim. Check it in the extraction tool."
    )


def test_an_embedded_copy_is_labelled_in_its_conversation(tmp_path):
    from core.report.restore import context_table
    from core.restore.view import context_view

    original = model("InstantMessage", one("From", party(*JO)), field("Body", "SYNTHETIC hi"))
    conn, ids = _copy_case(tmp_path, original)
    view = context_view(conn, ids["Chat[1]/Messages[1]/Embedded[1]"])
    html_ = context_table(view.lines)
    assert "Copy carried inside the message at Chat[1]/Messages[1]; not a message sent" in html_


def test_the_report_names_the_ufdr_importer_version(tmp_path):
    from core.ingest.ufdr import IMPORTER_VERSION
    from core.report.html import render_report

    original = model("InstantMessage", one("From", party(*JO)), field("Body", "SYNTHETIC hi"))
    conn, _ids = _copy_case(tmp_path, original)
    assert IMPORTER_VERSION == "0.3.0"
    assert f"{ufdr.IMPORTER_NAME} 0.3.0</td>" in render_report(conn)


# ---------------------------------------------------------------- RelatedModels (Reader 7.48)


def test_every_chat_message_imports_and_related_copies_never_add_records(tmp_path):
    """Public Reader 7.48 packages hold copies of records under RelatedModels, after a record's
    fields. A copy is never one of the record's messages, attachments or recipients."""
    conn, s = _import(related_package(tmp_path / "rel.ufdr"))
    locs = {r[0] for r in conn.execute("SELECT locator FROM messages")}
    assert len(locs) == 60 + 45 + 7
    assert {"Chat[1]/Messages[60]", "Chat[2]/Messages[45]", "Chat[3]/Messages[7]"} <= locs
    assert not any("Related" in x for x in locs)
    # Chat[1]/Messages[4] holds two copies of itself: one recipient, no attachment, still
    (mid,) = conn.execute(
        "SELECT id FROM messages WHERE locator = ?", ("Chat[1]/Messages[4]",)
    ).fetchone()
    assert conn.execute(
        "SELECT COUNT(*) FROM message_recipients WHERE message_id = ?", (mid,)
    ).fetchone() == (1,)
    # one attachment on every ninth message from the fifth, each hashed from the package
    assert conn.execute("SELECT COUNT(*), COUNT(sha256) FROM attachments").fetchone() == (13, 13)
    assert conn.execute("SELECT COUNT(*) FROM calls").fetchone() == (4,)
    counts = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    # 58 chat messages in the chats' copies of themselves, 24 self copies, 4 calls, 2 accounts
    assert counts["counts"]["related_copies"] == 88
    assert counts["counts"]["related_copies_matching_a_record"] == 88
    assert counts["ufdr"]["related_copies_by_type"] == {
        "Call": 4, "Chat": 3, "InstantMessage": 24, "UserAccount": 2
    }  # fmt: skip
    assert "related_copy_unmatched" not in _codes(s)
    info = next(i for i in s.items if i.code == "related_copies")
    assert info.level == "info"


def test_model_types_baker_does_not_know_are_listed_on_screen_and_in_the_report(tmp_path):
    conn, s = _import(related_package(tmp_path / "rel.ufdr"))
    listed = {i.plain.split(" was not imported")[0]: i for i in s.items if i.code == "not_imported"}
    assert set(listed) == set(UNKNOWN_TYPES)
    assert all(i.level == "attention" and "(1 record)" in i.plain for i in listed.values())
    html = render_report(conn)
    limits = html.split("<h2>Limitations</h2>", 1)[1].split("<h2>", 1)[0]
    for t in UNKNOWN_TYPES:
        assert f'<span class="q">{t}</span> was not imported' in limits
    check_report_text(html)


def test_a_related_copy_matching_no_record_is_listed_and_shown_in_the_report(tmp_path):
    conn, s = _import(related_package(tmp_path / "rel.ufdr", unmatched=True))
    items = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert {i.locators for i in items} == {
        # the second: a third copy of two same-second twins
        ("Chat[1]/Related[1]/Messages[31]", "Chat[3]/Related[1]/Messages[6]"),
        ("Call[1]/Related[1]",),
    }
    assert all(i.level == "attention" for i in items)
    assert {"Baker did not import it", "Baker did not import them"} <= {
        i.plain.split("so ", 1)[1].split(";")[0] for i in items
    }
    html = render_report(conn)
    assert "held only as a related copy" in html.split("<h2>Limitations</h2>", 1)[1]
    # the copy is not imported as a record, and nothing else changed
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (112,)


def test_a_lone_copy_never_hides_behind_a_same_second_twin(tmp_path):
    """Two messages with the same words, parties and second are two records. A copied chat
    holding them three times holds one message no record has: copies match the holder chat's
    messages one to one, so the third is listed, never absorbed by a twin (Baker Eval on #117)."""
    t = "2026-03-05T21:31:00.000-05:00"
    twins = [_msg("ok", t, id="m1"), _msg("ok", t, id="m2")]
    copied = _chat("k1", *(_msg("ok", t, id=f"c{i}") for i in (1, 2, 3)))
    xml = report_xml({"Chat": [_chat("k1", *twins, extra=(related(copied),))]})
    conn, s = _import(write_package(tmp_path / "twins.ufdr", xml))
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (2,)
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Chat[1]/Related[1]/Messages[3]",)
    p = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    assert (p["counts"]["related_copies"], p["counts"]["related_copies_matching_a_record"]) == (
        3, 2
    )  # fmt: skip
    d = ufdr_check.run(write_package(tmp_path / "twins2.ufdr", xml)).shareable
    assert d["differences"] == 0


def test_a_copy_is_matched_to_its_own_holder_only(tmp_path):
    """A copy of one message says what that message says; the same words, parties and time on
    another record of the package do not make it a copy (each copy is a copy of its holder)."""
    t = "2026-03-05T21:31:00.000-05:00"
    a = _chat("k1", _msg("ok", t, id="m1"), extra=(related(_chat("k2", _msg("hi", t, id="c1"))),))
    b = _chat("k2", _msg("hi", t, id="m2"))
    conn, s = _import(write_package(tmp_path / "own.ufdr", report_xml({"Chat": [a, b]})))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Chat[1]/Related[1]/Messages[1]",)


@pytest.mark.parametrize("change", ["deleted", "deleted_attr", "deleted_field", "attachment"])
def test_a_copy_differing_in_deleted_state_or_attachments_is_listed(tmp_path, change):
    t = "2026-03-05T21:31:00.000-05:00"
    if change == "deleted":
        copy = _msg("ok", t, id="c1", deleted_state="Deleted")
    elif change == "deleted_attr":  # the other forms of a deleted state the importer reads
        copy = _msg("ok", t, id="c1", deleted_state=None, deleted="True")
    elif change == "deleted_field":
        head, end = _msg("ok", t, id="c1", deleted_state=None).rsplit("</model>", 1)
        copy = f"{head}{field('RecordStatus', 'Deleted')}</model>{end}"
    else:
        head, end = _msg("ok", t, id="c1").rsplit("</model>", 1)
        att = model("Attachment", field("Filename", "x.png"), id="a1")
        copy = f"{head}{many('Attachments', [att])}</model>{end}"
    record = _msg("ok", t, id="m1", deleted_state=None if change != "deleted" else "Intact")
    xml = report_xml({"Chat": [_chat("k1", record, extra=(related(_chat("k1", copy)),))]})
    conn, s = _import(write_package(tmp_path / "d.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Chat[1]/Related[1]/Messages[1]",)
    d = ufdr_check.run(write_package(tmp_path / "d2.ufdr", xml)).shareable
    assert d["differences"] == 0


def test_a_copy_pointing_at_its_own_file_still_matches(tmp_path):
    """A copy decoded from another source names the same attachment but points at its own file
    (another path or file id): it says what the record says, so it is not listed."""
    t = "2026-03-05T21:31:00.000-05:00"

    def with_att(mid: str, path: str | None) -> str:
        parts = [field("Filename", "x.png")]
        if path:
            parts.append(field("attachment_extracted_path", path))
        head, end = _msg("ok", t, id=mid).rsplit("</model>", 1)
        att = model("Attachment", *parts, id=f"{mid}-a", file_id=f"{mid}-f")
        return f"{head}{many('Attachments', [att])}</model>{end}"

    copy = _chat("k1", with_att("c1", None))
    xml = report_xml({"Chat": [_chat("k1", with_att("m1", "files/x.png"), extra=(related(copy),))]})
    conn, s = _import(write_package(tmp_path / "f.ufdr", xml))
    assert "related_copy_unmatched" not in _codes(s)


def test_copies_inside_copies_are_matched_at_every_depth(tmp_path):
    t = "2026-03-05T21:31:00.000-05:00"

    def holding(mid: str, body: str, *tail: str) -> str:
        head, end = _msg(body, t, id=mid).rsplit("</model>", 1)
        return f"{head}{''.join(tail)}</model>{end}"

    deepest = related(_msg("changed", t, id="c3"))  # under a copy of a copy
    copy = holding("c1", "ok", related(holding("c2", "ok", deepest)))
    xml = report_xml({"Chat": [_chat("k1", holding("m1", "ok", related(copy)))]})
    conn, s = _import(write_package(tmp_path / "deep.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Chat[1]/Messages[1]/Related[1]/Related[1]/Related[1]",)
    p = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    assert (p["counts"]["related_copies"], p["counts"]["related_copies_matching_a_record"]) == (
        3, 2
    )  # fmt: skip


def test_a_chat_copied_inside_a_copied_chat_matches_that_copy(tmp_path):
    t = "2026-03-05T21:31:00.000-05:00"
    inner = _chat("k1", _msg("ok", t, id="c2"), _msg("extra", t, id="c3"))
    outer = _chat("k1", _msg("ok", t, id="c1"), extra=(related(inner),))
    xml = report_xml({"Chat": [_chat("k1", _msg("ok", t, id="m1"), extra=(related(outer),))]})
    conn, s = _import(write_package(tmp_path / "cc.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Chat[1]/Related[1]/Related[1]/Messages[2]",)


def test_a_copied_chat_keeps_only_each_messages_key_while_reading():
    """A long chat copied under RelatedModels is never held whole: each message is reduced to
    its content key as it closes."""
    t = "2026-03-05T21:31:00.000-05:00"
    copied = _chat("k1", *(_msg(f"m{i}", t, id=f"c{i}") for i in range(50)))
    xml = report_xml({"Chat": [_chat("k1", _msg("m0", t, id="m1"), extra=(related(copied),))]})
    seen: list[ufdr._El] = []
    reader = ufdr._Reader(
        lambda t: t == "Chat", lambda el: None, True, lambda h, el: seen.append(el)
    )
    reader.read(io.BytesIO(xml.encode()))
    (rel,) = seen
    msgs = [m for f in rel.children[0].children if f.attrs.get("name") == "Messages"
            for m in f.children if m.tag == "model"]  # fmt: skip
    assert len(msgs) == 50
    assert all(m.key is not None and m.children == [] for m in msgs)


def test_a_call_copy_with_caller_and_callee_swapped_is_listed(tmp_path):
    t = "2026-03-05T21:31:00.000-05:00"

    def call(cid: str, frm, to, *tail: str) -> str:
        return model(
            "Call",
            field("Source", "Phone"),
            many("Parties", [party(*frm, role="From"), party(*to, role="To")]),
            ts_field("TimeStamp", t),
            field("Duration", "00:01:00", "TimeSpan"),
            *tail,
            id=cid,
        )

    xml = report_xml({"Call": [call("k1", OWNER, JO, related(call("k1r", JO, OWNER)))]})
    conn, s = _import(write_package(tmp_path / "call.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Call[1]/Related[1]",)


T2 = "2026-03-05T21:31:00.000-05:00"


def _listed(tmp_path, name: str, xml: str) -> tuple[str, ...]:
    """Locators Baker lists as copies that do not match; ufdr-check must agree."""
    conn, s = _import(write_package(tmp_path / f"{name}.ufdr", xml))
    d = ufdr_check.run(write_package(tmp_path / f"{name}-check.ufdr", xml)).shareable
    assert d["differences"] == 0, d["records"]
    return tuple(loc for i in s.items if i.code == "related_copy_unmatched" for loc in i.locators)


def _with(msg: str, *tail: str) -> str:
    head, end = msg.rsplit("</model>", 1)
    return f"{head}{''.join(tail)}</model>{end}"


def test_a_chat_copied_three_levels_down_is_matched(tmp_path):
    deepest = _chat("k1", _msg("ok", T2, id="c3"), _msg("extra", T2, id="c4"))
    middle = _chat("k1", _msg("ok", T2, id="c2"), extra=(related(deepest),))
    outer = _chat("k1", _msg("ok", T2, id="c1"), extra=(related(middle),))
    xml = report_xml({"Chat": [_chat("k1", _msg("ok", T2, id="m1"), extra=(related(outer),))]})
    assert _listed(tmp_path, "deep3", xml) == (
        "Chat[1]/Related[1]/Related[1]/Related[1]/Messages[2]",
    )


def test_an_exact_chat_copy_inside_a_copied_chat_checks_clean(tmp_path):
    middle = _chat("k1", _msg("ok", T2, id="c2"))
    outer = _chat("k1", _msg("ok", T2, id="c1"), extra=(related(middle),))
    xml = report_xml({"Chat": [_chat("k1", _msg("ok", T2, id="m1"), extra=(related(outer),))]})
    assert _listed(tmp_path, "nested-ok", xml) == ()


def test_a_copy_of_a_message_with_a_repeated_id_matches_it(tmp_path):
    a = _chat("k1", _msg("ok", T2, id="m1"))
    b = _chat("k2", _with(_msg("ok", T2, id="m1"), related(_msg("ok", T2, id="c1"))))
    xml = report_xml({"Chat": [a, b]})
    conn, s = _import(write_package(tmp_path / "rep.ufdr", xml))
    assert "related_copy_unmatched" not in _codes(s)


def test_a_copy_with_an_empty_text_where_the_record_has_none_is_listed(tmp_path):
    record = _msg("ok", T2, id="m1").replace(field("Body", "ok"), "")
    copy = _msg("", T2, id="c1")
    assert field("Body", "") in copy and "Body" not in record
    xml = report_xml({"Chat": [_chat("k1", _with(record, related(copy)))]})
    assert _listed(tmp_path, "empty", xml) == ("Chat[1]/Messages[1]/Related[1]",)


def test_a_copy_of_a_chat_message_of_another_type_name_is_matched(tmp_path):
    record = model("ChatMessage", field("Body", "ok"), ts_field("TimeStamp", T2), id="m1")
    copy = model("ChatMessage", field("Body", "changed"), ts_field("TimeStamp", T2), id="c1")
    chat = model(
        "Chat",
        field("Source", "WhatsApp"),
        many("Messages", [_with(record, related(copy))], "ChatMessage"),
    )
    xml = report_xml({"Chat": [chat]})
    assert _listed(tmp_path, "type", xml) == ("Chat[1]/Messages[1]/Related[1]",)


def test_party_identifier_and_name_are_never_run_together(tmp_path):
    record = _msg("ok", T2, ("a", "b c", False), id="m1")
    copy = _msg("ok", T2, ("a b", "c", False), id="c1")
    xml = report_xml({"Chat": [_chat("k1", _with(record, related(copy)))]})
    assert _listed(tmp_path, "pair", xml) == ("Chat[1]/Messages[1]/Related[1]",)


def test_a_call_copy_differing_in_deleted_state_is_listed(tmp_path):
    def call(cid: str, state: str, *tail: str) -> str:
        return model(
            "Call",
            many("Parties", [party(*OWNER, role="From"), party(*JO, role="To")]),
            ts_field("TimeStamp", T2),
            *tail,
            id=cid,
            deleted_state=state,
        )

    xml = report_xml({"Call": [call("k1", "Intact", related(call("k1r", "Deleted")))]})
    conn, s = _import(write_package(tmp_path / "cd.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Call[1]/Related[1]",)


def test_a_call_copy_with_another_type_direction_is_listed(tmp_path):
    def call(cid: str, kind: str, *tail: str) -> str:
        return model(
            "Call",
            many("Parties", [party(*OWNER), party(*JO)]),
            ts_field("TimeStamp", T2),
            field("Type", kind),
            *tail,
            id=cid,
        )

    xml = report_xml({"Call": [call("k1", "Incoming", related(call("k1r", "Outgoing")))]})
    conn, s = _import(write_package(tmp_path / "ct.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Call[1]/Related[1]",)


def test_an_sms_copy_with_another_counterpart_is_listed(tmp_path):
    def sms(mid: str, who, *tail: str) -> str:
        return model(
            "SMS",
            field("Body", "ok"),
            ts_field("TimeStamp", T2),
            many("Parties", [party(*who)]),
            *tail,
            id=mid,
        )

    other = ("+15550100009", "Al", False)
    xml = report_xml({"SMS": [sms("s1", JO, related(sms("s1r", other)))]})
    assert _listed(tmp_path, "sms", xml) == ("SMS[1]/Related[1]",)


def test_a_repeated_id_message_and_its_copy_check_clean(tmp_path):
    a = _chat("k1", _msg("ok", T2, id="m1"))
    b = _chat("k2", _with(_msg("ok", T2, id="m1"), related(_msg("ok", T2, id="c1"))))
    assert _listed(tmp_path, "rep2", report_xml({"Chat": [a, b]})) == ()


def _sms(mid: str, *tail: str, who=JO, app: str = "SMS") -> str:
    return model(
        "SMS",
        field("Source", app),
        field("Body", "ok"),
        ts_field("TimeStamp", T2),
        many("Parties", [party(*who)]),
        *tail,
        id=mid,
    )


@pytest.mark.parametrize("name", ["Direction", "Folder", "Status"])
def test_a_message_copy_stating_another_direction_is_listed(tmp_path, name):
    held = (field(name, "Incoming" if name != "Folder" else "Inbox"),)
    copy = (field(name, "Outgoing" if name != "Folder" else "Sent"),)
    xml = report_xml({"SMS": [_sms("s1", *held, related(_sms("s1r", *copy)))]})
    assert _listed(tmp_path, f"dir-{name}", xml) == ("SMS[1]/Related[1]",)


def test_a_copy_whose_party_says_another_phone_owner_flag_is_listed(tmp_path):
    xml = report_xml({"SMS": [_sms("s1", related(_sms("s1r", who=(*JO[:2], True))))]})
    assert _listed(tmp_path, "owner", xml) == ("SMS[1]/Related[1]",)


def test_a_message_copy_from_another_app_is_listed(tmp_path):
    xml = report_xml({"SMS": [_sms("s1", related(_sms("s1r", app="iMessage")))]})
    assert _listed(tmp_path, "app", xml) == ("SMS[1]/Related[1]",)


def test_a_call_copy_from_another_app_is_listed(tmp_path):
    def call(cid: str, app: str, *tail: str) -> str:
        return model(
            "Call",
            field("Source", app),
            many("Parties", [party(*OWNER), party(*JO)]),
            ts_field("TimeStamp", T2),
            *tail,
            id=cid,
        )

    xml = report_xml({"Call": [call("k1", "Phone", related(call("k1r", "WhatsApp")))]})
    conn, s = _import(write_package(tmp_path / "capp.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Call[1]/Related[1]",)


def test_an_account_copy_with_another_name_is_listed(tmp_path):
    def acct(aid: str, name: str, *tail: str) -> str:
        parts = (field("Source", "WhatsApp"), field("Username", OWNER[0]), field("Name", name))
        return model("UserAccount", *parts, *tail, id=aid)

    xml = report_xml({"UserAccount": [acct("a1", "Me", related(acct("a1r", "Jo")))]})
    conn, s = _import(write_package(tmp_path / "acct.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("UserAccount[1]/Related[1]",)


def test_a_copied_chat_holding_a_repeated_id_message_checks_clean(tmp_path):
    a = _chat("k1", _msg("ok", T2, id="m1"))
    copy = _chat("k2", _msg("ok", T2, id="c1"), _msg("again", T2, id="c2"))
    b = _chat("k2", _msg("ok", T2, id="m1"), _msg("again", T2, id="m2"), extra=(related(copy),))
    assert _listed(tmp_path, "rep-chat", report_xml({"Chat": [a, b]})) == ()


def test_a_blank_deleted_state_falls_through_to_deleted_in_both(tmp_path):
    def sms(mid: str, *tail: str, **attrs: str) -> str:
        parts = (field("Body", "ok"), ts_field("TimeStamp", T2), many("Parties", [party(*JO)]))
        return model("SMS", *parts, *tail, id=mid, **attrs)

    copy = sms("s1r", deleted_state="Deleted")
    held = sms("s1", related(copy), deleted_state="", deleted="Deleted")
    assert _listed(tmp_path, "blank-state", report_xml({"SMS": [held]})) == ()


def test_an_sms_copy_with_its_counterparts_reversed_is_listed(tmp_path):
    al = ("+15550100009", "Al", False)

    def sms(mid: str, first, second, *tail: str) -> str:
        return model(
            "SMS",
            field("Body", "ok"),
            ts_field("TimeStamp", T2),
            many("Parties", [party(*first), party(*second)]),
            *tail,
            id=mid,
        )

    xml = report_xml({"SMS": [sms("s1", JO, al, related(sms("s1r", al, JO)))]})
    assert _listed(tmp_path, "order", xml) == ("SMS[1]/Related[1]",)


def test_a_call_copy_with_one_side_reordered_is_listed(tmp_path):
    al = ("+15550100009", "Al", False)

    def call(cid: str, callers, *tail: str) -> str:
        return model(
            "Call",
            many("From", [party(*p) for p in callers]),
            one("To", party(*OWNER)),
            ts_field("TimeStamp", T2),
            *tail,
            id=cid,
        )

    xml = report_xml({"Call": [call("k1", (JO, al), related(call("k1r", (al, JO))))]})
    conn, s = _import(write_package(tmp_path / "cside.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Call[1]/Related[1]",)


def test_a_copy_whose_embedded_message_differs_is_listed(tmp_path):
    def msg(mid: str, inner: str, *tail: str) -> str:
        return _with(_msg("ok", T2, id=mid), _embedded(_msg(inner, T2, id=f"{mid}e")), *tail)

    xml = report_xml({"InstantMessage": [msg("m1", "first", related(msg("m1r", "other")))]})
    assert _listed(tmp_path, "emb-diff", xml) == ("InstantMessage[1]/Related[1]",)


def test_an_exact_copy_of_an_embedded_message_checks_clean(tmp_path):
    inner = _with(_msg("inner", T2, id="e1"), related(_msg("inner", T2, id="e1r")))
    chat = _chat("k1", _with(_msg("ok", T2, id="m1"), _embedded(inner)))
    top = _with(_msg("top", T2, id="m2"), _embedded(inner.replace('"e1"', '"e2"')))
    xml = report_xml({"Chat": [chat], "InstantMessage": [top]})
    assert _listed(tmp_path, "emb-holder", xml) == ()


def test_content_keys_are_kept_only_for_records_holding_copies(tmp_path, monkeypatch):
    kept = {"records": 0, "chats": 0}
    real = ufdr._RecordMapper.settle_related

    def spy(self):
        kept["records"] = max(kept["records"], len(self.record_keys))
        kept["chats"] = max(kept["chats"], len(self.chat_keys))
        real(self)

    monkeypatch.setattr(ufdr._RecordMapper, "settle_related", spy)
    copy = _msg("ok", T2, id="c1")
    chats = [_chat("k1", _msg("a", T2, id="m1"), _with(_msg("ok", T2, id="m2"), related(copy)))]
    chats += [_chat(f"k{i}", _msg("b", T2, id=f"n{i}")) for i in range(2, 6)]
    conn, s = _import(write_package(tmp_path / "keys.ufdr", report_xml({"Chat": chats})))
    assert "related_copy_unmatched" not in _codes(s)
    assert kept == {"records": 1, "chats": 0}


def test_a_copy_of_another_message_kind_is_listed(tmp_path):
    def msg(type_: str, mid: str, *tail: str) -> str:
        parts = (field("Body", "ok"), ts_field("TimeStamp", T2), many("Parties", [party(*JO)]))
        return model(type_, *parts, *tail, id=mid)

    xml = report_xml({"SMS": [msg("SMS", "s1", related(msg("InstantMessage", "s1r")))]})
    assert _listed(tmp_path, "kind", xml) == ("SMS[1]/Related[1]",)


def test_copies_of_an_embedded_message_inside_a_copy_are_matched(tmp_path):
    def holder(mid: str, inner: str, *tail: str) -> str:
        return _with(_msg("ok", T2, id=mid), _embedded(inner), *tail)

    exact = _with(_msg("inner", T2, id="e2"), related(_msg("inner", T2, id="e2r")))
    differs = _with(_msg("inner", T2, id="e3"), related(_msg("not it", T2, id="e3r")))
    copies = related(holder("m1r", exact), holder("m1s", differs))
    top = holder("m1", _msg("inner", T2, id="e1"), copies)
    chat = _chat(
        "k1",
        _msg("a", T2, id="m2"),
        extra=(
            related(
                _chat("k1", holder("c1", differs.replace('"e3', '"e4'))),
            ),
        ),
    )
    xml = report_xml({"InstantMessage": [top], "Chat": [chat]})
    assert sorted(_listed(tmp_path, "emb-in-copy", xml)) == [
        "Chat[1]/Related[1]/Messages[1]",
        "Chat[1]/Related[1]/Messages[1]/Embedded[1]/Related[1]",
        "InstantMessage[1]/Related[2]/Embedded[1]/Related[1]",
    ]


def test_a_copied_chat_counts_messages_across_fields_of_one_name(tmp_path):
    copy = _with(
        _chat("k1", _msg("a", T2, id="c1")),
        many("Messages", [_msg("not it", T2, id="c2")], "InstantMessage"),
    )
    chat = _chat("k1", _msg("a", T2, id="m1"), extra=(related(copy),))
    assert _listed(tmp_path, "fields", report_xml({"Chat": [chat]})) == (
        "Chat[1]/Related[1]/Messages[2]",
    )


def test_copies_are_numbered_across_sibling_related_models(tmp_path):
    msg = _with(
        _msg("ok", T2, id="m1"),
        related(_msg("ok", T2, id="c1")),
        related(_msg("not it", T2, id="c2")),
    )
    xml = report_xml({"InstantMessage": [msg]})
    assert _listed(tmp_path, "siblings", xml) == ("InstantMessage[1]/Related[2]",)


def test_a_copy_held_by_an_embedded_message_of_another_type_name_is_matched(tmp_path):
    def custom(body: str, mid: str, *tail: str) -> str:
        m = _msg(body, T2, id=mid).replace('type="InstantMessage"', 'type="ChatMessage"', 1)
        return _with(m, *tail)

    inner = custom("inner", "e1", related(custom("not it", "e1r")))
    xml = report_xml({"InstantMessage": [_with(_msg("ok", T2, id="m1"), _embedded(inner))]})
    assert _listed(tmp_path, "emb-type", xml) == ("InstantMessage[1]/Embedded[1]/Related[1]",)


def test_a_copied_chat_saying_other_things_around_its_messages_is_listed(tmp_path):
    copy = _chat("k9", _msg("ok", T2, id="c1"))  # another chat id and name
    chat = _chat("k1", _msg("ok", T2, id="m1"), extra=(related(copy),))
    assert _listed(tmp_path, "chat-ctx", report_xml({"Chat": [chat]})) == (
        "Chat[1]/Related[1]/Messages[1]",
    )


@pytest.mark.parametrize("how", ["labels", "extra"])
def test_a_copy_marked_forwarded_where_the_record_is_not_is_listed(tmp_path, how):
    mark = (
        '<multiField name="Labels" type="Label"><value type="Label">Forwarded</value></multiField>'
        if how == "labels"
        else _extra("Forwarded")
    )
    copy = _with(_msg("ok", T2, id="m1r"), mark)
    xml = report_xml({"InstantMessage": [_with(_msg("ok", T2, id="m1"), related(copy))]})
    assert _listed(tmp_path, f"fwd-{how}", xml) == ("InstantMessage[1]/Related[1]",)


def test_a_copy_differing_two_embedded_levels_down_is_listed_by_both(tmp_path):
    def msg(mid: str, deepest: str, *tail: str) -> str:
        inner = _with(_msg("mid", T2, id=f"{mid}a"), _embedded(_msg(deepest, T2, id=f"{mid}b")))
        return _with(_msg("ok", T2, id=mid), _embedded(inner), *tail)

    xml = report_xml({"InstantMessage": [msg("m1", "deep", related(msg("m1r", "other")))]})
    assert _listed(tmp_path, "emb2", xml) == ("InstantMessage[1]/Related[1]",)


def test_copies_held_two_embedded_levels_down_are_matched(tmp_path):
    deepest = _with(_msg("deep", T2, id="e2"), related(_msg("not it", T2, id="e2r")))
    inner = _with(_msg("mid", T2, id="e1"), _embedded(deepest))
    xml = report_xml({"InstantMessage": [_with(_msg("ok", T2, id="m1"), _embedded(inner))]})
    assert _listed(tmp_path, "emb2-holder", xml) == (
        "InstantMessage[1]/Embedded[1]/Embedded[1]/Related[1]",
    )


def test_a_chat_message_skipped_between_the_two_reads_stores_nothing(tmp_path, monkeypatch):
    path = related_package(tmp_path / "rel.ufdr")
    real = ufdr._RecordMapper.chat

    def drop_one(self, el, chat):
        if el.pending:
            el.pending.pop()
        real(self, el, chat)

    monkeypatch.setattr(ufdr._RecordMapper, "chat", drop_one)
    conn = _db()
    with pytest.raises(ValueError, match="chat messages on the first read"):
        UfdrImporter(source_id="u1").import_source(path, conn)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (0,)


def test_a_copy_saying_the_same_words_to_someone_else_is_not_taken_for_the_record(tmp_path):
    """Same text, time and sender is not enough: a copy addressed to another person matches no
    record, so it is listed, not silently counted as a copy (Baker Eval on #117)."""
    t = "2026-03-05T21:31:00.000-05:00"
    other = ("+15550100003", "Sam", False)
    copies = related(
        _chat("k1", _msg("ok", t, id="c1")),  # an exact copy of the record
        _chat("k2", _msg("ok", t, to=(other,), id="c2")),  # the same words to someone else
    )
    xml = report_xml({"Chat": [_chat("k1", _msg("ok", t, id="m1"), extra=(copies,))]})
    conn, s = _import(write_package(tmp_path / "same.ufdr", xml))
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (1,)
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Chat[1]/Related[2]/Messages[1]",)
    p = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    assert p["counts"]["related_copies"] == 2
    assert p["counts"]["related_copies_matching_a_record"] == 1


def test_copies_held_by_a_message_embedded_in_an_sms_are_matched(tmp_path):
    def sms(mid: str, *tail: str) -> str:
        parts = (field("Body", "ok"), ts_field("TimeStamp", T2), many("Parties", [party(*JO)]))
        return model("SMS", *parts, *tail, id=mid)

    inner = _with(
        _msg("inner", T2, id="e1"),
        related(_msg("inner", T2, id="e1r"), _msg("not it", T2, id="e1s")),
    )
    xml = report_xml({"SMS": [sms("s1", _embedded(inner))]})
    assert _listed(tmp_path, "sms-emb", xml) == ("SMS[1]/Embedded[1]/Related[2]",)


def test_a_copy_of_another_custom_type_inside_a_copied_chat_is_listed_by_both(tmp_path):
    """A message copied inside a copied chat's message is matched, and so listed, whatever its
    type is named: here its type differs from the message holding it, so it matches nothing."""

    def custom(type_: str, body: str, mid: str, *tail: str) -> str:
        m = _msg(body, T2, id=mid).replace('type="InstantMessage"', f'type="{type_}"', 1)
        return _with(m, *tail)

    held = related(custom("ChatNote", "ok", "c1s"))
    copy = _chat("k1", custom("ChatMessage", "ok", "c1", held))
    chat = _chat("k1", custom("ChatMessage", "ok", "m1"), extra=(related(copy),))
    assert _listed(tmp_path, "custom-nested", report_xml({"Chat": [chat]})) == (
        "Chat[1]/Related[1]/Messages[1]/Related[1]",
    )


def test_copies_held_by_a_message_in_an_earlier_of_two_embedded_fields_are_matched(tmp_path):
    first = _with(_msg("first", T2, id="e1"), related(_msg("first", T2, id="e1r")))
    msg = _with(_msg("ok", T2, id="m1"), _embedded(first), _embedded(_msg("second", T2, id="e2")))
    xml = report_xml({"InstantMessage": [msg]})
    assert _listed(tmp_path, "emb-fields", xml) == ()
    conn, _s = _import(write_package(tmp_path / "emb-fields-rows.ufdr", xml))
    bodies = {r[0] for r in conn.execute("SELECT body FROM messages")}
    assert bodies == {"ok", "first", "second"}  # both embedded originals, in the order written


@pytest.mark.parametrize("mark", [{"carved": "true"}, {"decoding_confidence": "Low"}])
def test_a_copy_with_a_recovery_mark_its_record_lacks_is_listed(tmp_path, mark):
    copy = _msg("ok", T2, id="m1r", **mark)
    xml = report_xml({"InstantMessage": [_with(_msg("ok", T2, id="m1"), related(copy))]})
    assert _listed(tmp_path, f"recovery-{next(iter(mark))}", xml) == (
        "InstantMessage[1]/Related[1]",
    )


def test_a_call_copy_recovered_by_carving_is_listed(tmp_path):
    def call(cid: str, *tail: str, **attrs: str) -> str:
        parts = (one("From", party(*JO)), one("To", party(*OWNER)), ts_field("TimeStamp", T2))
        return model("Call", *parts, *tail, id=cid, **attrs)

    xml = report_xml({"Call": [call("k1", related(call("k1r", carved="true")))]})
    conn, s = _import(write_package(tmp_path / "carved-call.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Call[1]/Related[1]",)


def test_copies_are_matched_and_dropped_record_by_record(tmp_path, monkeypatch):
    held: list[int] = []
    real = ufdr._RecordMapper.settle_related

    def spy(self):
        held.append(sum(len(c.keys) for c in self.related_copies))
        real(self)

    monkeypatch.setattr(ufdr._RecordMapper, "settle_related", spy)
    msgs = [
        _with(_msg(f"m{i}", T2, id=f"m{i}"), related(_msg(f"m{i}", T2, id=f"m{i}r"),
                                                     _msg(f"m{i}", T2, id=f"m{i}s")))
        for i in range(6)
    ]  # fmt: skip
    conn, s = _import(write_package(tmp_path / "settle.ufdr", report_xml({"InstantMessage": msgs})))
    assert "related_copy_unmatched" not in _codes(s)
    assert max(held) == 2  # never more than one record's copies at a time
    p = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    assert p["counts"]["related_copies"] == p["counts"]["related_copies_matching_a_record"] == 12


def test_a_contact_copy_with_another_deleted_state_is_listed(tmp_path):
    def contact(cid: str, *tail: str, **attrs: str) -> str:
        entries = many("Entries", [model("PhoneNumber", field("Value", JO[0]))], "ContactEntry")
        return model("Contact", field("Name", "Jo"), entries, *tail, id=cid, **attrs)

    copy = contact("p1r", deleted_state="Deleted")
    xml = report_xml({"Contact": [contact("p1", related(copy), deleted_state="Intact")]})
    conn, s = _import(write_package(tmp_path / "contact-state.ufdr", xml))
    (item,) = [i for i in s.items if i.code == "related_copy_unmatched"]
    assert item.locators == ("Contact[1]/Related[1]",)


def test_a_message_copied_under_a_copied_chat_is_listed_by_both(tmp_path):
    copy = _chat("k1", _msg("ok", T2, id="c1"), extra=(related(_msg("ok", T2, id="c2")),))
    chat = _chat("k1", _msg("ok", T2, id="m1"), extra=(related(copy),))
    assert _listed(tmp_path, "msg-under-copy", report_xml({"Chat": [chat]})) == (
        "Chat[1]/Related[1]/Related[1]",
    )


def test_a_chat_copied_under_a_message_copy_is_listed_by_both(tmp_path):
    inner = _chat("k1", _msg("ok", T2, id="c1"))
    copy = _with(_msg("ok", T2, id="m1r"), related(inner))
    xml = report_xml({"InstantMessage": [_with(_msg("ok", T2, id="m1"), related(copy))]})
    assert _listed(tmp_path, "chat-in-copy", xml) == (
        "InstantMessage[1]/Related[1]/Related[1]/Messages[1]",
    )


def test_a_copy_whose_unnamed_attachment_names_only_its_own_file_id_matches(tmp_path):
    """The shape of the public Android packages: a copy's unnamed attachment names only its own
    file id where the holder's names the extracted path. Same message, so not listed."""

    def msg(mid: str, att: str, *tail: str) -> str:
        return _with(_msg("", T2, id=mid), many("Attachments", [att], "Attachment"), *tail)

    copy = msg("m1r", model("Attachment", file_id="f2"))
    held = msg("m1", model("Attachment", field("LocalPath", "files/a.cnt"), file_id="f1"),
               related(copy))  # fmt: skip
    assert _listed(tmp_path, "att-own-id", report_xml({"InstantMessage": [held]})) == ()


def test_a_copy_whose_attachment_has_another_mime_type_is_listed_by_both(tmp_path):
    def msg(mid: str, mime: str, *tail: str) -> str:
        att = model("Attachment", field("Filename", "a.jpg"), field("ContentType", mime))
        return _with(_msg("ok", T2, id=mid), many("Attachments", [att], "Attachment"), *tail)

    held = msg("m1", "image/jpeg", related(msg("m1r", "image/jpeg"), msg("m1s", "video/mp4")))
    xml = report_xml({"InstantMessage": [held]})
    assert _listed(tmp_path, "att-mime", xml) == ("InstantMessage[1]/Related[2]",)


@pytest.mark.parametrize("how", ["labels", "extra"])
def test_a_forwarded_mark_in_an_earlier_of_two_fields_counts(tmp_path, how):
    def labels(value: str) -> str:
        value_xml = f'<value type="Label">{value}</value>'
        return f'<multiField name="Labels" type="Label">{value_xml}</multiField>'

    def marks(first: str) -> tuple[str, str]:
        if how == "labels":
            return labels(first), labels("Starred")
        return _extra(first), _extra("Starred")

    copy = _with(_msg("ok", T2, id="m1r"), *marks("Forwarded"))
    held = _with(_msg("ok", T2, id="m1"), *marks("Read"), related(copy))
    xml = report_xml({"InstantMessage": [held]})
    assert _listed(tmp_path, f"fwd2-{how}", xml) == ("InstantMessage[1]/Related[1]",)
    mine = _with(_msg("ok", T2, id="m2"), *marks("Forwarded"))
    conn, s = _import(
        write_package(tmp_path / f"fwd2-{how}-rec.ufdr", report_xml({"InstantMessage": [mine]}))
    )
    assert "forwarded" in _codes(s)
