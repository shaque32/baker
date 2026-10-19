"""Each picked message in its own conversation, and what was exchanged with it that was not picked.

Exchanges. A thread's messages, in the thread's own order (UTC time, then the source's order,
untimed messages last: the order core/audit/context.py uses), fall into exchanges: a pause longer
than EXCHANGE_GAP between two consecutive messages starts a new one. A message with no usable
time is an exchange of its own, because code cannot tell what it was exchanged with.

Passages. For each unit (one government-document paragraph, one exhibit, or the examiner's tags)
and each exchange holding messages the unit picked:
- picked: the messages the unit picked, the words it quotes marked;
- before, between, after: the other messages of that exchange. Each is left out (the selection
  did not pick it anywhere), picked elsewhere (for a paragraph: another paragraph of the same
  document quotes it), or maybe picked (it holds words the selection quotes that code could not
  place on one message). Only left-out messages are counted as left out;
- earlier, later: when fewer than MIN_SIDE messages of the exchange come before (or after) the
  picks, the nearest messages outside it, with the pause between, so a pause is shown, not hidden.
Long runs are cut to the messages nearest the picks, and the rows say how many are not shown.

Quiet stretches. Given the case's timeline settings, each passage also names the quiet stretches
the Gaps check lists (core/timeline/gaps.py) in the thread's pause just before or just after its
exchange: on the phone, in the app or in the thread, at the level the Gaps check lists them.

The same picked messages on two sources make two passages. The second is folded into the first
when its picks are copies of the first's (core/selection/picks.py same_message), and the
difference between the two exchanges is counted.

Everything here is arithmetic over stored rows: positions, times, senders and text. It never says
why a message was not picked, and a message an examiner left out of a curated report is not in
the case to show (core/selection/paired.py compares such a report with a larger source of the
same phone, when the case holds one).
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from itertools import combinations, groupby
from typing import Literal
from zoneinfo import ZoneInfo

from core import encryption
from core.contracts import short_hash
from core.enrich.local_time import device_zone, parse_utc
from core.restore.match import Index
from core.restore.store import searched_statement
from core.restore.view import Line, ThreadInfo, message_lines, thread_info
from core.selection.picks import (
    MAX_PLACES,
    Facts,
    Lookup,
    Place,
    case_names,
    document_lookups,
    exhibit_ids,
    exhibit_lookups,
    facts,
    same_message,
    tagged,
)
from core.timeline.gaps import Gap, find_gaps
from core.timeline.records import CaseRecords
from core.timeline.settings import Settings

EXCHANGE_GAP = timedelta(hours=1)  # a longer pause between two messages starts a new exchange
MIN_SIDE = 3  # messages shown before and after the picks, reaching outside the exchange if needed
SIDE_CAP = 8  # messages of the exchange shown before (and after) the picks; the rest are counted
BETWEEN_CAP = 10  # messages shown in one run between two picks; the rest are counted
NEARBY_CAP = 5  # messages from the source's other conversations shown per passage

Kind = Literal["document", "exhibit", "tags"]
Role = Literal["picked", "before", "between", "after", "earlier", "later"]
_LAST = datetime.max.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Row:
    """One line of a passage: a message, or a count of messages not shown (line is None)."""

    role: Role
    line: Line | None = None
    more: int = 0  # messages of this role not shown here
    spans: tuple[tuple[int, int], ...] = ()  # the words the unit picked, in the message body
    elsewhere: bool = False  # not picked by this unit, but by the same selection elsewhere
    maybe: bool = False  # holds words the selection quotes that code could not place
    attachments: tuple[str, ...] = ()  # file names of the message's attachments
    gap_s: float | None = None  # seconds since the message shown above it, when both have times

    @property
    def left_out(self) -> bool:
        """A message of the exchange that the selection did not pick anywhere."""
        return (
            self.line is not None
            and self.role in ("before", "between", "after")
            and not (self.elsewhere or self.maybe)
        )

    @property
    def partial(self) -> bool:
        """The unit quotes words from this message, and the message holds more than them."""
        if self.line is None or not self.spans:
            return False
        body, spans = self.line.body, self.spans
        rest = [body[: spans[0][0]], body[spans[-1][1] :]]
        rest += [body[spans[i][1] : spans[i + 1][0]] for i in range(len(spans) - 1)]
        return any(ch.isalnum() for part in rest for ch in part)


@dataclass(frozen=True)
class Quiet:
    """A quiet stretch the Gaps check lists in the thread's pause just before or just after an
    exchange. A stretch is stated, never explained."""

    side: Literal["before", "after"]
    scope: str  # 'phone', 'app' or 'thread': where the Gaps check lists it
    start_utc: datetime  # that series' last record before the stretch
    end_utc: datetime  # and its first record after it


@dataclass(frozen=True)
class Passage:
    id: str  # page anchor, stable: unit, thread and first pick
    unit_id: str
    thread: ThreadInfo
    fidelity: str  # of the thread's source: curated_report, full_extraction or unknown
    zone: str | None  # the phone's time zone, for the exchange's times
    rows: tuple[Row, ...]
    picked_ids: tuple[str, ...]  # in thread order
    exchange: int  # messages in the exchange
    lead: int  # messages of the exchange before the first pick, whatever they are
    trail: int  # messages of the exchange after the last pick
    before: int  # left out, before the first pick
    between: int  # left out, between the first and the last pick
    after: int  # left out, after the last pick
    elsewhere: int  # in the exchange, picked by the same selection in another place
    maybe: int  # in the exchange, holding words the selection quotes that were not placed
    other_senders: int  # left out, from someone who sent none of the picked messages
    first_utc: datetime | None  # the exchange's first and last message
    last_utc: datetime | None
    opens_thread: bool  # the source holds no earlier message in this thread
    closes_thread: bool  # the source holds no later message in this thread
    prev_utc: datetime | None  # the thread's message just before the exchange, if it has a time
    next_utc: datetime | None  # and just after it
    exchange_ids: tuple[str, ...] = ()  # every message of the exchange, in thread order
    left_out_ids: tuple[str, ...] = ()  # every left-out message of the exchange, shown or not
    between_ids: tuple[str, ...] = ()  # those of them between the first and the last pick
    nearby: tuple[Line, ...] = ()  # the source's other conversations around the same time
    nearby_more: int = 0
    copy_of: str | None = None  # the passage on another source whose picks this one copies
    only_here: int = 0  # messages of this exchange that the copy_of passage's exchange lacks
    only_there: int = 0  # and the other way round
    quiet: tuple[Quiet, ...] = ()  # quiet stretches the Gaps check lists in the two pauses

    @property
    def pause_before_s(self) -> float | None:
        """From the thread's previous message to the exchange."""
        if self.prev_utc is None or self.first_utc is None:
            return None
        return (self.first_utc - self.prev_utc).total_seconds()

    @property
    def pause_after_s(self) -> float | None:
        """From the exchange to the thread's next message, when that has a time."""
        if self.next_utc is None or self.last_utc is None:
            return None
        return (self.next_utc - self.last_utc).total_seconds()

    @property
    def left_out(self) -> int:
        return self.before + self.between + self.after

    @property
    def partial(self) -> int:
        return sum(1 for r in self.rows if r.role == "picked" and r.partial)

    @property
    def same_as_copy(self) -> bool:
        return self.copy_of is not None and not self.only_here and not self.only_there

    @property
    def untimed(self) -> bool:
        return self.first_utc is None


@dataclass(frozen=True)
class Unit:
    """What one piece of the government's selection picked: a document paragraph's quotes, an
    exhibit's quoted messages, or the examiner's tags."""

    kind: Kind
    id: str  # paragraph id (its first page's), exhibit id, or 'tags'
    label: str  # '¶6' (tool text), the exhibit's label as pasted (cited), or 'Examiner tags'
    page: int | None = None  # a paragraph's page
    last_page: int | None = None  # the page it ends on, when it runs across a page break
    ids: tuple[str, ...] = ()  # a paragraph's stored parts, one per page it is printed on
    doc: str | None = None  # a paragraph's government document
    title: str | None = None  # the document's title, when the case has more than one (cited)
    text: str | None = None  # the paragraph as printed (cited)
    ocr: bool = False  # the paragraph's text came from OCR, so its quotes may not be verbatim
    lookups: tuple[Lookup, ...] = ()
    passages: tuple[Passage, ...] = ()

    @property
    def placed(self) -> int:
        return sum(1 for lk in self.lookups if lk.places)

    @property
    def primary(self) -> list[Passage]:
        """Passages that are not a copy of another; counts are taken from these."""
        return [p for p in self.passages if p.copy_of is None]


@dataclass(frozen=True)
class Mark:
    """Why a message shown in a passage is marked: a unit placed a pick on it (placed), or it
    holds words a unit quotes that were not placed (lookup.hits: every message they are in)."""

    unit: Unit
    lookup: Lookup | None  # None for an examiner tag
    placed: bool


@dataclass(frozen=True)
class SourceLine:
    id: str
    file_name: str
    fidelity: str
    messages: int
    tagged: int


@dataclass(frozen=True)
class SelectionAudit:
    units: tuple[Unit, ...]  # paragraphs in document order, then exhibits, then the tags
    sources: tuple[SourceLine, ...]  # every evidence source
    searched: str  # what the quote look-ups searched, with each source's coverage
    tagged_ids: frozenset[str] = frozenset()
    tagged_quoted: int = 0  # tagged messages a paragraph of the document quotes
    unsearched: tuple[str, ...] = ()  # labels of exhibits Context Restore has not searched yet
    paragraphs: int = 0  # government-document paragraphs in the case, quoting or not
    docs: tuple[tuple[str, str], ...] = ()  # (id, title) of each government document, in id order
    # message id -> one id for it and its copies on other sources, so counts take a message
    # seen on two phones once (only messages that have such a copy are listed)
    same: dict[str, str] = field(default_factory=dict)

    def of(self, kind: Kind) -> list[Unit]:
        return [u for u in self.units if u.kind == kind]

    @property
    def curated_only(self) -> bool:
        """No evidence source is recorded as a full extraction."""
        return all(s.fidelity != "full_extraction" for s in self.sources)

    def marks(self) -> dict[str, list[Mark]]:
        """record id -> every unit that placed a pick on it or quotes words found in it."""
        out: dict[str, list[Mark]] = defaultdict(list)
        tags = next((u for u in self.units if u.kind == "tags"), None)
        for u in self.units:
            for lk in u.lookups:
                placed = {p.record_id for p in lk.places}
                for rid in lk.hits:
                    out[rid].append(Mark(u, lk, rid in placed))
        if tags is not None:
            for rid in sorted(self.tagged_ids):
                out[rid].append(Mark(tags, None, True))
        return out


# ---------------------------------------------------------------- a thread's exchanges


def _natural(locator: str) -> tuple[object, ...]:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", locator))


@dataclass(frozen=True)
class _Msg:
    facts: Facts
    sender: str  # account id, else the sender as printed, else ''

    @property
    def id(self) -> str:
        return self.facts.id

    @property
    def utc(self) -> datetime | None:
        return self.facts.utc


class _Thread:
    """One thread's messages in order, and the exchange each one belongs to."""

    def __init__(self, conn: sqlite3.Connection, thread_id: str) -> None:
        rows = conn.execute(
            "SELECT id, ts_utc, locator, sender_account_id, sender_raw, body, source_id"
            " FROM messages WHERE thread_id = ?",
            (thread_id,),
        ).fetchall()
        # core/audit/context.py's order: known times first in UTC order, then source order.
        rows.sort(key=lambda r: (r[1] is None, r[1] or "", _natural(r[2]), r[0]))
        self.id = thread_id
        self.msgs = [
            _Msg(
                Facts(r[0], thread_id, r[6], " ".join(r[5].split()), parse_utc(r[1])),
                r[3] or r[4] or "",
            )
            for r in rows
        ]
        self.pos = {m.id: i for i, m in enumerate(self.msgs)}
        self.exchange: list[int] = []
        n = 0
        for i, m in enumerate(self.msgs):
            if i and not _close(self.msgs[i - 1], m):
                n += 1
            self.exchange.append(n)

    def bounds(self, i: int) -> tuple[int, int]:
        """First and last position of the exchange that holds position i."""
        a = b = i
        while a > 0 and self.exchange[a - 1] == self.exchange[i]:
            a -= 1
        while b + 1 < len(self.msgs) and self.exchange[b + 1] == self.exchange[i]:
            b += 1
        return a, b


def _close(a: _Msg, b: _Msg) -> bool:
    return a.utc is not None and b.utc is not None and b.utc - a.utc <= EXCHANGE_GAP


# ---------------------------------------------------------------- passages


@dataclass(frozen=True)
class _Built:
    passage: Passage
    source_id: str
    first_pos: int
    picks: tuple[Facts, ...]
    bodies: Counter[str]  # the exchange's messages, by text


def _cut(positions: list[int], keep: int, from_end: bool) -> tuple[list[int], int]:
    """At most `keep` positions, the ones nearest the picks; and how many were cut."""
    if len(positions) <= keep:
        return positions, 0
    return (positions[-keep:] if from_end else positions[:keep]), len(positions) - keep


def _between(run: list[int]) -> list[tuple[Role, int | None, int]]:
    """A run of messages between two picks; a long run keeps its ends and counts the middle."""
    if len(run) <= BETWEEN_CAP:
        return [("between", i, 0) for i in run]
    half = BETWEEN_CAP // 2
    return (
        [("between", i, 0) for i in run[:half]]
        + [("between", None, len(run) - 2 * half)]
        + [("between", i, 0) for i in run[-half:]]
    )


def _layout(th: _Thread, picks: list[int], a: int, b: int) -> list[tuple[Role, int | None, int]]:
    """The positions shown, in order, each with its role; None stands for a run not shown."""
    i0, i1 = picks[0], picks[-1]
    picked = set(picks)
    before, after = list(range(a, i0)), list(range(i1 + 1, b + 1))
    shown: list[tuple[Role, int | None, int]] = []
    if len(before) < MIN_SIDE:
        shown += [("earlier", i, 0) for i in range(max(0, a - (MIN_SIDE - len(before))), a)]
    kept, cut = _cut(before, SIDE_CAP, from_end=True)
    if cut:
        shown.append(("before", None, cut))
    shown += [("before", i, 0) for i in kept]
    run: list[int] = []
    for i in range(i0, i1 + 1):
        if i in picked:
            shown += _between(run)
            run = []
            shown.append(("picked", i, 0))
        else:
            run.append(i)
    kept, cut = _cut(after, SIDE_CAP, from_end=False)
    shown += [("after", i, 0) for i in kept]
    if cut:
        shown.append(("after", None, cut))
    if len(after) < MIN_SIDE:
        end = min(len(th.msgs), b + 1 + MIN_SIDE - len(after))
        shown += [("later", i, 0) for i in range(b + 1, end)]
    return shown


def _passage(
    conn: sqlite3.Connection,
    unit_id: str,
    th: _Thread,
    spans: dict[str, tuple[tuple[int, int], ...]],
    selection: set[str],
    maybe: set[str],
) -> _Built:
    msgs = th.msgs
    picks = sorted(th.pos[r] for r in spans)
    i0, i1 = picks[0], picks[-1]
    a, b = th.bounds(i0)
    picked = {msgs[i].id for i in picks}

    def status(i: int) -> str:
        mid = msgs[i].id
        if mid in picked:
            return "picked"
        if mid in selection:
            return "elsewhere"
        return "maybe" if mid in maybe else "left out"

    shown = _layout(th, picks, a, b)
    ids = [msgs[i].id for _, i, _ in shown if i is not None]
    lines = {ln.record_id: ln for ln in message_lines(conn, ids, None)}
    files = _attachments(conn, ids)
    rows: list[Row] = []
    prev: _Msg | None = None
    for role, i, more in shown:
        if i is None:
            rows.append(Row(role, more=more))
            prev = None
            continue
        m = msgs[i]
        gap = (m.utc - prev.utc).total_seconds() if prev and prev.utc and m.utc else None
        rows.append(
            Row(
                role,
                lines[m.id],
                spans=spans.get(m.id, ()),
                elsewhere=status(i) == "elsewhere",
                maybe=status(i) == "maybe",
                attachments=files.get(m.id, ()),
                gap_s=gap,
            )
        )
        prev = m

    def left_out(r: range) -> list[int]:
        return [i for i in r if status(i) == "left out"]

    senders = {msgs[i].sender for i in picks if msgs[i].sender}
    out_all = left_out(range(a, b + 1))
    info = thread_info(conn, th.id)
    assert info is not None  # noqa: S101 - th.id came from a stored message
    source_id, fidelity, device_id = conn.execute(
        "SELECT s.id, s.fidelity, t.device_id FROM threads t JOIN sources s ON s.id = t.source_id"
        " WHERE t.id = ?",
        (th.id,),
    ).fetchone()
    zone = device_zone(conn, device_id)
    first, last = msgs[a].utc, msgs[b].utc
    prev_t = msgs[a - 1].utc if a > 0 else None
    next_t = msgs[b + 1].utc if b + 1 < len(msgs) else None
    nearby, nearby_more = _nearby(conn, th.id, source_id, first, last, [msgs[i].utc for i in picks])
    passage = Passage(
        id="sel-" + short_hash([unit_id, th.id, msgs[i0].id]),
        unit_id=unit_id,
        thread=info,
        fidelity=fidelity,
        zone=zone.key if zone else None,
        rows=tuple(rows),
        picked_ids=tuple(msgs[i].id for i in picks),
        exchange=b - a + 1,
        lead=i0 - a,
        trail=b - i1,
        before=len(left_out(range(a, i0))),
        between=len(left_out(range(i0 + 1, i1))),
        after=len(left_out(range(i1 + 1, b + 1))),
        elsewhere=sum(1 for i in range(a, b + 1) if status(i) == "elsewhere"),
        maybe=sum(1 for i in range(a, b + 1) if status(i) == "maybe"),
        other_senders=sum(1 for i in out_all if msgs[i].sender and msgs[i].sender not in senders)
        if senders
        else 0,
        first_utc=first,
        last_utc=last,
        opens_thread=a == 0,
        closes_thread=b == len(msgs) - 1,
        prev_utc=prev_t,
        next_utc=next_t,
        exchange_ids=tuple(msgs[i].id for i in range(a, b + 1)),
        left_out_ids=tuple(msgs[i].id for i in out_all),
        between_ids=tuple(msgs[i].id for i in left_out(range(i0 + 1, i1))),
        nearby=tuple(nearby),
        nearby_more=nearby_more,
    )
    return _Built(
        passage,
        source_id,
        i0,
        tuple(msgs[i].facts for i in picks),
        Counter(msgs[i].facts.body for i in range(a, b + 1)),
    )


def _attachments(conn: sqlite3.Connection, ids: list[str]) -> dict[str, tuple[str, ...]]:
    if not ids:
        return {}
    out: dict[str, list[str]] = defaultdict(list)
    for mid, name in conn.execute(
        "SELECT message_id, coalesce(file_name, '(no file name)') FROM attachments"  # noqa: S608
        f" WHERE message_id IN ({','.join('?' * len(ids))}) ORDER BY id",
        ids,
    ):
        out[mid].append(name)
    return {k: tuple(v) for k, v in out.items()}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _nearby(
    conn: sqlite3.Connection,
    thread_id: str,
    source_id: str,
    first: datetime | None,
    last: datetime | None,
    picks: list[datetime | None],
) -> tuple[list[Line], int]:
    """Messages in the source's other conversations from EXCHANGE_GAP before the exchange to
    EXCHANGE_GAP after it: the NEARBY_CAP nearest the picks, in time order, and how many more."""
    times = [t for t in picks if t is not None]
    if first is None or last is None or not times:
        return [], 0
    lo, hi = first - EXCHANGE_GAP, last + EXCHANGE_GAP
    rows = conn.execute(
        "SELECT id, ts_utc FROM messages WHERE source_id = ? AND thread_id != ?"
        " AND ts_utc >= ? AND ts_utc <= ?",
        # a second either side, so a stored fraction of a second is not cut off by the text order
        (source_id, thread_id, _iso(lo - timedelta(seconds=1)), _iso(hi + timedelta(seconds=1))),
    ).fetchall()
    timed = [(rid, t) for rid, t in ((r[0], parse_utc(r[1])) for r in rows) if t and lo <= t <= hi]
    timed.sort(key=lambda x: (min(abs((x[1] - p).total_seconds()) for p in times), x[0]))
    keep = sorted(timed[:NEARBY_CAP], key=lambda x: (x[1], x[0]))
    return message_lines(conn, [rid for rid, _ in keep], None), max(0, len(timed) - NEARBY_CAP)


def _copies(x: _Built, p: _Built) -> bool:
    return (
        x.source_id != p.source_id
        and len(x.picks) == len(p.picks)
        and all(same_message(a, b) for a, b in zip(x.picks, p.picks, strict=True))
    )


def _merged(spans: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    """Spans in order, overlapping or touching ones joined: two quotes can share words."""
    out: list[tuple[int, int]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return tuple(out)


def _unit_passages(
    conn: sqlite3.Connection,
    unit_id: str,
    places: list[Place],
    selection: set[str],
    maybe: set[str],
    threads: dict[str, _Thread],
) -> list[Passage]:
    """Every passage of one unit in time order, each copy on another source right after the
    passage it copies."""
    spans: dict[str, dict[str, tuple[tuple[int, int], ...]]] = defaultdict(dict)
    for p in places:
        got = spans[p.thread_id].get(p.record_id, ())
        spans[p.thread_id][p.record_id] = _merged((*got, *p.spans))
    built: list[_Built] = []
    for tid in sorted(spans):
        if tid not in threads:
            threads[tid] = _Thread(conn, tid)
        th = threads[tid]
        by_exchange: dict[int, dict[str, tuple[tuple[int, int], ...]]] = defaultdict(dict)
        for rid, sp in spans[tid].items():
            by_exchange[th.exchange[th.pos[rid]]][rid] = sp
        for _, group in sorted(by_exchange.items()):
            built.append(_passage(conn, unit_id, th, group, selection, maybe))
    built.sort(
        key=lambda x: (x.passage.first_utc or _LAST, x.source_id, x.passage.thread.id, x.first_pos)
    )
    primaries: list[_Built] = []
    copies: dict[str, list[Passage]] = defaultdict(list)
    for x in built:
        first = next((p for p in primaries if _copies(x, p)), None)
        if first is None:
            primaries.append(x)
            continue
        copies[first.passage.id].append(
            replace(
                x.passage,
                copy_of=first.passage.id,
                only_here=sum((x.bodies - first.bodies).values()),
                only_there=sum((first.bodies - x.bodies).values()),
            )
        )
    return [q for p in primaries for q in (p.passage, *copies.get(p.passage.id, []))]


# ---------------------------------------------------------------- the whole case


_INDEXES: dict[str, tuple[tuple[object, ...], Index]] = {}  # database file -> (key, index)
_KEEP = 4  # databases whose index is kept in memory


def _forget_indexes() -> None:
    _INDEXES.clear()


encryption.on_lock(_forget_indexes)  # no message text stays in memory once a case is locked


def _index(conn: sqlite3.Connection) -> Index:
    """The matcher's index of every message body. Its tolerant and transliteration folds take
    seconds to build in a large case, so it is kept in memory for the database file while its
    messages are unchanged. Baker only ever adds messages, so their count, last rowid and total
    length tell when they changed. Locking any case drops every kept index."""
    path = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    key = tuple(
        conn.execute("SELECT COUNT(*), MAX(rowid), TOTAL(LENGTH(body)) FROM messages").fetchone()
    )
    kept = _INDEXES.get(path) if path else None
    if kept is not None and kept[0] == key:
        return kept[1]
    index = Index.from_db(conn)
    if path:
        _INDEXES.pop(path, None)
        while len(_INDEXES) >= _KEEP:
            _INDEXES.pop(next(iter(_INDEXES)))
        _INDEXES[path] = (key, index)
    return index


@dataclass(frozen=True)
class _Para:
    """One paragraph of a government document. The importer stores a paragraph that runs across
    a page break once per page (core/ingest/govdoc.py); its parts are read as one text, so a
    quotation that runs across the break is still one quote."""

    ids: tuple[str, ...]  # the stored parts, in page order
    doc: str
    page: int
    last_page: int
    para_no: int
    label: str | None
    text: str  # the parts joined by a line break
    ocr: bool
    title: str


def _paragraphs(conn: sqlite3.Connection) -> list[_Para]:
    rows = conn.execute(
        "SELECT p.id, p.govdoc_id, p.page, p.para_no, p.label, p.text, p.ocr, g.title"
        " FROM govdoc_paragraphs p JOIN govdocs g ON g.id = p.govdoc_id"
        " ORDER BY p.govdoc_id, p.para_no, p.page, p.char_start, p.id"
    ).fetchall()
    out = []
    for (doc, para_no), group in groupby(rows, key=lambda r: (r[1], r[3])):
        parts = list(group)
        out.append(
            _Para(
                ids=tuple(r[0] for r in parts),
                doc=doc,
                page=parts[0][2],
                last_page=parts[-1][2],
                para_no=para_no,
                label=parts[0][4],
                text="\n".join(r[5] for r in parts),
                ocr=any(r[6] for r in parts),
                title=parts[0][7],
            )
        )
    return out


def paragraph_label(label: str | None, para_no: int) -> str:
    """How the screen names a paragraph, as claim names do (core/review/status.py)."""
    return f"¶{label if label else '#' + str(para_no)}"


def selection_audit(
    conn: sqlite3.Connection, paragraph_id: str | None = None, timeline: Settings | None = None
) -> SelectionAudit:
    """The selection audit of the case as it is now. With paragraph_id, only that paragraph's
    unit: every paragraph's quotes are still looked up, so a message another paragraph quotes is
    not counted as left out. With timeline (the case's timeline settings), each passage also
    names the quiet stretches the Gaps check lists in its pauses."""
    index = _index(conn)
    names = case_names(conn)
    paras = _paragraphs(conn)
    many = len({p.doc for p in paras}) > 1
    lookups = {p.ids[0]: document_lookups(conn, p.text, index, names) for p in paras}
    placed: dict[str, set[str]] = defaultdict(set)  # govdoc id -> messages its paragraphs quote
    hits: dict[str, set[str]] = defaultdict(set)  # govdoc id -> messages holding words it quotes
    for p in paras:
        for lk in lookups[p.ids[0]]:
            placed[p.doc].update(pl.record_id for pl in lk.places)
            hits[p.doc].update(lk.hits)
    threads: dict[str, _Thread] = {}
    units: list[Unit] = []
    for p in paras:
        pid = p.ids[0]
        if not lookups[pid] or (paragraph_id is not None and paragraph_id not in p.ids):
            continue
        sel, maybe = placed[p.doc], hits[p.doc] - placed[p.doc]
        places = [pl for lk in lookups[pid] for pl in lk.places]
        units.append(
            Unit(
                kind="document",
                id=pid,
                label=paragraph_label(p.label, p.para_no),
                page=p.page,
                last_page=p.last_page if p.last_page != p.page else None,
                ids=p.ids,
                doc=p.doc,
                title=p.title if many else None,
                text=p.text,
                ocr=p.ocr,
                lookups=tuple(lookups[pid]),
                passages=tuple(_unit_passages(conn, pid, places, sel, maybe, threads)),
            )
        )
    quoted = set().union(*placed.values()) if placed else set()
    tags = tagged(conn)
    unsearched: list[str] = []
    if paragraph_id is None:
        for ex_id, ex_label in exhibit_ids(conn):
            lks = exhibit_lookups(conn, ex_id, index)
            if not lks:
                unsearched.append(ex_label)
                continue
            places = [pl for lk in lks for pl in lk.places]
            sel = {pl.record_id for pl in places}
            maybe = {h for lk in lks for h in lk.hits} - sel
            units.append(
                Unit(
                    kind="exhibit",
                    id=ex_id,
                    label=ex_label,
                    lookups=tuple(lks),
                    passages=tuple(_unit_passages(conn, ex_id, places, sel, maybe, threads)),
                )
            )
        if tags:
            sel = {t.record_id for t in tags}
            passages = [
                p
                for p in _unit_passages(conn, "tags", tags, sel, set(), threads)
                if any(r not in quoted for r in p.picked_ids)
            ]
            units.append(
                Unit(kind="tags", id="tags", label="Examiner tags", passages=tuple(passages))
            )
    if timeline is not None:
        stretches = find_gaps(CaseRecords(conn), [], timeline)  # stated times do not move them
        units = [
            replace(u, passages=tuple(replace(p, quiet=quiet(p, stretches)) for p in u.passages))
            for u in units
        ]
    return SelectionAudit(
        units=tuple(units),
        sources=tuple(_sources(conn)),
        searched=searched_statement(conn)[0],
        tagged_ids=frozenset(t.record_id for t in tags),
        tagged_quoted=sum(1 for t in tags if t.record_id in quoted),
        unsearched=tuple(unsearched),
        paragraphs=len(paras),
        docs=tuple(dict.fromkeys((p.doc, p.title) for p in paras)),
        same=_same_messages(conn, units),
    )


def quiet(p: Passage, stretches: list[Gap]) -> tuple[Quiet, ...]:
    """The stretches, of the passage's phone, of its thread's app or of its thread, that lie in
    the thread's pause just before or just after the exchange. A stretch that only touches a
    pause, or reaches past one of its ends, is not named."""
    t = p.thread
    pauses: list[tuple[Literal["before", "after"], datetime, datetime]] = []
    if p.prev_utc is not None and p.first_utc is not None:
        pauses.append(("before", p.prev_utc, p.first_utc))
    if p.last_utc is not None and p.next_utc is not None:
        pauses.append(("after", p.last_utc, p.next_utc))
    out: list[Quiet] = []
    for side, a, b in pauses:
        for g in stretches:
            sr = g.series
            if sr.source_id != t.source_id:
                continue
            if (sr.scope == "app" and sr.app != t.app) or (
                sr.scope == "thread" and sr.thread_id != t.id
            ):
                continue
            if a <= g.start < g.end <= b:
                out.append(Quiet(side, sr.scope, g.start, g.end))
    return tuple(sorted(out, key=lambda q: (q.side == "after", q.start_utc)))


def _same_messages(conn: sqlite3.Connection, units: list[Unit]) -> dict[str, str]:
    """For every message in the passages' exchanges that has a copy on another source
    (core/selection/picks.py same_message), the id that stands for all its copies. A group never
    holds two messages of one source, so two like messages on one phone stay two."""
    ids = sorted({r for u in units for p in u.passages for r in p.exchange_ids})
    by_body: dict[str, list[Facts]] = defaultdict(list)
    for f in facts(conn, ids).values():
        by_body[f.body].append(f)
    head = {i: i for i in ids}
    sources = {i: {f.source_id} for fs in by_body.values() for f in fs for i in [f.id]}

    def root(x: str) -> str:
        while head[x] != x:
            x = head[x]
        return x

    for group in by_body.values():
        for a, b in combinations(sorted(group, key=lambda f: (f.utc or _LAST, f.id)), 2):
            ra, rb = root(a.id), root(b.id)
            if ra != rb and same_message(a, b) and not sources[ra] & sources[rb]:
                keep, drop = min(ra, rb), max(ra, rb)
                head[drop] = keep
                sources[keep] |= sources.pop(drop)
    return {i: root(i) for i in ids if root(i) != i}


def _sources(conn: sqlite3.Connection) -> list[SourceLine]:
    return [
        SourceLine(*r)
        for r in conn.execute(
            "SELECT s.id, s.file_name, s.fidelity,"
            " (SELECT COUNT(*) FROM messages m WHERE m.source_id = s.id),"
            " (SELECT COUNT(*) FROM messages m WHERE m.source_id = s.id AND m.bookmarked = 1)"
            " FROM sources s WHERE s.kind != 'govdoc' ORDER BY s.id"
        )
    ]


# ---------------------------------------------------------------- what a passage says


def gap_text(seconds: float) -> str:
    s = round(abs(seconds))
    if s < 60:
        return f"{s} s"
    m = s // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h} h {m} min" if m else f"{h} h"
    d, h = divmod(h, 24)
    return f"{d} days {h} h" if h else f"{d} days"


def span_text(p: Passage) -> str:
    """The exchange's first and last time on the phone's own clock (UTC when its zone is not
    known): '2026-03-25 12:30 to 12:51 EDT'."""
    if p.first_utc is None:
        return "time unknown"
    zone = ZoneInfo(p.zone) if p.zone else UTC
    a = p.first_utc.astimezone(zone)
    b = (p.last_utc or p.first_utc).astimezone(zone)
    if a == b:
        return f"{a:%Y-%m-%d %H:%M} {a.tzname()}"
    if a.date() == b.date() and a.tzname() == b.tzname():
        return f"{a:%Y-%m-%d %H:%M} to {b:%H:%M} {b.tzname()}"
    return f"{a:%Y-%m-%d %H:%M} {a.tzname()} to {b:%Y-%m-%d %H:%M} {b.tzname()}"


def _at(t: datetime, zone: str | None) -> str:
    """One time on the phone's own clock (UTC when its zone is not known)."""
    local = t.astimezone(ZoneInfo(zone) if zone else UTC)
    return f"{local:%Y-%m-%d %H:%M} {local.tzname()}"


# What a quiet stretch has none of, by the level the Gaps check lists it at.
_QUIET_WHAT = {
    "phone": "messages or calls on this phone",
    "app": "messages in this app on this phone",
    "thread": "messages in this thread",
}


def _n(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else plural or word + 's'}"


# Per kind, in the tool's own words: who picks, the verb, what a picked message is, the heading
# for messages not picked, and what a message not picked is.
_WORDS: dict[Kind, tuple[str, str, str, str, str]] = {
    "document": ("", "quotes", "quoted", "Not quoted anywhere in the document", "not quoted"),
    "exhibit": ("This exhibit", "quotes", "quoted", "Not in this exhibit", "not in this exhibit"),
    "tags": ("The examiner", "tagged", "tagged", "Not tagged", "not tagged"),
}


def left_out_heading(kind: Kind) -> str:
    """How summary() opens its line about the messages not picked."""
    return _WORDS[kind][3]


def summary(unit: Unit, p: Passage) -> list[str]:
    """Plain statements about one passage, every one computed from the rows. Tool's own words
    only (an exhibit's label is cited text, so it is never put in here)."""
    who, verb, noun, heading, not_word = _WORDS[unit.kind]
    who = who or unit.label
    n = len(p.picked_ids)
    the_picked = f"the {noun} {'message' if n == 1 else 'messages'}"
    if p.untimed:
        return [
            f"{who} {verb} a message with no usable time in the source, so code cannot tell what "
            "was exchanged with it. It is listed after the thread's messages that have a time, so "
            "the messages shown beside it are not necessarily the ones sent or received around it."
        ]
    span = span_text(p)
    if p.exchange == n:
        what = "the only message" if n == 1 else f"all {n} messages"
        lines = [f"{who} {verb} {what} in this exchange ({span})."]
    else:
        lines = [f"{who} {verb} {n} of the {p.exchange} messages in this exchange ({span})."]
    parts = [f"{p.between} between {the_picked}"] if p.between else []
    parts += [f"{p.before} just before"] if p.before else []
    parts += [f"{p.after} just after"] if p.after else []
    if parts:
        lines.append(f"{heading}: {', '.join(parts)}.")
    if p.elsewhere:
        where = "another paragraph" if unit.kind == "document" else "another place"
        lines.append(
            f"{_n(p.elsewhere, 'more message')} in this exchange "
            f"{'is' if p.elsewhere == 1 else 'are'} {noun} in {where}."
        )
    if p.maybe:
        whose = "the document" if unit.kind == "document" else "this exhibit"
        lines.append(
            f"{_n(p.maybe, 'more message')} in this exchange may be {noun}: "
            f"{'it holds' if p.maybe == 1 else 'they hold'} words {whose} quotes that are also "
            f"found in other messages, so {'it is' if p.maybe == 1 else 'they are'} not counted "
            f"as {not_word}."
        )
    if p.other_senders:
        senders = "the sender" if n == 1 else "the senders"
        if p.other_senders == p.left_out == 1:
            subject = f"The message {not_word} is"
        elif p.other_senders == p.left_out:
            subject = f"All {p.left_out} {not_word} are"
        else:
            subject = (
                f"{p.other_senders} of the {p.left_out} {not_word} "
                f"{'is' if p.other_senders == 1 else 'are'}"
            )
        lines.append(f"{subject} from someone other than {senders} of {the_picked}.")
    if p.lead == 0:
        if p.opens_thread:
            lines.append("The source holds no earlier message in this thread.")
        elif p.pause_before_s is not None:
            lines.append(
                f"The previous message in this thread is {gap_text(p.pause_before_s)} earlier."
            )
    if p.trail == 0:
        if p.closes_thread:
            lines.append("The source holds no later message in this thread.")
        elif p.pause_after_s is not None:
            lines.append(f"The next message in this thread is {gap_text(p.pause_after_s)} later.")
        else:
            lines.append("The next message in this thread has no usable time.")
    for side in ("before", "after"):
        found = [qs for qs in p.quiet if qs.side == side]
        if not found:
            continue
        qs = max(found, key=lambda x: (x.end_utc - x.start_utc, -x.start_utc.timestamp()))
        what = (
            f"no {_QUIET_WHAT[qs.scope]} from {_at(qs.start_utc, p.zone)} to "
            f"{_at(qs.end_utc, p.zone)} ({gap_text((qs.end_utc - qs.start_utc).total_seconds())})"
        )
        lines.append(
            f"In the pause {side} this exchange, the Gaps check lists a quiet stretch: {what}."
            if len(found) == 1
            else f"In the pause {side} this exchange, the Gaps check lists {len(found)} quiet "
            f"stretches. The longest: {what}."
        )
    if p.partial and unit.kind != "tags":
        lines.append(
            f"{who} quotes only part of {_n(p.partial, 'message')}; the whole message is shown, "
            "the quoted words marked."
        )
    return lines


def lookup_note(lk: Lookup) -> str:
    """Where code found one quote, or why it was not placed. Tool's own words only."""
    if lk.skipped:
        if not lk.hits:
            return f"Not looked up: {lk.skipped}."
        n = len(lk.hits)
        what = "words" if any(ch.isalnum() for ch in lk.text) else "characters"
        return (
            f"Not looked up: {lk.skipped}. {_n(n, 'message')} {'is' if n == 1 else 'are'} just "
            f"these {what}, so {'it is' if n == 1 else 'they are'} marked as may be quoted."
        )
    loose = (
        f" The same words with different punctuation are in {_n(lk.loose, 'more message')}."
        if lk.loose
        else ""
    )
    if lk.part:
        return (
            "The whole quote was not found. Only the words after a colon or dash were found, in "
            f"{_n(lk.found, 'message')}, so it is not placed." + loose
        )
    if not lk.found and not lk.loose:
        return (
            "Not found in the messages searched. This does not show that the message was never "
            "sent or received."
        )
    if not lk.found:
        n = lk.loose
        return (
            "Not found as printed. The same words with different punctuation are in "
            f"{_n(n, 'message')}, so it is not placed and {'it is' if n == 1 else 'they are'} "
            "marked as may be quoted."
        )
    if lk.found > MAX_PLACES:
        return (
            f"Found in {lk.found:,} messages, too many to tell which one is meant. Not placed."
            + loose
        )
    if not lk.places:
        if lk.loose:
            return (
                f"Found in {_n(lk.found, 'message')}, and the same words with different "
                f"punctuation in {_n(lk.loose, 'more message')}. Code does not decide which one "
                "is meant. Not placed."
            )
        return (
            f"Found in {lk.found} messages. Code cannot confirm they are one message seen on "
            "different phones, so it does not decide which one is meant. Not placed."
        )
    if len(lk.places) == 1:
        return "Found in 1 message."
    return (
        f"Found in {len(lk.places)} messages with the same text, on {len(lk.places)} sources and "
        "at most 2 minutes apart, so read as copies of one message."
    )
