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


# ---------------------------------------------------------------- related copies (Reader 7.48)

# Model types public Reader 7.48 packages hold that Baker does not know (listed, not imported)
UNKNOWN_TYPES = ("AppsUsageLog", "ActivitySensorData", "FileUpload", "RecognizedDevice", "Activity")
OWNER = ("syn-owner-1", "Synthetic Owner", True)
FRIENDS = [(f"syn-friend-{i}", f"Friend {i}", False) for i in range(1, 4)]
_T0 = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)


def related(*models: str) -> str:
    """RelatedModels as Reader 7.48 writes it, after a model's fields: copies of other records,
    each with an id of its own. Baker never imports them as records."""
    return f'<jumptargets name="" /><RelatedModels>{"".join(models)}</RelatedModels>'


def _rel_msg(mid: str, body: str, ts: str, frm, to, att: str | None = None, *tail: str) -> str:
    parts = [
        field("Source", "Signal"),
        one("From", party(*frm, role="From")),
        many("To", [party(*p, role="To") for p in to]),
        field("Body", body),
        ts_field("TimeStamp", ts),
    ]
    if att is not None:
        parts.append(
            many(
                "Attachments",
                [
                    model(
                        "Attachment",
                        field("Filename", att),
                        field("ContentType", "image/png"),
                        field("attachment_extracted_path", f"files/Image/{att}"),
                        id=f"{mid}-att",
                    )
                ],
                "Attachment",
            )
        )
    return model("InstantMessage", *parts, *tail, id=mid)


def _rel_chat(key: str, msgs: list[str], *tail: str, cid: str | None = None) -> str:
    return model(
        "Chat",
        field("Source", "Signal"),
        field("Id", key),
        field("Name", f"Chat {key}"),
        many("Participants", [party(*OWNER), *(party(*p) for p in FRIENDS)]),
        many("Messages", msgs, "InstantMessage"),
        *tail,
        id=cid or f"chat-{key}",
    )


def _rel_call(cid: str, ts: str, duration: str | None) -> str:
    parts = [
        field("Source", "Phone"),
        many("Parties", [party(*OWNER, role="From"), party(*FRIENDS[0], role="To")]),
        ts_field("TimeStamp", ts),
        field("Direction", "Outgoing"),
    ]
    if duration is not None:
        parts.append(field("Duration", duration, "TimeSpan"))
    return model("Call", *parts, id=cid)


def _account(aid: str, username: str | None, app: str = "Signal", *tail: str) -> str:
    return model("UserAccount", field("Source", app), field("Username", username), *tail, id=aid)


def related_package(path: Path, unmatched: bool = False) -> Path:
    """A synthetic package shaped like public Cellebrite Reader 7.48 UFDRs: long chats (past
    the 30 messages after which copies begin), several chats, attachments and recipients, and
    RelatedModels copies of chats, messages, calls and accounts after each record's fields.
    The last chat holds two messages with the same words, parties and second. Each copy is a
    copy of the record holding it, as on the public packages: a chat's copy holds its own
    messages again. Two accounts name the same app and identifier; one has no identifier. The
    five model types Baker does not know are there too. With `unmatched`, one message and one
    call exist only as related copies, and the last chat's copy holds the repeated message a
    third time, so one copy matches no record of the package's own one to one."""
    files: dict[str, bytes] = {}

    def ts(c: int, i: int) -> str:
        return iso_local(_T0 + timedelta(days=c, minutes=7 * i), -300)

    chats: list[tuple[str, list[tuple[str, str, str, tuple, list, str | None]]]] = []
    for c, n in enumerate((60, 45, 5)):
        rows = []
        for i in range(n):
            frm = OWNER if i % 3 == 0 else FRIENDS[i % len(FRIENDS)]
            to = [p for p in (OWNER, *FRIENDS) if p != frm][: 1 + i % 3]
            att = f"syn-{c}-{i}.png" if i % 9 == 4 else None
            if att:
                files[f"files/Image/{att}"] = f"synthetic image {c}-{i}".encode()
            rows.append((f"m-{c}-{i}", f"synthetic message {c}-{i}", ts(c, i), frm, to, att))
        chats.append((f"k{c}", rows))
    same = ("synthetic same second", ts(2, 9), FRIENDS[0], [OWNER], None)
    chats[2][1].extend([("m-2-same-a", *same), ("m-2-same-b", *same)])

    def copies(c: int, picks: Iterable[int], tag: str) -> list[str]:
        return [_rel_msg(f"{r[0]}-{tag}", *r[1:]) for r in (chats[c][1][i] for i in picks)]

    out_chats = []
    for c, (key, rows) in enumerate(chats):
        msgs = []
        for i, r in enumerate(rows):
            # a message holding copies of itself, as Reader 7.48 writes some
            tail = (related(_rel_msg(f"{r[0]}-self1", *r[1:]), _rel_msg(f"{r[0]}-self2", *r[1:])),)
            msgs.append(_rel_msg(*r, *(tail if i % 10 == 3 else ())))
        # each chat ends with a copy of itself, holding some of its messages again
        copied = list(range(0, len(rows), 2))
        if c == 2:
            copied = [*range(0, 5, 2), 5, 6]  # both messages of the same second
        extra = copies(c, copied, f"rel{c}")
        if unmatched and c == 0:
            extra.append(
                _rel_msg("only-a-copy", "synthetic message only in a copy", ts(9, 1), FRIENDS[1],
                         [OWNER])
            )  # fmt: skip
        if unmatched and c == 2:
            extra.append(_rel_msg("m-2-same-c-rel", *same))  # a third, held only as a copy
        rel_chat = _rel_chat(key, extra, cid=f"chat-{key}-rel{c}")
        out_chats.append(_rel_chat(key, msgs, related(rel_chat)))
    calls = []
    for i in range(4):
        t = ts(5, i)
        copy = _rel_call(f"call-{i}-rel", t, "00:01:05")
        if unmatched and i == 0:
            copy = _rel_call("call-only-a-copy", ts(6, 0), "00:00:09")
        calls.append(_with_tail(_rel_call(f"call-{i}", t, "00:01:05"), related(copy)))
    accounts = [
        _with_tail(_account("acct-1", "syn-owner-1"), related(_account("acct-1r", "syn-owner-1"))),
        _account("acct-2", "syn-owner-1"),  # the same app and identifier again
        _account("acct-3", "syn-owner-mail", "Mail"),
        _with_tail(_account("acct-4", None, "Web"), related(_account("acct-4r", None, "Web"))),
    ]
    unknown = {
        t: [_with_tail(model(t, field("Source", "Synthetic"), id=f"{t}-1"),
                       related(model(t, field("Source", "Synthetic"), id=f"{t}-1-rel")))]
        for t in UNKNOWN_TYPES
    }  # fmt: skip
    xml = report_xml(
        {"Chat": out_chats, "Call": calls, "UserAccount": accounts, **unknown},
        metadata=[("DeviceInfoSelectedDeviceName", "Synthetic Phone")],
        project={"reportVersion": "7.48"},
    )
    return write_package(path, xml, files)


def _with_tail(model_xml: str, tail: str) -> str:
    """The model with `tail` (say, RelatedModels) as its last children."""
    head, end = model_xml.rsplit("</model>", 1)
    return f"{head}{tail}</model>{end}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("eval/out/ufdr"))
    a = ap.parse_args(argv)
    for p in write_case01(a.out):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
