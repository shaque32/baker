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

Quotes are checked against the original text only. A translation is never citable text, and
neither is anything Baker rendered itself (a call line, a placeholder).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

VERSION = "1.1.0"


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def find_quote(quote: str, record_text: str) -> tuple[int, int] | None:
    """Return the (start, end) span of the first exact, word-aligned match in record_text, or
    None if the quote does not qualify."""
    if not quote or not record_text:
        return None
    q, text = quote, record_text
    if not any(ch.isalnum() for ch in q):
        return None
    start = text.find(q)
    while start != -1:
        end = start + len(q)
        left_ok = start == 0 or not (_is_word_char(text[start - 1]) and _is_word_char(q[0]))
        right_ok = end == len(text) or not (_is_word_char(text[end]) and _is_word_char(q[-1]))
        if left_ok and right_ok:
            return start, end
        start = text.find(q, start + 1)
    return None


def verify_quote(quote: str, record_text: str) -> bool:
    """True only if quote appears verbatim in the record's original text (QuoteVerifier)."""
    return find_quote(quote, record_text) is not None


def record_text(conn: sqlite3.Connection, record_id: str) -> str | None:
    """The text a quote about this record must appear in, read from the case database.

    Messages cite their original body and attachments their file name. A contact cites its
    observed name and number, rendered "name: number" exactly as retrieval shows it to the
    labeler (core/enrich/records.py). Calls have no words: their rendered line is Baker's own
    text, so nothing may be quoted from it and calls are judged by the deterministic checks.
    Returns None for unknown ids and for records with nothing quotable.
    """
    kind = record_id.split(":", 1)[0]
    if kind == "msg":
        row = conn.execute("SELECT body FROM messages WHERE id = ?", (record_id,)).fetchone()
    elif kind == "att":
        row = conn.execute(
            "SELECT file_name FROM attachments WHERE id = ?", (record_id,)
        ).fetchone()
    elif kind == "contact":
        row = conn.execute(
            "SELECT coalesce(name, '(no name)') || ': ' || identifier FROM contacts WHERE id = ?",
            (record_id,),
        ).fetchone()
    else:
        return None
    return row[0] if row and row[0] is not None else None


def verify_record_quote(conn: sqlite3.Connection, record_id: str, quote: str) -> bool:
    """Check a quote against the record's original text as stored, never a rendered copy."""
    text = record_text(conn, record_id)
    return text is not None and verify_quote(quote, text)


def create(conn: sqlite3.Connection) -> Callable[[str, str], bool]:
    """Pipeline hook: the QuoteVerifier."""
    return verify_quote
