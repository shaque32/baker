"""Messages the extraction marks as forwarded, or that carry a forwarded or quoted original.

Each importer lists such messages, in full, in its coverage payload under `forwarded_records`.
Where the case database has the signed `messages.forwarded` and `messages.forwarded_from_raw`
columns (schema change signed by Arsh 2026-10-16), the importer also marks the message there,
with the original author when the source names one. A case made before those columns existed
still has the coverage list. Everything downstream reads them from here and fails closed:

- the pipeline stores a model's "supports" or "contradicts" on one as "complicates", so it can
  neither make a claim supported nor contradicted, and keeps it in front of the expert;
- a check whose outcome rests on one is inconclusive, and the sender check never names the
  forwarder as the one who wrote the words;
- the claim page and the report put a warning on the claim and on the record.

Three reasons are kept: `embedded_copy` (a forwarded or quoted message carried inside another
message, which the UFDR importer imports, one level deep, as a record of its own at the
carrying message's locator plus `/Embedded[n]`), `forwarded` (the extraction marks the message
forwarded) and `embedded` (the message carries another message inside it; a message nested
deeper than one level is not imported). An embedded copy is also marked forwarded in the
signed columns, but its locator makes it `embedded_copy`, so it is never described as sent by
whoever forwarded it. Deterministic checks leave embedded copies out of their inputs
(core/audit/checks/_common.NOT_COPY), so nothing is counted twice.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

PAYLOAD_KEY = "forwarded_records"
REASONS = ("embedded_copy", "forwarded", "embedded")  # first wins
COPY_STEP = "/Embedded["  # locator step of a copy imported from inside another message
COPY_LIKE = "%/Embedded[%"  # the same, as an SQL LIKE pattern ('[' is literal in SQLite LIKE)
RULE_VERSION = "1"  # how forwarded records are handled; named in every note below

STANCE_NOTE = (
    "Recorded as complicates: the extraction marks this message as forwarded or as carrying a "
    "forwarded or quoted message, or it is a forwarded or quoted copy carried inside another "
    "message, and Baker has not verified who first wrote the words (even "
    "where the extraction names an original author), so it "
    f"cannot support or contradict the claim (forwarded rule {RULE_VERSION}). Model's label: "
)
RECORD_NOTE = {
    "forwarded": "Forwarded: shown as sent by whoever forwarded it; who first wrote it is not "
    "recorded.",
    "embedded": "Carries a forwarded or quoted message, imported separately as a record of its "
    "own (a message nested deeper is not imported); who wrote which words is not verified.",
    "embedded_copy": "Forwarded or quoted copy carried inside another message, imported as its "
    "own record; who first wrote it is not verified.",
}


def has_columns(conn: sqlite3.Connection) -> bool:
    """The case database has the signed forwarded columns (a case made before them does not)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
    return {"forwarded", "forwarded_from_raw"} <= cols


def affected(conn: sqlite3.Connection) -> dict[str, str]:
    """Record id -> reason ('forwarded' wins over 'embedded') for every import in the case."""
    out: dict[str, str] = {}
    for (payload_json,) in conn.execute("SELECT payload_json FROM source_coverage"):
        try:
            listed = json.loads(payload_json).get(PAYLOAD_KEY) or {}
        except (ValueError, AttributeError):
            continue
        for reason in reversed(REASONS):
            for rid in listed.get(reason, []):
                out[rid] = reason
    if has_columns(conn):
        for (rid,) in conn.execute("SELECT id FROM messages WHERE forwarded = 1"):
            out[rid] = "forwarded"
    # a copy imported from inside another message wins, whatever else marks it
    for (rid,) in conn.execute("SELECT id FROM messages WHERE locator LIKE ?", (COPY_LIKE,)):
        out[rid] = "embedded_copy"
    return out


def mark(conn: sqlite3.Connection, listed: dict[str, list[str]], authors: dict[str, str]) -> None:
    """Mark the importer's forwarded messages in the signed columns, when the case has them.
    `authors` maps a message id to its original author as the source wrote it."""
    if not has_columns(conn):
        return
    conn.executemany(
        "UPDATE messages SET forwarded = 1, forwarded_from_raw = ? WHERE id = ?",
        [
            (authors.get(mid), mid)
            for mid in dict.fromkeys(
                [*listed.get("forwarded", []), *listed.get("embedded_copy", [])]
            )
        ],
    )


def original_author(conn: sqlite3.Connection, record_id: str) -> str | None:
    """Who first wrote a forwarded message, as the source wrote it; None when it does not say."""
    if not has_columns(conn):
        return None
    row = conn.execute(
        "SELECT forwarded_from_raw FROM messages WHERE id = ?", (record_id,)
    ).fetchone()
    return row[0] if row else None


# The warning on a forwarded record whose original author the source names. The author is the
# source's text, so callers render it as a cited span between these two parts, never as Baker's
# own words (it can be anything, such as Telegram's "Deleted Account").
AUTHOR_NOTE = (
    "Forwarded: shown as sent by whoever forwarded it; the extraction names ",
    " as the original author, which Baker has not checked.",
)


def _shown_sender(conn: sqlite3.Connection, record_id: str) -> str | None:
    """A message's sender as Baker shows it (identifier, then display name in brackets)."""
    r = conn.execute(
        "SELECT a.identifier, a.display_name FROM messages m"
        " LEFT JOIN accounts a ON a.id = m.sender_account_id WHERE m.id = ?",
        (record_id,),
    ).fetchone()
    if not r:
        return None
    return " ".join(x for x in (r[0], f"({r[1]})" if r[1] else None) if x) or None


def parent_id(conn: sqlite3.Connection, record_id: str) -> str | None:
    """The record that carried an embedded copy, from the copy's locator."""
    r = conn.execute(
        "SELECT source_id, locator FROM messages WHERE id = ?", (record_id,)
    ).fetchone()
    if not r or COPY_STEP not in r[1]:
        return None
    return f"msg:{r[0]}:{r[1].rsplit(COPY_STEP, 1)[0]}"


def record_note(conn: sqlite3.Connection, record_id: str, reason: str) -> list[tuple[str, bool]]:
    """The warning on one affected record, as parts: (text, cited). A cited part is the
    source's own text (a sender or author as written) and is rendered as a quote, never as
    Baker's words. The claim page and the report both render this."""
    if reason == "embedded_copy":
        parent = parent_id(conn, record_id) or "(not found)"
        sender = _shown_sender(conn, record_id)
        carrier = _shown_sender(conn, parent) if parent else None
        parts: list[tuple[str, bool]] = [
            (
                f"Forwarded or quoted copy carried inside record {parent}, imported as its own "
                "record. ",
                False,
            )
        ]
        if sender:
            parts += [
                ("The sender shown, ", False),
                (sender, True),
                (
                    ", is the one the extraction names for the embedded message, not verified; ",
                    False,
                ),
            ]
        else:
            parts.append(("The extraction names no sender for the embedded message; ", False))
        if carrier:
            parts += [
                ("the message that carried it was sent by ", False),
                (carrier, True),
                (".", False),
            ]
        else:
            parts.append(("the message that carried it names no sender.", False))
        return parts
    author = original_author(conn, record_id) if reason == "forwarded" else None
    if author:
        return [(AUTHOR_NOTE[0], False), (author, True), (AUTHOR_NOTE[1], False)]
    return [(RECORD_NOTE[reason], False)]


def record_note_text(conn: sqlite3.Connection, record_id: str, reason: str) -> str:
    """record_note as one plain sentence, cited parts in double quotes."""
    return "".join(f'"{t}"' if cited else t for t, cited in record_note(conn, record_id, reason))


def copy_label(locator: str) -> str | None:
    """A short label for a message listed in a thread or timeline when it is a copy imported
    from inside another message; None for any other record."""
    if COPY_STEP not in locator:
        return None
    return (
        f"Copy carried inside the message at {locator.rsplit(COPY_STEP, 1)[0]}; not a message "
        "sent at this point in the conversation."
    )


def among(found: dict[str, str], record_ids: Iterable[str]) -> list[str]:
    """The record ids that are affected, in order, each once."""
    return [r for r in dict.fromkeys(record_ids) if r in found]


def claim_warning(found: dict[str, str], record_ids: Iterable[str]) -> str | None:
    """One sentence for a claim whose evidence or checks rest on affected records."""
    hit = among(found, record_ids)
    if not hit:
        return None
    copies = [r for r in hit if found[r] == "embedded_copy"]
    if copies:
        return _copy_warning(len(hit) - len(copies), len(copies))
    n = len(hit)
    these = "this message" if n == 1 else f"these {n} messages"
    return (
        f"{n} record{'s' if n != 1 else ''} this claim's evidence or checks rest on "
        f"{'is a message' if n == 1 else 'are messages'} the extraction marks as forwarded or "
        f"as carrying a forwarded or quoted message. Baker shows {these} as sent by whoever "
        "forwarded or quoted, and has not verified who first wrote the words, even where the "
        "extraction names an original author, so "
        f"{'it' if n == 1 else 'they'} cannot support or contradict this claim. Check "
        f"{'it' if n == 1 else 'each'} in the extraction tool."
    )


def _copy_warning(marked: int, copies: int) -> str:
    """The claim warning when some of the records are copies imported from inside another
    message; `marked` counts the others (marked forwarded, or carrying such a message)."""
    n = marked + copies
    copy_words = (
        "is a forwarded or quoted copy carried inside another message, imported as its own record"
        if copies == 1
        else "are forwarded or quoted copies carried inside other messages, each imported as its "
        "own record"
    )
    if marked == 0:
        return (
            f"{n} record{'s' if n != 1 else ''} this claim's evidence or checks rest on "
            f"{copy_words}. Baker shows the sender the extraction names for "
            f"{'it' if n == 1 else 'each'}, which it has not verified, so "
            f"{'it' if n == 1 else 'they'} cannot support or contradict this claim. Check "
            f"{'it' if n == 1 else 'each'} in the extraction tool."
        )
    return (
        f"{n} records this claim's evidence or checks rest on are affected. {marked} "
        f"{'is a message' if marked == 1 else 'are messages'} the extraction marks as forwarded "
        "or as carrying a forwarded or quoted message, which Baker shows as sent by whoever "
        f"forwarded or quoted; {copies} {copy_words}, shown with the sender the extraction names "
        "for the embedded message. Baker has not verified who first wrote any of these words, "
        "even where the extraction names an original author, so they cannot support or "
        "contradict this claim. Check each in the extraction tool."
    )


def check_note(found: dict[str, str], record_ids: Iterable[str]) -> str | None:
    """Why a check that rests on affected records is inconclusive, or None."""
    hit = among(found, record_ids)
    if not hit:
        return None
    return (
        f"Inconclusive (forwarded rule {RULE_VERSION}): the outcome rests on "
        f"{', '.join(hit)}, which the extraction marks as forwarded or as carrying a forwarded "
        "or quoted message (or which are such a message, imported as its own record); Baker "
        "has not verified who first wrote those words."
    )
