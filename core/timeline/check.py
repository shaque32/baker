"""The Timeline check: each time the government document states, beside the phone records'
own timestamps. Derived by code; it never sets or changes a verdict.

A stated time is tied to records only by what the document's own sentence names, found by code:
- quoted words (two or more words, not a contact, account or thread name), found verbatim and
  word-aligned in a message body (line breaks in the document are read as spaces);
- a phone number in a sentence about a call, matched to calls with that number (last ten
  digits).
Each quote or number goes with the stated time nearest to it in the same sentence. When the
sentence puts the record before or after the stated time ("after that call PETROV sent ..."),
the check tests that order instead of closeness.

Comparison. A stated time without a zone is read in the record's phone's own zone (the
importer's devices.timezone), never in the offset a report printed. A record inside the stated
time, or within the case's tolerance of it, matches; otherwise the difference is shown. Where the
report printed a different offset than the phone's zone, the check also says whether the stated
time agrees with the printed clock instead: that is how a report's display setting turns into a
wrong time in a government document.

A statement with no tied record shows the records the phones hold around it. Nothing here
says a record is or is not the one the document means; the expert decides that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from core.audit.quotes import find_quote
from core.identity.aliases import stored as stored_aliases
from core.timeline.records import CaseRecords, Record, zone
from core.timeline.settings import Settings
from core.timeline.stated import StatedTime, quotes

MAX_SHOWN = 4  # records shown per quote or number, nearest first
MAX_NEARBY = 6

Relation = Literal["at", "after", "before", "sequence"]
Status = Literal["inside", "within", "differs", "no_time", "no_zone"]
RowStatus = Literal["differs", "order", "weekday", "matches", "not_tied", "not_compared"]

_CALL_WORDS = re.compile(r"\b(?:call|calls|called|calling|phoned|dialed|dialled|rang)\b", re.I)
_NUMBER = re.compile(r"(?<![\w])\+?\d[\d ().\-]{7,}\d(?![\w])")
_AFTER = re.compile(r"\b(?:after|afterwards?|later|then|following|subsequently)\b", re.I)
_BEFORE = re.compile(r"\b(?:before|earlier|prior|previously)\b", re.I)


@dataclass(frozen=True)
class Compared:
    record: Record
    status: Status
    delta_s: float | None  # signed: negative = before the stated time; 0 = inside
    zone: str | None  # the zone the stated time was read in for this record
    printed_note: str | None = None
    order_conflict: bool = False


@dataclass(frozen=True)
class Link:
    how: Literal["quote", "number"]
    words: str  # the quoted words, or the number as the document wrote it
    relation: Relation
    shown: tuple[Compared, ...]  # nearest first
    total: int  # records found

    @property
    def ok(self) -> bool:
        return any(c.status in ("inside", "within") for c in self.shown)


@dataclass(frozen=True)
class TimelineRow:
    stated: StatedTime
    status: RowStatus
    summary: str  # one plain sentence in the tool's own words
    zone_label: str  # how the stated time was read
    start_utc: datetime | None  # for ordering; None when not compared
    links: tuple[Link, ...] = ()
    nearby: tuple[Compared, ...] = ()  # moments with no tied record: records around it
    nearby_total: int = 0
    counts: tuple[tuple[str, str, int], ...] = ()  # days and ranges: (phone, app, records)
    notes: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------- arithmetic


def fmt_delta(seconds: float) -> str:
    s = int(round(abs(seconds)))
    if s < 60:
        return f"{s} s"
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = [f"{d} day{'s' if d != 1 else ''}" if d else "", f"{h} h" if h else "",
             f"{m} min" if m and not d else ""]  # fmt: skip
    return " ".join(p for p in parts if p) or "under a minute"


def window_utc(st: StatedTime, tz: str) -> tuple[datetime | None, datetime | None]:
    """The stated wall-clock range [start, end) in tz, as UTC. An open side is None."""
    z = zone(tz)
    if z is None:
        raise ValueError(f"unknown time zone {tz!r}")
    conv = [None if t is None else t.replace(tzinfo=z).astimezone(UTC) for t in (st.start, st.end)]
    return conv[0], conv[1]


def _distance(t: datetime, start: datetime | None, end: datetime | None) -> float:
    """Signed seconds from the range [start, end): 0 inside, negative before, positive after."""
    if start is not None and t < start:
        return -(start - t).total_seconds()
    if end is not None and t >= end:
        return (t - end).total_seconds()  # end is exclusive
    return 0.0


def _naive_distance(t: datetime, st: StatedTime) -> float:
    if st.start is not None and t < st.start:
        return -(st.start - t).total_seconds()
    if st.end is not None and t >= st.end:
        return (t - st.end).total_seconds()
    return 0.0


def compare(st: StatedTime, rec: Record, tol_s: float, relation: Relation = "at") -> Compared:
    tz = st.zone or rec.tz
    if rec.ts_utc is None:
        return Compared(rec, "no_time", None, tz)
    if tz is None or zone(tz) is None:
        return Compared(rec, "no_zone", None, None)
    start, end = window_utc(st, tz)
    d = _distance(rec.ts_utc, start, end)
    status: Status = "inside" if d == 0 else "within" if abs(d) <= tol_s else "differs"
    note = None
    loc = rec.local()
    if st.zone is None and rec.offset_min is not None and loc is not None:
        own = loc.utcoffset()
        printed = timedelta(minutes=rec.offset_min)
        if own is not None and own != printed:
            wall = (rec.ts_utc + printed).replace(tzinfo=None)
            pd = _naive_distance(wall, st)
            off = _offset_str(rec.offset_min)
            if status == "differs" and abs(pd) <= tol_s:
                note = (
                    f"The stated time agrees with the clock the report printed ({rec.ts_raw}, "
                    f"UTC{off}), not with the phone's own zone ({rec.tz})."
                )
            elif status != "differs" and abs(pd) > tol_s:
                note = (
                    f"The report printed {rec.ts_raw} (UTC{off}); in the phone's own zone "
                    f"({rec.tz}) it is {rec.when()}."
                )
    conflict = False
    if relation == "after":
        conflict = start is not None and rec.ts_utc < start - timedelta(seconds=tol_s)
    elif relation == "before":
        conflict = end is not None and rec.ts_utc >= end + timedelta(seconds=tol_s)
    return Compared(rec, status, d, tz, note, conflict)


def _offset_str(minutes: int) -> str:
    sign = "-" if minutes < 0 else "+"
    h, m = divmod(abs(minutes), 60)
    return f"{sign}{h:02d}:{m:02d}"


# ---------------------------------------------------------------- tying records to a statement


def _names(data: CaseRecords) -> set[str]:
    """Names a quote may just be (a contact, an account's display name, a thread title, a
    person or another name the expert gave them)."""
    out: set[str] = set()
    for sql in (
        "SELECT name FROM contacts WHERE name IS NOT NULL",
        "SELECT display_name FROM accounts WHERE display_name IS NOT NULL",
        "SELECT identifier FROM accounts",
        "SELECT title FROM threads WHERE title IS NOT NULL",
        "SELECT name FROM persons",
    ):
        out |= {" ".join(r[0].split()).casefold() for r in data.conn.execute(sql) if r[0]}
    out |= {" ".join(a.alias.split()).casefold() for a in stored_aliases(data.conn)}  # #181
    return out


def _relation(sentence: str, a: int, b: int, quote_after: bool) -> Relation:
    between = sentence[min(a, b) : max(a, b)]
    after, before = bool(_AFTER.search(between)), bool(_BEFORE.search(between))
    if after == before:
        return "sequence" if after else "at"
    # "At 10:05 p.m. ... after that call PETROV sent 'x'": the record comes after the time.
    return "after" if after == quote_after else "before"


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _nearest(stated: list[StatedTime], pos: int) -> StatedTime | None:
    best = None
    for st in stated:
        d = min(abs(pos - st.start_i), abs(pos - st.end_i))
        if best is None or d < best[0]:
            best = (d, st)
    return None if best is None else best[1]


def _rank(found: list[Record], st: StatedTime, tol_s: float, rel: Relation) -> list[Compared]:
    comps = [compare(st, r, tol_s, rel) for r in found]
    return sorted(
        comps,
        key=lambda c: (c.delta_s is None, abs(c.delta_s or 0), c.record.source_id, c.record.id),
    )


def tie_records(
    data: CaseRecords, stated: list[StatedTime], texts: dict[str, str], tol_s: float
) -> dict[str, list[Link]]:
    """Links for each stated time id, from the quotes and phone numbers of its sentence."""
    names = _names(data)
    links: dict[str, list[Link]] = {}
    by_sentence: dict[tuple[str, int], list[StatedTime]] = {}
    for st in stated:
        if st.compared:
            by_sentence.setdefault((st.paragraph_id, st.sentence_start), []).append(st)
    messages = [r for r in data.records if r.kind == "message"]
    calls = [r for r in data.records if r.kind == "call"]
    for (pid, s0), group in by_sentence.items():
        text = texts[pid]
        sentence = group[0].sentence
        s1 = s0 + len(sentence)
        for q in quotes(text):
            if not (s0 <= q.start < s1):
                continue
            words = q.text
            if len(words.split()) < 2 or words.casefold() in names:
                continue
            st = _nearest(group, q.start)
            if st is None:
                continue
            found = [r for r in messages if words in r.what and find_quote(words, r.what)]
            rel = _relation(text, st.end_i, q.start, q.start > st.start_i)
            ranked = _rank(found, st, tol_s, rel)
            links.setdefault(st.id, []).append(
                Link("quote", words, rel, tuple(ranked[:MAX_SHOWN]), len(found))
            )
        if not _CALL_WORDS.search(sentence):
            continue
        quoted = [(q.start, q.end) for q in quotes(text)]
        for m in _NUMBER.finditer(text, s0, s1):
            if any(a <= m.start() < b for a, b in quoted):
                continue
            digits = _digits(m.group(0))
            if len(digits) < 10:
                continue
            tail = digits[-10:]
            found = [r for r in calls if _call_has(r, tail)]
            st = _nearest(group, m.start())
            if st is None:
                continue
            rel = _relation(text, st.end_i, m.start(), m.start() > st.start_i)
            ranked = _rank(found, st, tol_s, rel)
            links.setdefault(st.id, []).append(
                Link(
                    "number",
                    " ".join(m.group(0).split()),
                    rel,
                    tuple(ranked[:MAX_SHOWN]),
                    len(found),
                )  # fmt: skip
            )
    return links


def _call_has(rec: Record, tail: str) -> bool:
    return any(_digits(x).endswith(tail) for x in rec.parties)


# ---------------------------------------------------------------- rows


def _zone_label(st: StatedTime, data: CaseRecords) -> str:
    if st.zone is not None:
        return f"{st.zone_words}, as the document states"
    shared = data.shared_zone()
    if shared:
        return f"{shared}, the phones' own zone (the document names none)"
    return "each phone's own zone (the document names none)"


def _sort_key(st: StatedTime, data: CaseRecords) -> datetime | None:
    if not st.compared:
        return None
    tz = st.zone or data.shared_zone() or "UTC"
    start, end = window_utc(st, tz)
    return start or end


def _candidates(data: CaseRecords, st: StatedTime, tol_s: float) -> list[Record]:
    """Timed records that could be within tol_s of the stated time, in any phone's zone."""
    pad = timedelta(seconds=tol_s)
    seen: dict[str, Record] = {}
    for tz in {st.zone} if st.zone else data.zones():
        start, end = window_utc(st, tz)
        for r in data.between(None if start is None else start - pad,
                              None if end is None else end + pad):  # fmt: skip
            seen[r.id] = r
    return list(seen.values())


def _around(data: CaseRecords, st: StatedTime, tol_s: float) -> tuple[list[Compared], int]:
    comps = []
    for r in _candidates(data, st, tol_s):
        c = compare(st, r, tol_s)
        if c.status in ("inside", "within"):
            comps.append(c)
    comps.sort(key=lambda c: (abs(c.delta_s or 0), c.record.source_id, c.record.id))
    return comps[:MAX_NEARBY], len(comps)


def _counts(data: CaseRecords, st: StatedTime) -> list[tuple[str, str, int]]:
    """Records inside the stated days on each phone and app, each phone in its own zone."""
    tally: dict[tuple[str, str], int] = {}
    for tz in {st.zone} if st.zone else data.zones():
        start, end = window_utc(st, tz)
        for r in data.between(start, end):
            if (st.zone or r.tz) != tz or (end is not None and r.ts_utc == end):
                continue  # another phone's zone, or exactly at the exclusive end
            k = (data.phone(r.source_id).name, "Calls" if r.kind == "call" else r.app)
            tally[k] = tally.get(k, 0) + 1
    return [(p, a, n) for (p, a), n in sorted(tally.items())]


def _row(st: StatedTime, data: CaseRecords, links: list[Link], s: Settings) -> TimelineRow:
    tol_s = s.tolerance_min * 60
    zone_label = _zone_label(st, data)
    notes: list[str] = []
    if st.weekday_note:
        notes.append(st.weekday_note)
    if st.on_or_about:
        notes.append('The document says "on or about"; it is compared as that day.')
    if st.approx:
        notes.append("The document gives an approximate time; it is read as 8 minutes either side.")
    if not st.compared:
        what = st.note or "not read"
        if st.readings:
            what += " (" + " or ".join(f"{d:%B} {d.day}, {d.year}" for d in st.readings) + ")"
        return TimelineRow(st, "not_compared", f"Not compared: {what}.", "", None,
                           notes=tuple(notes))  # fmt: skip
    if st.kind == "open":
        notes.append("One end of this range is open; only the stated end is compared.")
    if st.zone is None and len(data.zones()) < len(data.phones):
        notes.append(
            "A phone in this case does not state its time zone; its records are not compared."
        )

    key = _sort_key(st, data)
    tol = f"{s.tolerance_min} min"
    flagged = [c for lk in links for c in lk.shown if c.order_conflict]
    at_links = [lk for lk in links if lk.relation == "at"]
    differs = [lk for lk in at_links if lk.total and not lk.ok and _timed(lk)]
    weekday_bad = st.weekday_ok is False

    if differs:
        lk = differs[0]
        best = next(c for c in lk.shown if c.delta_s is not None)
        side = "before" if (best.delta_s or 0) < 0 else "after"
        summary = (
            f"No record the sentence names is within {tol} of the stated time. The nearest, "
            f"{_label(lk)}, is {fmt_delta(best.delta_s or 0)} {side} it ({best.record.when()})."
        )
        status: RowStatus = "differs"
    elif flagged:
        c = flagged[0]
        lk = next(x for x in links if c in x.shown)
        want = "after" if lk.relation == "after" else "before"
        side = "before" if (c.delta_s or 0) < 0 else "after"
        summary = (
            f"The document places {_label(lk)} {want} the stated time; the record is "
            f"{fmt_delta(c.delta_s or 0)} {side} it ({c.record.when()})."
        )
        status = "order"
    elif weekday_bad:
        summary = st.weekday_note or "The weekday does not match the date."
        status = "weekday"
    elif any(lk.ok for lk in at_links) or (links and all(lk.relation != "at" for lk in links)
                                           and any(lk.total for lk in links)):  # fmt: skip
        ok = [lk for lk in links if lk.total]
        summary = "Records the sentence names are at the stated time (within " + tol + ")."
        if all(lk.relation != "at" for lk in ok):
            summary = "The records the sentence names are in the order it states."
        status = "matches"
    else:
        status = "not_tied"
        if links and not any(lk.total for lk in links):
            summary = "No message holds the quoted words verbatim, and no call has the number."
            if all(lk.how == "quote" for lk in links):
                summary = "No message holds the quoted words verbatim."
            elif all(lk.how == "number" for lk in links):
                summary = "No call in the case has this number."
        elif links:
            summary = "The records the sentence names have no usable time or phone zone."
        else:
            summary = "The sentence names no quoted words or call number to tie a record to it."

    nearby: list[Compared] = []
    nearby_total = 0
    counts: list[tuple[str, str, int]] = []
    if status == "not_tied":
        if st.kind == "moment":
            nearby, nearby_total = _around(data, st, tol_s)
            summary += (
                f" The phones hold {nearby_total} record{'s' if nearby_total != 1 else ''} "
                f"within {tol} of it."
            )
        else:
            counts = _counts(data, st)
    for lk in links:
        for c in lk.shown:
            if c.printed_note and c.printed_note not in notes:
                notes.append(c.printed_note)
    return TimelineRow(
        st, status, summary, zone_label, key, tuple(links), tuple(nearby), nearby_total,
        tuple(counts), tuple(notes),
    )  # fmt: skip


def _timed(lk: Link) -> bool:
    return any(c.delta_s is not None for c in lk.shown)


def _label(lk: Link) -> str:
    return f'the message "{lk.words}"' if lk.how == "quote" else f"the call with {lk.words}"


def timeline(data: CaseRecords, stated: list[StatedTime], s: Settings) -> list[TimelineRow]:
    """One row per stated time: compared rows in time order, then the ones not compared."""
    texts = dict(data.conn.execute("SELECT id, text FROM govdoc_paragraphs"))
    links = tie_records(data, stated, texts, s.tolerance_min * 60)
    rows = [_row(st, data, links.get(st.id, []), s) for st in stated]
    far = datetime.max.replace(tzinfo=UTC)
    return sorted(
        rows,
        key=lambda r: (r.start_utc is None, r.start_utc or far, r.stated.para_no, r.stated.start_i),
    )


FLAGGED: frozenset[RowStatus] = frozenset({"differs", "order", "weekday"})
STATUS_TEXT: dict[RowStatus, str] = {
    "differs": "Differs",
    "order": "Order differs",
    "weekday": "Weekday differs",
    "matches": "Matches",
    "not_tied": "No record tied",
    "not_compared": "Not compared",
}
