"""Timeline check and Gaps pages of the review screen. Pure functions of the case database and
the case's timeline settings, rendered with the report's own fragments (core/report/timeline.py),
so the screen and the report never disagree. Changing a setting goes through
core/timeline/settings.py, which writes the audit log.
"""

from __future__ import annotations

import sqlite3

from core.report.timeline import (
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
    form = page.form(
        "/timeline/settings",
        "<div class='settings-head'>"
        "<p class='muted'>Used by the Timeline and Gaps checks. Your name is recorded in the audit "
        "log with any change.</p></div><div class='fields'>"
        "<label class='field'>Time tolerance<span class='unit-input'>"
        f"<input type='number' name='tolerance_min' required inputmode='numeric' "
        f"min='{TOLERANCE_RANGE[0]}' max='{TOLERANCE_RANGE[1]}' value='{s.tolerance_min}'>"
        "<span class='unit'>min</span></span><small>How far a phone record may sit from a time "
        "the document states before the Timeline shows the difference.</small></label>"
        "<label class='field'>Shortest quiet stretch<span class='unit-input'>"
        f"<input type='number' name='gap_hours' required inputmode='numeric' "
        f"min='{GAP_RANGE[0]}' max='{GAP_RANGE[1]}' value='{s.gap_hours}'>"
        "<span class='unit'>hours</span></span><small>Gaps lists only stretches with no "
        "messages or calls at least this long.</small></label>"
        "</div><div class='actions'><button type='submit' class='primary'>Save settings</button>"
        "</div>",
        cls="box settings",
        back=back,
    )
    return (
        "<details class='case-settings'><summary>Case settings: tolerance "
        f"{s.tolerance_min} min, shortest quiet stretch {s.gap_hours} h</summary>{form}</details>"
    )


def _count(n: int) -> str:
    return f" <span class='n'>{n}</span>"


def _folds(*details: str) -> str:
    """The page's explanation and its settings, folded side by side; an open one takes the row."""
    return f"<div class='tl-folds'>{''.join(details)}</div>"


def timeline_page(conn: sqlite3.Connection, page: Page, s: Settings) -> str:
    views = compute(conn, s, gaps=False)
    rows = views.rows
    folds = _folds(
        "<details class='more'><summary>How Mabillon reads the dates</summary><p>Code reads the "
        "dates and ties a record to a statement only by the quoted words or call number in the "
        "same sentence. Times without a zone are read in the phone's own zone, never in the "
        "offset a report printed.</p></details>",
        _settings_form(page, s, "/timeline"),
    )
    out = [
        "<div class='pg-timeline'><h1>The document's clock against the phones'</h1>"
        "<p class='lede'>Each date and time the government document states, beside the phone "
        "records' own timestamps. A difference is for you to weigh; it does not change any "
        "verdict.</p>",
    ]
    if not rows:
        out.append(folds)
        out.append(
            "<p class='muted'>No date or time to show. Import the government document on "
            "<a href='/setup'>Set up and run</a>.</p></div>"
        )
        return page.wrap("Timeline check", "".join(out), wide=True)
    flagged = [r for r in rows if r.status in FLAGGED]
    out.append(f"<p class='tl-summary'>{e(timeline_summary(rows, s))}</p>")
    out.append(folds)
    if flagged:
        out.append(
            f"<h2>Differences{_count(len(flagged))}</h2>" + timeline_rows(flagged, views.data)
        )
    rest = [r for r in rows if r.status not in FLAGGED and r.status != "not_compared"]
    if rest:
        out.append(f"<h2>In time order{_count(len(rest))}</h2>" + timeline_rows(rest, views.data))
    skipped = [r for r in rows if r.status == "not_compared"]
    if skipped:
        out.append(
            f"<h2>Not compared{_count(len(skipped))}</h2><p class='muted'>Dates Mabillon could "
            "not read plainly, such as a numeric date that reads either way. Mabillon never "
            "picks a month and day order.</p>" + timeline_rows(skipped, views.data)
        )
    out.append("</div>")
    return page.wrap("Timeline check", "".join(out), wide=True)


def gaps_page(conn: sqlite3.Connection, page: Page, s: Settings) -> str:
    views = compute(conn, s, rows=False)
    out = [
        "<div class='pg-gaps'><h1>Where the records go quiet</h1><p class='lede'>Stretches "
        "with no messages or calls, on each phone, in each app and in each thread, measured "
        f"against that series' own pace.</p><p class='caveat'>{e(NOT_FOUND)}</p>",
        _folds(
            "<details class='more'><summary>When a stretch is listed</summary><p>A stretch is "
            "listed when it lasts at least the shortest quiet stretch in the case settings "
            f"({s.gap_hours} h) and the series' pace would put at least {MIN_EXPECTED} records "
            "in it.</p></details>",
            _settings_form(page, s, "/gaps"),
        ),
    ]
    if not views.data.phones:
        out.append(
            "<p class='muted'>No extraction report is imported yet. Import one on "
            "<a href='/setup'>Set up and run</a>.</p>"
        )
    else:
        out.append(gap_lists(views))
    out.append("</div>")
    return page.wrap("Gaps", "".join(out), wide=True)
