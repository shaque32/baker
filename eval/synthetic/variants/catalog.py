"""Every report layout variant, with what a correct import must give back.

A variant either reads the records exactly (compared with the phone in base.py) or its coverage
record says what was not read; `attention` lists the coverage codes that must be reported.
Run them with `python -m eval.synthetic.variants.check`; tests/test_ingest_variants.py runs the
same set. All data is synthetic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

from eval.synthetic.variants import excel as xl
from eval.synthetic.variants import pdf
from eval.synthetic.variants.base import (
    DEVICE_OFFSET,
    PHONE,
    Msg,
    Phone,
    dmy24,
    iso,
    local,
    long_month,
    many,
    month_name,
    us12,
)

MsgRow = tuple[str, str | None, str | None, str]  # body, ts_utc, sender identifier, direction
CallRow = tuple[str | None, str | None, str | None, str, int | None]


def utc_str(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def msgs(
    phone: Phone = PHONE,
    *,
    ts: Callable[[Msg], bool] = lambda m: True,
    body: Callable[[Msg], str] = lambda m: m.body,
    only: Callable[[Msg], bool] = lambda m: True,
) -> list[MsgRow]:
    return [
        (
            body(m),
            utc_str(m.utc) if ts(m) else None,
            m.sender.ident,
            "outgoing" if m.outgoing else "incoming",
        )
        for m in phone.messages
        if only(m)
    ]


def calls(phone: Phone = PHONE, *, ts: bool = True, duration: bool = True) -> list[CallRow]:
    out: list[CallRow] = []
    for c in phone.calls:
        frm = c.party.ident if c.direction in ("Incoming", "Missed") else None
        to = c.party.ident if c.direction == "Outgoing" else None
        out.append(
            (
                utc_str(c.utc) if ts else None,
                frm,
                to,
                c.direction.lower(),
                c.duration_s if duration else None,
            )
        )
    return out


@dataclass(frozen=True)
class Expected:
    messages: list[MsgRow] | None = None  # None: not compared row by row
    message_count: int | None = None
    calls: list[CallRow] | None = None
    contacts: int | None = None
    attachments: list[str] | None = None
    status: str = "complete"
    attention: frozenset[str] = frozenset()  # coverage codes that must be reported
    info: frozenset[str] = frozenset()  # informational codes that must be reported
    bodies_reflowed: bool = False  # PDF: compare bodies with whitespace collapsed


@dataclass(frozen=True)
class Built:
    path: Path
    written: dict[str, int] = field(default_factory=dict)  # Excel: data rows per sheet


@dataclass(frozen=True)
class Variant:
    name: str
    what: str
    build: Callable[[Path], Built]
    expect: Expected
    importer_kwargs: dict[str, object] = field(default_factory=dict)

    @property
    def fmt(self) -> str:
        return "pdf" if self.name.startswith("p") else "xlsx"


def _xlsx(name: str, specs: Callable[[], list[xl.SheetSpec]]) -> Callable[[Path], Built]:
    def build(out: Path) -> Built:
        path = out / f"{name}.xlsx"
        return Built(path, xl.write(path, specs()))

    return build


def _pdf(name: str, report: Callable[[], pdf.Report]) -> Callable[[Path], Built]:
    def build(out: Path) -> Built:
        return Built(report().write(out / f"{name}.pdf"))

    return build


BASE = Expected(messages=msgs(), calls=calls(), contacts=4, attachments=["map.jpg"])


# ---------------------------------------------------------------- Excel variants


def x02() -> list[xl.SheetSpec]:
    specs = xl.sheets(
        chats_title="Instant Messages",
        rename={
            "Chat #": "Conversation ID",
            "Name": "Conversation Name",
            "Source": "Application",
            "Participants": "Members",
            "From": "Sender",
            "To": "Recipients",
            "Body": "Message",
            "Timestamp": "Date/Time",
            "Direction": "Message Direction",
            "Deleted": "Record Status",
            "Attachment #1": "Attachments",
        },
        order=[
            "Timestamp",
            "Body",
            "From",
            "To",
            "Direction",
            "Source",
            "Chat #",
            "Name",
            "Participants",
            "Attachment #1",
            "#",
            "Deleted",
            "Location",
        ],  # fmt: skip
        extra={"Location": lambda i, m: None, "Message Status": lambda i, m: "Read"},
        title_rows=[["Instant Messages (7)"], ["Filter: all records"], ["Exported: synthetic"]],
    )
    sms = [m for m in PHONE.messages if m.chat is None]
    specs[4] = xl.table(
        "Text Messages",
        xl.sms_cols(us12),
        sms,
        rename={
            "From": "Sender",
            "To": "Receiver",
            "Body": "Message Body",
            "Timestamp": "Time Stamp",
            "Type": "Message Type",
        },  # fmt: skip
        order=["Body", "Timestamp", "From", "To", "Type", "#", "Deleted"],
    )
    specs[5] = xl.table(
        "Call History",
        xl.call_cols(us12),
        list(PHONE.calls),
        rename={
            "Type": "Call Type",
            "Parties": "Party",
            "Timestamp": "Start Time",
            "Duration": "Call Duration",
            "Source": "Application",
        },  # fmt: skip
        order=["Timestamp", "Duration", "Type", "Parties", "Source", "#", "Deleted"],
    )
    return specs


def _split_date_time(cols: list, dayfirst: bool, header_offset: bool) -> list:
    """Replace 'Timestamp' with separate 'Date' and 'Time' columns."""

    def date(i, r):
        d = local(r.utc, DEVICE_OFFSET)
        return f"{d.day:02d}/{d.month:02d}/{d.year}" if dayfirst else f"{d.month}/{d.day}/{d.year}"

    def time(i, r):
        return local(r.utc, DEVICE_OFFSET).strftime("%H:%M:%S")

    out = []
    for h, f in cols:
        if h == "Timestamp":
            out += [("Date", date), ("Time (UTC-4)" if header_offset else "Time", time)]
        else:
            out.append((h, f))
    return out


def x03() -> list[xl.SheetSpec]:
    specs = xl.sheets(time_zone=None)
    chats = [m for m in PHONE.messages if m.chat is not None]
    sms = [m for m in PHONE.messages if m.chat is None]
    specs[3] = xl.table("Chats", _split_date_time(xl.chat_cols(PHONE, us12), True, True), chats)
    specs[4] = xl.table("SMS Messages", _split_date_time(xl.sms_cols(us12), True, True), sms)
    specs[5] = xl.table(
        "Call Log", _split_date_time(xl.call_cols(us12), True, True), list(PHONE.calls)
    )
    return specs


NAMED_ZONE_KEY = "m09"


def x04() -> list[xl.SheetSpec]:
    styles = [
        lambda u, o: iso(u, o),
        month_name,
        long_month,
        lambda u, o: us12(u, o, "bare"),
        lambda u, o: iso(u, 0),  # the same instant written in UTC with 'Z'
        lambda u, o: us12(u, o, "long"),
    ]
    order = {m.key: k for k, m in enumerate(PHONE.messages)}

    def chat_ts(m: Msg):
        return lambda u, o: styles[order[m.key] % len(styles)](u, o)

    def ts_for(m: Msg, u: datetime, o: int) -> str:
        if m.key == NAMED_ZONE_KEY:
            return us12(u, o, None) + " EDT"
        return chat_ts(m)(u, o)

    specs = xl.sheets(time_zone=None)
    chats = [m for m in PHONE.messages if m.chat is not None]
    sms = [m for m in PHONE.messages if m.chat is None]
    cols = [
        (h, (lambda i, m: ts_for(m, m.utc, DEVICE_OFFSET)) if h == "Timestamp" else f)
        for h, f in xl.chat_cols(PHONE, us12)
    ]
    specs[3] = xl.table("Chats", cols, chats)
    scols = [
        (h, (lambda i, m: ts_for(m, m.utc, DEVICE_OFFSET)) if h == "Timestamp" else f)
        for h, f in xl.sms_cols(us12)
    ]
    specs[4] = xl.table("SMS Messages", scols, sms)
    specs[5] = xl.table("Call Log", xl.call_cols(lambda u, o: month_name(u, o)), list(PHONE.calls))
    return specs


def no_suffix(u: datetime, o: int) -> str:
    return us12(u, o, None)


AMBIGUOUS = PHONE.shifted(timedelta(days=-9))  # every date falls on 4 to 7 March


def x08() -> list[xl.SheetSpec]:
    wa = [m for m in PHONE.messages if m.chat == "g1"]
    tg = [m for m in PHONE.messages if m.chat == "t1"]
    sms = [m for m in PHONE.messages if m.chat is None]
    cols = [c for c in xl.chat_cols(PHONE, us12) if c[0] != "Source"]
    timeline = xl.SheetSpec(
        "Timeline",
        [["#", "Type", "Timestamp", "From", "Body"]]
        + [
            [i, "Chat", us12(m.utc, DEVICE_OFFSET), m.sender.cell(), m.body]
            for i, m in enumerate(PHONE.messages, start=1)
        ],
    )
    locations = xl.SheetSpec(
        "Locations", [["#", "Time", "Latitude", "Longitude"], [1, "3/14/2026 1:00:00 PM", 0.0, 0.0]]
    )
    graph = xl.SheetSpec(
        "Social Graph", [["From", "To", "Weight"], ["+15550100002", "+15550100003", 4]]
    )
    return [
        xl.table("Chats - WhatsApp", cols, wa),
        xl.table("Instant Messages (Telegram)", cols, tg),
        xl.table("SMS Messages", xl.sms_cols(us12), sms),
        timeline,
        locations,
        graph,
    ]


def x09() -> list[xl.SheetSpec]:
    specs = xl.sheets()
    chats = [m for m in PHONE.messages if m.chat is not None]
    specs[3] = xl.table(
        "Chats", xl.chat_cols(PHONE, us12), chats, drop=("Timestamp", "Direction", "Deleted")
    )
    specs[5] = xl.table("Call Log", xl.call_cols(us12), list(PHONE.calls), drop=("Duration",))
    return specs


def _merged_chats(body_merge: bool) -> xl.SheetSpec:
    """Title merged across the sheet, a two-row header with 'Timestamp' over 'Date' and
    'Time', chat columns merged down each chat's rows. With `body_merge`, one message's text
    cell is merged down over the next message's row."""
    heads = ["#", "Chat #", "Name", "Source", "Participants", "From", "To", "Body",
             "Timestamp", None, "Direction", "Attachment #1"]  # fmt: skip
    letters = "ABCDEFGHIJKL"
    rows: list[list[xl.Cell]] = [["Chats (7)"] + [None] * 11, list(heads)]
    rows.append([None] * 8 + ["Date", "Time"] + [None, None])
    merges = ["A1:L1", "I2:J2"] + [
        f"{letters[c]}2:{letters[c]}3" for c, h in enumerate(heads) if h and h != "Timestamp"
    ]
    chats = [m for m in PHONE.messages if m.chat is not None]
    r0 = len(rows) + 1
    for i, m in enumerate(chats, start=1):
        c = PHONE.chat(m.chat)
        first = i == 1 or chats[i - 2].chat != m.chat
        d = local(m.utc, DEVICE_OFFSET)
        h12 = d.hour % 12 or 12
        body: str | None = m.body
        if body_merge and m.key == "m03":
            body = None  # covered by m02's merged text cell
        rows.append(
            [
                i,
                m.chat if first else None,
                c.name if first else None,  # type: ignore[union-attr]
                c.app if first else None,  # type: ignore[union-attr]
                "\n".join(w.cell() for w in c.members) if first else None,  # type: ignore[union-attr]
                m.sender.cell(),
                "\n".join(w.cell() for w in m.to),
                body,
                f"{d.month}/{d.day}/{d.year}",
                f"{h12}:{d.minute:02d}:{d.second:02d} {'AM' if d.hour < 12 else 'PM'}(UTC-4)",
                "Outgoing" if m.outgoing else "Incoming",
                m.attachments[0] if m.attachments else None,
            ]
        )
    # chat columns merged down each chat's run of rows
    start = 0
    for k in range(1, len(chats) + 1):
        if k == len(chats) or chats[k].chat != chats[start].chat:
            if k - start > 1:
                for col in "BCDE":
                    merges.append(f"{col}{r0 + start}:{col}{r0 + k - 1}")
            start = k
    if body_merge:
        r = r0 + [m.key for m in chats].index("m02")
        merges.append(f"H{r}:H{r + 1}")
    return xl.SheetSpec("Chats", rows, header_rows=3, merges=merges)


def x10(body_merge: bool = False) -> list[xl.SheetSpec]:
    specs = xl.sheets()
    specs[3] = _merged_chats(body_merge)
    return specs


UNICODE_BODIES = {
    "m01": "Line one\nLine two",
    "m02": "  padded on both sides  ",
    "m03": "tab\tseparated",
    "m05": "Привет, посылка пришла?",
    "m06": "CRLF line\r\nsecond line",
    "m07": "ok 👍",
}
UNICODE = replace(
    PHONE,
    messages=tuple(replace(m, body=UNICODE_BODIES.get(m.key, m.body)) for m in PHONE.messages),
)


def x11() -> list[xl.SheetSpec]:
    """Excel writes a carriage return as _x000D_, never as a raw CR: an XML reader turns a raw
    CR into LF, so writing one would make the file depend on which XML writer openpyxl uses."""
    excel = replace(
        UNICODE,
        messages=tuple(replace(m, body=m.body.replace("\r", "_x000D_")) for m in UNICODE.messages),
    )
    return xl.sheets(excel)


ATTACHMENTS_ONLY = replace(
    PHONE,
    messages=tuple(replace(m, body="") if m.key in ("m04", "m06") else m for m in PHONE.messages),
)


def x12() -> list[xl.SheetSpec]:
    specs = xl.sheets(ATTACHMENTS_ONLY)
    chats = [m for m in ATTACHMENTS_ONLY.messages if m.chat is not None]
    extra = {
        "Attachment #2": lambda i, m: "route.png" if m.key == "m04" else None,
        "Attachments": lambda i, m: "voice_note.opus\nimage2.jpg" if m.key == "m06" else None,
    }
    specs[3] = xl.table("Chats", xl.chat_cols(ATTACHMENTS_ONLY, us12), chats, extra=extra)
    return specs


JUNK_TIMES = {"m03": "N/A", "m05": 46095.4}


def x13() -> list[xl.SheetSpec]:
    specs = xl.sheets()
    chats = [m for m in PHONE.messages if m.chat is not None]
    cols = [
        (h, (lambda i, m: JUNK_TIMES.get(m.key, us12(m.utc, DEVICE_OFFSET))))
        if h == "Timestamp"
        else (h, f)
        for h, f in xl.chat_cols(PHONE, us12)
    ]
    sheet = xl.table("Chats", cols, chats)
    header = sheet.rows[1]
    data = sheet.rows[2:]
    width = len(header)
    sheet.rows = [
        sheet.rows[0],
        header,
        *data[:3],
        [None] * width,
        list(header),  # header repeated mid-sheet
        *data[3:],
        [99] + [None] * (width - 1),  # a row number and nothing else
        ["Total: 7 records"] + [None] * (width - 1),
    ]
    specs[3] = sheet
    return specs


def x14() -> list[xl.SheetSpec]:
    specs = xl.sheets()
    chats = [m for m in PHONE.messages if m.chat is not None]
    german = [
        ("Nr.", lambda i, m: i),
        ("Absender", lambda i, m: m.sender.cell()),
        ("Empfänger", lambda i, m: "\n".join(w.cell() for w in m.to)),
        ("Nachricht", lambda i, m: m.body),
        ("Zeitstempel", lambda i, m: us12(m.utc, DEVICE_OFFSET)),
    ]
    specs[3] = xl.table("Chats", german, chats)
    specs[5] = xl.SheetSpec(
        "Call Log",
        [["Call Log"], ["#", "Time", "Name", "Latitude", "Longitude"]]
        + [[1, "3/14/2026 1:00:00 PM(UTC-4)", "Trailhead", 0.0, 0.0]],
        header_rows=2,
    )
    return specs


def x15() -> list[xl.SheetSpec]:
    specs = xl.sheets()
    chats = [m for m in PHONE.messages if m.chat is not None]
    extra = {
        "Timestamp ": lambda i, m: us12(m.utc + timedelta(minutes=5), DEVICE_OFFSET),
        "Identifier": lambda i, m: f"chat-{m.chat}",
    }
    specs[3] = xl.table("Chats", xl.chat_cols(PHONE, us12), chats, extra=extra)
    return specs


LONG_BODY = ("A long synthetic message. " * 1300)[:32767]
CELL_LIMIT = replace(
    PHONE,
    messages=tuple(replace(m, body=LONG_BODY) if m.key == "m01" else m for m in PHONE.messages),
)

LARGE_N = 20000


def x18() -> list[xl.SheetSpec]:
    specs = xl.sheets()
    specs[3].hidden = True
    return specs


# ---------------------------------------------------------------- PDF variants


def _pdf_rows(cols: list, records: list) -> list[list[object]]:
    return [[h for h, _f in cols]] + [
        [f(i, r) for _h, f in cols] for i, r in enumerate(records, start=1)
    ]


def _pdf_chat_cols(phone: Phone, ts=us12) -> list:
    keep = ("#", "Chat #", "Source", "From", "To", "Body", "Timestamp", "Direction")
    return [c for c in xl.chat_cols(phone, ts) if c[0] in keep]


CHAT_WIDTHS = [20, 34, 52, 92, 92, 110, 96, 48]
SMS_WIDTHS = [20, 100, 100, 130, 110, 50]
CALL_WIDTHS = [20, 60, 60, 110, 140, 60]


def _pdf_sms_cols(ts=us12) -> list:
    return [c for c in xl.sms_cols(ts) if c[0] != "Deleted"]


def _pdf_call_cols(ts=us12) -> list:
    return [c for c in xl.call_cols(ts) if c[0] != "Deleted"]


def _pdf_summary(r: pdf.Report) -> pdf.Report:
    return (
        r.title("Extraction Report")
        .line("Extraction type: Advanced Logical")
        .line("Device: SyntheticPhone V2")
        .line("UFED Physical Analyzer version: 7.70.0.1")
        .line("Time zone: UTC-4")
    )


def _contacts_table() -> pdf.TableBlock:
    rows: list[list[object]] = [["#", "Name", "Entries"]] + [
        [i, c.name, "\n".join(c.entries)] for i, c in enumerate(PHONE.contacts, start=1)
    ]
    return pdf.TableBlock(rows, [30, 120, 240], wrap=(2,))


def p01() -> pdf.Report:
    chats = [m for m in PHONE.messages if m.chat is not None]
    sms = [m for m in PHONE.messages if m.chat is None]
    return (
        _pdf_summary(pdf.Report())
        .heading("Chats (7)")
        .table(
            pdf.TableBlock(_pdf_rows(_pdf_chat_cols(PHONE), chats), CHAT_WIDTHS, wrap=(3, 4, 5, 6))
        )  # fmt: skip
        .heading("SMS Messages (2)")
        .table(pdf.TableBlock(_pdf_rows(_pdf_sms_cols(), sms), SMS_WIDTHS, wrap=(1, 2, 3, 4)))
        .heading("Call Log (4)")
        .table(
            pdf.TableBlock(_pdf_rows(_pdf_call_cols(), list(PHONE.calls)), CALL_WIDTHS, wrap=(3, 4))
        )  # fmt: skip
        .heading("Contacts (3)")
        .table(_contacts_table())
    )


def p02() -> pdf.Report:
    wa = [m for m in PHONE.messages if m.chat == "g1"]
    tg = [m for m in PHONE.messages if m.chat == "t1"]
    sms = [m for m in PHONE.messages if m.chat is None]
    rename = {"From": "Sender", "To": "Recipients", "Body": "Message", "Timestamp": "Date/Time"}
    order = ["Timestamp", "From", "To", "Body", "Direction", "Chat #", "#"]

    def chat_cols():
        cols = [c for c in _pdf_chat_cols(PHONE, dmy24) if c[0] != "Source"]
        cols.sort(key=lambda c: order.index(c[0]))
        return [(rename.get(h, h), f) for h, f in cols]

    widths = [110, 92, 92, 110, 48, 34, 20]
    calls_cols = [
        (h if h != "Type" else "Call Type", f) for h, f in _pdf_call_cols(dmy24) if h != "Source"
    ]
    return (
        _pdf_summary(pdf.Report())
        .heading("WhatsApp Chats (4)")
        .table(pdf.TableBlock(_pdf_rows(chat_cols(), wa), widths, wrap=(0, 1, 2, 3)))
        .heading("Telegram Chats (3)")
        .table(pdf.TableBlock(_pdf_rows(chat_cols(), tg), widths, wrap=(0, 1, 2, 3)))
        .heading("Text Messages (2)")
        .table(
            pdf.TableBlock(_pdf_rows(_pdf_sms_cols(dmy24), sms), SMS_WIDTHS, wrap=(1, 2, 3, 4))
        )  # fmt: skip
        .heading("Call History (4)")
        .table(
            pdf.TableBlock(
                _pdf_rows(calls_cols, list(PHONE.calls)), [20, 60, 110, 140, 60], wrap=(2, 3)
            )
        )  # fmt: skip
    )


PAGED = many(60, body_words=14)


PAGED_SMS = replace(
    PHONE,
    messages=tuple(
        replace([m for m in PHONE.messages if m.chat is None][k % 2], key=f"s{k}")
        for k in range(40)
    ),
)


def p03() -> pdf.Report:
    return (
        _pdf_summary(pdf.Report())
        .heading("Chats (60)")
        .subheading("Chat: Weekend plan (WhatsApp)")
        .table(
            pdf.TableBlock(
                _pdf_rows(_pdf_chat_cols(PAGED), list(PAGED.messages)),
                CHAT_WIDTHS,
                wrap=(3, 4, 5, 6),
            )
        )  # fmt: skip
        .heading("SMS Messages (40)")
        .table(
            pdf.TableBlock(
                _pdf_rows(_pdf_sms_cols(), list(PAGED_SMS.messages)),
                SMS_WIDTHS,
                wrap=(1, 2, 3, 4),
                repeat_header=True,
            )
        )  # fmt: skip
    )


def p04() -> pdf.Report:
    chats = [m for m in PHONE.messages if m.chat is not None]
    sms = [m for m in PHONE.messages if m.chat is None]
    return (
        _pdf_summary(pdf.Report())
        .heading("Chats (7)")
        .table(
            pdf.TableBlock(
                _pdf_rows(_pdf_chat_cols(PHONE), chats), CHAT_WIDTHS, wrap=(3, 4, 5, 6), grid=False
            )
        )  # fmt: skip
        .heading("SMS Messages (2)")
        .table(pdf.TableBlock(_pdf_rows(_pdf_sms_cols(), sms), SMS_WIDTHS, wrap=(1, 2, 3, 4)))
    )


def p05() -> pdf.Report:
    chats = [m for m in PHONE.messages if m.chat is not None]
    sms = [m for m in PHONE.messages if m.chat is None]
    posts = [
        ["#", "Author", "Body", "Timestamp"],
        [1, "@kai_m Kai", "Trail day!", "3/14/2026 9:00:00 AM(UTC-4)"],
    ]
    first = PHONE.messages[0]
    timeline = [
        ["#", "Type", "Body", "Timestamp"],
        [1, "Chat", first.body, us12(first.utc, DEVICE_OFFSET)],
    ]
    return (
        _pdf_summary(pdf.Report())
        .table(pdf.TableBlock(_pdf_rows(_pdf_sms_cols(), sms), SMS_WIDTHS, wrap=(1, 2, 3, 4)))
        .heading("Chats (7)")
        .table(
            pdf.TableBlock(_pdf_rows(_pdf_chat_cols(PHONE), chats), CHAT_WIDTHS, wrap=(3, 4, 5, 6))
        )  # fmt: skip
        .heading("Social Media Posts (1)")
        .table(pdf.TableBlock(posts, [20, 100, 200, 140], wrap=(2, 3)))
        .heading("Timeline (1)")
        .table(pdf.TableBlock(timeline, [20, 60, 200, 140], wrap=(2, 3)))
    )


# ---------------------------------------------------------------- the catalog


def _v(name: str, what: str, build, expect: Expected, **kw: object) -> Variant:
    return Variant(name, what, build, expect, kw)


A = frozenset
VARIANTS: tuple[Variant, ...] = (
    _v("x01_baseline", "the case01 layout", _xlsx("x01", xl.sheets), BASE),
    _v(
        "x02_renamed_reordered",
        "other sheet and column names, other column order, three rows above the header, "
        "columns Baker does not read",
        _xlsx("x02", x02),
        replace(BASE, info=A({"unknown_columns"})),
    ),
    _v(
        "x03_split_date_time_dayfirst",
        "separate Date and Time columns, day-first dates, 24-hour times, the offset in the "
        "column name, no report time zone",
        _xlsx("x03", x03),
        replace(BASE, info=A({"header_offset"})),
    ),
    _v(
        "x04_offset_styles",
        "ISO with offset and Z, month names, weekday prefix, bare -0400, (UTC-04:00), and one "
        "time with a zone name",
        _xlsx("x04", x04),
        replace(
            BASE,
            messages=msgs(ts=lambda m: m.key != NAMED_ZONE_KEY),
            status="needs_review",
            attention=A({"times_named_zone"}),
        ),
    ),
    _v(
        "x05_report_offset",
        "times without offsets; the summary gives a fixed UTC-4",
        _xlsx("x05", lambda: xl.sheets(ts=no_suffix, time_zone="UTC-4")),
        replace(BASE, info=A({"times_offset_from_report_settings"})),
    ),
    _v(
        "x06_named_report_zone",
        "times without offsets; the summary names a zone, which is never applied",
        _xlsx(
            "x06",
            lambda: xl.sheets(ts=no_suffix, time_zone="(UTC-05:00) Eastern Time (US & Canada)"),
        ),
        replace(
            BASE,
            messages=msgs(ts=lambda m: False),
            calls=calls(ts=False),
            status="needs_review",
            attention=A({"times_no_offset"}),
            info=A({"report_time_zone_not_fixed"}),
        ),
    ),
    _v(
        "x07_ambiguous_dates",
        "every date has day and month at 12 or below (4 to 7 March), nothing decides the order",
        _xlsx("x07", lambda: xl.sheets(AMBIGUOUS)),
        replace(
            BASE,
            messages=msgs(AMBIGUOUS, ts=lambda m: False),
            calls=calls(AMBIGUOUS, ts=False),
            status="needs_review",
            attention=A({"times_ambiguous_day_month"}),
        ),
    ),
    _v(
        "x07b_ambiguous_dates_stated",
        "the same dates, day first, with the order stated at import",
        _xlsx("x07b", lambda: xl.sheets(AMBIGUOUS, ts=dmy24)),
        replace(
            BASE,
            messages=msgs(AMBIGUOUS),
            calls=calls(AMBIGUOUS),
            info=A({"date_order_stated"}),
        ),
        date_order="dmy",
    ),
    _v(
        "x08_sheets_extra_and_missing",
        "no summary, contacts, calls or accounts; one sheet per app named in the title; "
        "Timeline, Locations and an unknown sheet",
        _xlsx("x08", x08),
        Expected(
            messages=msgs(),
            calls=[],
            contacts=0,
            attachments=["map.jpg"],
            status="needs_review",
            attention=A({"not_imported"}),
            info=A(
                {"category_not_imported", "categories_not_found", "no_summary", "app_from_title"}
            ),  # fmt: skip
        ),
    ),
    _v(
        "x09_missing_columns",
        "chats without Timestamp, Direction and Deleted; calls without Duration",
        _xlsx("x09", x09),
        replace(
            BASE,
            messages=msgs(ts=lambda m: m.chat is None),
            calls=calls(duration=False),
            status="needs_review",
            attention=A({"missing_time"}),
        ),
    ),
    _v(
        "x10_merged_cells",
        "title merged across, a two-row header with Timestamp over Date and Time, chat "
        "columns merged down each chat",
        _xlsx("x10", x10),
        replace(BASE, info=A({"merged_cells_filled", "header_note"})),
    ),
    _v(
        "x10b_merged_body",
        "one message's text cell merged down over the next message",
        _xlsx("x10b", lambda: x10(body_merge=True)),
        replace(
            BASE,
            messages=msgs(body=lambda m: "" if m.key == "m03" else m.body),
            status="needs_review",
            attention=A({"merged_cells_not_filled"}),
        ),
    ),
    _v(
        "x11_multiline_unicode",
        "line breaks (LF and CRLF), tabs, leading and trailing spaces, Cyrillic and emoji; "
        "the CR stored as Excel stores it",
        _xlsx("x11", x11),
        replace(BASE, messages=msgs(UNICODE), info=A({"cells_with_excel_escapes_decoded"})),
    ),
    _v(
        "x12_attachments_only",
        "messages with no text, attachments in Attachment #1, #2 and a multi-line Attachments",
        _xlsx("x12", x12),
        replace(
            BASE,
            messages=msgs(ATTACHMENTS_ONLY),
            attachments=["map.jpg", "route.png", "voice_note.opus", "image2.jpg"],
        ),
    ),
    _v(
        "x13_junk_rows",
        "a blank row, the header repeated mid-sheet, a row number alone, a footer, 'N/A' and "
        "a bare number as times",
        _xlsx("x13", x13),
        replace(
            BASE,
            messages=msgs(ts=lambda m: m.key not in JUNK_TIMES),
            status="needs_review",
            attention=A(
                {"rows_skipped_no_values_in_known_columns", "times_unparsed", "times_numeric"}
            ),  # fmt: skip
        ),
    ),
    _v(
        "x14_unreadable_sheets",
        "a Chats sheet with German column names; a Call Log sheet holding locations",
        _xlsx("x14", x14),
        replace(
            BASE,
            messages=msgs(only=lambda m: m.chat is None),
            calls=[],
            attachments=[],
            status="needs_review",
            attention=A({"not_imported"}),
        ),
    ),
    _v(
        "x15_duplicate_columns",
        "a second Timestamp column (a later time) and an Identifier column beside Chat #",
        _xlsx("x15", x15),
        replace(BASE, status="needs_review", attention=A({"duplicate_column"})),
    ),
    _v(
        "x16_excel_cell_limit",
        "a message text of exactly 32,767 characters, Excel's cell limit",
        _xlsx("x16", lambda: xl.sheets(CELL_LIMIT)),
        replace(
            BASE,
            messages=msgs(CELL_LIMIT),
            status="needs_review",
            attention=A({"body_at_excel_cell_limit"}),
        ),
    ),
    _v(
        "x17_large",
        f"{LARGE_N:,} messages in one chat",
        _xlsx("x17", lambda: xl.sheets(many(LARGE_N))),
        replace(BASE, messages=None, message_count=LARGE_N, attachments=[]),
    ),
    _v(
        "x18_hidden_sheet",
        "the Chats sheet is hidden in the workbook",
        _xlsx("x18", x18),
        replace(BASE, info=A({"hidden_sheets"})),
    ),
    _v(
        "p01_baseline",
        "PDF: section headings over ruled tables, wrapped cells",
        _pdf("p01", p01),
        replace(BASE, attachments=[], bodies_reflowed=True),
    ),
    _v(
        "p02_per_app_dayfirst",
        "PDF: one section per app, other column names and order, day-first 24-hour times",
        _pdf("p02", p02),
        replace(
            BASE, contacts=0, attachments=[], bodies_reflowed=True, info=A({"app_from_title"})
        ),  # fmt: skip
    ),
    _v(
        "p03_page_breaks",
        "PDF: a 60-row chat table running over pages without its header, a sub-heading, and "
        "an SMS table that repeats its header on each page",
        _pdf("p03", p03),
        Expected(
            messages=msgs(PAGED) + msgs(PAGED_SMS),
            calls=[],
            contacts=0,
            attachments=[],
            bodies_reflowed=True,
        ),
    ),
    _v(
        "p04_unruled_section",
        "PDF: the chats table drawn without ruling lines",
        _pdf("p04", p04),
        Expected(
            messages=msgs(only=lambda m: m.chat is None),
            calls=[],
            contacts=0,
            attachments=[],
            status="needs_review",
            attention=A({"not_imported"}),
            bodies_reflowed=True,
        ),
    ),
    _v(
        "p05_unknown_sections",
        "PDF: a table before any heading, a 'Social Media Posts' section and a Timeline",
        _pdf("p05", p05),
        Expected(
            messages=msgs(),
            calls=[],
            contacts=0,
            attachments=[],
            status="needs_review",
            attention=A({"not_imported"}),
            info=A({"category_not_imported", "pdf_tables_kind_from_columns"}),
            bodies_reflowed=True,
        ),
    ),
)


def by_name(name: str) -> Variant:
    return next(v for v in VARIANTS if v.name == name)
