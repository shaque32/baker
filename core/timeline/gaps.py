"""Quiet stretches: spans with no messages or calls, on each phone, in each app and in each
thread. Derived by code from the stored times; nothing is stored.

A stretch is listed when it lasts at least the case's shortest-stretch setting and the series'
own average pace (records between its first and last, over that time) would put at least
MIN_EXPECTED records in it, so a thread that is quiet most of the time does not flood the list.
A thread's stretch that its whole app shares, or an app's stretch its whole phone shares, is
listed once, at the widest level.

A stretch is stated, never explained: Baker does not say why records are absent, and a missing
record does not mean nothing happened. Each stretch says what was searched (the source and its
coverage), how many records in the series have no usable time, what other phones hold in the
same span, and which times the government document states inside it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from core.timeline.check import window_utc
from core.timeline.records import CaseRecords, Record, zone
from core.timeline.settings import Settings
from core.timeline.stated import StatedTime

MIN_EXPECTED = 8
MAX_DAYS_SHOWN = 120  # the daily strip; longer spans are shown by week
SCOPES = ("phone", "app", "thread")


@dataclass(frozen=True)
class Series:
    source_id: str
    scope: str  # 'phone', 'app' or 'thread'
    app: str | None  # 'Calls' for the call log
    thread_id: str | None
    thread: str | None
    timed: tuple[Record, ...]  # in time order
    untimed: int


@dataclass(frozen=True)
class Gap:
    series: Series
    before: Record  # the last record before the stretch
    after: Record  # the first record after it
    expected: float  # records the series' own average pace would put in the stretch
    per_day: float  # that pace
    elsewhere: tuple[tuple[str, int], ...]  # (phone, records) other phones hold in the stretch
    stated: tuple[StatedTime, ...]  # stated times that overlap the stretch

    @property
    def start(self) -> datetime:
        return _ts(self.before)

    @property
    def end(self) -> datetime:
        return _ts(self.after)

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()


def _ts(r: Record) -> datetime:
    if r.ts_utc is None:  # series hold timed records only
        raise ValueError(f"{r.id} has no usable time")
    return r.ts_utc


def _app_of(r: Record) -> str:
    return "Calls" if r.kind == "call" else r.app


def series(data: CaseRecords) -> list[Series]:
    groups: dict[tuple[str, str, str | None, str | None], list[Record]] = {}
    titles: dict[str, str | None] = {}
    for r in data.records:
        groups.setdefault((r.source_id, "phone", None, None), []).append(r)
        groups.setdefault((r.source_id, "app", _app_of(r), None), []).append(r)
        if r.thread_id is not None:
            groups.setdefault((r.source_id, "thread", r.app, r.thread_id), []).append(r)
            titles[r.thread_id] = r.thread
    out = []
    for (sid, scope, app, tid), recs in groups.items():
        timed = sorted((r for r in recs if r.ts_utc is not None), key=lambda r: (r.ts_utc, r.id))
        out.append(
            Series(
                sid,
                scope,
                app,
                tid,
                titles.get(tid) if tid else None,
                tuple(timed),
                len(recs) - len(timed),
            )  # fmt: skip
        )
    return sorted(
        out, key=lambda s: (s.source_id, SCOPES.index(s.scope), s.app or "", s.thread or "")
    )


def _covers(outer: Gap, inner: Gap) -> bool:
    return outer.start <= inner.start and inner.end <= outer.end


def _stated_in(stated: Iterable[StatedTime], data: CaseRecords, g_start, g_end, source_id):
    out = []
    tz = data.phone(source_id).tz
    for st in stated:
        if not st.compared or (st.zone is None and zone(tz) is None):
            continue
        start, end = window_utc(st, st.zone or tz)  # type: ignore[arg-type]
        if (start is None or start < g_end) and (end is None or end > g_start):
            out.append(st)
    return tuple(out)


def find_gaps(data: CaseRecords, stated: list[StatedTime], s: Settings) -> list[Gap]:
    min_s = s.gap_hours * 3600
    found: list[Gap] = []
    for sr in series(data):
        t = sr.timed
        if len(t) < 2:
            continue
        span = (_ts(t[-1]) - _ts(t[0])).total_seconds()
        if span <= 0:
            continue
        per_s = (len(t) - 1) / span
        for a, b in zip(t, t[1:], strict=False):
            a_t, b_t = _ts(a), _ts(b)
            gap_s = (b_t - a_t).total_seconds()
            if gap_s < min_s or per_s * gap_s < MIN_EXPECTED:
                continue
            elsewhere: dict[str, int] = {}
            for r in data.between(a_t, b_t, closed=False):
                if r.source_id != sr.source_id:
                    name = data.phone(r.source_id).name
                    elsewhere[name] = elsewhere.get(name, 0) + 1
            found.append(
                Gap(
                    sr,
                    a,
                    b,
                    per_s * gap_s,
                    per_s * 86400,
                    tuple(sorted(elsewhere.items())),
                    _stated_in(stated, data, a_t, b_t, sr.source_id),
                )  # fmt: skip
            )
    # list each stretch once, at the widest level that has it
    out = []
    for g in found:
        wider = [
            w
            for w in found
            if w.series.source_id == g.series.source_id
            and SCOPES.index(w.series.scope) < SCOPES.index(g.series.scope)
            and (w.series.scope == "phone" or w.series.app == g.series.app)
            and _covers(w, g)
        ]
        if not wider:
            out.append(g)
    return out


# ---------------------------------------------------------------- daily strip


@dataclass(frozen=True)
class Strip:
    """Records per local day (or week) for each app on one phone."""

    source_id: str
    unit: str  # 'day' or 'week'
    labels: tuple[date, ...]  # first day of each bucket
    rows: tuple[tuple[str, tuple[int, ...]], ...]  # (app, counts)
    tz: str | None


def strips(data: CaseRecords) -> list[Strip]:
    out = []
    for sid, phone in data.phones.items():
        recs = [r for r in data.records if r.source_id == sid and r.ts_utc is not None]
        if not recs:
            continue
        days = [local_day(_ts(r), phone.tz) for r in recs]
        lo, hi = min(days), max(days)
        n_days = (hi - lo).days + 1
        unit = "day" if n_days <= MAX_DAYS_SHOWN else "week"
        step = 1 if unit == "day" else 7
        n = (n_days + step - 1) // step
        labels = tuple(lo + timedelta(days=i * step) for i in range(n))
        counts: dict[str, list[int]] = {}
        for r, d in zip(recs, days, strict=True):
            row = counts.setdefault(_app_of(r), [0] * n)
            row[(d - lo).days // step] += 1
        out.append(
            Strip(
                sid,
                unit,
                labels,
                tuple((app, tuple(c)) for app, c in sorted(counts.items())),
                phone.tz,
            )  # fmt: skip
        )
    return out


def local_day(t: datetime, tz: str | None) -> date:
    z = zone(tz)
    return (t.astimezone(z) if z else t).date()
