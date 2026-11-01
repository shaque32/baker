"""Selection audit pages of the review screen: every message the government's document quotes,
an exhibit quotes or the examiner tagged, in its own exchange with the messages around it that
were not picked; and one message opened in its conversation.

Pure functions of the case database, like ui/pages.py, and rendered with the same HTML fragments
as the report (core/report/selection.py), so the screen and the report never disagree. Nothing
here writes to the case: the selection audit is derived each time it is shown.

On the screen the long opening explanations fold under a disclosure (every word stays on the
page), and each page's body sits in its own wrapper (pg-selection, pg-context) so its look lives
in ui/css/selection.py.
"""

from __future__ import annotations

import sqlite3

from core.report.paired import paired_html
from core.report.selection import INTRO, Links, mark_html, selection_html
from core.restore.view import context_view
from core.review.status import claim_states
from core.selection.audit import selection_audit
from core.selection.paired import paired_check
from core.timeline.settings import Settings
from ui.pages import Page, _folded, link
from ui.restore_pages import conversation

COVERAGE_HEAD = "<div class='banner'><strong>What this can show.</strong>"


def _links() -> Links:
    return Links(
        context=lambda rid: link("/selection/context", id=rid),
        claim=lambda cid: link("/claim", id=cid),
        gaps="/gaps",
    )


def _calmer(html: str) -> str:
    """The selection audit's opening as the screen shows it: the first paragraph stays, the
    paragraph that defines exchanges and counts folds under a disclosure, and the coverage notice
    folds to its bold first sentence. Every word stays on the page. If the report's opening ever
    changes shape, the text is shown as it is."""
    if not html.startswith(INTRO):
        return html
    lead, sep, terms = INTRO.partition("</p>")
    rest = html[len(INTRO) :]
    out = (
        lead
        + sep
        + "<details class='terms'><summary>How exchanges and counts are defined</summary>"
        + terms
        + "</details>"
    )
    if rest.startswith(COVERAGE_HEAD):
        end = rest.index("</div>") + len("</div>")
        out += _folded(rest[:end])
        rest = rest[end:]
    return out + rest


def selection_page(conn: sqlite3.Connection, page: Page, timeline: Settings) -> str:
    """timeline: the case's timeline settings, for the quiet stretches the Gaps tab lists."""
    audit = selection_audit(conn, timeline=timeline)
    states = claim_states(conn)
    body = (
        "<div class='pg-selection'><h1>Selection audit</h1>"
        + _calmer(selection_html(audit, _links(), states))
        + paired_html(
            paired_check(conn, states, audit),
            claim_link=lambda cid: link("/claim", id=cid),
            context=lambda rid: link("/selection/context", id=rid),
        )
        + "<p class='letter-link'><a href='/request-letter'>Draft request for the full "
        "extraction</a></p></div>"
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
        "<p class='picked'>This message: " + " ".join(mark_html(m) for m in marks) + "</p>"
        if marks
        else "<p class='muted'>Nothing in the selection picks this message.</p>"
    )
    body = (
        "<div class='pg-context'><p class='back'><a href='/selection'>Back to the selection "
        "audit</a></p><h1>Message in its conversation</h1>"
        + picked
        + "<p class='muted tiers'>Messages are observed; the phone's local time is derived from "
        "UTC and the phone's time zone. The message is highlighted.</p>"
        + conversation(view)
        + "</div>"
    )
    return page.wrap("Message in its conversation", body, wide=True)
