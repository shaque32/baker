"""Context Restore pages of the review screen: paste an exhibit, see each quoted message found in
the extraction and opened in its own conversation, and the draft request for the full extraction.

Pure functions of the case database, like ui/pages.py, and rendered with the same HTML fragments
as the report (core/report/restore.py), so the screen and the report never disagree. Adding and
removing an exhibit go through core/restore/store.py, which writes the audit log.
"""

from __future__ import annotations

import html
import sqlite3

from core.report.letter import needs_request, request_letter
from core.report.restore import exhibit_section, match_notes, view_block
from core.restore.store import (
    MAX_EXHIBIT_CHARS,
    load_excerpt,
    load_excerpts,
    load_exhibit,
    load_exhibits,
    load_match,
    stale_reason,
)
from core.restore.view import match_view
from ui.pages import Page, e, link, q


def _found_counts(conn: sqlite3.Connection, ex_id: str) -> tuple[int, int]:
    excerpts = load_excerpts(conn, ex_id)
    found = sum(
        1
        for x in excerpts
        if conn.execute(
            "SELECT 1 FROM exhibit_matches WHERE excerpt_id = ? LIMIT 1", (x.id,)
        ).fetchone()
    )
    return found, len(excerpts)


def exhibits_page(conn: sqlite3.Connection, page: Page) -> str:
    exhibits = load_exhibits(conn)
    out = [
        "<h1>Exhibits</h1><p>Paste the messages a government exhibit quotes. Mabillon finds each "
        "one in the imported extraction and shows it in its own conversation, with the "
        "messages around it and related threads. Code finds and verifies every match; no model "
        "decides one. Screenshots are not read: type or paste the text.</p>"
    ]
    if needs_request(conn):
        out.append(
            "<p class='warn'>Only curated reports (or sources of unknown coverage) are imported. "
            "<a href='/request-letter'>Draft request for the full extraction</a></p>"
        )
    if exhibits:
        out.append(
            "<table><thead><tr><th>Exhibit</th><th>Quoted messages found</th><th>Added</th>"
            "<th>Status</th></tr></thead>"
        )
        stale_any = False
        for ex in exhibits:
            found, total = _found_counts(conn, ex.id)
            stale = stale_reason(conn, ex.id)
            stale_any = stale_any or stale is not None
            out.append(
                f"<tr><td><a href='{e(link('/exhibit', id=ex.id))}'>{q(ex.label)}</a></td>"
                f"<td>{found} of {total}</td><td>{e(ex.added_by)}, "
                f"{e(ex.added_at_utc.strftime('%Y-%m-%d %H:%M UTC'))}</td>"
                f"<td>{e(stale or 'Current')}</td></tr>"
            )
        out.append("</table>")
        if stale_any:
            out.append(
                page.form(
                    "/exhibit/rematch",
                    "Some exhibits were searched before the latest import or matcher change. "
                    "<button type='submit'>Search all exhibits again</button>",
                    back="/exhibits",
                )
            )
    else:
        out.append("<p class='muted'>No exhibit added yet.</p>")

    paragraphs = list(
        conn.execute(
            "SELECT p.id, p.page, coalesce(p.label, p.para_no), substr(p.text, 1, 80)"
            " FROM govdoc_paragraphs p ORDER BY p.govdoc_id, p.para_no"
        )
    )
    options = "<option value=''>(none)</option>" + "".join(
        f"<option value='{e(pid)}'>Page {pg}, paragraph {e(lbl)}: {e(txt)}</option>"
        for pid, pg, lbl, txt in paragraphs
    )
    out.append(
        "<h2>Add an exhibit</h2>"
        + page.form(
            "/exhibit/add",
            "<p><label>Exhibit name <input type='text' name='label' required maxlength='120' "
            "class='wide' placeholder='Government Exhibit 4'></label></p>"
            f"<p><label>Cited in (optional) <select name='paragraph'>{options}</select></label>"
            "</p><p><label>Quoted messages, as the exhibit prints them<br>"
            f"<textarea name='text' rows='12' required maxlength='{MAX_EXHIBIT_CHARS}'>"
            "</textarea></label></p><fieldset class='msgsplit'><legend>One message per</legend>"
            "<label><input type='radio' name='split' value='line' checked> line</label>"
            "<label><input type='radio' name='split' value='block'> paragraph <span "
            "class='muted'>(blank line between messages; keeps a message that runs over several "
            "lines whole)</span></label></fieldset><p class='muted'>A time or sender name printed "
            "in front of a message is set aside and shown, not compared. An ellipsis marks "
            "words the exhibit left out; Mabillon shows them.</p>"
            "<button type='submit'>Add and search</button>",
            back="/exhibits",
        )
    )
    return page.wrap("Exhibits", "".join(out))


def exhibit_page(conn: sqlite3.Connection, page: Page, ex_id: str) -> str | None:
    ex = load_exhibit(conn, ex_id)
    if ex is None:
        return None
    back = link("/exhibit", id=ex.id)
    body = [
        "<p><a href='/exhibits'>All exhibits</a></p>",
        exhibit_section(conn, ex, match_link=lambda m: link("/exhibit/match", id=m.id)),
        f"<details><summary>Exhibit text as pasted</summary><pre class='exhibit-text'>"
        f"{q(ex.text)}</pre></details>",
        page.form(
            "/exhibit/rematch",
            f"<input type='hidden' name='id' value='{e(ex.id)}'>"
            "<button type='submit'>Search again</button> against the messages imported now.",
            back=back,
        ),
        page.form(
            "/exhibit/remove",
            f"<input type='hidden' name='id' value='{e(ex.id)}'>"
            "<button type='submit'>Remove this exhibit</button> The removal is recorded in the "
            "audit log with your name.",
            back="/exhibits",
        ),
    ]
    return page.wrap(ex.label, "".join(body))


def match_page(conn: sqlite3.Connection, page: Page, match_id: str) -> str | None:
    m = load_match(conn, match_id)
    if m is None:
        return None
    excerpt = load_excerpt(conn, m.excerpt_id)
    if excerpt is None:
        return None
    ex = load_exhibit(conn, excerpt.exhibit_id)
    body_row = conn.execute("SELECT body FROM messages WHERE id = ?", (m.record_id,)).fetchone()
    if ex is None or body_row is None:
        return None
    out = [
        f"<p><a href='{e(link('/exhibit', id=ex.id))}'>Back to {e(ex.label)}</a></p>",
        f"<h1>Quoted message {excerpt.seq} in context</h1>",
        f"<p>The exhibit prints:</p><blockquote>{q(excerpt.text)}</blockquote>",
        "<ul>" + "".join(f"<li>{n}</li>" for n in match_notes(excerpt, m, body_row[0])) + "</ul>",
        f"<p class='muted'>Match tier derived: found and verified by code (matcher "
        f"{e(m.matcher_version)}). Messages are observed; the phone's local time is derived "
        "from UTC and the phone's time zone.</p>",
        view_block(match_view(conn, m)),
    ]
    return page.wrap(f"{ex.label}, message {excerpt.seq}", "".join(out))


def letter_page(conn: sqlite3.Connection, page: Page) -> str:
    text = request_letter(conn)
    if text is None:
        body = (
            "<h1>Request for the full extraction</h1><p>Every evidence source in this case is "
            "recorded as a full extraction, so no request is drafted.</p>"
        )
    else:
        body = (
            "<h1>Request for the full extraction (draft)</h1><p>Built from the imported "
            "sources for counsel to review and complete. Not legal advice. Mabillon does not send "
            "it anywhere. <a href='/request-letter.txt'>Download as text</a></p>"
            f"<pre class='letter'>{html.escape(text)}</pre>"
        )
    return page.wrap("Request letter", body)
