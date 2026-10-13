"""Synthetic Cellebrite-style UFDR packages. Everything here is invented; no real case data.

A UFDR is a zip holding report.xml (the decoded data) and the extracted files it points to.
This writer follows Cellebrite's public descriptions of that structure (docs/ingest/ufdr.md);
it has not been compared with a real package, which is why the importer labels its support
unverified.

    python -m eval.synthetic.ufdr --out eval/out/ufdr   # item1.ufdr and item2.ufdr

`case01_package` renders one case01 phone from the same rows its Excel report holds, so an
import of either file must give the same canonical records (tests/test_ufdr.py).
The builders (`model`, `field`, `party`, ...) are also what the tests use for edge cases.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from core.ingest.cellebrite_common import parse_parties
from eval.synthetic.generate import CALL_COLUMNS, CHAT_COLUMNS, Rendered, build

NAMESPACE = "http://pa.cellebrite.com/report/2.0"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)  # fixed, so the same input gives the same bytes


# ---------------------------------------------------------------- XML builders


def _text(value: str) -> str:
    """A value as report.xml writes it: CDATA, or escaped text when CDATA cannot hold it (a
    carriage return, which XML readers turn into a line feed, or the sequence ']]>')."""
    if "\r" in value or "]]>" in value:
        return escape(value).replace("\r", "&#13;")
    return f"<![CDATA[{value}]]>"


def _attrs(attrs: dict[str, str | None]) -> str:
    return "".join(f" {k}={quoteattr(v)}" for k, v in attrs.items() if v is not None)


def field(name: str, value: str | None, type_: str = "String") -> str:
    if value is None:
        return f'<field name="{name}" type="{type_}" />'
    return (
        f'<field name="{name}" type="{type_}"><value type="{type_}">{_text(value)}</value></field>'
    )


def ts_field(name: str, value: str | None) -> str:
    return field(name, value, "TimeStamp")


def model(type_: str, *parts: str, **attrs: str | None) -> str:
    a = {"type": type_, "deleted_state": "Intact", **attrs}
    return f"<model{_attrs(a)}>{''.join(parts)}</model>"


def one(name: str, child: str, type_: str = "Party") -> str:
    return f'<modelField name="{name}" type="{type_}">{child}</modelField>'


def many(name: str, children: Iterable[str], type_: str = "Party") -> str:
    return f'<multiModelField name="{name}" type="{type_}">{"".join(children)}</multiModelField>'


def party(ident: str | None, name: str | None, owner: bool = False, role: str | None = None) -> str:
    parts = [field("Identifier", ident), field("Name", name)]
    if role is not None:
        parts.append(field("Role", role, "PartyRole"))
    parts.append(field("IsPhoneOwner", "True" if owner else "False", "Boolean"))
    return model("Party", *parts)


def iso_local(utc: datetime, offset_min: int) -> str:
    """'2026-03-14T21:50:20.000-04:00': the wall clock at the offset, with the offset."""
    local = utc.astimezone(UTC) + timedelta(minutes=offset_min)
    sign = "+" if offset_min >= 0 else "-"
    h, m = divmod(abs(offset_min), 60)
    return f"{local:%Y-%m-%dT%H:%M:%S}.000{sign}{h:02d}:{m:02d}"


def report_xml(
    models: dict[str, list[str]],
    metadata: Iterable[tuple[str, str]] = (),
    extractions: Iterable[dict[str, str]] = ({"type": "Logical", "deviceName": "Phone"},),
    project: dict[str, str] | None = None,
    extra: str = "",
) -> str:
    """report.xml: project, extractions, a Device Info metadata section, decoded models grouped
    by type in the order given, and `extra` (for example taggedFiles) after them."""
    exts = "".join(
        f"<extractionInfo{_attrs({'id': str(i), 'name': e.get('type'), 'index': str(i), **e})} />"
        for i, e in enumerate(extractions)
    )
    meta = "".join(
        f'<item name="{escape(k)}" sourceExtraction="0">{_text(v)}</item>' for k, v in metadata
    )
    decoded = "".join(
        f'<modelType type="{t}">{"".join(ms)}</modelType>' for t, ms in models.items() if ms
    )
    p = {"id": "synthetic", "name": "SYNTHETIC", "reportVersion": "5.2.0.0", **(project or {})}
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<project{_attrs(p)} xmlns="{NAMESPACE}">'
        f"<sourceExtractions>{exts}</sourceExtractions>"
        f'<sections><section name="Device Info"><metadata section="Device Info">{meta}'
        "</metadata></section></sections>"
        f"<decodedData>{decoded}</decodedData>{extra}</project>"
    )


def write_package(
    path: Path, xml: str | bytes, files: dict[str, bytes] | None = None, member: str = "report.xml"
) -> Path:
    """A deterministic zip: report.xml first, then the files in name order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    with zipfile.ZipFile(path, "w") as z:
        for name, body in [(member, data), *sorted((files or {}).items())]:
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, body)
    return path


# ---------------------------------------------------------------- case01


def _party_models(cell: object, role: str | None = None) -> list[str]:
    """The case01 report's party cell, as the same parties the Excel import reads from it."""
    return [
        party(p.identifier, p.name, p.owner, role)
        for p in parse_parties(cell if isinstance(cell, str) else None)
    ]


def _deleted(cell: object) -> str:
    return "Deleted" if cell == "Deleted" else "Intact"


def _mime(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower()
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


def case01_package(r: Rendered) -> tuple[str, dict[str, bytes]]:
    """report.xml and attachment files for one case01 phone, from its Excel report's rows."""
    sheets = dict(r.sheets)
    when = {m["locator"]: m for m in r.messages} | {c["locator"]: c for c in r.calls}

    def ts(loc: str) -> str:
        rec = when[loc]
        utc = datetime.fromisoformat(rec["ts_utc"].replace("Z", "+00:00"))
        return iso_local(utc, rec["ts_offset_min"])

    summary = {row[0]: row[1] for row in sheets["Summary"][1:] if len(row) > 1}
    dev = r.device
    metadata = [
        ("DeviceInfoSelectedDeviceName", str(summary["Device"])),
        ("DeviceInfoOSVersion", str(summary["OS version"])),
        ("DeviceInfoExtractionStartDateTime", iso_local(dev.extracted_at, 0)),
        ("DeviceInfoTimeZone", str(summary["Device time zone"])),
        ("Case number", str(summary["Case number"])),
    ]
    extractions = [{"type": str(summary["Extraction type"]), "deviceName": str(summary["Device"])}]

    accounts = [
        model("UserAccount", field("Source", row[1]), field("Username", row[2]),
              field("Name", row[3] or None))
        for row in sheets["User Accounts"][2:]
    ]  # fmt: skip
    contacts = []
    for row in sheets["Contacts"][2:]:
        entries = []
        for line in str(row[2]).splitlines():
            label, _, value = line.partition(": ")
            kind = "PhoneNumber" if value.startswith("+") else "UserID"
            entries.append(model(kind, field("Category", label), field("Value", value)))
        contacts.append(
            model(
                "Contact",
                field("Source", row[3]),
                field("Name", row[1]),
                many("Entries", entries, "ContactEntry"),
                deleted_state=_deleted(row[4]),
            )
        )

    col = {c: i for i, c in enumerate(CHAT_COLUMNS)}
    files: dict[str, bytes] = {}
    chats: dict[object, dict] = {}
    for n, row in enumerate(sheets["Chats"][2:], start=3):
        loc = f"Chats!{n}"
        c = chats.setdefault(
            row[col["Chat #"]],
            {"row": row, "messages": []},
        )
        atts = []
        name = row[col["Attachment #1"]]
        if name:
            path = f"files/Chats/{row[col['Chat #']]}/{name}"
            files[path] = f"SYNTHETIC attachment {name} for {loc}\n".encode()
            atts.append(
                model(
                    "Attachment",
                    field("Filename", str(name)),
                    field("ContentType", _mime(str(name))),
                    field("attachment_extracted_path", path.replace("/", "\\")),
                )
            )
        c["messages"].append(
            model(
                "InstantMessage",
                field("Source", row[col["Source"]]),
                one("From", "".join(_party_models(row[col["From"]]))),
                many("To", _party_models(row[col["To"]])),
                field("Body", row[col["Body"]]),
                ts_field("TimeStamp", ts(loc)),
                *([many("Attachments", atts, "Attachment")] if atts else []),
                deleted_state=_deleted(row[col["Deleted"]]),
            )
        )
    chat_models = [
        model(
            "Chat",
            field("Source", c["row"][col["Source"]]),
            field("Id", str(key)),
            field("Name", c["row"][col["Name"]]),
            many("Participants", _party_models(c["row"][col["Participants"]])),
            many("Messages", c["messages"], "InstantMessage"),
        )
        for key, c in chats.items()
    ]

    cc = {c: i for i, c in enumerate(CALL_COLUMNS)}
    calls = [
        model(
            "Call",
            field("Source", row[cc["Source"]]),
            field("Type", row[cc["Type"]], "CallType"),
            ts_field("TimeStamp", ts(f"Call Log!{n}")),
            field("Duration", row[cc["Duration"]], "TimeSpan"),
            many(
                "Parties",
                _party_models(row[cc["From"]], "From") + _party_models(row[cc["To"]], "To"),
            ),
            deleted_state=_deleted(row[cc["Deleted"]]),
        )
        for n, row in enumerate(sheets["Call Log"][2:], start=3)
    ]
    xml = report_xml(
        {"UserAccount": accounts, "Contact": contacts, "Chat": chat_models, "Call": calls},
        metadata,
        extractions,
    )
    return xml, files


def write_case01(out: Path) -> list[Path]:
    """item1.ufdr and item2.ufdr for synthetic case01."""
    paths = []
    for r in build():
        xml, files = case01_package(r)
        paths.append(write_package(out / f"{r.device.key}.ufdr", xml, files))
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("eval/out/ufdr"))
    a = ap.parse_args(argv)
    for p in write_case01(a.out):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
