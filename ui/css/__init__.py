"""Page-level CSS, one module per page, so a change to one page's look never edits the same
lines as another's. Each module holds a CSS string; PAGE_CSS joins them after the shared theme
(ui/theme.py), and Page.wrap puts it on every page. Rules here are scoped to their page's own
markup, so a page module never restyles another page. Shared controls (buttons, fields,
checkboxes, tables) stay in ui/theme.py.
"""

from __future__ import annotations

from ui.css import (
    activity,
    cases,
    claim,
    claims,
    exhibits,
    help,
    identities,
    log,
    overview,
    selection,
    setup,
    timeline,
)

PAGE_CSS = "".join(
    m.CSS
    for m in (
        cases,
        overview,
        claims,
        claim,
        identities,
        exhibits,
        selection,
        timeline,
        log,
        activity,
        help,
        setup,
    )
)
