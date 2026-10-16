"""Verbatim quote check (QuoteVerifier).

A stance label's quote becomes evidence only if it appears, character for character, in the
record's original text: an exact substring, with no normalization of any kind. No case folding,
no whitespace collapsing, no ellipsis stitching, no translation, not even Unicode NFC (an
accent typed as a separate combining mark differs from a precomposed one, and the quote is
discarded). This is exactly the rule core/audit/invariants.py re-checks, so a quote that
passes here can never stop the run there.

Two further rules stop a quote that is technically a substring from passing as evidence:
- it must contain at least one letter or digit (no quoting punctuation or whitespace);
- it must start and end on a word boundary, so "package" cannot be cut out of "packages" and
  "its done" cannot be cut out of "bits done".

Quotes are checked against the original text only. A translation is never citable text.
Contacts, calls and attachments have no words of their own: their text is the line
core.enrich.records renders and the labeler is shown ("Marc Garage: +1...", "outgoing Phone call
from +1... to +1..., duration 84 s"). A quote from such a line must take in a letter or digit of
one of the record's own fields (cites_record). Baker's words in the line (" call from ",
", duration ") and its placeholders for a missing field ("(no name)", "unknown",
"(no file name)") cannot verify a quote by themselves.

VERSION is the version of the whole quote check: the text a quote is checked against
(core.enrich.records), the matching and the own-field rule here, and the stored re-check
(core.audit.invariants.quote_is_verbatim). Bump it on any change to which quotes pass. Every
audit run records it (core.pipeline) and the report prints it beside the rule version.
1.2.0 (#76): contacts and calls are checked as the labeler sees them, and a quote of Baker's
words or placeholders alone fails.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Sequence

from core.enrich import records

VERSION = "1.2.0"


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def find_quotes(quote: str, record_text: str) -> Iterator[tuple[int, int]]:
    """Every exact, word-aligned match of the quote in record_text, as (start, end) spans; none if
    the quote does not qualify."""
    if not quote or not record_text:
        return
    q, text = quote, record_text
    if not any(ch.isalnum() for ch in q):
        return
    start = text.find(q)
    while start != -1:
        end = start + len(q)
        left_ok = start == 0 or not (_is_word_char(text[start - 1]) and _is_word_char(q[0]))
        right_ok = end == len(text) or not (_is_word_char(text[end]) and _is_word_char(q[-1]))
        if left_ok and right_ok:
            yield start, end
        start = text.find(q, start + 1)


def find_quote(quote: str, record_text: str) -> tuple[int, int] | None:
    """Return the (start, end) span of the first exact, word-aligned match in record_text, or
    None if the quote does not qualify."""
    return next(find_quotes(quote, record_text), None)


def verify_quote(quote: str, record_text: str) -> bool:
    """True only if quote appears verbatim in the record's original text (QuoteVerifier)."""
    return find_quote(quote, record_text) is not None


def cites_record(quote: str, record_text: str, own: Sequence[records.Span]) -> bool:
    """True if the quote matches record_text verbatim and word-aligned (find_quotes) at a place
    that takes in a letter or digit of the record's own fields (own: their (start, end) spans in
    record_text). A quote of only Baker's words or a placeholder, such as "(no name)", fails.
    Passing here implies passing verify_quote."""
    return any(
        record_text[i].isalnum()
        for start, end in find_quotes(quote, record_text)
        for a, b in own
        for i in range(max(a, start), min(b, end))
    )


def record_text(conn: sqlite3.Connection, record_id: str) -> str | None:
    """The text a quote about this record must appear in: the record as the labeler is shown it
    (core.enrich.records). None for unknown ids."""
    return records.record_text(conn, record_id)


def verify_record_quote(conn: sqlite3.Connection, record_id: str, quote: str) -> bool:
    """The full check on one stored record: verbatim, word-aligned, and citing its own fields."""
    rec = records.get_record(conn, record_id)
    return rec is not None and cites_record(quote, rec.text or "", rec.own)


def create(conn: sqlite3.Connection) -> Callable[[str, str], bool]:
    """Pipeline hook: the QuoteVerifier."""
    return verify_quote
