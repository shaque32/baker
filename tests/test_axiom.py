"""Magnet AXIOM report import (core/ingest/axiom.py). UNVERIFIED format support: every export
here is synthetic (eval/synthetic/axiom.py), built from public descriptions of the formats.

The anchor: synthetic case01 rendered as an AXIOM XML report and as an AXIOM Excel report imports
to the same messages, threads, recipients, contacts, attachments and calls its Cellebrite report
gives, so everything after import (retrieval, checks, rules) works unchanged."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core.audit.invariants import FORBIDDEN_WORDS, check_report_text
from core.db import apply_schema
from core.ingest import axiom, coverage
from core.ingest.axiom import AxiomImporter, classify, date_format_order, field_name
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.pick import report_importer
from core.ingest.ufdr import UfdrImporter
from core.report.html import render_report
from eval.synthetic.axiom import report_xml, workbook_sheets, write_case01, write_xml
from eval.synthetic.generate import generate
from eval.synthetic.xlsx import write_xlsx
from tests.test_coverage_display import _screen, _send, _setup


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


def _import(
    path: Path, sid: str = "a1", **kw
) -> tuple[sqlite3.Connection, coverage.CoverageSummary]:
    conn = _db()
    AxiomImporter(source_id=sid, **kw).import_source(path, conn)
    s = coverage.summary(conn, sid)
    assert s is not None
    return conn, s


def _codes(s: coverage.CoverageSummary) -> dict[str, str]:
    return {i.code: i.level for i in s.items}


def _both(tmp_path: Path, arts, name: str = "x") -> list[Path]:
    """The same artifacts as an XML report and as an Excel report."""
    xml = write_xml(tmp_path / f"{name}.xml", report_xml(arts))
    xlsx = tmp_path / f"{name}.xlsx"
    write_xlsx(xlsx, workbook_sheets(arts))
    return [xml, xlsx]


OWNER_WA = ("Android WhatsApp Accounts Information", [[("Phone Number", "15550100001@wa")]])


def _wa(*hits) -> tuple[str, list]:
    return ("Android WhatsApp Messages", list(hits))


def _msg(body: str, ts: str | None, ts_name: str = "Message Date/Time - UTC+00:00 (M/d/yyyy)",
         **extra: str | None) -> list:  # fmt: skip
    return [
        ("Sender", extra.pop("sender", "15550100002@wa")),
        ("Sender Name", extra.pop("sender_name", "Jo")),
        ("Recipient(s)", extra.pop("to", "15550100001@wa")),
        ("Message", body),
        (ts_name, ts),
        *extra.items(),
    ]


# ---------------------------------------------------------------- case01 parity


@pytest.fixture(scope="module")
def case01(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("case01")
    generate(out)
    write_case01(out)
    return out


PARITY = {
    "threads": "SELECT id, app, title FROM threads",
    "messages": "SELECT thread_id, sender_account_id, direction, ts_utc, body, deleted_flag"
    " FROM messages",
    "recipients": "SELECT m.thread_id, m.ts_utc, m.body, r.account_id FROM message_recipients r"
    " JOIN messages m ON m.id = r.message_id",
    "calls": "SELECT app, direction, ts_utc, duration_s, deleted_flag FROM calls",
    "contacts": "SELECT name, identifier FROM contacts",
    "attachments": "SELECT m.thread_id, m.ts_utc, a.file_name FROM attachments a"
    " JOIN messages m ON m.id = a.message_id",
    "devices": "SELECT id, label, model, os_version FROM devices",
}
ACCOUNTS = "SELECT id, app, identifier, display_name, device_id IS NOT NULL FROM accounts"


@pytest.mark.parametrize("ext", ["xml", "xlsx"])
@pytest.mark.parametrize("device", ["item1", "item2"])
def test_case01_as_axiom_gives_the_same_records_as_its_cellebrite_report(case01, device, ext):
    xl = _db()
    CellebriteExcelImporter(source_id=device).import_source(case01 / f"{device}.xlsx", xl)
    ax = _db()
    AxiomImporter(source_id=device).import_source(case01 / f"{device}-axiom.{ext}", ax)
    for name, sql in PARITY.items():
        a = sorted(map(repr, xl.execute(sql)))
        b = sorted(map(repr, ax.execute(sql)))
        assert a == b, name
        assert a or name == "attachments", name  # item2 has no attachments
    # An AXIOM call log names only the partner, so the phone's own number on its calls (which
    # the Cellebrite report marks '(owner)') is the one account AXIOM does not give.
    a = set(xl.execute(ACCOUNTS))
    b = set(ax.execute(ACCOUNTS))
    assert b < a and {r[1] for r in a - b} == {"Phone"}
    # each call's partner is the caller or callee the Cellebrite report gives
    sides = (
        "SELECT ts_utc, from_account_id FROM calls UNION SELECT ts_utc, to_account_id FROM calls"
    )
    partners = set(ax.execute(sides)) - {
        (t, None) for (t,) in ax.execute("SELECT ts_utc FROM calls")
    }
    assert len(partners) == ax.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    assert partners <= set(xl.execute(sides))
    # every account the accounts artifacts name is the phone's own
    owners = {r[0] for r in ax.execute("SELECT id FROM accounts WHERE device_id IS NOT NULL")}
    assert owners == {r[0] for r in a if r[4] and r[1] != "Phone"}


def test_case01_axiom_source_kind_locators_and_coverage(case01):
    path = case01 / "item1-axiom.xml"
    conn, s = _import(path, "item1")
    kind, fidelity, sha, tool = conn.execute(
        "SELECT kind, fidelity, sha256, tool_name FROM sources"
    ).fetchone()
    assert (kind, fidelity) == ("axiom", "curated_report")  # a report export: never complete
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()
    assert tool == "Magnet AXIOM (report export)"
    mid, loc = conn.execute("SELECT id, locator FROM messages ORDER BY rowid LIMIT 1").fetchone()
    assert loc.startswith("Artifact[") and "/Hit[" in loc and mid == f"msg:item1:{loc}"
    payload = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    assert payload["importer"] == "axiom" and payload["importer_version"] == axiom.IMPORTER_VERSION
    assert payload["format_support"] == "unverified" and payload["axiom"]["format"] == "xml"
    assert set(payload["axiom"]["recovery_method_values"]) == {"Parsing"}
    (logged,) = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'import'"
    ).fetchone()
    assert json.loads(logged) == payload
    assert s.status == "needs_review" and s.format_unverified
    assert s.headline.startswith("Unverified format. Imported all ")
    codes = _codes(s)
    assert codes["category_not_imported"] == "info"  # Chrome Web History, listed with its count
    assert codes["date_order"] == "info" and codes["header_offset"] == "info"
    assert "AXIOM reader is not yet verified" in s.items[0].plain

    xconn, xs = _import(case01 / "item1-axiom.xlsx", "item1")
    (xloc,) = xconn.execute("SELECT locator FROM messages ORDER BY rowid LIMIT 1").fetchone()
    assert xloc.endswith("!2")  # sheet!row, the header on row 1
    ext, extracted = xconn.execute("SELECT extraction_type, tool_version FROM sources").fetchone()
    assert (ext, extracted) == ("logical", "SYNTHETIC")  # from the Case Information sheet
    assert "header_note" in _codes(xs)  # the 31-character sheet names are said to be cut


def test_case01_exports_are_deterministic(tmp_path):
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
    a = write_case01(tmp_path / "a")
    b = write_case01(tmp_path / "b")
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]


# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("name", "truncated", "expected"),
    [
        ("Android WhatsApp Messages", False, ("chats", "WhatsApp")),
        ("iOS WhatsApp Messages", False, ("chats", "WhatsApp")),
        ("Signal Messages - iOS", False, ("chats", "Signal")),
        ("Facebook Messenger Messages", False, ("chats", "Facebook Messenger")),
        ("Instagram Direct Messages", False, ("chats", "Instagram")),
        ("Snapchat Chat Messages", False, ("chats", "Snapchat")),
        ("iOS Telegram Chats", False, ("chats", "Telegram")),
        ("Android SMS", False, ("sms", "SMS")),
        ("Android SMS/MMS", False, ("sms", "SMS")),
        ("iOS iMessage/SMS/MMS", False, ("sms", "SMS")),
        ("Android Call Logs", False, ("calls", "Phone")),
        ("WhatsApp Calls", False, ("calls", "WhatsApp")),
        ("Android Contacts", False, ("contacts", None)),
        ("Apple Contacts - iOS", False, ("contacts", None)),
        ("Android WhatsApp Accounts Information", False, ("accounts", "WhatsApp")),
        ("Android WhatsApp Accounts Infor", True, ("accounts", "WhatsApp")),
        ("Android WhatsApp Accounts Infor", False, (None, None)),
        ("iOS Device Information", False, ("device", None)),
        ("Chrome Web History", False, (None, None)),
        ("Chat Statistics", False, (None, None)),
    ],
)
def test_artifact_names_give_kind_and_app(name, truncated, expected):
    assert classify(name, truncated) == expected


def test_time_field_names_state_offset_and_date_format():
    f = field_name("Message Sent Date/Time - UTC-05:00 (M/d/yyyy)")
    assert (f.base, f.offset, f.zone, f.date_format) == (
        "message sent date/time",
        -300,
        None,
        "M/d/yyyy",
    )
    assert field_name("Call Date/Time - UTC (dd.MM.yyyy)").offset == 0
    named = field_name("Call Date/Time - Eastern Standard Time (M/d/yyyy)")
    assert named.offset is None and named.zone == "Eastern Standard Time"
    assert field_name("Recipient(s)").base == "recipient(s)"
    assert field_name("Signal Messages - iOS").offset is None  # not a time
    assert [date_format_order(x) for x in ("M/d/yyyy", "dd/MM/yyyy", "yyyy-MM-dd", None)] == [
        "mdy", "dmy", "ymd", None,
    ]  # fmt: skip


# ---------------------------------------------------------------- records, times, flags


@pytest.fixture
def edge(tmp_path) -> list[Path]:
    arts = [
        OWNER_WA,
        _wa(
            _msg("hi", "3/4/2026 9:00:00 PM", **{"Recovery method": "Carving"}),
            _msg("no time", None),
            _msg(
                "sent",
                "3/5/2026 10:00:00 AM",
                sender="15550100001@wa",
                sender_name=None,
                to="15550100002@wa Jo",
            ),
        ),
        (
            "Android SMS",
            [
                [
                    ("Partner", "+15550100003"),
                    ("Partner Name", "Sam"),
                    ("Message", "dmy"),
                    ("Message Direction", "Incoming"),
                    ("Received Date/Time - UTC+01:00 (dd/MM/yyyy)", "04/03/2026 21:00:00"),
                    ("Sent Date/Time - UTC+01:00 (dd/MM/yyyy)", "04/03/2026 20:59:00"),
                    ("Mood", "odd"),
                ]
            ],
        ),
        (
            "WhatsApp Calls",
            [
                [
                    ("Partner", "+15550100003"),
                    ("Direction", "Outgoing"),
                    ("Call Date/Time - Eastern Standard Time (M/d/yyyy)", "3/4/2026 9:00:00 PM"),
                    ("Call Duration", "about a minute"),
                ]
            ],
        ),
        (
            "Android Call Logs",
            [
                [
                    ("Partner", "+15550100004"),
                    ("Direction", "Missed"),
                    ("Call Date/Time - UTC+00:00 (M/d/yyyy)", "3/4/2026 9:00:00 PM"),
                    ("Call Duration", "00:00:00"),
                ],
            ],
        ),
        ("Android Emails", [[("Subject", "x")]]),
        ("Weird Thing", [[("Foo", "bar")]]),
    ]
    return _both(tmp_path, arts, "edge")


@pytest.mark.parametrize("i", [0, 1])
def test_times_read_with_the_offset_and_date_format_their_field_names_state(edge, i):
    conn, s = _import(edge[i])
    rows = dict(conn.execute("SELECT body, ts_utc FROM messages"))
    assert rows["hi"] == "2026-03-04T21:00:00Z"  # 3/4 read month first, as the name says
    assert rows["dmy"] == "2026-03-04T19:59:00Z"  # 04/03 read day first, UTC+01:00 applied
    assert rows["no time"] is None
    raw = dict(conn.execute("SELECT body, ts_raw FROM messages"))
    assert raw["dmy"] == "04/03/2026 20:59:00"  # the sent time is used before the received
    calls = {
        r[0]: r[1:] for r in conn.execute("SELECT direction, ts_utc, ts_raw, duration_s FROM calls")
    }
    # a zone name is never applied: the time is kept as written, with no UTC time
    assert calls["outgoing"] == (None, "3/4/2026 9:00:00 PM", None)
    assert calls["missed"] == ("2026-03-04T21:00:00Z", "3/4/2026 9:00:00 PM", 0)
    codes = _codes(s)
    for code in ("carved", "no_time", "duration_unread", "times_no_offset", "not_imported"):
        assert codes[code] == "attention", code
    assert codes["category_not_imported"] == "info"  # Android Emails
    assert codes["header_zone_name"] == "info" and codes["unknown_columns"] == "info"
    text = coverage.format_text(s, 50)
    assert "check each one in AXIOM Examine" in text
    assert "Weird Thing" in text and "Mood" in text


@pytest.mark.parametrize("i", [0, 1])
def test_direction_parties_and_threads_follow_the_shared_mapping(edge, i):
    conn, _s = _import(edge[i])
    sender = dict(conn.execute("SELECT body, sender_account_id FROM messages"))
    direction = dict(conn.execute("SELECT body, direction FROM messages"))
    assert sender["hi"] == "acct:a1:WhatsApp:15550100002@wa"
    assert direction["hi"] == "incoming" and direction["sent"] == "outgoing"  # from the owner
    assert direction["dmy"] == "incoming"  # stated
    owner = conn.execute(
        "SELECT device_id FROM accounts WHERE id = 'acct:a1:WhatsApp:15550100001@wa'"
    ).fetchone()
    assert owner == ("dev:a1",)
    names = dict(conn.execute("SELECT id, display_name FROM accounts"))
    assert names["acct:a1:WhatsApp:15550100002@wa"] == "Jo"
    assert names["acct:a1:SMS:+15550100003"] == "Sam"
    sms_thread = conn.execute("SELECT thread_id FROM messages WHERE body = 'dmy'").fetchone()
    assert sms_thread == ("thr:a1:SMS:sms:+15550100003",)  # one thread per counterpart
    calls = dict(conn.execute("SELECT direction, from_account_id FROM calls"))
    assert calls["missed"] == "acct:a1:Phone:+15550100004"  # a missed call's partner called


def test_stated_date_order_wins_and_contradicting_values_are_counted(tmp_path):
    arts = [_wa(_msg("a", "3/4/2026 9:00:00 PM"), _msg("b", "3/25/2026 9:00:00 PM"))]
    xml = _both(tmp_path, arts)[0]
    conn, s = _import(xml, date_order="dmy")
    rows = dict(conn.execute("SELECT body, ts_utc FROM messages"))
    assert rows["a"] == "2026-04-03T21:00:00Z"  # day first, as stated
    assert rows["b"] == "2026-03-25T21:00:00Z"  # can only be month first: read as written
    assert _codes(s)["values_contradicting_stated_date_order"] == "attention"


def test_a_field_name_without_a_zone_gives_no_utc_time_and_no_guessed_order(tmp_path):
    arts = [_wa(_msg("a", "3/4/2026 9:00:00 PM", ts_name="Message Date/Time"))]
    conn, s = _import(_both(tmp_path, arts)[0])
    assert conn.execute("SELECT ts_utc, ts_raw FROM messages").fetchone() == (
        None,
        "3/4/2026 9:00:00 PM",
    )
    assert "times_ambiguous_day_month" in _codes(s)


def test_coverage_own_words_never_use_forbidden_words(edge):
    _conn, s = _import(edge[0])
    for item in s.items:
        own = "".join(t for t, quoted in item.parts if not quoted)
        assert not FORBIDDEN_WORDS.search(own), own


# ---------------------------------------------------------------- refusals


def _refused(path: Path, match: str) -> None:
    conn = _db()
    with pytest.raises(ValueError, match=match):
        AxiomImporter(source_id="x").import_source(path, conn)
    assert conn.execute("SELECT COUNT(*) FROM sources").fetchone() == (0,)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (0,)


def test_a_document_type_or_entity_is_refused(tmp_path):
    p = tmp_path / "d.xml"
    p.write_text('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY e "x">]><r><Artifact/></r>')
    _refused(p, "document type")


def test_broken_or_foreign_xml_stores_nothing(tmp_path):
    p = tmp_path / "b.xml"
    p.write_text("<ReportData><Artifact name='Android SMS'><Hits><Hit>")
    _refused(p, "not well-formed")
    q = tmp_path / "f.xml"
    q.write_text("<project><decodedData/></project>")
    _refused(q, "not a Magnet AXIOM XML report")


# ---------------------------------------------------------------- picking the importer


def test_the_right_importer_is_picked_for_each_file(case01):
    assert report_importer(case01 / "item1.xlsx") is CellebriteExcelImporter
    assert report_importer(case01 / "item1-axiom.xlsx") is AxiomImporter
    assert report_importer(case01 / "item1-axiom.xml") is AxiomImporter
    assert report_importer(Path("x.ufdr")) is UfdrImporter


# ---------------------------------------------------------------- where the expert sees it


def test_baker_import_reads_an_axiom_export_and_says_it_is_unverified(case01, tmp_path, capsys):
    db = tmp_path / "c.db"
    assert cli_main(["init", "--db", str(db)]) == 0
    report = str(case01 / "item2-axiom.xlsx")
    assert cli_main(["import", "--db", str(db), "--report", report]) == 0
    out = capsys.readouterr().out
    assert "(curated_report)" in out and "Unverified format." in out
    assert "AXIOM reader is not yet verified" in out


def test_case_screen_imports_an_axiom_xml_and_shows_it_unverified(case01, tmp_path):
    app = _screen(tmp_path)
    assert _send(app, case01 / "item2-axiom.xml").status == 303
    page = _setup(app)
    assert "Imported item2-axiom.xml" in page and "Unverified format." in page
    assert "AXIOM reader is not yet verified" in page
    assert ".xml" in page  # the upload form takes AXIOM XML reports
    check_report_text(page)


def test_report_limitations_say_the_axiom_reader_is_unverified(case01, edge):
    conn = _db()
    AxiomImporter(source_id="item2").import_source(case01 / "item2-axiom.xml", conn)
    AxiomImporter(source_id="edge").import_source(edge[0], conn)
    html = render_report(conn)
    limits = html.split("<h2>Limitations</h2>", 1)[1].split("<h2>", 1)[0]
    assert limits.count("Magnet AXIOM reader, which is not yet verified") == 2
    assert "examiner-curated report" in limits  # no absence finding rests on it
    assert 'Baker did not read all of <span class="q">edge.xml' in limits
    check_report_text(html)


def test_an_encrypted_case_imports_an_axiom_xml_through_decryption(case01, tmp_path):
    from core import encryption
    from core.db import connect
    from tests.test_coverage_display import HOST
    from ui.app import Request

    app = _screen(tmp_path / "plain")
    path = case01 / "item2-axiom.xml"
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
    assert _send(app, path).status == 303
    assert "Imported item2-axiom.xml" in _setup(app)
    assert encryption.is_encrypted_file(case.inputs / "item2-axiom.xml")
    conn = connect(case.db)
    sid = conn.execute("SELECT id FROM sources WHERE kind = 'axiom'").fetchone()[0]
    plain = _db()
    AxiomImporter(source_id=sid).import_source(path, plain)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert conn.execute("SELECT sha256 FROM sources WHERE id = ?", (sid,)).fetchone() == (sha,)
    for name, sql in PARITY.items():
        assert sorted(map(repr, conn.execute(sql))) == sorted(map(repr, plain.execute(sql))), name
    conn.close()


# ---------------------------------------------------------------- review follow-ups


def test_a_hit_with_its_first_time_field_blank_takes_the_next_one(tmp_path):
    sent = "Sent Date/Time - UTC+00:00 (M/d/yyyy)"
    received = "Received Date/Time - UTC+01:00 (d/M/yyyy)"
    arts = [
        (
            "Android SMS",
            [
                [("Partner", "+15550100003"), ("Message", "out"), (sent, "3/4/2026 9:00:00 PM"),
                 (received, None)],
                [("Partner", "+15550100003"), ("Message", "in"), (sent, None),
                 (received, "3/4/2026 9:00:00 PM")],
            ],
        )
    ]  # fmt: skip
    for path in _both(tmp_path, arts):
        conn, s = _import(path)
        rows = dict(conn.execute("SELECT body, ts_utc FROM messages"))
        assert rows == {"out": "2026-03-04T21:00:00Z", "in": "2026-04-03T20:00:00Z"}
        assert "no_time" not in _codes(s)


def test_hits_with_nothing_in_fields_baker_reads_are_listed_not_imported(tmp_path):
    arts = [_wa(_msg("hi", "3/4/2026 9:00:00 PM"), [("Mood", "odd")])]
    for path in _both(tmp_path, arts):
        conn, s = _import(path)
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (1,)
        assert _codes(s)["rows_skipped_no_values_in_known_columns"] == "attention"


def test_a_workbook_with_only_contacts_and_accounts_is_still_read_as_axiom(tmp_path):
    arts = [
        OWNER_WA,
        ("Android Contacts", [[("Display Name", "Jo"), ("Phone Number(s)", "+15550100002")]]),
    ]
    xlsx = _both(tmp_path, arts)[1]
    assert report_importer(xlsx) is AxiomImporter


def test_device_details_baker_cannot_read_are_listed(tmp_path):
    arts = [("iOS Device Information", [[("Handset Label", "x")]]), _wa(_msg("hi", None))]
    conn, s = _import(_both(tmp_path, arts)[0])
    entry = next(e for e in json.loads(
        conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0]
    )["not_imported"] if e["name"] == "iOS Device Information")  # fmt: skip
    assert entry["reason"] == "device details with no field Baker knows"
    assert "not_imported" in _codes(s)


def test_hits_outside_the_artifact_hits_hierarchy_are_not_read(tmp_path):
    p = tmp_path / "h.xml"
    p.write_text(
        "<R><Artifact name='Android SMS'><Hit><Fragment name='Message'>stray</Fragment></Hit>"
        "<Hits><Hit><Fragment name='Message'>kept</Fragment>"
        "<Fragment name='Partner'>+15550100003</Fragment></Hit></Hits></Artifact></R>"
    )
    conn, _s = _import(p)
    assert [r[0] for r in conn.execute("SELECT body FROM messages")] == ["kept"]


def test_the_acquisition_time_key_applies_its_own_zone_and_format(tmp_path):
    xlsx = tmp_path / "s.xlsx"
    sheets = workbook_sheets(
        [_wa(_msg("hi", "3/4/2026 9:00:00 PM"))],
        [("Acquisition Date/Time - UTC-05:00 (d/M/yyyy)", "3/4/2026 9:00:00 PM")],
    )
    write_xlsx(xlsx, sheets)
    conn, _s = _import(xlsx)
    assert conn.execute("SELECT extracted_at_utc FROM sources").fetchone() == (
        "2026-04-04T02:00:00Z",
    )


def test_values_against_the_field_date_format_are_not_called_a_stated_order(tmp_path):
    arts = [_wa(_msg("a", "3/25/2026 9:00:00 PM", ts_name="Message Date/Time - UTC (d/M/yyyy)"))]
    _conn, s = _import(_both(tmp_path, arts)[0])
    codes = _codes(s)
    assert codes["values_contradicting_field_date_format"] == "attention"
    assert "values_contradicting_stated_date_order" not in codes


# ---------------------------------------------------------------- forwarded and quoted (gate 4)
# The field names are the ones core/ingest/axiom.py assumes (unverified on a real export).


def _fwd_case(tmp_path: Path, ext: str, **extra: str | None):
    """The phone's owner sends a hit marked forwarded, or quoting Jo's words."""
    hit = _msg(
        "SYNTHETIC see you at noon",
        "3/10/2026 3:00:00 PM",
        sender="15550100001@wa",
        sender_name=None,
        to="15550100002@wa",
        **{"Chat ID": "c1", **extra},
    )
    arts = [OWNER_WA, _wa(hit)]
    path = _both(tmp_path, arts)[0 if ext == "xml" else 1]
    conn, s = _import(path)
    return conn, s


def _rows(conn):
    return conn.execute(
        "SELECT id, locator, body, ts_raw, ts_utc, direction, forwarded, forwarded_from_raw,"
        " thread_id FROM messages ORDER BY locator"
    ).fetchall()


@pytest.mark.parametrize("ext", ["xml", "xlsx"])
def test_a_hit_marked_forwarded_is_marked_with_its_original_author_as_written(tmp_path, ext):
    from core.ingest import forwarded

    conn, s = _fwd_case(tmp_path, ext, **{"Forwarded": "Yes", "Forwarded From": " Jo (old #) "})
    ((mid, _loc, body, *_r, fwd, author, _t),) = _rows(conn)
    assert body == "SYNTHETIC see you at noon" and fwd == 1 and author == "Jo (old #)"
    assert forwarded.affected(conn) == {mid: "forwarded"}
    assert _codes(s)["forwarded"]
    payload = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    assert payload["forwarded_records"] == {"forwarded": [mid]}
    assert payload["importer_version"] == "0.2.0"
    # never credited to the forwarder: the note names the author as the extraction's text
    assert forwarded.record_note_text(conn, mid, "forwarded") == (
        'Forwarded: shown as sent by whoever forwarded it; the extraction names "Jo (old #)" as '
        "the original author, which Baker has not checked."
    )


@pytest.mark.parametrize("value", ["No", "false", "0", "", None])
def test_a_forwarded_flag_saying_no_marks_nothing(tmp_path, value):
    conn, _s = _fwd_case(tmp_path, "xml", Forwarded=value)
    assert [r[6] for r in _rows(conn)] == [None]


def test_an_unknown_forwarded_value_fails_closed(tmp_path):
    conn, _s = _fwd_case(tmp_path, "xml", Forwarded="Maybe")
    assert [r[6] for r in _rows(conn)] == [1]


@pytest.mark.parametrize("ext", ["xml", "xlsx"])
def test_a_quoted_message_is_its_own_record_like_a_ufdr_embedded_copy(tmp_path, ext):
    from core.ingest import forwarded

    conn, s = _fwd_case(
        tmp_path,
        ext,
        **{
            "Quoted Message": "  SYNTHETIC Jo's exact words\n",
            "Quoted Message Sender": "15550100002@wa",
            "Quoted Message Sender Name": "Jo",
        },
    )
    parent, copy = _rows(conn)
    assert copy[1] == f"{parent[1]}/Embedded[1]" and copy[0] == f"msg:a1:{copy[1]}"
    if ext == "xml":
        assert copy[2] == "  SYNTHETIC Jo's exact words\n"  # verbatim
    assert copy[3] is None and copy[4] is None  # no time: never on the timeline
    assert copy[5] != "outgoing" and parent[5] == "outgoing"  # never the owner's words
    assert copy[6:8] == (1, "15550100002@wa")  # marked, author as written
    assert parent[6] is None  # the hit itself is not marked forwarded
    assert copy[8] == parent[8]  # same thread, and no thread made for the copy alone
    assert conn.execute("SELECT COUNT(*) FROM threads").fetchone() == (1,)
    sender = conn.execute(
        "SELECT a.identifier, a.display_name FROM messages m"
        " JOIN accounts a ON a.id = m.sender_account_id WHERE m.id = ?",
        (copy[0],),
    ).fetchone()
    # Jo, never the forwarder or the phone owner (the account keeps the first name seen: none,
    # from the hit's recipient)
    assert sender == ("15550100002@wa", None)
    found = forwarded.affected(conn)
    assert found == {parent[0]: "embedded", copy[0]: "embedded_copy"}
    assert forwarded.record_note_text(conn, copy[0], "embedded_copy") == (
        f"Forwarded or quoted copy carried inside record {parent[0]}, imported as its own "
        'record. The sender shown, "15550100002@wa", is the one the extraction names for '
        "the embedded message, not verified; the message that carried it was sent by "
        '"15550100001@wa".'
    )
    codes = _codes(s)
    assert codes["embedded_messages_imported"] == "info"
    assert "embedded_original_imported" in codes
    assert "embedded_message_imported_separately" in codes
    tc = json.loads(conn.execute("SELECT payload_json FROM source_coverage").fetchone()[0])
    (table,) = [t for t in tc["tables"] if t["kind"] == "chats"]
    assert table["rows_imported"] == 1  # the export's own hits only


def test_a_forwarded_hit_carrying_its_original_takes_the_copy_sender_as_author(tmp_path):
    conn, _s = _fwd_case(
        tmp_path, "xml", Forwarded="True", **{"Quoted Message": "SYNTHETIC hi",
                                              "Quoted Message Sender": "15550100002@wa"}
    )  # fmt: skip
    parent, copy = _rows(conn)
    assert parent[6:8] == (1, "15550100002@wa") and copy[6:8] == (1, "15550100002@wa")


def test_a_quoted_message_with_no_sender_names_none(tmp_path):
    from core.ingest import forwarded

    conn, _s = _fwd_case(tmp_path, "xml", **{"Quoted Message": "SYNTHETIC no one named"})
    parent, copy = _rows(conn)
    assert copy[6:8] == (1, None)
    assert forwarded.record_note_text(conn, copy[0], "embedded_copy") == (
        f"Forwarded or quoted copy carried inside record {parent[0]}, imported as its own "
        "record. The extraction names no sender for the embedded message; the message that "
        'carried it was sent by "15550100001@wa".'
    )


def _sender(conn, quoted: str):
    from tests.checks.helpers import check, stipulate

    stipulate(conn, "person:b", "Bee", "dev:a1")
    return check(conn, "sender", quoted_text=quoted, person_ids=["person:b"],
                 device_ids=["dev:a1"])  # fmt: skip


def test_checks_resting_on_an_axiom_forward_fail_closed_and_never_credit_the_forwarder(tmp_path):
    from core.contracts import CheckOutcome

    plain, _s = _fwd_case(tmp_path / "p", "xml")
    assert _sender(plain, "see you at noon").outcome is CheckOutcome.PASS
    conn, _s = _fwd_case(tmp_path / "f", "xml", Forwarded="Yes")
    r = _sender(conn, "see you at noon")
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "marked as forwarded" in r.detail and "was sent by" not in r.detail


def test_a_check_on_quoted_words_rests_on_the_copy_and_is_inconclusive(tmp_path):
    from core.contracts import CheckOutcome
    from core.ingest import forwarded

    conn, _s = _fwd_case(
        tmp_path, "xml", **{"Quoted Message": "SYNTHETIC Jo said this first",
                            "Quoted Message Sender": "15550100002@wa"}
    )  # fmt: skip
    r = _sender(conn, "Jo said this first")
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert any(forwarded.COPY_STEP in rid for rid in r.record_ids)
    assert "was sent by" not in r.detail
    found = forwarded.affected(conn)
    assert "cannot support or contradict" in forwarded.claim_warning(found, r.record_ids)


def test_the_report_names_the_axiom_importer_version(tmp_path):
    conn, _s = _fwd_case(tmp_path, "xml", **{"Quoted Message": "SYNTHETIC hi"})
    assert axiom.IMPORTER_VERSION == "0.2.0"
    html_ = render_report(conn)
    assert "axiom 0.2.0</td>" in html_
