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
from core.ingest import coverage, ufdr
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.ufdr import UfdrImporter
from core.report.html import render_report
from eval.synthetic.generate import generate
from eval.synthetic.ufdr import (
    field,
    iso_local,
    many,
    model,
    one,
    party,
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
    assert "does not record who first wrote" in item.plain
    emb = next(i for i in s.items if i.code == "embedded_message_not_imported")
    assert emb.locators == ("Chat[1]/Messages[2]",)
    # the embedded original is not imported as the forwarder's words
    bodies = [b for (b,) in conn.execute("SELECT body FROM messages ORDER BY locator")]
    assert "SYNTHETIC original words" not in bodies
