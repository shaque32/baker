"""Timeline check and Gaps pages of the review screen. Pure functions of the case database and
the case's timeline settings, rendered with the report's own fragments (core/report/timeline.py),
so the screen and the report never disagree. Changing a setting goes through
core/timeline/settings.py, which writes the audit log.
"""

from __future__ import annotations

import sqlite3

from core.report.timeline import (
    CSS,
    NOT_FOUND,
    compute,
    gap_lists,
    timeline_rows,
    timeline_summary,
)
from core.timeline.check import FLAGGED
from core.timeline.gaps import MIN_EXPECTED
from core.timeline.settings import GAP_RANGE, TOLERANCE_RANGE, Settings
from ui.pages import Page, e


def _settings_form(page: Page, s: Settings, back: str) -> str:
    return page.form(
        "/timeline/settings",
        "<strong>Case settings</strong> "
        f"<label>Time tolerance <input type='number' name='tolerance_min' required "
        f"min='{TOLERANCE_RANGE[0]}' max='{TOLERANCE_RANGE[1]}' value='{s.tolerance_min}' "
        "style='width:5em'> min</label> · "
        f"<label>Shortest quiet stretch <input type='number' name='gap_hours' required "
        f"min='{GAP_RANGE[0]}' max='{GAP_RANGE[1]}' value='{s.gap_hours}' style='width:5em'> "
        "h</label> <button type='submit'>Save</button>"
        "<div class='muted'>Your name is recorded in the audit log with any change.</div>",
        back=back,
    )


def timeline_page(conn: sqlite3.Connection, page: Page, s: Settings) -> str:
    views = compute(conn, s, gaps=False)
    rows = views.rows
    out = [
        f"<style>{CSS}</style>",
        "<div class='eyebrow'>Timeline check</div><h1>The document's clock against the "
        "phones'</h1><p>Each date and time the government document states, beside the phone "
        "records' own timestamps. Code reads the dates and ties a record to a statement only by "
        "the quoted words or call number in the same sentence. Times without a zone are read "
        "in the phone's own zone, never in the offset a report printed. A difference is for "
        "you to weigh; it does not change any verdict.</p>",
        _settings_form(page, s, "/timeline"),
    ]
    if not rows:
        out.append(
            "<p class='muted'>No date or time to show. Import the government document on "
            "<a href='/setup'>Set up and run</a>.</p>"
        )
        return page.wrap("Timeline check", "".join(out), wide=True)
    flagged = [r for r in rows if r.status in FLAGGED]
    out.append(f"<div class='flash'>{e(timeline_summary(rows, s))}</div>")
    if flagged:
        out.append("<h2>Differences</h2>" + timeline_rows(flagged, views.data))
    rest = [r for r in rows if r.status not in FLAGGED and r.status != "not_compared"]
    if rest:
        out.append("<h2>In time order</h2>" + timeline_rows(rest, views.data))
    skipped = [r for r in rows if r.status == "not_compared"]
    if skipped:
        out.append(
            "<h2>Not compared</h2><p class='muted'>Dates Baker could not read plainly, such as "
            "a numeric date that reads either way. Baker never picks a month and day order.</p>"
            + timeline_rows(skipped, views.data)
        )
    return page.wrap("Timeline check", "".join(out), wide=True)


def gaps_page(conn: sqlite3.Connection, page: Page, s: Settings) -> str:
    views = compute(conn, s, rows=False)
    out = [
        f"<style>{CSS}</style>",
        "<div class='eyebrow'>Gaps</div><h1>Where the records go quiet</h1><p>Stretches with "
        "no messages or calls, on each phone, in each app and in each thread, measured against "
        "that series' own pace. A stretch is listed when it lasts at least the shortest "
        f"stretch below and the series' pace would put at least {MIN_EXPECTED} records in it. "
        f"{e(NOT_FOUND)}</p>",
        _settings_form(page, s, "/gaps"),
    ]
    if not views.data.phones:
        out.append(
            "<p class='muted'>No extraction report is imported yet. Import one on "
            "<a href='/setup'>Set up and run</a>.</p>"
        )
    else:
        out.append(gap_lists(views))
    return page.wrap("Gaps", "".join(out), wide=True)
