"""Exhibits in the case database: add, match, load, remove.

An exhibit is the expert's paste of a government exhibit's quoted messages. It is stored exactly
as pasted and never edited. Adding or removing one is an expert action in the audit log.
Its excerpts and matches are derived: match_exhibit() deletes and rewrites them, so a new import
or a new matcher version is applied by matching again. Every match written here passed
core/restore/match.verify against the stored message body; nothing else is ever written.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from core.contracts import (
    ExcerptSplit,
    Exhibit,
    ExhibitExcerpt,
    ExhibitMatch,
    MatchMethod,
    SourceRef,
    excerpt_id,
    exhibit_id,
    exhibit_match_id,
)
from core.restore.match import MATCHER_VERSION, Found, Index, find
from core.review import audit_log

Clock = Callable[[], datetime]
MAX_EXHIBIT_CHARS = 100_000  # the review screen's form limit allows this much Cyrillic
MAX_LABEL_CHARS = 120
_BLANK_LINE_RE = re.compile(r"\n[ \t\f\v\r ]*\n")


class ExhibitError(Exception):
    pass


def _now(clock: Clock | None) -> datetime:
    return (clock or (lambda: datetime.now(UTC)))()


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- splitting


def split_excerpts(text: str, split: ExcerptSplit) -> list[tuple[int, int]]:
    """(start, end) of each quoted message in the exhibit text, trimmed of surrounding spaces.

    line: every line is one message. block: blank lines separate messages, so a message that
    runs over several lines stays whole. Parts with no letter or digit are skipped.
    """
    if split is ExcerptSplit.LINE:
        bounds, pos = [], 0
        for line in text.splitlines(keepends=True):
            bounds.append((pos, pos + len(line)))
            pos += len(line)
    else:
        bounds, pos = [], 0
        for m in _BLANK_LINE_RE.finditer(text):
            bounds.append((pos, m.start()))
            pos = m.end()
        bounds.append((pos, len(text)))
    out = []
    for a, b in bounds:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if any(ch.isalnum() for ch in text[a:b]):
            out.append((a, b))
    return out


# ---------------------------------------------------------------- what was searched


def searched_sources(conn: sqlite3.Connection) -> list[tuple]:
    """(id, file_name, fidelity, extraction_type, messages, first ts_utc, last ts_utc) for each
    source with messages, in id order."""
    return list(
        conn.execute(
            "SELECT s.id, s.file_name, s.fidelity, s.extraction_type, COUNT(m.id),"
            " MIN(m.ts_utc), MAX(m.ts_utc) FROM sources s JOIN messages m ON m.source_id = s.id"
            " GROUP BY s.id ORDER BY s.id"
        )
    )


FIDELITY_WORDS = {
    "curated_report": "examiner-curated report",
    "full_extraction": "full extraction",
    "unknown": "coverage unknown",
}


def searched_statement(conn: sqlite3.Connection) -> tuple[str, tuple[str, ...]]:
    """What a search covers, in plain words, and the ids of the sources searched."""
    srcs = searched_sources(conn)
    if not srcs:
        return (
            "No messages are imported in this case, so nothing was searched.",
            (),
        )
    total = sum(s[4] for s in srcs)
    parts = []
    for _sid, name, fidelity, extraction, n, first, last in srcs:
        span = f", {first[:10]} to {last[:10]} UTC" if first and last else ""
        parts.append(
            f"{name} ({FIDELITY_WORDS.get(fidelity, fidelity)}, {extraction.replace('_', ' ')}"
            f" extraction, {n:,} messages{span})"
        )
    text = (
        f"Searched the text of {total:,} messages in {len(srcs)} source"
        f"{'' if len(srcs) == 1 else 's'}: {'; '.join(parts)}. Matching tried exact, then "
        "tolerant (letter case, spacing and line breaks, quote and dash styles, Unicode form), "
        "then Cyrillic-Latin transliteration. Only message text was searched, not translations, "
        f"attachments, call logs, contacts or images. Matcher {MATCHER_VERSION}."
    )
    return text, tuple(s[0] for s in srcs)


# ---------------------------------------------------------------- writing


def add_exhibit(
    conn: sqlite3.Connection,
    label: str,
    text: str,
    split: ExcerptSplit,
    actor: str,
    paragraph_id: str | None = None,
    clock: Clock | None = None,
) -> Exhibit:
    """Store a pasted exhibit as an expert action, then match it."""
    if not actor.startswith("expert:") or len(actor) <= len("expert:"):
        raise ExhibitError("an exhibit is added by an expert")
    label = " ".join(label.split())
    if not label or len(label) > MAX_LABEL_CHARS:
        raise ExhibitError(f"name the exhibit (up to {MAX_LABEL_CHARS} characters)")
    if not text.strip():
        raise ExhibitError("paste the exhibit's quoted messages")
    if len(text) > MAX_EXHIBIT_CHARS:
        raise ExhibitError(f"the exhibit text is longer than {MAX_EXHIBIT_CHARS:,} characters")
    if not split_excerpts(text, split):
        raise ExhibitError("the exhibit text has no words to search for")
    if paragraph_id is not None and (
        conn.execute("SELECT 1 FROM govdoc_paragraphs WHERE id = ?", (paragraph_id,)).fetchone()
        is None
    ):
        raise ExhibitError("no such paragraph in the government document")
    now = _now(clock)
    ex = Exhibit(
        id=exhibit_id(label, text),
        label=label,
        paragraph_id=paragraph_id,
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        split=split,
        added_by=actor,
        added_at_utc=now,
    )
    if conn.execute("SELECT 1 FROM exhibits WHERE id = ?", (ex.id,)).fetchone():
        raise ExhibitError("this exhibit is already in the case")
    with conn:
        conn.execute(
            "INSERT INTO exhibits (id, label, paragraph_id, text, sha256, split, added_by,"
            " added_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ex.id, ex.label, ex.paragraph_id, ex.text, ex.sha256, ex.split.value, actor)
            + (_iso(now),),
        )
        audit_log.append(
            conn,
            now,
            actor,
            "exhibit_add",
            {
                "exhibit_id": ex.id,
                "label": ex.label,
                "sha256": ex.sha256,
                "split": ex.split.value,
                "paragraph_id": ex.paragraph_id,
            },
        )
        _match(conn, ex, Index.from_db(conn), now)
    return ex


def remove_exhibit(
    conn: sqlite3.Connection, exhibit_id_: str, actor: str, clock: Clock | None = None
) -> None:
    if not actor.startswith("expert:") or len(actor) <= len("expert:"):
        raise ExhibitError("an exhibit is removed by an expert")
    ex = load_exhibit(conn, exhibit_id_)
    if ex is None:
        raise ExhibitError("no such exhibit")
    now = _now(clock)
    with conn:
        _clear(conn, ex.id)
        conn.execute("DELETE FROM exhibits WHERE id = ?", (ex.id,))
        audit_log.append(
            conn, now, actor, "exhibit_remove", {"exhibit_id": ex.id, "label": ex.label}
        )


def match_exhibits(
    conn: sqlite3.Connection, exhibit_ids: list[str] | None = None, clock: Clock | None = None
) -> int:
    """Match exhibits again (all of them by default), against the messages imported now."""
    exhibits = [e for e in load_exhibits(conn) if exhibit_ids is None or e.id in exhibit_ids]
    if not exhibits:
        return 0
    index = Index.from_db(conn)
    now = _now(clock)
    with conn:
        for ex in exhibits:
            _match(conn, ex, index, now)
    return len(exhibits)


def _clear(conn: sqlite3.Connection, ex_id: str) -> None:
    conn.execute(
        "DELETE FROM exhibit_matches WHERE excerpt_id IN"
        " (SELECT id FROM exhibit_excerpts WHERE exhibit_id = ?)",
        (ex_id,),
    )
    conn.execute("DELETE FROM exhibit_excerpts WHERE exhibit_id = ?", (ex_id,))


def _match(conn: sqlite3.Connection, ex: Exhibit, index: Index, now: datetime) -> None:
    """Rewrite one exhibit's excerpts and matches. Runs inside the caller's transaction."""
    _clear(conn, ex.id)
    searched, source_ids = searched_statement(conn)
    matched = not_found = dropped = 0
    for seq, (a, b) in enumerate(split_excerpts(ex.text, ex.split), start=1):
        text = ex.text[a:b]
        outcome = find(text, index)
        dropped += outcome.dropped
        statement = searched
        if outcome.total > len(outcome.found):
            statement += (
                f" Found in {outcome.total:,} messages; the first {len(outcome.found)} are shown,"
                " so this text is too common to place on its own."
            )
        exc = ExhibitExcerpt(
            id=excerpt_id(ex.id, seq),
            exhibit_id=ex.id,
            seq=seq,
            char_start=a,
            char_end=b,
            text=text,
            searched=statement,
            source_ids=source_ids,
            matcher_version=MATCHER_VERSION,
        )
        conn.execute(
            "INSERT INTO exhibit_excerpts (id, exhibit_id, seq, char_start, char_end, text,"
            " searched, source_ids_json, matcher_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                exc.id,
                ex.id,
                seq,
                a,
                b,
                text,
                statement,
                json.dumps(list(source_ids)),
                MATCHER_VERSION,
            ),
        )
        for f in outcome.found:
            _insert_match(conn, exc.id, f)
        matched += bool(outcome.found)
        not_found += not outcome.found
    audit_log.append(
        conn,
        now,
        "system",
        "exhibit_match",
        {
            "exhibit_id": ex.id,
            "matcher_version": MATCHER_VERSION,
            "excerpts_found": matched,
            "excerpts_not_found": not_found,
            "matches_failed_verification": dropped,
            "source_ids": list(source_ids),
        },
    )


def _insert_match(conn: sqlite3.Connection, exc_id: str, f: Found) -> None:
    m = ExhibitMatch(
        id=exhibit_match_id(exc_id, f.record_id),
        excerpt_id=exc_id,
        record_id=f.record_id,
        ref=f.ref,
        method=f.method,
        spans=f.spans,
        excerpt_spans=f.excerpt_spans,
        matcher_version=MATCHER_VERSION,
    )
    conn.execute(
        "INSERT INTO exhibit_matches (id, excerpt_id, record_id, source_id, locator, method,"
        " spans_json, excerpt_spans_json, matcher_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            m.id,
            exc_id,
            m.record_id,
            m.ref.source_id,
            m.ref.locator,
            m.method.value,
            json.dumps([list(s) for s in m.spans]),
            json.dumps([list(s) for s in m.excerpt_spans]),
            MATCHER_VERSION,
        ),
    )


# ---------------------------------------------------------------- reading


def _exhibit(r: tuple) -> Exhibit:
    return Exhibit(
        id=r[0],
        label=r[1],
        paragraph_id=r[2],
        text=r[3],
        sha256=r[4],
        split=ExcerptSplit(r[5]),
        added_by=r[6],
        added_at_utc=datetime.fromisoformat(r[7].replace("Z", "+00:00")),
    )


_EXHIBIT_COLS = "id, label, paragraph_id, text, sha256, split, added_by, added_at_utc"


def has_restore_tables(conn: sqlite3.Connection) -> bool:
    """False for a case database made before Context Restore (contracts 0.3.0)."""
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'exhibit_matches'"
        ).fetchone()
        is not None
    )


def load_exhibits(conn: sqlite3.Connection) -> list[Exhibit]:
    if not has_restore_tables(conn):
        return []
    rows = conn.execute(f"SELECT {_EXHIBIT_COLS} FROM exhibits ORDER BY added_at_utc, id")  # noqa: S608
    return [_exhibit(r) for r in rows]


def load_exhibit(conn: sqlite3.Connection, ex_id: str) -> Exhibit | None:
    r = conn.execute(f"SELECT {_EXHIBIT_COLS} FROM exhibits WHERE id = ?", (ex_id,)).fetchone()  # noqa: S608
    return _exhibit(r) if r else None


_EXCERPT_COLS = (
    "id, exhibit_id, seq, char_start, char_end, text, searched, source_ids_json, matcher_version"
)


def _excerpt(r: tuple) -> ExhibitExcerpt:
    return ExhibitExcerpt(
        id=r[0],
        exhibit_id=r[1],
        seq=r[2],
        char_start=r[3],
        char_end=r[4],
        text=r[5],
        searched=r[6],
        source_ids=tuple(json.loads(r[7])),
        matcher_version=r[8],
    )


def load_excerpts(conn: sqlite3.Connection, ex_id: str) -> list[ExhibitExcerpt]:
    rows = conn.execute(
        f"SELECT {_EXCERPT_COLS} FROM exhibit_excerpts WHERE exhibit_id = ? ORDER BY seq",  # noqa: S608
        (ex_id,),
    )
    return [_excerpt(r) for r in rows]


def load_excerpt(conn: sqlite3.Connection, exc_id: str) -> ExhibitExcerpt | None:
    r = conn.execute(
        f"SELECT {_EXCERPT_COLS} FROM exhibit_excerpts WHERE id = ?",  # noqa: S608
        (exc_id,),
    ).fetchone()
    return _excerpt(r) if r else None


def _match_row(r: tuple) -> ExhibitMatch:
    return ExhibitMatch(
        id=r[0],
        excerpt_id=r[1],
        record_id=r[2],
        ref=SourceRef(source_id=r[3], locator=r[4]),
        method=MatchMethod(r[5]),
        spans=tuple(tuple(s) for s in json.loads(r[6])),
        excerpt_spans=tuple(tuple(s) for s in json.loads(r[7])),
        matcher_version=r[8],
    )


_MATCH_COLS = (
    "x.id, x.excerpt_id, x.record_id, x.source_id, x.locator, x.method, x.spans_json,"
    " x.excerpt_spans_json, x.matcher_version"
)


def load_matches(conn: sqlite3.Connection, exc_id: str) -> list[ExhibitMatch]:
    rows = conn.execute(
        f"SELECT {_MATCH_COLS} FROM exhibit_matches x JOIN messages m ON m.id = x.record_id"  # noqa: S608
        " WHERE x.excerpt_id = ? ORDER BY x.source_id, m.ts_utc, x.record_id",
        (exc_id,),
    )
    return [_match_row(r) for r in rows]


def load_match(conn: sqlite3.Connection, match_id: str) -> ExhibitMatch | None:
    r = conn.execute(
        f"SELECT {_MATCH_COLS} FROM exhibit_matches x WHERE x.id = ?",  # noqa: S608
        (match_id,),
    ).fetchone()
    return _match_row(r) if r else None


def stale_reason(conn: sqlite3.Connection, ex_id: str) -> str | None:
    """Why an exhibit's stored matches may be out of date, or None if they are current."""
    excerpts = load_excerpts(conn, ex_id)
    if not excerpts:
        return "This exhibit has not been searched yet."
    if any(x.matcher_version != MATCHER_VERSION for x in excerpts):
        return "It was searched with an older matcher version."
    _, now_ids = searched_statement(conn)
    if set(excerpts[0].source_ids) != set(now_ids):
        return "Sources were imported or removed after it was searched."
    return None
