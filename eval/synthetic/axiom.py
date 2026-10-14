"""Synthetic Magnet AXIOM report exports. Everything here is invented; no real case data.

Two exports of one phone: the XML report (`Artifact` / `Hits` / `Hit` / `Fragment`) and the
Excel report (one sheet per artifact type). The writer follows public descriptions of those
formats (docs/ingest/axiom.md); it has not been compared with a real export, which is why the
importer labels its support unverified.

    python -m eval.synthetic.axiom --out eval/out/axiom   # item1-axiom.xml, item1-axiom.xlsx, ...

`case01_artifacts` renders one case01 phone from the same rows its Cellebrite Excel report
holds, so an import of either AXIOM file gives the same messages, threads and contacts as the
Cellebrite report (tests/test_axiom.py). The builders (`hit`, `artifact`, `report_xml`,
`workbook_sheets`) are also what the tests use for edge cases.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from core.ingest.cellebrite_common import parse_parties
from eval.synthetic.generate import CALL_COLUMNS, CHAT_COLUMNS, Rendered, build
from eval.synthetic.xlsx import write_xlsx

UTC_MDY = " - UTC+00:00 (M/d/yyyy)"
SHEET_LIMIT = 31

Hit = list[tuple[str, str | None]]  # (fragment name, value) in order
Artifact = tuple[str, list[Hit]]


def mdy(utc: datetime) -> str:
    """'2/16/2026 3:36:36 PM': the time in UTC, month first, as the field name states."""
    t = utc.astimezone(UTC)
    hour = t.hour % 12 or 12
    return f"{t.month}/{t.day}/{t.year} {hour}:{t:%M:%S} {'PM' if t.hour >= 12 else 'AM'}"


def report_xml(artifacts: Iterable[Artifact]) -> str:
    """An XML report: each artifact with its hits and fragments. Case details are not written:
    no public description says where an AXIOM XML report keeps them."""
    arts = []
    for name, hits in artifacts:
        body = "".join(
            "<Hit>"
            + "".join(f"<Fragment name={quoteattr(f)}>{_text(v)}</Fragment>" for f, v in h)
            + "</Hit>"
            for h in hits
        )
        arts.append(f"<Artifact name={quoteattr(name)}><Hits>{body}</Hits></Artifact>")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f"<ReportData><Artifacts>{''.join(arts)}</Artifacts></ReportData>"
    )


def _text(value: str | None) -> str:
    if value is None:
        return ""
    if "\r" in value or "]]>" in value:
        return escape(value).replace("\r", "&#13;")
    return f"<![CDATA[{value}]]>"


def workbook_sheets(
    artifacts: Iterable[Artifact], case_info: Iterable[tuple[str, str]] = ()
) -> list[tuple[str, list[list[str | int | None]]]]:
    """The Excel report: a case sheet, then one sheet per artifact, named as the artifact and
    cut at Excel's 31-character limit, with the fragment names as the header row."""
    sheets: list[tuple[str, list[list[str | int | None]]]] = [
        ("Case Information", [[k, v] for k, v in case_info])
    ]
    for name, hits in artifacts:
        cols: list[str] = []
        for h in hits:
            for f, _v in h:
                if f not in cols:
                    cols.append(f)
        rows: list[list[str | int | None]] = [list(cols)]
        for h in hits:
            d = dict(h)
            rows.append([d.get(c) for c in cols])
        sheets.append((name[:SHEET_LIMIT], rows))
    return sheets


def write_xml(path: Path, xml: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(xml.encode("utf-8"))
    return path


# ---------------------------------------------------------------- case01


def _ident_and_name(cell: object) -> tuple[str | None, str | None]:
    ps = parse_parties(cell if isinstance(cell, str) else None)
    return (ps[0].identifier, ps[0].name) if ps else (None, None)


def _lines_without_owner_mark(cell: object) -> str | None:
    """A party cell as AXIOM might write it: one party per line, no '(owner)' mark (the phone's
    own accounts come from the accounts artifacts)."""
    ps = parse_parties(cell if isinstance(cell, str) else None)
    return "\n".join(" ".join(x for x in (p.identifier, p.name) if x) for p in ps) or None


_CHAT_ARTIFACT = {
    "WhatsApp": "{p} WhatsApp Messages",
    "Telegram": "{p} Telegram Messages",
    "Instagram": "Instagram Direct Messages",
    "SMS": "{p} SMS",
}


def case01_artifacts(r: Rendered) -> tuple[list[Artifact], list[tuple[str, str]]]:
    """The artifacts and case information of one case01 phone, from its Excel report's rows."""
    sheets = dict(r.sheets)
    when = {m["locator"]: m for m in r.messages} | {c["locator"]: c for c in r.calls}
    plat = "iOS" if "ios" in r.device.os_version.lower() else "Android"
    summary = {row[0]: row[1] for row in sheets["Summary"][1:] if len(row) > 1}

    def ts(loc: str) -> str:
        return mdy(datetime.fromisoformat(when[loc]["ts_utc"].replace("Z", "+00:00")))

    arts: list[Artifact] = [
        (
            f"{plat} Device Information",
            [[("Device Name", str(summary["Device"])), ("OS Version", str(summary["OS version"]))]],
        )
    ]
    for row in sheets["User Accounts"][2:]:
        app, user, name = str(row[1]), str(row[2]), row[3] or None
        id_field = "Phone Number" if app in ("SMS", "WhatsApp") else "User Name"
        arts.append(
            (f"{plat} {app} Accounts Information", [[(id_field, user), ("Display Name", name)]])
        )
    arts.append(
        (
            f"{plat} Contacts",
            [
                [
                    ("Display Name", str(row[1])),
                    ("Phone Number(s)", str(row[2])),
                    ("Source", "contacts2.db"),
                    ("Recovery method", "Parsing"),
                ]
                for row in sheets["Contacts"][2:]
            ],
        )
    )
    col = {c: i for i, c in enumerate(CHAT_COLUMNS)}
    by_app: dict[str, list[Hit]] = {}
    for n, row in enumerate(sheets["Chats"][2:], start=3):
        loc = f"Chats!{n}"
        sender, sender_name = _ident_and_name(row[col["From"]])
        app = str(row[col["Source"]])
        by_app.setdefault(app, []).append(
            [
                ("Chat ID", str(row[col["Chat #"]])),
                ("Conversation Name", row[col["Name"]] or None),
                ("Sender", sender),
                ("Sender Name", sender_name),
                ("Recipient(s)", _lines_without_owner_mark(row[col["To"]])),
                ("Message", row[col["Body"]]),
                ("Message Date/Time" + UTC_MDY, ts(loc)),
                ("Direction", row[col["Direction"]]),
                ("Deleted", row[col["Deleted"]]),
                ("Attachment", row[col["Attachment #1"]] or None),
                ("Tags", row[col["Tag"]] or None),
                ("Source", "msgstore.db"),
                ("Location", f"Table: messages(id: {n})"),
                ("Recovery method", "Parsing"),
                ("Item ID", str(n)),
            ]
        )
    for app, hits in by_app.items():
        arts.append((_CHAT_ARTIFACT[app].format(p=plat), hits))
    cc = {c: i for i, c in enumerate(CALL_COLUMNS)}
    calls: list[Hit] = []
    for n, row in enumerate(sheets["Call Log"][2:], start=3):
        incoming = row[cc["Type"]] in ("Incoming", "Missed")
        partner, partner_name = _ident_and_name(row[cc["From"] if incoming else cc["To"]])
        calls.append(
            [
                ("Partner", partner),
                ("Partner Name", partner_name),
                ("Direction", row[cc["Type"]]),
                ("Call Date/Time" + UTC_MDY, ts(f"Call Log!{n}")),
                ("Call Duration", row[cc["Duration"]]),
                ("Deleted", row[cc["Deleted"]]),
                ("Source", "call_history.db"),
                ("Recovery method", "Parsing"),
            ]
        )
    arts.append((f"{plat} Call Logs", calls))
    arts.append(
        (
            "Chrome Web History",
            [[("URL", "https://example.invalid/synthetic"), ("Title", "SYNTHETIC")]],
        )
    )
    case_info = [
        ("Case number", str(summary["Case number"])),
        ("Evidence number", str(summary["Evidence number"])),
        ("Device", str(summary["Device"])),
        ("Acquisition type", str(summary["Extraction type"])),
        ("AXIOM version", "SYNTHETIC"),
    ]
    return arts, case_info


def write_case01(out: Path) -> list[Path]:
    """item1-axiom.xml, item1-axiom.xlsx, item2-axiom.xml and item2-axiom.xlsx for synthetic
    case01, next to (never over) the Cellebrite reports in `out`."""
    paths = []
    for r in build():
        arts, info = case01_artifacts(r)
        paths.append(write_xml(out / f"{r.device.key}-axiom.xml", report_xml(arts)))
        xlsx = out / f"{r.device.key}-axiom.xlsx"
        write_xlsx(xlsx, workbook_sheets(arts, info))
        paths.append(xlsx)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("eval/out/axiom"))
    a = ap.parse_args(argv)
    for p in write_case01(a.out):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
