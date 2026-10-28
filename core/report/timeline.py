"""The Timeline check and the quiet stretches in HTML, shared by the review screen and the report
(the same fragments, so the two never disagree).

Everything cited (government document text, message bodies, call parties, thread titles, file
names) goes through q(), so the forbidden-word check can tell it from the tool's own words.
Tiers: a stated time and a record's stored time are observed; the comparison, a record's local
time and a quiet stretch are derived (computed by code). Nothing here is a verdict.
"""

from __future__ import annotations

import html
import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from core.ingest import forwarded
from core.timeline.check import (
    FLAGGED,
    STATUS_TEXT,
    Compared,
    Link,
    TimelineRow,
    fmt_delta,
    timeline,
    window_utc,
)
from core.timeline.gaps import MIN_EXPECTED, Gap, Strip, find_gaps, strips
from core.timeline.records import CaseRecords
from core.timeline.settings import Settings
from core.timeline.stated import StatedTime, read_document

FIDELITY = {
    "curated_report": (
        "an examiner-curated report: it holds only what the examiner chose to include, so a "
        "quiet stretch may only reflect that choice"
    ),
    "full_extraction": "a full extraction",
    "unknown": "a source whose coverage is not known",
}
NOT_FOUND = (
    "Not found does not mean it did not happen. Mabillon does not say why a stretch is quiet."
)

CSS = """
.tl { list-style: none; margin: 14px 0; padding: 0; }
.tl > li { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 12px 16px; margin: 10px 0; display: grid; gap: 6px 18px;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr) 150px; }
.tl > li.flag { border-color: var(--con-line); }
.tl .said { font-size: 14.5px; }
.tl .meta, .gap .meta { font: 400 12px var(--sans); color: var(--muted); }
.tl .recs { font-size: 13px; }
.tl .recs ul { margin: 4px 0; padding-left: 18px; }
.tl .st { text-align: right; }
.tl .notes { grid-column: 1 / -1; font-size: 12.5px; color: var(--muted); margin: 0;
  padding-left: 18px; }
.chip { display: inline-block; font: 500 12px var(--sans); padding: 2px 9px;
  border-radius: 999px; border: 1px solid var(--line-strong); background: var(--panel);
  color: var(--muted); white-space: nowrap; }
.chip.flag { color: var(--con); background: var(--con-bg); border-color: var(--con-line); }
.chip.ok { color: var(--sup); background: var(--sup-bg); border-color: var(--sup-line); }
.d-ok { color: var(--sup); } .d-flag { color: var(--con); font-weight: 600; }
.gap { background: var(--card); border: 1px solid var(--unp-line); border-radius: 14px;
  padding: 12px 18px; margin: 12px 0; }
.gap .stmt { font: 400 21px/1.3 var(--serif); margin: 4px 0 8px; }
.gap dl { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 4px 14px;
  margin: 6px 0; font-size: 13px; }
.gap dt { color: var(--muted); }
.gap dd { margin: 0; }
.strips { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 12px 16px; margin: 12px 0; overflow-x: auto; }
.strip { display: grid; grid-template-columns: 110px minmax(0, 1fr) 70px; gap: 10px;
  align-items: end; margin: 6px 0; font-size: 12.5px; min-width: 520px; }
.bars { display: flex; align-items: flex-end; gap: 2px; height: 40px; }
.bars span { flex: 1; background: #3f3d38; border-radius: 2px 2px 0 0; min-height: 0; }
.bars span.z { background: transparent; }
.bars span.g { background: var(--unp-bg); border: 1px dashed var(--unp-line); border-radius: 2px; }
.axis { display: flex; justify-content: space-between; font: 11.5px var(--sans);
  color: var(--muted); }
@media (max-width: 760px) {
  .tl > li { grid-template-columns: minmax(0, 1fr); }
  .tl .st { text-align: left; }
  .gap dl { grid-template-columns: minmax(0, 1fr); }
}
"""


def q(text: object) -> str:
    """A cited span: text from the government document or the evidence."""
    return f'<span class="q">{html.escape(str(text))}</span>'


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


@dataclass(frozen=True)
class Views:
    rows: list[TimelineRow]
    gaps: list[Gap]
    strips: list[Strip]
    data: CaseRecords


def compute(conn: sqlite3.Connection, s: Settings, rows: bool = True, gaps: bool = True) -> Views:
    """Both views, or only the one a page shows."""
    data = CaseRecords(conn)
    stated = read_document(conn)
    return Views(
        timeline(data, stated, s) if rows else [],
        find_gaps(data, stated, s) if gaps else [],
        strips(data) if gaps else [],
        data,
    )


# ---------------------------------------------------------------- timeline


def _read_as(st: StatedTime, data: CaseRecords) -> str:
    tz = st.zone or data.shared_zone()
    if tz is None or not st.compared:
        return ""
    start, end = window_utc(st, tz)
    wall = " to ".join(f"{t:%Y-%m-%d %H:%M}" if t else "open" for t in (st.start, st.end))
    utc = " to ".join(f"{t:%Y-%m-%d %H:%M}" if t else "open" for t in (start, end))
    return f"Read as {wall} {tz} ({utc} UTC); the end is exclusive."


def _status_chip(row: TimelineRow) -> str:
    cls = "flag" if row.status in FLAGGED else "ok" if row.status == "matches" else ""
    return f"<span class='chip {cls}'>{e(STATUS_TEXT[row.status])}</span>"


def _compared_line(c: Compared, data: CaseRecords) -> str:
    r = c.record
    phone = data.phone(r.source_id)
    if c.status == "no_time":
        how = "<span class='d-flag'>no usable time</span>"
    elif c.status == "no_zone":
        how = "not compared: the phone's time zone is not known"
    elif c.status == "inside":
        how = "<span class='d-ok'>inside the stated time</span>"
    else:
        side = "before" if (c.delta_s or 0) < 0 else "after"
        cls = "d-ok" if c.status == "within" else "d-flag"
        how = f"<span class='{cls}'>{e(fmt_delta(c.delta_s or 0))} {side} the stated time</span>"
    if c.order_conflict:
        how += " <span class='d-flag'>(the document puts it on the other side)</span>"
    what = f"&ldquo;{q(r.what)}&rdquo;" if r.kind == "message" else q(r.what)
    printed = f", printed {q(r.ts_raw)}" if r.ts_raw else ""
    label = forwarded.copy_label(r.locator)
    if label:
        what += f" <strong class='warn'>{e(label)}</strong>"
    return (
        f"<li>{e(r.when())}{printed}: {how}<br>{'Message' if r.kind == 'message' else 'Call'} "
        f"{what} <span class='meta'>{q(phone.file_name)} {e(r.locator)} · "
        f"{e(r.id)}</span></li>"
    )


def _link_block(lk: Link, data: CaseRecords) -> str:
    head = (
        f"Quoted words &ldquo;{q(lk.words)}&rdquo;"
        if lk.how == "quote"
        else f"Calls with {q(lk.words)}"
    )
    rel = {
        "at": "",
        "after": " (the document says this came after the stated time)",
        "before": " (the document says this came before the stated time)",
        "sequence": " (the sentence orders events; not compared for closeness)",
    }[lk.relation]
    if not lk.total:
        found = (
            "no message holds these words verbatim"
            if lk.how == "quote"
            else "no call in the case has this number"
        )
        return f"<div>{head}{e(rel)}: {found}.</div>"
    more = (
        f"<div class='meta'>{lk.total - len(lk.shown)} more, further from the stated time</div>"
        if lk.total > len(lk.shown)
        else ""
    )
    items = "".join(_compared_line(c, data) for c in lk.shown)
    return f"<div>{head}{e(rel)}: {lk.total} found<ul>{items}</ul>{more}</div>"


def timeline_rows(rows: list[TimelineRow], data: CaseRecords) -> str:
    out = ["<ol class='tl'>"]
    for row in rows:
        st = row.stated
        recs = "".join(_link_block(lk, data) for lk in row.links)
        if row.nearby:
            near = "".join(_compared_line(c, data) for c in row.nearby)
            more = row.nearby_total - len(row.nearby)
            recs += (
                f"<div>Records around it (not tied by the document)<ul>{near}</ul>"
                + (f"<div class='meta'>{more} more</div>" if more > 0 else "")
                + "</div>"
            )
        if row.counts:
            items = "".join(
                f"<li>{q(p)}: {n} {q(a)} record{'s' if n != 1 else ''}</li>"
                for p, a, n in row.counts
            )
            recs += (
                f"<details><summary>Records the phones hold in this time</summary><ul>{items}"
                "</ul></details>"
            )
        notes = "".join(f"<li>{e(n)}</li>" for n in row.notes)
        flag = " class='flag'" if row.status in FLAGGED else ""
        out.append(
            f"<li{flag} id='{e(st.id)}'><div><div class='meta'>{e(st.location)} · document"
            f"</div><div class='said'>{q(st.text)}</div>"
            f"<details><summary>The sentence</summary>{q(' '.join(st.sentence.split()))}"
            f"</details><div class='meta'>{e(_read_as(st, data)) or e(row.zone_label)}</div>"
            f"</div><div class='recs'><div class='meta'>Phone records</div>"
            f"<div>{e(row.summary)}</div>{recs}</div>"
            f"<div class='st'>{_status_chip(row)}<div class='meta'>derived</div></div>"
            + (f"<ul class='notes'>{notes}</ul>" if notes else "")
            + "</li>"
        )
    out.append("</ol>")
    return "".join(out)


def _v(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def timeline_summary(rows: list[TimelineRow], s: Settings) -> str:
    compared = [r for r in rows if r.status != "not_compared"]
    n = {k: sum(1 for r in rows if r.status == k) for k in STATUS_TEXT}
    parts = [
        f"The document states {len(rows)} date{'s' if len(rows) != 1 else ''} or time"
        f"{'s' if len(rows) != 1 else ''}; {len(compared)} could be compared.",
    ]
    if n["differs"]:
        parts.append(
            f"{n['differs']} {_v(n['differs'], 'differs', 'differ')} from the records the "
            "sentence names by more than "
            f"{s.tolerance_min} min."
        )
    if n["order"]:
        parts.append(
            f"{n['order']} {_v(n['order'], 'puts', 'put')} a record on the other side of the "
            "stated time."
        )
    if n["weekday"]:
        parts.append(
            f"{n['weekday']} {_v(n['weekday'], 'names', 'name')} a weekday the calendar does not "
            "agree with."
        )
    parts.append(
        f"{n['matches']} {_v(n['matches'], 'matches', 'match')}, and {n['not_tied']} "
        f"{_v(n['not_tied'], 'names', 'name')} no record Mabillon can tie to it."
    )
    return " ".join(parts)


# ---------------------------------------------------------------- quiet stretches


def _phone_name(data: CaseRecords, source_id: str) -> str:
    return data.phone(source_id).name


def _what(g: Gap) -> str:
    """What the stretch has none of, with the app and thread names cited as the data has them."""
    sr = g.series
    if sr.scope == "phone":
        return "messages or calls"
    if sr.scope == "app":
        return "calls" if sr.app == "Calls" else f"{q(sr.app)} messages"
    return f"messages in the {q(sr.app)} thread {q(sr.thread or '(untitled)')}"


def gap_card(g: Gap, data: CaseRecords, timeline_href: str = "/timeline") -> str:
    """timeline_href: where the timeline rows are ('' when they are on the same page)."""
    sr = g.series
    phone = data.phone(sr.source_id)
    what = _what(g)
    stmt = (
        f"No {what} on {q(phone.name)} between {e(g.before.when())} and "
        f"{e(g.after.when())}: {e(fmt_delta(g.seconds))}."
    )
    elsewhere = (
        "; ".join(f"{q(p)} holds {n} record{'s' if n != 1 else ''}" for p, n in g.elsewhere)
        or "No other phone in the case holds a record in this stretch."
    )
    stated = (
        "".join(
            f"<li><a href='{e(timeline_href)}#{e(st.id)}'>{e(st.location)}</a>: {q(st.text)}</li>"
            for st in g.stated
        )
        if g.stated
        else ""
    )
    untimed = (
        f"<dt>No usable time</dt><dd>{sr.untimed} record{'s' if sr.untimed != 1 else ''} "
        "in this series have no usable time and could fall in this stretch.</dd>"
        if sr.untimed
        else ""
    )
    return (
        f"<div class='gap'><div class='meta'>{e(sr.scope)} · derived</div>"
        f"<div class='stmt'>{stmt}</div><dl>"
        f"<dt>Pace</dt><dd>{g.per_day:.1f} a day between this series' first and last record; "
        f"about {g.expected:.0f} would fall in this stretch at that pace.</dd>"
        f"<dt>Either side</dt><dd>Last before: {e(g.before.id)}; first after: "
        f"{e(g.after.id)}.</dd>"
        f"<dt>Searched</dt><dd>{what} imported from {q(phone.file_name)}, "
        f"{e(FIDELITY.get(phone.fidelity, phone.fidelity))}.</dd>"
        f"<dt>Other phones</dt><dd>{elsewhere}</dd>{untimed}"
        + (
            f"<dt>The document</dt><dd>States a time in this stretch:<ul>{stated}</ul></dd>"
            if stated
            else ""
        )  # fmt: skip
        + f"</dl><div class='meta'>{e(NOT_FOUND)}</div></div>"
    )


def strip_block(sp: Strip, gaps: list[Gap], data: CaseRecords) -> str:
    def quiet(app: str, i: int) -> bool:
        day0 = sp.labels[i]
        span = 1 if sp.unit == "day" else 7
        for g in gaps:
            s = g.series
            if s.source_id != sp.source_id or s.scope != "app" or s.app != app:
                continue
            a, b = g.before.local(), g.after.local()
            if a and b and a.date() < day0 and day0 + timedelta(days=span - 1) < b.date():
                return True
        return False

    peak = max((max(c) for _, c in sp.rows if c), default=1) or 1
    rows = []
    for app, counts in sp.rows:
        cells = []
        for i, n in enumerate(counts):
            if quiet(app, i):
                cls, h = "g", 100
            else:
                cls, h = ("", max(6, round(n * 100 / peak))) if n else ("z", 0)
            cells.append(
                f"<span class='{cls}' style='height:{h}%' title='{sp.labels[i]:%Y-%m-%d}: {n}'>"
                "</span>"
            )
        bars = "".join(cells)
        per = sum(counts) / max(len(counts), 1)
        rows.append(
            f"<div class='strip'><div>{q(app)}</div><div class='bars' role='img' "
            f"aria-label='records per {sp.unit}'>{bars}</div>"
            f"<div class='meta'>{per:.1f}/{sp.unit}</div></div>"
        )
    first, last = sp.labels[0], sp.labels[-1]
    zone = sp.tz or "UTC (phone zone unknown)"
    return (
        f"<div class='strips'><div><strong>{q(_phone_name(data, sp.source_id))}</strong> "
        f"<span class='meta'>records per local {sp.unit}, {e(zone)}; shaded: a quiet stretch "
        f"listed below</span></div>{''.join(rows)}"
        f"<div class='strip'><div></div><div class='axis'><span>{first:%b %d}</span>"
        f"<span>{last:%b %d}</span></div><div></div></div></div>"
    )


def gap_lists(views: Views) -> str:
    data = views.data
    out = []
    for sid in data.phones:
        mine = [g for g in views.gaps if g.series.source_id == sid]
        sp = next((x for x in views.strips if x.source_id == sid), None)
        out.append(f"<h2>{q(_phone_name(data, sid))}</h2>")
        if sp is not None:
            out.append(strip_block(sp, mine, data))
        wide = sorted((g for g in mine if g.series.scope != "thread"), key=lambda g: -g.expected)
        threads = sorted((g for g in mine if g.series.scope == "thread"), key=lambda g: -g.expected)
        if not wide and not threads:
            out.append("<p class='muted'>No quiet stretch meets the settings on this phone.</p>")
        out += [gap_card(g, data) for g in wide]
        if threads:
            out.append(
                f"<details><summary>Quiet stretches inside single threads ({len(threads)})"
                f"</summary>{''.join(gap_card(g, data) for g in threads)}</details>"
            )
    return "".join(out)


# ---------------------------------------------------------------- report


def report_section(conn: sqlite3.Connection, s: Settings) -> str:
    """Both views for the report: the timeline in full, the quiet stretches per phone and app
    (thread-level stretches are counted and left to the screen)."""
    views = compute(conn, s)
    if not views.rows and not views.gaps:
        return ""
    out = ["<h2>Timeline check</h2>"]
    if views.rows:
        out.append(
            f"<p>{e(timeline_summary(views.rows, s))} Tolerance {s.tolerance_min} min. Code "
            "reads the dates and ties a record to a statement only by the quoted words or call "
            "number in the same sentence. These findings do not change any verdict.</p>"
        )
        out.append(timeline_rows(views.rows, views.data))
    else:
        out.append("<p class='muted'>The government document states no date Mabillon could read."
                   "</p>")  # fmt: skip
    out.append("<h2>Quiet stretches</h2>")
    wide = sorted((g for g in views.gaps if g.series.scope != "thread"), key=lambda g: -g.expected)
    n_thread = sum(1 for g in views.gaps if g.series.scope == "thread")
    out.append(
        f"<p>Stretches of at least {s.gap_hours} h with no records, on each phone and in each "
        f"app, where the series' own pace would put at least {MIN_EXPECTED} records. "
        f"{e(NOT_FOUND)}"
        + (
            f" {n_thread} more stretches inside single threads are listed on the review screen."
            if n_thread
            else ""
        )  # fmt: skip
        + "</p>"
    )
    if wide:
        out += [gap_card(g, views.data, "") for g in wide]
    else:
        out.append("<p class='muted'>None meets the settings.</p>")
    return "".join(out)
