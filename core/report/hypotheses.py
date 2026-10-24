"""Other explanations in HTML, shared by the claim page of the review screen and the report (the
same fragment, so the two never disagree).

Every name, message body, file name and the claim's own words go through q(), so the
forbidden-word check can tell them from the tool's own words. Tiers: each record that fits is
observed (its time on the phone's own clock is derived); the alternative itself is derived,
found by code. Nothing here is a verdict, and nothing here changes one.
"""

from __future__ import annotations

import html
from collections.abc import Callable

from core.hypotheses.explain import FAMILY_TEXT, Alternative, Fit
from core.identity.links import CITE_CLOSE, CITE_OPEN

INTRO = (
    "Other explanations the records raise, found by code with no model. Each is a lead for you "
    "to weigh, with the records that fit it. They are not findings and never change a verdict."
)

CSS = """
.alts { margin: 10px 0; }
.alt { border: 1px solid var(--line); border-left: 3px solid var(--unp-line);
  border-radius: 0 10px 10px 0; background: var(--card); padding: 8px 14px; margin: 8px 0; }
.alt h4 { margin: 2px 0 4px; font-size: 14px; font-weight: 600; }
.alt p { font-size: 14px; margin: 4px 0; }
.alt .fam { font: 500 10.5px var(--mono); letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--muted); }
.alt ul { margin: 6px 0; padding-left: 18px; font-size: 13px; }
.alt li { margin: 4px 0; }
.alt .meta { font: 400 11.5px var(--mono); color: var(--muted); word-break: break-all; }
.alt .searched { font-size: 12px; color: var(--muted); margin: 4px 0 0; }
"""


def _q(text: object) -> str:
    return f'<span class="q">{html.escape(str(text))}</span>'


def _e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def note_html(note: str) -> str:
    """Mabillon's words, with the case's own words inside shown as cited text."""
    out, rest = [], note
    while CITE_OPEN in rest:
        before, _, after = rest.partition(CITE_OPEN)
        cited, _, rest = after.partition(CITE_CLOSE)
        out.append(_e(before) + _q(cited))
    return "".join(out) + _e(rest)


def _fit(f: Fit, href: Callable[[Fit], str | None]) -> str:
    where = " ".join(x for x in (f.source_id, f.locator) if x)
    ids = " · ".join(dict.fromkeys(x for x in (where, f.record_id) if x))
    tier = "observed record" + (", local time derived" if f.local else "")
    target = href(f)
    look = f" · <a href='{_e(target)}'>See it in its conversation</a>" if target else ""
    when = f"{_e(f.when)} · " if f.when else ""
    text = _q(f.quote) if f.quote else _e(f.label)  # a call's label is Mabillon's words, not cited
    return (
        f"<li>{text}<br>{note_html(f.note)}<br><span class='meta'>{when}{_e(ids)} · "
        f"{tier}</span>{look}</li>"
    )


def alternatives_html(
    alts: list[Alternative], href: Callable[[Fit], str | None] = lambda f: None
) -> str:
    """The alternatives for one claim; '' when the records raise none."""
    if not alts:
        return ""
    out = [f"<div class='alts'><p class='muted'>{_e(INTRO)}</p>"]
    for a in alts:
        more = (
            f"<p class='muted'>Showing {len(a.fits)} of {a.total}.</p>"
            if a.total > len(a.fits)
            else ""
        )
        out.append(
            f"<div class='alt' data-kind='{_e(a.kind)}'><span class='fam'>derived · "
            f"{_e(FAMILY_TEXT[a.family])}</span><h4>{_e(a.title)}</h4><p>{note_html(a.summary)}</p>"
            "<ul>" + "".join(_fit(f, href) for f in a.fits) + "</ul>" + more
        )
        if a.searched:
            out.append(f"<p class='searched'>{note_html(a.searched)}</p>")
        out.append("</div>")
    out.append("</div>")
    return "".join(out)
