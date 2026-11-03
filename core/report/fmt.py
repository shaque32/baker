"""The three HTML helpers every report section and every review-screen page use.

One copy, so the forbidden-word check (core/audit/invariants.py), which tells cited text from
the tool's own words by the exact `<span class="q">` and `<span class="said">` markup, sees the
same markup everywhere.
"""

from __future__ import annotations

import html


def e(text: object) -> str:
    """The tool's own words, escaped. None prints as nothing."""
    return html.escape("" if text is None else str(text))


def q(text: object) -> str:
    """A cited span: text from the government document or the evidence, not the tool's words."""
    return f'<span class="q">{html.escape(str(text))}</span>'


def said(text: object) -> str:
    """A reason or note an expert typed, as they wrote it. Never for Mabillon's or a model's
    text."""
    return f'<span class="said">{html.escape(str(text))}</span>'
