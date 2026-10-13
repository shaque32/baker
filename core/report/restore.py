"""Context Restore in HTML: one section per exhibit, shared by the report and the review screen.

Everything quoted (exhibit text, message text, sender text as printed) goes through q(), so the
forbidden-word check can tell it from the tool's own words. A highlighted span is its own q()
element inside <mark>, because a cited span never contains markup.

Display rules:
- A match shows how it was found (exact, tolerant, transliteration), what the tolerant step set
  aside, the words the exhibit added that were not compared (a printed time or sender), the words
  it left out (an ellipsis), and whether the message goes on past the quoted words.
- The match is tier derived (code found and verified it). Messages are observed. The phone's
  local time is derived from UTC and the phone's zone.
- A quoted message that was not found says what was searched and each source's coverage, and
  never that the message does not exist.
"""

from __future__ import annotations

import html
import sqlite3
from collections.abc import Callable

from core.contracts import Exhibit, ExhibitExcerpt, ExhibitMatch, MatchMethod
from core.restore.fold import differences
from core.restore.match import MAX_MATCHES, omitted
from core.restore.store import (
    FIDELITY_WORDS,
    load_excerpts,
    load_exhibits,
    load_matches,
    searched_sources,
    stale_reason,
)
from core.restore.view import Line, MatchView, match_view

REPORT_CONTEXT_MAX_MATCHES = 3  # excerpts with more matches list them without full context

CSS = """
mark { background: #fbf1cf; color: inherit; padding: 0 2px; border-radius: 3px;
  border-bottom: 2px solid var(--await); }
tr.target td { font-weight: bold; background: var(--warn); }
.ctx td { font-size: 12px; } .ctx td.t { white-space: nowrap; }
.exhibit { border: 1px solid var(--line); border-radius: 14px;
  background: var(--card); padding: 6px 20px 14px; margin: 18px 0; }
.nf { color: var(--await); font-weight: bold; }
.piece { font: 12.5px var(--mono); border: 1px solid var(--line);
  background: var(--panel); padding: 0 4px; white-space: pre-wrap; }
pre.letter { white-space: pre-wrap; border: 1px solid var(--line); background: var(--panel);
  padding: 12px; font: 13px/1.45 var(--mono); }
.item { border: 1px solid var(--line); padding: 8px 12px; margin: 10px 0; }
pre.exhibit-text { white-space: pre-wrap; font: 13px/1.45 var(--mono);
  background: var(--panel); padding: 8px; border: 1px solid var(--line); }
"""

METHOD_WORDS = {
    MatchMethod.EXACT: "Exact match: character for character",
    MatchMethod.TOLERANT: "Tolerant match",
    MatchMethod.TRANSLITERATION: "Transliteration match (Cyrillic and Latin spelling)",
}


def q(text: object) -> str:
    return f'<span class="q">{html.escape(str(text))}</span>'


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def shown(text: str) -> str:
    """A piece of cited text set off in its own box, so spaces and punctuation stay visible."""
    return f"<span class='piece'>{q(text)}</span>"


def highlighted(text: str, spans: tuple[tuple[int, int], ...]) -> str:
    """The full text, the matched spans marked."""
    out, pos = [], 0
    for a, b in spans:
        if a > pos:
            out.append(q(text[pos:a]))
        out.append(f"<mark>{q(text[a:b])}</mark>")
        pos = b
    if pos < len(text):
        out.append(q(text[pos:]))
    return "".join(out)


def body_of(conn: sqlite3.Connection, record_id: str) -> str:
    r = conn.execute("SELECT body FROM messages WHERE id = ?", (record_id,)).fetchone()
    return r[0] if r else ""


def match_notes(excerpt: ExhibitExcerpt, m: ExhibitMatch, body: str) -> list[str]:
    """Plain statements about how the exhibit's words relate to the message, all from code."""
    notes = [METHOD_WORDS[m.method] + "."]
    if m.method is not MatchMethod.EXACT:
        diffs: list[str] = []
        for (a, b), (c, d) in zip(m.excerpt_spans, m.spans, strict=True):
            for dname in differences(excerpt.text[a:b], body[c:d], m.method.value):
                if dname not in diffs:
                    diffs.append(dname)
        if diffs:
            notes.append("The exhibit and the message differ in: " + ", ".join(diffs) + ".")
    before = excerpt.text[: m.excerpt_spans[0][0]].strip()
    after = excerpt.text[m.excerpt_spans[-1][1] :].strip()
    if before or after:
        parts = ([f"before the quoted words {shown(before)}"] if before else []) + (
            [f"after them {shown(after)}"] if after else []
        )
        notes.append(
            "Exhibit text set aside, not compared (a label, time or punctuation the exhibit "
            "prints around the message): " + "; ".join(parts) + "."
        )
    gaps = [g for g in omitted(body, m.spans) if g.strip()]
    if gaps:
        notes.append(
            "<strong>The exhibit leaves out words from this message:</strong> "
            + "; ".join(shown(g.strip()) for g in gaps)
            + "."
        )
    if body[: m.spans[0][0]].strip() or body[m.spans[-1][1] :].strip():
        notes.append("<strong>The exhibit quotes only part of this message.</strong>")
    return notes


def not_found_text(conn: sqlite3.Connection, excerpt: ExhibitExcerpt) -> str:
    curated = [
        s[1]
        for s in searched_sources(conn)
        if s[0] in excerpt.source_ids and s[2] != "full_extraction"
    ]
    out = (
        "<p><span class='nf'>Not found in the messages searched.</span> This does not show "
        "that the message was never sent or received. "
    )
    if curated:
        out += (
            e("; ".join(curated))
            + (" is" if len(curated) == 1 else " are")
            + " not a full extraction: messages left out of a curated report were not available "
            "to search. See the draft request for the full extraction (Selection audit). "
        )
    return out + f"</p><p class='muted'>{e(excerpt.searched)}</p>"


def context_table(lines: tuple[Line, ...] | list[Line]) -> str:
    out = [
        "<table class='ctx'><thead><tr><th>UTC (observed)</th><th>Phone's local time "
        "(derived)</th><th>As printed</th><th>Sender</th><th>Direction</th><th>Message</th>"
        "<th>Tier</th><th>Source</th></tr></thead>"
    ]
    for ln in lines:
        who = e(ln.sender) + (f"<br>shown as {q(ln.shown_as)}" if ln.shown_as else "")
        cls = " class='target'" if ln.is_target else ""
        out.append(
            f"<tr{cls}><td class='t'>{e(ln.utc)}</td><td class='t'>{e(ln.local)}</td>"
            f"<td>{q(ln.raw or 'not given')}</td><td>{who}</td><td>{e(ln.direction)}</td>"
            f"<td>{q(ln.body)}</td><td>{e(ln.tier.value)}</td>"
            f"<td class='mono'>{e(ln.source_id)} {e(ln.locator)}</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


def view_block(view: MatchView) -> str:
    t = view.thread
    out = [
        f"<p>Conversation: {e(t.app)} thread {q(t.title or '(untitled)')} on {q(t.device)} in "
        f"{q(t.file_name)}, {t.messages:,} messages"
        + (f", {e(t.first_utc)} to {e(t.last_utc)} UTC" if t.first_utc else "")
        + f". Showing {len(view.lines)}"
        + (
            f"; {view.before:,} earlier and {view.after:,} later not shown"
            if view.before or view.after
            else ""
        )
        + ".</p>",
        context_table(view.lines),
    ]
    if view.related:
        out.append(
            "<h4>Related threads between the same participants</h4><p class='muted'>Matched by "
            "identifier as the sources show it (phone numbers by their digits), plus identity "
            "links an expert confirmed. Messages from the same period as the conversation "
            "above.</p>"
        )
        for r in view.related:
            rt = r.thread
            out.append(
                f"<p><strong>{e(rt.app)} thread {q(rt.title or '(untitled)')}</strong> on "
                f"{q(rt.device)} in {q(rt.file_name)} ({rt.messages:,} messages). Shares "
                + ", ".join(q(s.split(":", 1)[1]) for s in r.shared)
                + ".</p>"
            )
            if r.nearest:
                out.append(
                    "<p class='muted'>No message in this thread falls in the same period. "
                    + ("The nearest before and after:" if r.lines else "")
                    + "</p>"
                )
            if r.lines:
                out.append(context_table(r.lines))
            if r.more:
                out.append(f"<p class='muted'>{r.more:,} more messages in the period.</p>")
    else:
        out.append("<p class='muted'>No other thread shares these participants' identifiers.</p>")
    return "".join(out)


def exhibit_section(
    conn: sqlite3.Connection,
    ex: Exhibit,
    match_link: Callable[[ExhibitMatch], str] | None = None,
    full_context: bool = True,
) -> str:
    """One exhibit: header, each quoted message with its matches or what was searched.

    match_link (the review screen) links each match to its own context page; the report has
    none and prints the context inline instead, for excerpts with few matches.
    """
    out = [f"<div class='exhibit' id='{e(ex.id)}'>"]
    out.append(
        f"<h3>{q(ex.label)}</h3><p class='muted'>Pasted by {e(ex.added_by)} on "
        f"{e(ex.added_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC'))}; SHA-256 of the pasted text "
        f"<span class='mono'>{e(ex.sha256)}</span>; one quoted message per "
        f"{'line' if ex.split.value == 'line' else 'paragraph'}.</p>"
    )
    stale = stale_reason(conn, ex.id)
    if stale:
        out.append(f"<div class='banner'><strong>Search again.</strong> {e(stale)}</div>")
    excerpts = load_excerpts(conn, ex.id)
    found = 0
    for x in excerpts:
        matches = load_matches(conn, x.id)
        found += bool(matches)
        out.append(f"<h4>Quoted message {x.seq}</h4><blockquote>{q(x.text)}</blockquote>")
        if not matches:
            out.append(not_found_text(conn, x))
            continue
        if len(matches) > 1:
            out.append(
                f"<p>Found in {len(matches)} messages. Each is shown; check which one the "
                "exhibit means.</p>"
            )
            if len(matches) >= MAX_MATCHES:
                out.append(f"<p class='muted'>{e(x.searched)}</p>")
        for m in matches:
            body = body_of(conn, m.record_id)
            src = conn.execute(
                "SELECT file_name, fidelity FROM sources WHERE id = ?", (m.ref.source_id,)
            ).fetchone()
            where = f"{q(src[0])} ({e(FIDELITY_WORDS.get(src[1], src[1]))})" if src else ""
            link = f" <a href='{e(match_link(m))}'>Open in context</a>" if match_link else ""
            out.append(
                f"<div class='item'><p>{where} <span class='mono'>{e(m.ref.locator)} "
                f"{e(m.record_id)}</span> · tier derived (found and verified by code, matcher "
                f"{e(m.matcher_version)}){link}</p>"
                f"<blockquote>{highlighted(body, m.spans)}</blockquote><ul>"
                + "".join(f"<li>{n}</li>" for n in match_notes(x, m, body))
                + "</ul>"
            )
            if full_context and match_link is None and len(matches) <= REPORT_CONTEXT_MAX_MATCHES:
                out.append(view_block(match_view(conn, m)))
            out.append("</div>")
        if full_context and match_link is None and len(matches) > REPORT_CONTEXT_MAX_MATCHES:
            out.append(
                "<p class='muted'>Too many matches to print each conversation here; open them "
                "on the review screen.</p>"
            )
    out.insert(
        2,
        f"<p>{found} of {len(excerpts)} quoted message{'' if len(excerpts) == 1 else 's'} "
        "found in the extraction.</p>",
    )
    out.append("</div>")
    return "".join(out)


def restore_section(conn: sqlite3.Connection) -> str:
    """The report's Context Restore section: every exhibit the expert pasted."""
    exhibits = load_exhibits(conn)
    out = [
        "<h2 id='context-restore'>Context Restore</h2><p>Messages the government quotes in its "
        "exhibits, found in the extraction and shown in their own conversations. Code finds and "
        "verifies every match; no model decides one. Context can weaken or strengthen the "
        "government's reading.</p>"
    ]
    if not exhibits:
        out.append("<p class='muted'>No exhibit was added to this case.</p>")
        return "".join(out)
    out += [exhibit_section(conn, ex) for ex in exhibits]
    return "".join(out)
