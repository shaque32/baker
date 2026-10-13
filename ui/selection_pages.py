"""Selection audit pages of the review screen: every message the government's document quotes,
an exhibit quotes or the examiner tagged, in its own exchange with the messages around it that
were not picked; and one message opened in its conversation.

Pure functions of the case database, like ui/pages.py, and rendered with the same HTML fragments
as the report (core/report/selection.py), so the screen and the report never disagree. Nothing
here writes to the case: the selection audit is derived each time it is shown.
"""

from __future__ import annotations

import sqlite3

from core.report.restore import view_block
from core.report.selection import Links, mark_html, selection_html
from core.restore.view import context_view
from core.review.status import claim_states
from core.selection.audit import selection_audit
from ui.pages import Page, link


def _links() -> Links:
    return Links(
        context=lambda rid: link("/selection/context", id=rid),
        claim=lambda cid: link("/claim", id=cid),
    )


def selection_page(conn: sqlite3.Connection, page: Page) -> str:
    audit = selection_audit(conn)
    body = (
        "<h1>Selection audit</h1>"
        + selection_html(audit, _links(), claim_states(conn))
        + "<p><a href='/request-letter'>Draft request for the full extraction</a></p>"
    )
    return page.wrap("Selection audit", body)


def context_page(conn: sqlite3.Connection, page: Page, record_id: str) -> str | None:
    """One message in its conversation: 20 messages either side, and related threads."""
    try:
        view = context_view(conn, record_id)
    except LookupError:
        return None
    marks = selection_audit(conn).marks().get(record_id, [])
    picked = (
        "<p>This message: " + " ".join(mark_html(m) for m in marks) + "</p>"
        if marks
        else "<p class='muted'>Nothing in the selection picks this message.</p>"
    )
    body = (
        "<p><a href='/selection'>Back to the selection audit</a></p>"
        "<h1>Message in its conversation</h1>"
        + picked
        + "<p class='muted'>Messages are observed; the phone's local time is derived from UTC "
        "and the phone's time zone. The message is highlighted.</p>" + view_block(view)
    )
    return page.wrap("Message in its conversation", body)
