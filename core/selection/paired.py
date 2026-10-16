"""Paired selection audit: a curated report against a larger source of the same phone.

An examiner-curated report holds what the examiner chose. When the case also holds a larger
source of the same phone (a UFDR, or any source not marked curated), code can say which records
of the larger source the report does not hold, and list those near each claim's messages.

Pairing. A curated report is compared with a larger source when both list at least one of the
phone's own accounts (the same app and identifier) and both state the same device model (an
account can be signed in on more than one phone). The page names the shared accounts, so the
expert can see why the two were read as one phone. Records the larger source dates after the
report's extraction, or holds with no time (every contact), are never counted as left out;
when the report's extraction time is not known, nothing is listed.

Matching fails closed. Each record of the report is:
- matched: exactly one record of the larger source has the same app, direction, text (Unicode
  and spacing normalized) and a time at most MATCH_WINDOW apart, and no other report record could
  be that same record;
- ambiguous: more than one record could be it, or another report record could be the same one.
  Code does not decide which; every candidate is "may be in the report", never counted left out;
- unmatched: no record of the larger source could be it. A record of the larger source with the
  same app and direction within NEAR of an unmatched report record (or with the same text, or
  with no time on either side) may be that record changed by a format, so it is "may be in the
  report" too, never counted left out. While any contact of the report is not found, every
  contact of the larger source not matched may be it.

A record of the larger source is "not in the report" only when none of the above applies. When
fewer than MIN_ALIGNED of the report's messages and calls are matched or ambiguous, the two may
not be the same phone, or a format may be read differently; then nothing is listed as left out.

Near each claim. A claim's records are the messages its paragraph quotes (placed by the
selection audit) and the records of its evidence (supports, contradicts, complicates). Records
of the larger source not in the report within NEAR of one of them are listed per claim, by
thread (threads holding a claim record first), then by time distance; calls come last. Order is
code only, never a model's ranking. Nothing here is stored, and nothing sets or changes a
verdict.

Tiers: records are observed; pairing, match states and distances are derived by code.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property
from typing import Literal

from core.enrich.local_time import parse_utc
from core.review.status import ClaimState
from core.selection.audit import EXCHANGE_GAP, SelectionAudit

MATCH_WINDOW = timedelta(seconds=60)  # the same record printed by two exports of one phone
NEAR = EXCHANGE_GAP  # one hour: what counts as near a claim's record, as in the selection audit
MIN_ALIGNED = 0.95  # share of the report's messages and calls that must be found to list omissions
AGAINST_OR_FOR = ("supports", "contradicts", "complicates")

Kind = Literal["message", "call", "contact"]
State = Literal["matched", "ambiguous", "unmatched"]
FullState = Literal["in_report", "may_be", "not_in_report", "not_compared"]


@dataclass(frozen=True)
class Rec:
    """One record of either source, as the pairing reads it."""

    id: str
    kind: Kind
    source_id: str
    locator: str
    app: str
    direction: str  # 'unknown' for contacts
    ts: datetime | None
    ts_raw: str | None
    text: str  # message body; a contact's name; '' for a call
    party: str | None  # sender of a message, the other party of a call, a contact's identifier
    thread_id: str | None = None
    thread_title: str | None = None
    duration_s: int | None = None

    def key(self) -> tuple[object, ...]:
        if self.kind == "message":
            return ("message", self.app.casefold(), norm(self.text))
        if self.kind == "call":
            return ("call", self.app.casefold(), self.duration_s)
        return ("contact", norm(self.party or "").casefold(), norm(self.text))


@dataclass(frozen=True)
class SourceLine:
    id: str
    file_name: str
    fidelity: str
    zone: str | None  # the phone's time zone, for display
    extracted_at: datetime | None = None  # when the source's extraction was made
    models: tuple[str, ...] = ()  # the device models the source states, normalized


@dataclass(frozen=True)
class Match:
    """One record of the report and what code found for it in the larger source."""

    record: Rec
    state: State
    candidates: tuple[str, ...]  # ids in the larger source that could be this record


@dataclass(frozen=True)
class Pair:
    report: SourceLine
    full: SourceLine
    basis: tuple[str, ...]  # the phone's own accounts both list: 'Telegram 7001001'
    matches: tuple[Match, ...]  # every record of the report: messages, calls, contacts
    full_records: dict[str, Rec]
    full_state: dict[str, FullState]
    may_be_why: dict[str, str]  # full id -> why it may be in the report
    listed: bool  # whether records not in the report are listed at all
    not_listed_why: str | None = None

    def count(self, kind: Kind, state: State) -> int:
        return sum(1 for m in self.matches if m.record.kind == kind and m.state == state)

    def total(self, kind: Kind) -> int:
        return sum(1 for m in self.matches if m.record.kind == kind)

    def full_count(self, kind: Kind, state: FullState) -> int:
        return sum(
            1
            for rid, s in self.full_state.items()
            if s == state and self.full_records[rid].kind == kind
        )

    def left_out(self, kind: Kind) -> list[Rec]:
        """Records of the larger source not in the report, in thread then time order. Empty
        when the pair is not listed."""
        if not self.listed:
            return []
        recs = [
            self.full_records[rid]
            for rid, s in self.full_state.items()
            if s == "not_in_report" and self.full_records[rid].kind == kind
        ]
        return sorted(recs, key=_order)

    @cached_property
    def left_by_time(self) -> _ByTime:
        """Timed messages and calls of the larger source not in the report."""
        return _ByTime(
            r
            for rid, r in self.full_records.items()
            if self.full_state[rid] == "not_in_report" and r.kind != "contact" and r.ts
        )

    @cached_property
    def whole_threads(self) -> frozenset[str]:
        """Conversations of the larger source none of whose messages is in the report or may
        be in it. A message not compared (dated after the report, or untimed) is no sign the
        report holds part of the conversation."""
        seen: dict[str, bool] = {}
        for rid, r in self.full_records.items():
            if r.kind == "message" and r.thread_id:
                out = self.full_state[rid] in ("not_in_report", "not_compared")
                seen[r.thread_id] = seen.get(r.thread_id, True) and out
        return frozenset(t for t, all_out in seen.items() if all_out)

    def missing_threads(self) -> list[tuple[str, str | None, str, int, bool]]:
        """(thread id, title, app, records not in the report, the report holds none of the
        thread) for each conversation of the larger source with records not in the report."""
        if not self.listed:
            return []
        by: dict[str, list[Rec]] = defaultdict(list)
        for r in self.full_records.values():
            if r.kind == "message" and r.thread_id:
                by[r.thread_id].append(r)
        out = []
        for tid in sorted(by, key=_natural):
            recs = by[tid]
            n = sum(1 for r in recs if self.full_state[r.id] == "not_in_report")
            if n:
                out.append((tid, recs[0].thread_title, recs[0].app, n, tid in self.whole_threads))
        return out


@dataclass(frozen=True)
class Nearby:
    record: Rec  # a record of the larger source not in the report
    distance_s: float  # to the nearest claim record
    anchor_id: str  # that claim record


@dataclass(frozen=True)
class Group:
    thread_id: str | None  # None for calls
    title: str | None
    app: str
    has_anchor: bool  # the thread holds one of the claim's records
    whole: bool  # the report holds none of this conversation
    items: tuple[Nearby, ...]


@dataclass(frozen=True)
class ClaimNearby:
    """What a larger source holds near one claim's records that its report does not."""

    claim_id: str
    claim_name: str
    pair: Pair
    anchors: tuple[str, ...]  # the claim's records on this pair's two sources
    untimed: tuple[str, ...] = ()  # of those, records with no time, so nothing is near them
    groups: tuple[Group, ...] = ()

    @property
    def total(self) -> int:
        return sum(len(g.items) for g in self.groups)

    def ordered(self) -> list[Nearby]:
        return [n for g in self.groups for n in g.items]


@dataclass(frozen=True)
class PairedCheck:
    pairs: tuple[Pair, ...]
    unpaired: tuple[SourceLine, ...]  # curated reports with no larger source of the same phone
    larger: tuple[SourceLine, ...]  # every source not marked curated
    claims: tuple[ClaimNearby, ...] = ()
    no_records: tuple[tuple[str, str], ...] = field(default=())  # (claim id, name): none on a pair


# ---------------------------------------------------------------- helpers


def norm(text: str) -> str:
    """Text as compared: Unicode NFC, line ends and runs of spaces as one space, ends trimmed.
    Letter case and punctuation count."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def _natural(value: str) -> tuple[object, ...]:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", value))


def _order(r: Rec) -> tuple[object, ...]:
    return (_natural(r.thread_id or ""), r.ts is None, r.ts or datetime.min, _natural(r.locator))


def _dir_ok(a: str, b: str) -> bool:
    return a == b or "unknown" in (a, b)


# ---------------------------------------------------------------- loading


def _sources(conn: sqlite3.Connection) -> list[SourceLine]:
    out = []
    for sid, name, fidelity, extracted in conn.execute(
        "SELECT id, file_name, fidelity, extracted_at_utc FROM sources WHERE kind != 'govdoc'"
        " ORDER BY id"
    ):
        zone = conn.execute(
            "SELECT timezone FROM devices WHERE source_id = ? AND timezone IS NOT NULL"
            " ORDER BY id LIMIT 1",
            (sid,),
        ).fetchone()
        models = sorted(
            {
                norm(m).casefold()
                for (m,) in conn.execute(
                    "SELECT model FROM devices WHERE source_id = ? AND model IS NOT NULL", (sid,)
                )
                if norm(m)
            }
        )
        out.append(
            SourceLine(
                sid, name, fidelity, zone[0] if zone else None, parse_utc(extracted),
                tuple(models),
            )
        )  # fmt: skip
    return out


def _own_accounts(conn: sqlite3.Connection, source_id: str) -> set[tuple[str, str]]:
    return {
        (app.casefold(), norm(ident).casefold())
        for app, ident in conn.execute(
            "SELECT app, identifier FROM accounts WHERE source_id = ? AND device_id IS NOT NULL",
            (source_id,),
        )
    }


def _records(conn: sqlite3.Connection, source_id: str) -> list[Rec]:
    recs = []
    for row in conn.execute(
        "SELECT m.id, m.locator, t.app, m.direction, m.ts_utc, m.ts_raw, m.body,"
        " COALESCE(m.sender_raw, a.display_name, a.identifier), m.thread_id, t.title"
        " FROM messages m JOIN threads t ON t.id = m.thread_id"
        " LEFT JOIN accounts a ON a.id = m.sender_account_id"
        " WHERE m.source_id = ? ORDER BY m.id",
        (source_id,),
    ):
        mid, loc, app, direction, ts, raw, body, sender, tid, title = row
        recs.append(
            Rec(mid, "message", source_id, loc, app, direction, parse_utc(ts), raw, body,
                sender, tid, title)
        )  # fmt: skip
    for row in conn.execute(
        "SELECT c.id, c.locator, c.app, c.direction, c.ts_utc, c.ts_raw, c.duration_s,"
        " CASE WHEN c.direction = 'outgoing' THEN COALESCE(t.display_name, t.identifier)"
        " ELSE COALESCE(f.display_name, f.identifier) END"
        " FROM calls c LEFT JOIN accounts f ON f.id = c.from_account_id"
        " LEFT JOIN accounts t ON t.id = c.to_account_id WHERE c.source_id = ? ORDER BY c.id",
        (source_id,),
    ):
        cid, loc, app, direction, ts, raw, dur, other = row
        recs.append(
            Rec(cid, "call", source_id, loc, app, direction, parse_utc(ts), raw, "", other,
                duration_s=dur)
        )  # fmt: skip
    for cid, loc, name, ident in conn.execute(
        "SELECT id, locator, name, identifier FROM contacts WHERE source_id = ? ORDER BY id",
        (source_id,),
    ):
        recs.append(Rec(cid, "contact", source_id, loc, "", "unknown", None, None, name or "",
                        ident))  # fmt: skip
    return recs


# ---------------------------------------------------------------- matching


class _ByTime:
    """Records sorted by time, for window look-ups; records with no time kept apart."""

    def __init__(self, recs: Iterable[Rec]) -> None:
        recs = list(recs)
        timed = sorted((r for r in recs if r.ts is not None), key=lambda r: (r.ts, r.id))
        self.times = [r.ts for r in timed]
        self.timed = timed
        self.untimed = [r for r in recs if r.ts is None]

    def near(self, at: datetime | None, window: timedelta) -> list[Rec]:
        """Every record within window of at, and every record with no time. With at None,
        every record: a record with no time could be any of them."""
        if at is None:
            return self.timed + self.untimed
        lo = bisect_left(self.times, at - window)
        hi = bisect_right(self.times, at + window)
        return self.timed[lo:hi] + self.untimed


def match(
    report: list[Rec], full: list[Rec]
) -> tuple[list[Match], dict[str, FullState], dict[str, str]]:
    """Every report record matched, ambiguous or unmatched; every full record in the report,
    may be in it, or not in it. Pure function of the two record lists."""
    grouped: dict[tuple[object, ...], list[Rec]] = defaultdict(list)
    for f in full:
        grouped[f.key()].append(f)
    index = {k: _ByTime(v) for k, v in grouped.items()}
    cands: dict[str, list[str]] = {}
    claimed: dict[str, list[str]] = defaultdict(list)  # full id -> report ids that could be it
    for r in report:
        pool = index.get(r.key())
        found = (
            sorted(f.id for f in pool.near(r.ts, MATCH_WINDOW) if _dir_ok(r.direction, f.direction))
            if pool is not None
            else []
        )
        cands[r.id] = found
        for fid in found:
            claimed[fid].append(r.id)
    matches = []
    state: dict[str, FullState] = {f.id: "not_in_report" for f in full}
    why: dict[str, str] = {}
    for r in report:
        found = cands[r.id]
        if not found:
            matches.append(Match(r, "unmatched", ()))
        elif len(found) == 1 and claimed[found[0]] == [r.id]:
            matches.append(Match(r, "matched", tuple(found)))
            state[found[0]] = "in_report"
        else:
            matches.append(Match(r, "ambiguous", tuple(found)))
    for m in matches:
        if m.state == "ambiguous":
            for fid in m.candidates:
                if state[fid] != "in_report":
                    state[fid] = "may_be"
                    why.setdefault(fid, "ambiguous")
    # A record of the larger source near a report record not found may be that record printed
    # differently: same kind, app and direction, within NEAR (or either has no time), or a
    # message with the same text at any time.
    lost = [m.record for m in matches if m.state == "unmatched" and m.record.kind != "contact"]
    by_app: dict[tuple[str, str], list[Rec]] = defaultdict(list)
    by_text: dict[tuple[str, str], list[Rec]] = defaultdict(list)
    for r in lost:
        by_app[(r.kind, r.app.casefold())].append(r)
        if r.kind == "message":
            by_text[(r.app.casefold(), norm(r.text))].append(r)
    near = {k: _ByTime(v) for k, v in by_app.items()}
    for f in full:
        if state[f.id] != "not_in_report" or f.kind == "contact":
            continue
        pool = near.get((f.kind, f.app.casefold()))
        close = pool.near(f.ts, NEAR) if pool is not None else []
        if f.kind == "message":
            close = close + by_text.get((f.app.casefold(), norm(f.text)), [])
        if any(_dir_ok(r.direction, f.direction) for r in close):
            state[f.id] = "may_be"
            why[f.id] = "near_unmatched"
    # Contacts have no time to be near. Two exports can print one contact differently (a number
    # spaced or not, a name's case), so while any report contact is not found, every contact of
    # the larger source may be it, and none is counted left out.
    if any(m.state == "unmatched" and m.record.kind == "contact" for m in matches):
        for f in full:
            if f.kind == "contact" and state[f.id] == "not_in_report":
                state[f.id] = "may_be"
                why[f.id] = "near_unmatched"
    return matches, state, why


def _pair(conn: sqlite3.Connection, report: SourceLine, full: SourceLine,
          basis: tuple[str, ...]) -> Pair:  # fmt: skip
    rrecs, frecs = _records(conn, report.id), _records(conn, full.id)
    matches, state, why = match(rrecs, frecs)
    # A record the larger source dates after the report's extraction did not exist when the
    # report was made, so it is never counted as left out; nor is one with no time, which
    # cannot be placed before it. Contacts carry no time, so no contact is ever counted.
    cut = report.extracted_at
    if cut is not None:
        for f in frecs:
            if state[f.id] == "not_in_report" and (f.ts is None or f.ts > cut):
                state[f.id] = "not_compared"
                why[f.id] = "after_report" if f.ts is not None else "no_time"
    timed = [m for m in matches if m.record.kind != "contact"]
    found = sum(1 for m in timed if m.state != "unmatched")
    listed, reason = True, None
    if cut is None:
        listed = False
        reason = (
            "The report's extraction time is not known, so records made after the report "
            "cannot be told from records it left out; nothing is listed."
        )
    elif not timed:
        listed = False
        reason = "The report holds no messages or calls to compare, so nothing is listed."
    elif found < MIN_ALIGNED * len(timed):
        listed = False
        reason = (
            f"Only {found:,} of the report's {len(timed):,} messages and calls were found in "
            "the larger source. The two may not be the same phone, or one of the formats may "
            "be read differently, so code does not list what the report left out."
        )
    return Pair(
        report, full, basis, tuple(matches), {r.id: r for r in frecs}, state, why, listed, reason
    )


def pairs(conn: sqlite3.Connection) -> tuple[list[Pair], list[SourceLine], list[SourceLine]]:
    """Every (curated report, larger source) of the same phone; curated reports with none;
    every larger source."""
    srcs = _sources(conn)
    curated = [s for s in srcs if s.fidelity == "curated_report"]
    larger = [s for s in srcs if s.fidelity != "curated_report"]
    own = {s.id: _own_accounts(conn, s.id) for s in srcs}
    out, unpaired = [], []
    for r in curated:
        mine = []
        for f in larger:
            shared = own[r.id] & own[f.id]
            # An account can be signed in on more than one phone, so a shared account alone
            # does not make one phone: both sources must also state the same device model.
            if shared and r.models and r.models == f.models:
                mine.append(_pair(conn, r, f, _basis(conn, r.id, shared)))
        if mine:
            out += mine
        else:
            unpaired.append(r)
    return out, unpaired, larger


def _basis(
    conn: sqlite3.Connection, source_id: str, shared: set[tuple[str, str]]
) -> tuple[str, ...]:
    """The phone's own accounts both sources list, as the report prints them."""
    shown = [
        f"{app} {ident}"
        for app, ident in conn.execute(
            "SELECT app, identifier FROM accounts WHERE source_id = ? AND device_id IS NOT NULL"
            " ORDER BY app, identifier",
            (source_id,),
        )
        if (app.casefold(), norm(ident).casefold()) in shared
    ]
    return tuple(dict.fromkeys(shown))


# ---------------------------------------------------------------- near each claim


def claim_records(state: ClaimState, audit: SelectionAudit) -> tuple[str, ...]:
    """A claim's records: the messages its paragraph quotes (as the selection audit placed
    them), then its evidence records that support, contradict or complicate, in order."""
    ids: list[str] = []
    pid = state.claim.paragraph_id
    for u in audit.units:
        if u.kind == "document" and pid in u.ids:
            ids += [pl.record_id for lk in u.lookups for pl in lk.places]
    ids += [x.record_id for x in state.evidence if x.stance.value in AGAINST_OR_FOR]
    return tuple(dict.fromkeys(ids))


def near_claim(pair: Pair, claim_id: str, name: str, record_ids: Iterable[str],
               report_recs: dict[str, Match]) -> ClaimNearby | None:  # fmt: skip
    """The records of pair's larger source not in its report within NEAR of a claim record.
    None when no claim record is on either source of the pair."""
    points: list[tuple[str, str | None, datetime]] = []  # (claim record, full thread, time)
    anchors, untimed = [], []
    for rid in record_ids:
        m = report_recs.get(rid)
        if m is not None:
            if m.record.kind == "contact":
                continue
            anchors.append(rid)
            rec = pair.full_records[m.candidates[0]] if m.state == "matched" else m.record
            threads = {pair.full_records[c].thread_id for c in m.candidates}
            thread = rec.thread_id if m.state == "matched" else (
                threads.pop() if len(threads) == 1 else None
            )  # fmt: skip
        elif rid in pair.full_records and pair.full_records[rid].kind != "contact":
            anchors.append(rid)
            rec = pair.full_records[rid]
            thread = rec.thread_id
        else:
            continue
        if rec.ts is None:
            untimed.append(rid)
        else:
            points.append((rid, thread, rec.ts))
    if not anchors:
        return None
    anchor_threads = {t for _, t, _ in points if t}
    near: dict[str, Nearby] = {}
    if pair.listed:
        for a, _, t in points:
            for f in pair.left_by_time.near(t, NEAR):
                d = abs((f.ts - t).total_seconds())
                if f.id not in near or (d, a) < (near[f.id].distance_s, near[f.id].anchor_id):
                    near[f.id] = Nearby(f, d, a)
    by: dict[str | None, list[Nearby]] = defaultdict(list)
    for n in near.values():
        by[n.record.thread_id if n.record.kind == "message" else None].append(n)
    groups = []
    for tid, items in by.items():
        items.sort(key=lambda n: (n.distance_s, n.record.ts, _natural(n.record.locator)))
        first = items[0].record
        whole = tid in pair.whole_threads
        groups.append(
            Group(tid, first.thread_title if tid else None, first.app if tid else "Calls",
                  tid in anchor_threads, whole, tuple(items))
        )  # fmt: skip
    groups.sort(
        key=lambda g: (
            g.thread_id is None,  # calls last
            not g.has_anchor,  # threads holding a claim record first
            g.items[0].distance_s,
            _natural(g.thread_id or ""),
        )
    )
    return ClaimNearby(claim_id, name, pair, tuple(anchors), tuple(untimed), tuple(groups))


def paired_check(
    conn: sqlite3.Connection, states: list[ClaimState], audit: SelectionAudit
) -> PairedCheck:
    """The paired selection audit of the case as it is now, with each claim's nearby records.
    audit: the selection audit, for the messages each claim's paragraph quotes."""
    ps, unpaired, larger = pairs(conn)
    claims: list[ClaimNearby] = []
    none: list[tuple[str, str]] = []
    for p in ps:
        report_recs = {m.record.id: m for m in p.matches}
        for st in states:
            cn = near_claim(p, st.claim.id, st.name, claim_records(st, audit), report_recs)
            if cn is None:
                if (st.claim.id, st.name) not in none:
                    none.append((st.claim.id, st.name))
            else:
                claims.append(cn)
    on_a_pair = {c.claim_id for c in claims}
    none = [x for x in none if x[0] not in on_a_pair]
    return PairedCheck(tuple(ps), tuple(unpaired), tuple(larger), tuple(claims), tuple(none))
