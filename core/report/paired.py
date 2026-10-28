"""The paired selection audit in HTML, shared by the report and the review screen: a curated
report against a larger source of the same phone, and what the larger source holds near each
claim's messages that the report does not (core/selection/paired.py).

Both the screen's Selection tab and the report's Selection audit section render it with
paired_html, so they list the same records in the same order. Everything quoted (file names,
account names, message text, senders) goes through q(), so the forbidden-word check can tell it
from the tool's own words.

Tiers: records are observed; pairing, match states and distances are derived by code. No model
is involved, and nothing here sets or changes a verdict.
"""

from __future__ import annotations

import hashlib
import html
from collections.abc import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.enrich.local_time import format_local
from core.report.restore import q
from core.restore.store import FIDELITY_WORDS
from core.selection.audit import gap_text
from core.selection.paired import ClaimNearby, Nearby, Pair, PairedCheck, Rec

SHOW = 25  # records listed per claim and pair; the rest are counted
SHOW_RECORDS = 50  # report records not found or found more than once, listed per pair
SHOW_THREADS = 50  # conversations with records not in the report, listed per pair

CSS = """
.pair { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 12px 16px; margin: 14px 0; }
.pair h4 { margin: 4px 0 8px; font-size: 16px; }
.pair .where { font: 400 12px var(--sans); color: var(--muted); overflow-wrap: anywhere; }
.pair-claim { border-top: 1px solid var(--line); padding: 10px 0 4px; }
.pair-claim table td { font-size: 13px; vertical-align: top; overflow-wrap: anywhere; }
.pair-claim tr.thr td { background: var(--panel); font-weight: 600; }
"""


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def _n(n: int, word: str, plural: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else plural or word + 's'}"


def anchor(claim_id: str, pair_index: int = 0) -> str:
    """The page anchor of one claim's list on one pair (its index in PairedCheck.pairs). The
    pair number comes first and ends at the first '-', so no two (claim, pair) share an anchor
    whatever the claim id holds."""
    return f"paired-{pair_index + 1}-{claim_id}"


def tag(value: str) -> str:
    """A record or source id as a data attribute. Ids carry source text (a sheet or file name),
    which is not the tool's words, so attributes hold a digest the forbidden-word check passes."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _index(check: PairedCheck, p: Pair) -> int:
    return next((i for i, x in enumerate(check.pairs) if x is p), 0)


def _when(r: Rec, zone: str | None) -> str:
    try:
        z = ZoneInfo(zone) if zone else None
    except (ZoneInfoNotFoundError, ValueError):
        z = None
    return format_local(r.ts, z, r.ts_raw)


def _distance(n: Nearby, anchor_ts: object) -> str:
    after = n.record.ts is not None and anchor_ts is not None and n.record.ts >= anchor_ts
    return f"{gap_text(n.distance_s)} {'after' if after else 'before'}"


def _what(r: Rec) -> str:
    if r.kind == "call":
        dur = "duration not shown" if r.duration_s is None else f"{r.duration_s:,} s"
        return f"{e(r.direction.capitalize())} call, {e(dur)}"
    return q(r.text) if r.text else "<span class='muted'>(no text)</span>"


def _source(p: Pair, full: bool) -> str:
    s = p.full if full else p.report
    return f"{q(s.file_name)} ({e(FIDELITY_WORDS.get(s.fidelity, s.fidelity))})"


def _counts(p: Pair) -> str:
    rows = []
    for kind, label in (("message", "Messages"), ("call", "Calls"), ("contact", "Contacts")):
        rows.append(
            f"<tr><td>{label}</td><td>{p.total(kind):,}</td><td>{p.count(kind, 'matched'):,}</td>"
            f"<td>{p.count(kind, 'ambiguous'):,}</td><td>{p.count(kind, 'unmatched'):,}</td>"
            f"<td>{p.full_count(kind, 'not_in_report') if p.listed else 'not listed'}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Records</th><th>In the report</th><th>Found once</th>"
        "<th>Found more than once</th><th>Not found</th><th>In the larger source only</th>"
        "</tr></thead>" + "".join(rows) + "</table>"
    )


def _unsure(p: Pair) -> str:
    """The report's records not found, or found more than once, so every state is visible."""
    odd = [m for m in p.matches if m.state != "matched"]
    if not odd:
        return "<p>Every record of the report was found exactly once in the larger source.</p>"
    items = []
    for m in odd[:SHOW_RECORDS]:
        r = m.record
        state = (
            "not found in the larger source"
            if m.state == "unmatched"
            else f"found {len(m.candidates):,} times, or another report record could be the same "
            "one, so code does not decide which"
        )
        where = f"{e(r.kind)} {q(r.locator)}"
        if r.kind != "contact":
            where += f", {e(_when(r, p.report.zone))}"
        text = q(f"{r.text} ({r.party})") if r.kind == "contact" else _what(r)
        items.append(f"<li data-odd='{tag(r.id)}'>{where}: {text}: {state}.</li>")
    more = len(odd) - min(len(odd), SHOW_RECORDS)
    return (
        f"<details><summary>{_n(len(odd), 'report record')} not found or found more than once"
        "</summary><ul>" + "".join(items) + "</ul>"
        + (f"<p class='muted'>{more:,} more not shown.</p>" if more else "")
        + "</details>"
    )  # fmt: skip


def _left_out(p: Pair) -> str:
    if not p.listed:
        return f"<p class='caution'>{e(p.not_listed_why)}</p>"
    msgs, calls = (p.full_count(k, "not_in_report") for k in ("message", "call"))
    threads = p.missing_threads()
    whole = sum(1 for t in threads if t[4])
    may_be = sum(1 for s in p.full_state.values() if s == "may_be")
    line = (
        f"<p><strong>{_source(p, True)} holds {_n(msgs, 'message')} in "
        f"{_n(len(threads), 'conversation')}"
        + (f" ({whole:,} of them not in the report at all)" if whole else "")
        + f" and {_n(calls, 'call')} that the report does not.</strong>"
    )
    if may_be:
        line += (
            f" Not counted: {_n(may_be, 'record')} that may be in the report: a report record "
            "could be one of several, or a report record not found is near it in the same app "
            "and direction, so it may be that record printed differently."
        )
    later = sum(1 for s in p.full_state.values() if s == "not_compared")
    if later:
        line += (
            f" Also not counted: {_n(later, 'record')} dated after the report's extraction, or "
            "with no time to place before it (every contact), so the report may not have been "
            "able to hold them."
        )
    out = [line + "</p>"]
    if threads:
        rows = "".join(
            f"<tr><td>{q(title or tid)}</td><td>{q(app)}</td><td>{n:,}</td>"
            f"<td>{'Not in the report at all' if none else 'Partly in the report'}</td></tr>"
            for tid, title, app, n, none in threads[:SHOW_THREADS]
        )
        more = len(threads) - min(len(threads), SHOW_THREADS)
        out.append(
            "<details><summary>Conversations with messages not in the report</summary><table>"
            "<thead><tr><th>Conversation</th><th>App</th><th>Not in the report</th><th></th>"
            f"</tr></thead>{rows}</table>"
            + (f"<p class='muted'>{_n(more, 'more conversation')} not shown.</p>" if more else "")
            + "</details>"
        )
    return "".join(out)


def _claim(cn: ClaimNearby, index: int, claim_link: Callable[[str], str] | None,
           context: Callable[[str], str] | None) -> str:  # fmt: skip
    p = cn.pair
    name = (
        f"<a href='{e(claim_link(cn.claim_id))}'>{e(cn.claim_name)}</a>"
        if claim_link
        else f"<a href='#{e(cn.claim_id)}'>{e(cn.claim_name)}</a>"
    )
    head = f"<p><strong>{name}</strong>: {len(cn.anchors):,} of the claim's records are on these "
    head += "two sources"
    if cn.untimed:
        head += f" ({_n(len(cn.untimed), 'has', 'have')} no time, so nothing is near it)"
    div = (
        f"<div class='pair-claim' id='{e(anchor(cn.claim_id, index))}' "
        f"data-claim='{e(cn.claim_id)}'>"
    )
    if not p.listed:
        return f"{div}{head}; nothing is listed for this pair (see above).</p></div>"
    total = cn.total
    if not total:
        return (
            f"{div}{head}; the larger source holds nothing within an hour of them that the "
            "report does not.</p></div>"
        )
    head += (
        f". <strong>Within an hour of them, the larger source holds {_n(total, 'record')} the "
        "report does not.</strong> Listed by conversation (the claim's own first), then by "
        "time from the nearest claim record.</p>"
    )
    times = {}
    for rid in cn.anchors:
        m = next((x for x in p.matches if x.record.id == rid), None)
        rec = (
            p.full_records[m.candidates[0]]
            if m is not None and m.state == "matched"
            else (m.record if m is not None else p.full_records.get(rid))
        )
        times[rid] = rec.ts if rec else None
    rows, shown = [], 0
    for g in cn.groups:
        if shown >= SHOW:
            break
        if g.thread_id is None:
            label = "Calls"
        else:
            label = f"{q(g.title or g.thread_id)} · {q(g.app)}"
            if g.has_anchor:
                label += " · the claim's own conversation"
            if g.whole:
                label += " · not in the report at all"
        rows.append(f"<tr class='thr'><td colspan='4'>{label}</td></tr>")
        for n in g.items:
            if shown >= SHOW:
                break
            shown += 1
            r = n.record
            what = _what(r)
            if context and r.kind == "message":
                what += f" <a href='{e(context(r.id))}'>open</a>"
            rows.append(
                f"<tr data-rec='{tag(r.id)}'><td class='mono'>{e(_when(r, p.full.zone))}</td>"
                f"<td>{e(_distance(n, times.get(n.anchor_id)))}</td>"
                f"<td>{q(r.party) if r.party else ''}"
                f"{' (outgoing)' if r.direction == 'outgoing' else ''}</td><td>{what}</td></tr>"
            )
    more = total - shown
    table = (
        "<table><thead><tr><th>Time on the phone</th><th>From the nearest claim record</th>"
        "<th>Sender or other party</th><th>Message</th></tr></thead>" + "".join(rows) + "</table>"
        + (f"<p class='muted'>{more:,} more not shown.</p>" if more else "")
    )  # fmt: skip
    return f"{div}{head}{table}</div>"


def paired_html(
    check: PairedCheck,
    claim_link: Callable[[str], str] | None = None,
    context: Callable[[str], str] | None = None,
) -> str:
    """The section body. claim_link and context: where the screen links (None in the report,
    which links within the page)."""
    out = [
        "<h3 id='paired-audit'>Curated report against a larger source of the same phone</h3>",
        "<p>Each record of an examiner-curated report is looked for in a larger source of the "
        "same phone: found once, found more than once, or not found. Records found more than "
        "once, and records near a report record not found, may be in the report and are never "
        "counted as left out. Code does all of it; no model ranks anything. It never changes a "
        "verdict. Not yet checked on real Cellebrite or AXIOM exports: synthetic data only.</p>",
    ]
    if not check.pairs:
        curated = check.unpaired
        if not curated:
            out.append(
                "<p>No source is marked an examiner-curated report, so nothing is compared.</p>"
            )
        elif not check.larger:
            out.append(
                "<p>The case holds no larger source (a UFDR or a full extraction) to compare the "
                "curated report with, so what it left out cannot be listed. The request below "
                "asks for it.</p>"
            )
    for s in check.unpaired if check.pairs or check.larger else ():
        out.append(
            f"<p>{q(s.file_name)} has no larger source in this case that lists one of the same "
            "phone's own accounts and states the same device model, so it is not compared.</p>"
        )
    for i, p in enumerate(check.pairs):
        mine = [c for c in check.claims if c.pair is p]
        out.append(
            f"<div class='pair' data-pair='{tag(p.report.id + '|' + p.full.id)}'>"
            f"<h4>{_source(p, False)} against {_source(p, True)}</h4>"
            "<p class='where'>Read as the same phone because both list the phone's own "
            f"{'account' if len(p.basis) == 1 else 'accounts'} "
            + ", ".join(q(b) for b in p.basis)
            + ". · tier derived</p>"
            + _counts(p)
            + _left_out(p)
            + _unsure(p)
            + "<h4>Near each claim</h4>"
            + (
                "".join(_claim(c, i, claim_link, context) for c in mine)
                or "<p>No claim's records are on these two sources.</p>"
            )
            + "</div>"
        )
    if check.pairs and check.no_records:
        out.append(
            "<p class='muted'>Claims with no quoted message or cited evidence on a compared "
            "source, so nothing is listed near them: "
            + ", ".join(e(name) for _, name in check.no_records)
            + ".</p>"
        )
    return "".join(out)


def claim_line(check: PairedCheck, claim_id: str, page: str) -> str:
    """One line for a claim page: what the larger sources hold near the claim's records. page
    is where the lists are; the link goes to the first list with records near the claim, else to
    the first list that holds nothing, else to the first."""
    mine = [c for c in check.claims if c.claim_id == claim_id]
    if not mine:
        return ""
    target = (
        next((c for c in mine if c.pair.listed and c.total), None)
        or next((c for c in mine if not c.pair.listed), None)
        or mine[0]
    )
    href = f"{page}#{anchor(claim_id, _index(check, target.pair))}"
    listed = [c for c in mine if c.pair.listed]
    unlisted = list(dict.fromkeys(c.pair.full.file_name for c in mine if not c.pair.listed))
    total = sum(c.total for c in listed)
    if not listed:
        found = "nothing is listed for this claim; the list says why"
    elif total:
        names = list(dict.fromkeys(c.pair.full.file_name for c in listed if c.total))
        found = (
            f"{', '.join(q(n) for n in names)} {'holds' if len(names) == 1 else 'hold'} "
            f"{_n(total, 'record')} within an hour of this claim's records that the curated "
            "report does not"
        )
    else:
        found = "the larger source holds nothing within an hour of this claim's records that "
        found += "the curated report does not"
    if listed and unlisted:
        found += (
            f"; nothing is listed for {', '.join(q(n) for n in unlisted)}, so that source may "
            "still hold records the report left out"
        )
    return (
        f"<p class='caution'>Curated report check: {found}. "
        f"<a href='{e(href)}'>See the list</a>. This does not change the verdict.</p>"
    )
