"""UFDR self-check (core/ingest/ufdr_check.py): the offline check an expert runs on a first real
UFDR. Every package here is synthetic (eval/synthetic/ufdr.py).

What it must do: agree with the importer on packages the importer reads right, catch an import
that went wrong, and never put case content in the files meant to be sent back."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core.ingest import ufdr, ufdr_check
from eval.synthetic.generate import generate
from eval.synthetic.ufdr import (
    field,
    many,
    model,
    one,
    party,
    report_xml,
    ts_field,
    write_case01,
    write_package,
)

T = "2026-03-05T21:31:00.000-05:00"
OWNER = ("+15550100001", None, True)
JO = ("+15550100002", "Jo", False)


def _msg(body: str | None, ts: str | None = T, frm=JO, to=(OWNER,), *extra: str, **attrs) -> str:
    parts = [field("Source", "WhatsApp")]
    if frm is not None:
        parts.append(one("From", party(*frm)))
    if to:
        parts.append(many("To", [party(*p) for p in to]))
    parts += [field("Body", body), ts_field("TimeStamp", ts), *extra]
    return model("InstantMessage", *parts, **attrs)


def _att(*parts: str, type_: str = "Attachment") -> str:
    return model(type_, *parts)


def _variants() -> tuple[str, dict[str, bytes]]:
    """One package with the layouts the importer was built to read, each a little different."""
    files = {"files/Image/a.jpg": b"SYNTHETIC jpeg"}
    chat_msgs = [
        _msg("plain"),
        _msg("from the owner", T, OWNER, (JO,)),
        _msg(None),  # no body
        _msg("   spaced  \n"),  # kept verbatim
        _msg("utc", "2026-03-05T21:31:00Z"),
        _msg("no offset", "2026-03-05T21:31:00"),
        _msg("report form", "3/5/2026 9:31:00 PM(UTC-5)"),
        _msg("no time", None),
        _msg("trash", T, deleted_state="Trash"),
        _msg("deleted", T, deleted_state="Deleted"),
        _msg("unknown state", T, deleted_state="Unknown"),
        _msg("name only sender", T, (None, "Someone", False)),
        _msg("stated direction", T, JO, (OWNER,), field("Direction", "Incoming")),
        _msg(
            "parties with roles",
            T,
            None,
            (),
            many("Parties", [party(*JO, role="From"), party(*OWNER, role="To")]),
        ),
        _msg(
            "attachments",
            T,
            JO,
            (OWNER,),
            many(
                "Attachments",
                [
                    _att(field("Filename", "a.jpg"), field("LocalPath", "files\\Image\\a.jpg")),
                    _att(field("LocalPath", "files/Image/a.jpg")),  # name from the path
                    _att(field("ContentType", "image/png")),  # neither: not recorded
                    _att(field("Filename", "f.bin"), type_="File"),
                ],
                "Attachment",
            ),
        ),
        _msg(
            "one attachment",
            T,
            JO,
            (OWNER,),
            one("Attachment", _att(field("Filename", "x"))),
            id="m-dup",
        ),  # fmt: skip
    ]
    chats = [
        model(
            "Chat",
            field("Source", "WhatsApp"),
            field("Id", "c1"),
            many("Participants", [party(*OWNER), party(*JO)]),
            many("Messages", chat_msgs, "InstantMessage"),
        ),
        model(
            "Chat",
            field("Source", "Telegram"),
            field("Id", "c2"),
            many("Participants", [party(*OWNER), party(*JO)]),
            many("OtherMessages", [_msg("a message under another field")], "InstantMessage"),
        ),
    ]
    sms = [
        model(
            "SMS",
            many("Parties", [party(*JO, role="From"), party(*OWNER, role="To")]),
            field("Folder", "Inbox"),
            field("Body", "sms in"),
            ts_field("TimeStamp", T),
        ),
        model(
            "SMS",
            many("Parties", [party("+15550100003", "Al", False)]),  # no role: counterpart
            field("Folder", "Sent"),
            field("Body", "sms out"),
            ts_field("TimeStamp", T),
        ),
    ]
    calls = [
        model(
            "Call",
            field("Type", "Incoming", "CallType"),
            ts_field("TimeStamp", T),
            field("Duration", "00:01:05", "TimeSpan"),
            many("Parties", [party(*JO, role="From"), party(*OWNER, role="To")]),
        ),
        model("Call", field("Type", "Outgoing"), field("Duration", "65"), ts_field("TimeStamp", T),
              many("Parties", [party(*JO, role="To")])),
        model("Call", field("Type", "Missed"), field("Duration", "1.02:03:04.500"),
              ts_field("StartTime", T), many("Parties", [party(*JO)]), deleted_state="Deleted"),
        model("Call", field("Type", "Rejected"), field("Duration", "about a minute"),
              ts_field("TimeStamp", T)),
    ]  # fmt: skip
    entry = lambda v: model("PhoneNumber", field("Value", v))  # noqa: E731
    contacts = [
        model("Contact", field("Name", "Jo"), many("Entries", [entry("+1"), entry("+2"),
                                                               entry("+1")])),
        model("Contact", field("Name", "Nobody")),
    ]  # fmt: skip
    accounts = [model("UserAccount", field("Source", "WhatsApp"), field("Username", OWNER[0]))]
    top_im = [_msg("the same message again", id="m-dup"), _msg("on its own")]
    xml = report_xml(
        {
            "UserAccount": accounts,
            "Chat": chats,
            "InstantMessage": top_im,
            "SMS": sms,
            "Call": calls,
            "Contact": contacts,
            "Location": [model("Location", field("Name", "somewhere"))],
        },
        [("DeviceInfoSelectedDeviceName", "Phone"), ("UFED Physical Analyzer version", "7.60.0.1")],
    )
    return xml, files


@pytest.fixture(scope="module")
def variants(tmp_path_factory) -> Path:
    xml, files = _variants()
    return write_package(tmp_path_factory.mktemp("v") / "variants.ufdr", xml, files)


def _by(d: dict, record: str, check: str) -> dict:
    return next(c for c in d["checks"] if c["record"] == record and c["check"] == check)


def _rec(d: dict, record: str) -> dict:
    return next(r for r in d["records"] if r["record"] == record)


# ---------------------------------------------------------------- agreement


def test_case01_packages_check_clean(tmp_path):
    generate(tmp_path)
    for path in write_case01(tmp_path):
        d = ufdr_check.run(path).shareable
        assert d["imported"] and d["differences"] == 0, path.name
        assert _rec(d, "messages")["in_report_xml"] > 100
        assert all(c["compared"] for c in d["checks"] if c["check"] in ("body", "time_utc"))


def test_variants_agree_except_what_baker_does_not_import(variants):
    d = ufdr_check.run(variants).shareable
    assert d["imported"]
    msgs = _rec(d, "messages")
    # 16 chat messages, 1 under another field name, 2 top-level (one repeats an id), 2 SMS
    assert msgs["in_report_xml"] == 21
    assert (msgs["missing"], msgs["extra"], msgs["repeats_imported_once"]) == (0, 0, 1)
    assert msgs["imported_by_baker"] == 20
    differing = {(c["record"], c["check"]): c for c in d["checks"] if c["differ"]}
    assert differing == {}, differing
    assert _by(d, "messages", "time_utc")["compared"] >= 15  # ISO with offset, read separately
    assert _by(d, "calls", "duration")["compared"] == 3  # 'about a minute' is not checked
    assert _by(d, "calls", "direction")["not_checked"] == 1  # 'Rejected'
    assert _by(d, "contacts", "entries")["compared"] == 2
    assert _rec(d, "attachments")["in_report_xml"] == _rec(d, "attachments")["imported_by_baker"]
    assert _by(d, "messages", "attachment_files_hashed")["compared"] == 1
    # what Baker does not read is named: the Location type, and the call's StartTime shape
    assert {"type": "Location", "records": 1, "reason": "category not imported"} in d[
        "baker_coverage"
    ]["types_not_imported"]
    assert d["package"]["physical_analyzer_version"] == "7.60.0.1"
    assert (
        "9/9/9999 9:99:99 PM(UTC-9)" in d["value_shapes"]["Chat.Messages>InstantMessage.TimeStamp"]
    )


def test_a_top_level_type_baker_does_not_import_shows_as_missing(tmp_path):
    xml = report_xml({"Message": [_msg("x").replace('type="InstantMessage"', 'type="Message"')]})
    d = ufdr_check.run(write_package(tmp_path / "m.ufdr", xml)).shareable
    assert _rec(d, "messages")["missing"] == 1
    assert _rec(d, "messages")["first_missing_locators"] == ["Message[1]"]
    assert d["differences"] == 1


# ---------------------------------------------------------------- it catches a wrong import


@pytest.mark.parametrize(
    ("column", "value", "check"),
    [
        ("body", "'changed'", "body"),
        ("ts_utc", "'2026-01-01T00:00:00Z'", "time_utc"),
        ("ts_raw", "'2026-01-01'", "time_as_written"),
        ("deleted_flag", "1 - COALESCE(deleted_flag, 0)", "record_state"),
        ("direction", "'unknown'", "direction"),
        ("sender_account_id", "NULL", "sender"),
    ],
)
def test_it_catches_a_message_field_the_importer_got_wrong(
    variants, monkeypatch, column, value, check
):
    real = ufdr.UfdrImporter.import_source

    def broken(self, path, conn):
        src = real(self, path, conn)
        conn.execute(
            f"UPDATE messages SET {column} = {value} WHERE locator = 'Chat[1]/Messages[1]'"  # noqa: S608
        )
        return src

    monkeypatch.setattr(ufdr.UfdrImporter, "import_source", broken)
    d = ufdr_check.run(variants).shareable
    c = _by(d, "messages", check)
    assert c["differ"] == 1 and c["first_differing_locators"] == ["Chat[1]/Messages[1]"]
    assert d["differences"] == 1


def test_it_catches_records_the_importer_dropped_or_made_up(variants, monkeypatch):
    real = ufdr.UfdrImporter.import_source

    def broken(self, path, conn):
        src = real(self, path, conn)
        conn.execute("DELETE FROM message_recipients WHERE message_id LIKE '%Chat[1]/Messages[2]'")
        conn.execute("DELETE FROM attachments WHERE message_id LIKE '%Chat[1]/Messages[2]'")
        conn.execute("DELETE FROM messages WHERE locator = 'Chat[1]/Messages[2]'")
        conn.execute("UPDATE calls SET locator = 'Call[9]' WHERE locator = 'Call[1]'")
        conn.execute("UPDATE calls SET duration_s = 1 WHERE locator = 'Call[2]'")
        return src

    monkeypatch.setattr(ufdr.UfdrImporter, "import_source", broken)
    d = ufdr_check.run(variants).shareable
    assert _rec(d, "messages")["first_missing_locators"] == ["Chat[1]/Messages[2]"]
    calls = _rec(d, "calls")
    assert calls["first_missing_locators"] == ["Call[1]"]
    assert calls["first_extra_locators"] == ["Call[9]"]
    assert _by(d, "calls", "duration")["first_differing_locators"] == ["Call[2]"]


def test_a_refused_package_is_still_described(tmp_path):
    xml = report_xml(
        {"Call": [model("Call", ts_field("TimeStamp", T))]},
        extractions=[{"type": "Logical", "deviceName": "PHONE-A"},
                     {"type": "Logical", "deviceName": "PHONE-B"}],
    )  # fmt: skip
    r = ufdr_check.run(write_package(tmp_path / "two.ufdr", xml))
    d = r.shareable
    assert not d["imported"]
    assert d["import_refused_because"] == "the package holds extractions from more than one device"
    assert _rec(d, "calls")["missing"] == 1
    assert "PHONE-A" in (r.import_error or "") and "PHONE-A" not in json.dumps(d)


# ---------------------------------------------------------------- no case content in what is sent


CANARY = "QZXJ"


def _canary_package() -> tuple[str, dict[str, bytes]]:
    """Every free-form value holds the marker, and identifiers use digits found nowhere else."""
    c = CANARY
    me = ("+19998887776", f"{c} Owner", True)
    jo = (f"jo.{c.lower()}@example.invalid", f"{c} Jo", False)
    att = _att(
        field("Filename", f"{c}.jpg"),
        field("LocalPath", f"files/{c}/{c}.jpg"),
        field("SHA256", "ab" * 32),
    )
    msgs = [
        _msg(f"{c} secret body", T, jo, (me,), many("Attachments", [att], "Attachment"),
             field("Status", f"{c}status"), field("Folder", f"Folder{c}"), id=f"id-{c}"),
        _msg(f"{c} other", f"{c} 2026", me, (jo,), field("Direction", f"{c}ward")),
    ]  # fmt: skip
    chat = model(
        "Chat",
        field("Source", f"{c}App"),
        field("Id", f"chat-{c}"),
        field("Name", f"{c} group"),
        many("Participants", [party(*me), party(*jo)]),
        many("Messages", msgs, "InstantMessage"),
        id=f"chat-{c}",
    )
    calls = [
        model(
            "Call",
            field("Type", f"{c}type"),
            field("Duration", f"{c}"),
            ts_field("TimeStamp", T),
            many("Parties", [party(*jo, role="From")]),
        )
    ]
    entry = model("PhoneNumber", field("Value", "+19998887775"))
    contacts = [model("Contact", field("Name", f"{c} Contact"), many("Entries", [entry]))]
    xml = report_xml(
        {
            "UserAccount": [
                model(
                    "UserAccount",
                    field("Source", f"{c}App"),
                    field("Username", "+19998887776"),
                    field("Name", f"{c}"),
                )
            ],
            "Chat": [chat],
            "Call": calls,
            "Contact": contacts,
        },  # fmt: skip
        [
            ("DeviceInfoSelectedDeviceName", f"{c} Phone"),
            ("DeviceInfoOSVersion", f"{c} OS"),
            ("DeviceInfoTimeZone", f"{c}/Zone"),
            ("Case number", f"{c}-0001"),
            ("Examiner", f"{c} Examiner"),
            ("UFED Physical Analyzer version", f"{c}"),
        ],
        [{"type": f"{c}Logical", "deviceName": f"{c} Phone", "name": f"{c}"}],
        project={"name": f"{c} project", "reportVersion": f"{c}", "id": f"{c}"},
    )
    return xml, {f"files/{c}/{c}.jpg": f"{c} bytes".encode()}


def test_shareable_files_hold_no_case_content(tmp_path):
    xml, files = _canary_package()
    package = write_package(tmp_path / f"{CANARY}.ufdr", xml, files)
    r = ufdr_check.run(package)
    assert r.shareable["imported"]
    paths = ufdr_check.write(r, tmp_path / "out")
    shared = [p.read_text(encoding="utf-8") for p in paths[:2]]
    for text in shared:
        assert CANARY not in text and CANARY.lower() not in text
        assert not re.search(r"999888777\d", text)
        assert "ab" * 32 not in text and "example.invalid" not in text
        assert str(tmp_path) not in text
    private = paths[2].read_text(encoding="utf-8")
    assert f"{CANARY} secret body" in private  # the private file is where the content goes
    assert "PRIVATE" in private
    # the shapes still say what kind of value it was
    d = json.loads(shared[1])
    assert d["package"]["report_version"] == "(shape AAAA)"
    assert d["values"]["Chat.Messages>InstantMessage.Direction"] == {"(shape AAAAaaaa)": 1}


def test_write_never_overwrites(tmp_path, variants):
    r = ufdr_check.run(variants)
    ufdr_check.write(r, tmp_path / "out")
    with pytest.raises(ValueError, match="already exists"):
        ufdr_check.write(r, tmp_path / "out")


def test_shape():
    assert ufdr_check.shape("2026-03-05T21:31:00.000-05:00") == "9999-99-99T99:99:99.999-99:99"
    assert ufdr_check.shape("Daniel Petrov 5") == "Aaaaaa Aaaaaa 9"
    assert ufdr_check.shape("Петров") == "Aaaaaa"


# ---------------------------------------------------------------- the command


def test_cli(tmp_path, variants, capsys):
    out = tmp_path / "check"
    assert cli_main(["ufdr-check", "--package", str(variants), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "Differences found: 0" in printed and "ufdr-check-private.md" in printed
    assert {p.name for p in out.iterdir()} == {
        "ufdr-check.md",
        "ufdr-check.json",
        "ufdr-check-private.md",
    }


def test_a_node_field_is_named_as_not_read(tmp_path):
    msg = _msg("x", T, JO, (OWNER,), '<nodeField name="Photo" type="Node"></nodeField>')
    xml = report_xml({"InstantMessage": [msg]})
    d = ufdr_check.run(write_package(tmp_path / "n.ufdr", xml)).shareable
    assert d["differences"] == 0
    assert "Photo" in d["baker_coverage"]["fields_baker_does_not_read"]["InstantMessage"]
    assert d["model_kinds"]["InstantMessage"]["fields"]["Photo (nodeField)"] == 1
