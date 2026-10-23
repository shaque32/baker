"""Every date and time a government document states, read by code. No model is involved.

Each paragraph is searched for dates ("March 12, 2026", "Monday, March 9, 2026", "3/25/2026",
"2026-03-12"), ranges ("between March 20 and March 23, 2026", "From March 10 through March 31,
2026", "March 20-23, 2026"), open ranges ("before March 12", "since March 10", "from March 10"
with no end) and a time of day tied to a date ("At 2:31 a.m. on March 5, 2026", "on March 14,
2026 at 10:05 p.m.", "between 8 and 9 p.m. on March 9").

Every rule fails closed: what code cannot read plainly is listed as not read, with the reason,
and never compared.
- A date with no year takes the one year its paragraph states, else the one year the whole
  document states. With none, or several, it is not read.
- Numeric dates never get a month/day order by assumption. 3/25/2026 can only be March 25 and
  25/3/2026 only March 25; 3/5/2026 could be March 5 or May 3, so both readings are listed and
  neither is compared. Two-digit years are not read.
- A time of day is in the zone the document names beside it (UTC, EST, ...). With none, it is
  read in the phone's own zone (core/timeline/check.py), and the screen says so.
- "about 7:58 p.m." is 8 minutes either side, as the signed case01 assumption sheet reads it.
- Dates inside quoted words belong to the quoted message, not to the document's account of
  when something happened, so they are skipped.
- A weekday the document gives beside a date is checked against the calendar.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

ABOUT_MINUTES = 8  # "at about 7:58 p.m." is 7:50 to 8:06 (case01 sheet, C09)

Kind = Literal["moment", "day", "range", "open", "ambiguous", "unread"]

_MONTH_NAMES = (
    ("january", "jan"),
    ("february", "feb"),
    ("march", "mar"),
    ("april", "apr"),
    ("may",),
    ("june", "jun"),
    ("july", "jul"),
    ("august", "aug"),
    ("september", "sept", "sep"),
    ("october", "oct"),
    ("november", "nov"),
    ("december", "dec"),
)
MONTHS = {name: i + 1 for i, names in enumerate(_MONTH_NAMES) for name in names}
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WD_SHORT = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
             "fri": 4, "sat": 5, "sun": 6}  # fmt: skip
WEEKDAYS = {**{w: i for i, w in enumerate(_WEEKDAYS)}, **_WD_SHORT}

_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_WD = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_AMPM = r"(?:a\.?\s?m\.?|p\.?\s?m\.?)(?![a-z])"

# "Monday, March 9, 2026", "March 20-23, 2026", "Mar. 5", "March 12th"
_NAMED = re.compile(
    rf"(?:\b(?P<wd>{_WD})\.?,?\s+)?\b(?P<mon>{_MON})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?![\d:/])(?!\s*{_AMPM})"
    rf"(?:\s*(?:-|–|—)\s*(?P<day2>\d{{1,2}})(?![\d:/])(?!\s*{_AMPM}))?"
    rf"(?:,?\s+(?P<year>\d{{4}})(?!\d))?",
    re.IGNORECASE,
)
_NUMERIC = re.compile(r"(?<![\d/.])(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})(?![\d/])")
_ISO = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_YEAR = re.compile(r"(?<!\d)(19\d\d|20\d\d)(?!\d)")

_ZONES = {
    "utc": "UTC",
    "gmt": "UTC",
    "z": "UTC",
    "est": "Etc/GMT+5",
    "edt": "Etc/GMT+4",
    "cst": "Etc/GMT+6",
    "cdt": "Etc/GMT+5",
    "mst": "Etc/GMT+7",
    "mdt": "Etc/GMT+6",
    "pst": "Etc/GMT+8",
    "pdt": "Etc/GMT+7",
    "et": "America/New_York",
    "eastern": "America/New_York",
    "ct": "America/Chicago",
    "central": "America/Chicago",
    "mt": "America/Denver",
    "mountain": "America/Denver",
    "pt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
}
_ZONE_WORDS = (
    r"UTC|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT|ET|CT|MT|PT|Eastern|Central|Mountain|Pacific"
)
_APPROX = r"(?:about|approximately|approx\.|around|roughly|circa)"
_TIME = re.compile(
    rf"(?:\b(?P<approx>{_APPROX})\s+)?"
    rf"(?:\b(?P<h>\d{{1,2}})(?::(?P<m>[0-5]\d))?\s*(?P<ap>{_AMPM})(?![a-z])"
    rf"|\b(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)(?![\d:])(?!\s*{_AMPM})"
    rf"|\b(?P<word>noon|midnight)\b)"
    rf"(?:\s*\(?\s*(?P<zone>{_ZONE_WORDS})\b\)?(?:\s+time\b)?)?",
    re.IGNORECASE,
)
# 'between 8 and 9 p.m.': the first time takes the second's a.m. or p.m.
_BARE_HOUR = re.compile(r"\b(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\s+(?:and|to|-|–)\s+$")
_QUOTE = re.compile(r"\"([^\"]+)\"|“([^”]+)”")
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"”]?\s+(?=[\"“(]?[A-Z0-9])")

_RANGE_JOIN = re.compile(r"^\s*(?:-|–|—|to|through|thru|until|till)\s*$", re.IGNORECASE)
_AND_JOIN = re.compile(r"^\s*and\s*$", re.IGNORECASE)
_BETWEEN = re.compile(r"\b(?:between|from)\s+$", re.IGNORECASE)
_OPEN = re.compile(
    r"\b(?P<w>on or before|on or after|before|prior to|until|up to|after|since|from)\s+$",
    re.IGNORECASE,
)
_ON_OR_ABOUT = re.compile(r"\bon or about\s+$", re.IGNORECASE)
_TIME_BEFORE_DATE = re.compile(r"^\s*,?\s*(?:on\s+)?$", re.IGNORECASE)
_TIME_AFTER_DATE = re.compile(r"^\s*,?\s*(?:at\s+)?$", re.IGNORECASE)


@dataclass(frozen=True)
class Quote:
    """Words the document puts in quotation marks. text has line breaks folded to spaces,
    because a PDF wraps lines where the quoted message had none."""

    text: str
    start: int  # span in the paragraph, quotation marks excluded
    end: int


@dataclass(frozen=True)
class StatedTime:
    id: str  # 'st:<paragraph id>#<n>', n counting from 1 in reading order
    paragraph_id: str
    page: int
    para_no: int
    para_label: str  # paragraph number as printed, else its position
    raw: str  # verbatim slice of the paragraph text
    start_i: int  # span of raw in the paragraph
    end_i: int
    sentence: str  # verbatim slice: the sentence raw sits in
    sentence_start: int
    kind: Kind
    start: datetime | None = None  # wall clock, inclusive (None for an open start)
    end: datetime | None = None  # wall clock, exclusive (None for an open end)
    approx: bool = False  # "about 7:58 p.m."
    on_or_about: bool = False  # "on or about March 12": compared as that day, noted
    zone_words: str | None = None  # the zone as the document wrote it beside the time
    zone: str | None = None  # IANA name for zone_words; None = read in the phone's zone
    weekday_note: str | None = None
    weekday_ok: bool | None = None  # None when the document gave no weekday
    readings: tuple[date, ...] = ()  # both readings of an ambiguous numeric date
    note: str = ""  # why a statement was not read or not compared

    @property
    def text(self) -> str:
        return " ".join(self.raw.split())

    @property
    def compared(self) -> bool:
        return self.kind in ("moment", "day", "range", "open")

    @property
    def location(self) -> str:
        return f"page {self.page}, ¶{self.para_label}"


# ---------------------------------------------------------------- pieces


@dataclass
class _Date:
    s: int
    e: int
    month: int | None = None
    day: int | None = None
    year: int | None = None
    day2: int | None = None  # "March 20-23"
    weekday: str | None = None
    readings: tuple[date, ...] = ()
    problem: str = ""


@dataclass
class _Time:
    s: int
    e: int
    at: time
    approx: bool
    zone_words: str | None
    end_at: time | None = None  # "between 8 and 9 p.m."


def quotes(text: str) -> list[Quote]:
    out = []
    for m in _QUOTE.finditer(text):
        g = 1 if m.group(1) is not None else 2
        words = " ".join(m.group(g).split())
        if words:
            out.append(Quote(words, m.start(g), m.end(g)))
    return out


_NO_END = re.compile(
    r"(?:\b[ap]\.\s?m\.|\b(?:Mr|Mrs|Ms|Dr|No|St|Jr|Sr|Inc|Co|Ave|approx)\.|\b[A-Z]\.)[\"”]?\s*$",
    re.IGNORECASE,
)


def sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans. A full stop after 'a.m.', a title or an initial ("R. Calder") does not
    end a sentence; a stray split only narrows what a quote is tied to."""
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        if _NO_END.search(text[max(start, m.start() - 8) : m.start() + 1]):
            continue
        spans.append((start, m.start() + len(m.group(0).rstrip())))
        start = m.end()
    spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _inside(i: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= i < e for s, e in spans)


def _named_dates(text: str, quoted: list[tuple[int, int]]) -> list[_Date]:
    out = []
    for m in _NAMED.finditer(text):
        if _inside(m.start("mon"), quoted):
            continue
        out.append(
            _Date(
                s=m.start(),
                e=m.end(),
                month=MONTHS[m.group("mon").lower()],
                day=int(m.group("day")),
                year=int(m.group("year")) if m.group("year") else None,
                day2=int(m.group("day2")) if m.group("day2") else None,
                weekday=m.group("wd"),
            )
        )
    return out


def _numeric_dates(text: str, quoted: list[tuple[int, int]]) -> list[_Date]:
    out = []
    for m in _ISO.finditer(text):
        if _inside(m.start(), quoted):
            continue
        y, mo, d = (int(x) for x in m.groups())
        out.append(_Date(m.start(), m.end(), mo, d, y))
    for m in _NUMERIC.finditer(text):
        if _inside(m.start(), quoted):
            continue
        a, b, ys = int(m.group(1)), int(m.group(2)), m.group(3)
        if len(ys) == 2:
            out.append(_Date(m.start(), m.end(), problem="two-digit year; not read"))
            continue
        y = int(ys)
        md = _try_date(y, a, b)  # month/day
        dm = _try_date(y, b, a)  # day/month
        if md and dm and md != dm:
            out.append(
                _Date(
                    m.start(),
                    m.end(),
                    readings=(md, dm),
                    problem="numeric date that reads either way; Mabillon does not pick an order",
                )
            )
        elif (d := md or dm) is not None:
            out.append(_Date(m.start(), m.end(), d.month, d.day, d.year))
        else:
            out.append(_Date(m.start(), m.end(), problem="not a calendar date"))
    return out


def _try_date(y: int, mo: int, d: int) -> date | None:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _hour(h: int, m: int, ap: str) -> time | None:
    if not 1 <= h <= 12:
        return None
    pm = ap.lower().startswith("p")
    return time((h % 12) + (12 if pm else 0), m)


def _times(text: str, quoted: list[tuple[int, int]]) -> list[_Time]:
    out = []
    for m in _TIME.finditer(text):
        if _inside(m.start(), quoted):
            continue
        zone = m.group("zone")
        approx = bool(m.group("approx"))
        if m.group("word"):
            at = time(12, 0) if m.group("word").lower() == "noon" else time(0, 0)
        elif m.group("h24") is not None:
            at = time(int(m.group("h24")), int(m.group("m24")))
        else:
            got = _hour(int(m.group("h")), int(m.group("m") or 0), m.group("ap"))
            if got is None:
                continue
            at = got
        t = _Time(m.start(), m.end(), at, approx, zone)
        # "between 8 and 9 p.m." / "from 8:15 to 8:40 p.m.": a bare first time before this one
        bare = _BARE_HOUR.search(text[max(0, m.start() - 16) : m.start()])
        if bare is not None and m.group("ap"):
            first = _hour(int(bare.group("h")), int(bare.group("m") or 0), m.group("ap"))
            if first is not None and first < at:
                t = _Time(m.start() - len(bare.group(0)), m.end(), first, approx, zone, at)
        elif (
            out
            and out[-1].end_at is None
            and _RANGE_JOIN.match(text[out[-1].e : m.start()].replace("and", "-"))
        ):
            prev = out.pop()
            t = _Time(prev.s, m.end(), prev.at, prev.approx or approx, zone or prev.zone_words, at)
        out.append(t)
    return out


def _years(text: str) -> set[int]:
    return {int(y) for y in _YEAR.findall(text)}


# ---------------------------------------------------------------- reading a paragraph


def read_paragraph(
    paragraph_id: str,
    page: int,
    para_no: int,
    label: str | None,
    text: str,
    doc_years: set[int],
) -> list[StatedTime]:
    """Every stated date or time in one paragraph, in reading order."""
    quoted = [(q.start, q.end) for q in quotes(text)]
    dates = sorted(_named_dates(text, quoted) + _numeric_dates(text, quoted), key=lambda d: d.s)
    dates = _drop_overlaps(dates)
    times = _times(text, quoted)
    para_years = _years(text)
    spans = sentences(text)

    def year_for(d: _Date, partner: _Date | None = None) -> tuple[int | None, str]:
        if d.year is not None:
            return d.year, ""
        if partner is not None and partner.year is not None:
            return partner.year, ""
        for pool in (para_years, doc_years):
            if len(pool) == 1:
                return next(iter(pool)), ""
            if len(pool) > 1:
                return None, "no year beside it, and the paragraph names more than one"
        return None, "no year stated"

    def resolve(d: _Date, partner: _Date | None = None) -> tuple[date | None, str]:
        if d.problem:
            return None, d.problem
        y, why = year_for(d, partner)
        if y is None:
            return None, why
        if d.month is None or d.day is None:
            return None, "not a calendar date"
        got = _try_date(y, d.month, d.day)
        return (got, "") if got else (None, "not a calendar date")

    used_times: set[int] = set()
    items: list[dict] = []
    i = 0
    while i < len(dates):
        d = dates[i]
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        before = text[max(0, d.s - 24) : d.s]
        joined = nxt is not None and (
            _RANGE_JOIN.match(text[d.e : nxt.s])
            or (_AND_JOIN.match(text[d.e : nxt.s]) and _BETWEEN.search(before))
        )
        if joined and nxt is not None:
            lead = _BETWEEN.search(before)
            s = d.s - (len(lead.group(0)) if lead else 0)
            items.append({"kind": "range", "a": d, "b": nxt, "s": s, "e": nxt.e})
            i += 2
            continue
        items.append({"kind": "date", "a": d, "s": d.s, "e": d.e})
        i += 1

    out: list[StatedTime] = []
    for it in items:
        a: _Date = it["a"]
        s, e = it["s"], it["e"]
        fields: dict = {}
        if it["kind"] == "range":
            b: _Date = it["b"]
            d1, why1 = resolve(a, b)
            d2, why2 = resolve(b, a) if b.month is not None or b.problem else (None, "")
            if a.readings or b.readings:
                fields = {"kind": "ambiguous", "readings": a.readings + b.readings,
                          "note": a.problem or b.problem}  # fmt: skip
            elif d1 is None or d2 is None:
                fields = {"kind": "unread", "note": why1 or why2}
            elif d2 < d1:
                fields = {"kind": "unread", "note": "the range ends before it starts"}
            else:
                fields = {
                    "kind": "range",
                    "start": datetime.combine(d1, time(0, 0)),
                    "end": datetime.combine(d2 + timedelta(days=1), time(0, 0)),
                }
        else:
            d1, why = resolve(a)
            if a.readings:
                fields = {"kind": "ambiguous", "readings": a.readings, "note": a.problem}
            elif d1 is None:
                fields = {"kind": "unread", "note": why}
            elif a.day2 is not None:
                d2 = _try_date(d1.year, d1.month, a.day2)
                if d2 is None or d2 < d1:
                    fields = {"kind": "unread", "note": "the range does not read as dates"}
                else:
                    fields = {
                        "kind": "range",
                        "start": datetime.combine(d1, time(0, 0)),
                        "end": datetime.combine(d2 + timedelta(days=1), time(0, 0)),
                    }
            else:
                fields = {
                    "kind": "day",
                    "start": datetime.combine(d1, time(0, 0)),
                    "end": datetime.combine(d1 + timedelta(days=1), time(0, 0)),
                }
                # a time of day tied to this date
                for t in times:
                    if id(t) in used_times:
                        continue
                    if t.e <= a.s and _TIME_BEFORE_DATE.match(text[t.e : a.s]):
                        s = min(s, _lead_at(text, t.s))
                    elif t.s >= a.e and _TIME_AFTER_DATE.match(text[a.e : t.s]):
                        e = max(e, t.e)
                    else:
                        continue
                    used_times.add(id(t))
                    start = datetime.combine(d1, t.at)
                    end = (
                        datetime.combine(d1, t.end_at)
                        if t.end_at is not None
                        else start + timedelta(minutes=1)
                    )
                    if t.approx:
                        start -= timedelta(minutes=ABOUT_MINUTES)
                        end += timedelta(minutes=ABOUT_MINUTES)
                    fields = {
                        "kind": "moment",
                        "start": start,
                        "end": end,
                        "approx": t.approx,
                        "zone_words": t.zone_words,
                        "zone": _ZONES.get((t.zone_words or "").lower()),
                    }
                    s = min(s, t.s)
                    break
            if a.weekday and d1 is not None and not a.readings:
                want = WEEKDAYS[a.weekday.lower().rstrip(".")]
                actual = _WEEKDAYS[d1.weekday()].capitalize()
                ok = d1.weekday() == want
                fields["weekday_ok"] = ok
                fields["weekday_note"] = (
                    f"The document calls {d1:%B} {d1.day}, {d1.year} a {a.weekday}; "
                    + ("the calendar agrees." if ok else f"it was a {actual}.")
                )
        if fields.get("kind") in ("day", "range", "moment"):
            fields, lead = _open_or_about(text, s, fields)
            s -= lead
        out.append(_make(paragraph_id, page, para_no, label, text, spans, s, e, fields))

    # times of day not tied to any date
    for t in times:
        if id(t) in used_times:
            continue
        out.append(
            _make(
                paragraph_id,
                page,
                para_no,
                label,
                text,
                spans,
                t.s,
                t.e,
                {"kind": "unread", "note": "a time of day with no date beside it"},
            )  # fmt: skip
        )
    out.sort(key=lambda x: (x.start_i, x.end_i))
    return [
        StatedTime(**{**x.__dict__, "id": f"st:{paragraph_id}#{n}"})
        for n, x in enumerate(out, start=1)
    ]


def _lead_at(text: str, i: int) -> int:
    m = re.search(r"\bat\s+$", text[max(0, i - 4) : i], re.IGNORECASE)
    return i - len(m.group(0)) if m else i


def _drop_overlaps(dates: list[_Date]) -> list[_Date]:
    out: list[_Date] = []
    for d in dates:
        if out and d.s < out[-1].e:
            continue
        out.append(d)
    return out


def _open_or_about(text: str, s: int, fields: dict) -> tuple[dict, int]:
    """'on or about X' is compared as X and noted; 'before X', 'since X' and the like leave
    one end open. Returns the fields and how many characters of lead-in words to include."""
    before = text[max(0, s - 20) : s]
    about = _ON_OR_ABOUT.search(before)
    if about is not None:
        return {**fields, "on_or_about": True}, len(about.group(0))
    m = _OPEN.search(before)
    if m is None or (m.group("w").lower() == "from" and fields["kind"] == "range"):
        return fields, 0
    w, lead = m.group("w").lower(), len(m.group(0))
    start, end = fields["start"], fields["end"]
    if w in ("before", "prior to"):
        return {**fields, "kind": "open", "start": None, "end": start}, lead
    if w in ("on or before", "until", "up to"):
        return {**fields, "kind": "open", "start": None, "end": end}, lead
    if w == "after":
        return {**fields, "kind": "open", "start": end, "end": None}, lead
    return {**fields, "kind": "open", "start": start, "end": None}, lead  # since, from, on or after


def _make(
    paragraph_id: str,
    page: int,
    para_no: int,
    label: str | None,
    text: str,
    spans: list[tuple[int, int]],
    s: int,
    e: int,
    fields: dict,
) -> StatedTime:
    over = [(a, b) for a, b in spans if a < e and s < b] or [(0, len(text))]
    ss, se = over[0][0], over[-1][1]  # a stated time never straddles two sentences
    return StatedTime(
        id="",
        paragraph_id=paragraph_id,
        page=page,
        para_no=para_no,
        para_label=label or str(para_no),
        raw=text[s:e],
        start_i=s,
        end_i=e,
        sentence=text[ss:se],
        sentence_start=ss,
        **fields,
    )


def read_document(conn: sqlite3.Connection) -> list[StatedTime]:
    """Every stated date and time in every imported government document, in document order.
    OCR paragraphs are read too; their text is not verbatim, and the screen says so."""
    rows = list(
        conn.execute(
            "SELECT p.id, p.govdoc_id, p.page, p.para_no, p.label, p.text FROM govdoc_paragraphs p"
            " ORDER BY p.govdoc_id, p.para_no"
        )
    )
    years_by_doc: dict[str, set[int]] = {}
    for _, doc, _, _, _, text in rows:
        years_by_doc.setdefault(doc, set()).update(_years(text))
    out: list[StatedTime] = []
    for pid, doc, page, para_no, label, text in rows:
        out += read_paragraph(pid, page, para_no, label, text, years_by_doc[doc])
    return out
