"""What the government picked out of the extraction, found by code. No model is involved.

Three kinds of pick:
- document: words a government-document paragraph puts in quotation marks ("..." or “...”),
  found in message bodies with the Context Restore matcher (core/restore/match.py: exact,
  tolerant and transliteration, every match re-verified against the stored body). Line breaks
  inside the quotation marks are read as spaces, because a PDF wraps lines where the quoted
  message had none. Quoted words that are a name in the case (a contact, an account's
  identifier or display name, a thread title, a person), fewer than two words, or marks with no
  letter or digit are not looked up, and the screen lists them as not looked up. A message whose
  whole text is such a quote may still be the one quoted, so it is kept as a hit.
- exhibit: each quoted message of an exhibit the expert pasted (Context Restore's excerpts),
  looked up again the same way, so every match is known and not only the ones Context Restore
  keeps.
- tag: messages a report marks with an examiner tag (messages.bookmarked = 1).

Placing a quote fails closed. Its words are looked for with every method of the matcher, not
only the first that finds something, and also as the same words with any punctuation between
them (Lookup.loose). It is placed only when every message they are found in is one message: a
single message, or copies of it on different sources (the same text, within COPY_WINDOW of each
other), at most MAX_PLACES of them. Otherwise Mabillon does not decide which message the document
means and says how often the words were found. Every message the words were found in is kept
(Lookup.hits), so a message that may be the one quoted is never counted as left out.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import combinations
from weakref import WeakKeyDictionary

from core.contracts import MatchMethod
from core.enrich.local_time import parse_utc
from core.identity.aliases import stored as stored_aliases
from core.restore.fold import fold
from core.restore.match import WORD_RE, Found, Index, core_groups, find_every, segments
from core.restore.store import load_excerpts, load_exhibits

MIN_WORDS = 2  # a single quoted word is a term or a name, not a quoted message
SHORT_WORDS = 6  # a quote not looked up is still matched to messages of at most this many words
MAX_PLACES = 4  # one message seen on more sources than this is not plausible; too common
COPY_WINDOW = timedelta(minutes=2)  # copies of one message on two phones, sent and received

QUOTE_RE = re.compile(r"\"([^\"]+)\"|“([^”]+)”")


@dataclass(frozen=True)
class Place:
    """One message a pick lands on."""

    record_id: str
    thread_id: str
    spans: tuple[tuple[int, int], ...] = ()  # the picked words in the message body; () for a tag
    method: MatchMethod | None = None  # how the words were found; None for a tag


@dataclass(frozen=True)
class Lookup:
    """One quote (a paragraph's quoted words, or one quoted message of an exhibit) and where
    code found it."""

    text: str  # as printed, line breaks read as spaces
    seq: int  # position in its paragraph or exhibit, from 1
    places: tuple[Place, ...] = ()  # one message, or its copies on other sources
    found: int = 0  # messages the matcher found the words in, in the whole case
    loose: int = 0  # more messages holding the same words with different punctuation
    skipped: str | None = None  # why the words were not looked up
    part: bool = False  # only the words after a colon or dash were found, not the whole quote
    span: tuple[int, int] | None = None  # in the paragraph text, quotation marks excluded
    hits: tuple[str, ...] = ()  # every message the words were found in, placed or not


@dataclass(frozen=True)
class Facts:
    """What decides whether two messages are copies of one message."""

    id: str
    thread_id: str
    source_id: str
    body: str  # whitespace folded
    utc: datetime | None


def paragraph_quotes(text: str) -> list[tuple[int, int, str]]:
    """(start, end, words) for each pair of quotation marks in a paragraph, in reading order."""
    out = []
    for m in QUOTE_RE.finditer(text):
        g = 1 if m.group(1) is not None else 2
        words = " ".join(m.group(g).split())
        if words:
            out.append((m.start(g), m.end(g), words))
    return out


def _key(text: str) -> str:
    return " ".join(text.split()).strip().lstrip("@").casefold()


def case_names(conn: sqlite3.Connection) -> set[str]:
    """Every name a quote may just be: contacts, account identifiers and display names, thread
    titles, persons and the other names the expert gave them, compared ignoring case, spacing
    and a leading '@'."""
    names: set[str] = set()
    for sql in (
        "SELECT name FROM contacts",
        "SELECT identifier FROM accounts",
        "SELECT display_name FROM accounts",
        "SELECT title FROM threads",
        "SELECT name FROM persons",
    ):
        names.update(_key(r[0]) for r in conn.execute(sql) if r[0])
    names.update(_key(a.alias) for a in stored_aliases(conn))  # a person's other names (#181)
    names.discard("")
    return names


def skip_reason(words: str, names: set[str]) -> str | None:
    """Why quoted words are not looked up in the messages, or None to look them up."""
    if _key(words) in names:
        return "a name in the case, not a quoted message"
    n = len(WORD_RE.findall(words))
    if n == 0:
        return "no letters or digits to look up"
    if n < MIN_WORDS:
        return "a single word, too short to place a message"
    return None


def _marks(folded: str) -> str:
    """A text with no letter or digit, as compared: its characters other than spaces, emoji skin
    tones aside (the tolerant fold already drops variation selectors)."""
    return "".join(
        ch for ch in folded if not ch.isspace() and not "\U0001f3fb" <= ch <= "\U0001f3ff"
    )


@dataclass
class _Words:
    """Every message of an index by its words (tolerant fold, letter case and marks aside)."""

    seq: list[str]  # per message, ' w1 w2 w3 ', for finding a run of words
    short: dict[tuple[str, ...], list[str]]  # messages of at most SHORT_WORDS words, by words
    marks: dict[str, list[str]]  # messages with no letter or digit, by their marks


_WORDS: WeakKeyDictionary[Index, _Words] = WeakKeyDictionary()


def _words_of(index: Index) -> _Words:
    w = _WORDS.get(index)
    if w is None:
        w = _Words([], defaultdict(list), defaultdict(list))
        for b, f in zip(index.bodies, index.folded("tolerant"), strict=True):
            words = WORD_RE.findall(f.text)
            w.seq.append(" " + " ".join(words) + " ")
            if not words:
                if key := _marks(f.text):
                    w.marks[key].append(b.record_id)
            elif len(words) <= SHORT_WORDS:
                w.short[tuple(words)].append(b.record_id)
        _WORDS[index] = w
    return w


def whole_messages(words: str, index: Index) -> tuple[str, ...]:
    """Messages whose whole text is the quoted words, letter case and punctuation aside; for a
    quote with no letter or digit ("?"), messages that are just those marks. A quote that is not
    looked up (a name, a single word, a mark) may still be one of them, so they are never counted
    as left out."""
    folded = fold(words).text
    key = tuple(WORD_RE.findall(folded))
    w = _words_of(index)
    if not key:
        marks = _marks(folded)
        return tuple(sorted(w.marks.get(marks, ()))) if marks else ()
    if len(key) > SHORT_WORDS:
        return ()
    return tuple(sorted(w.short.get(key, ())))


def same_words(text: str, index: Index) -> tuple[str, ...]:
    """Messages holding the text's words in a run, letter case and every mark between the words
    aside, so the same words with different punctuation count. The pieces around an ellipsis
    must come in order in one message, as in the matcher."""
    pieces = []
    for a, b in segments(text, 0, len(text)):
        words = WORD_RE.findall(fold(text[a:b]).text)
        if words:
            pieces.append(" " + " ".join(words) + " ")
    if not pieces:
        return ()
    out = []
    for b, seq in zip(index.bodies, _words_of(index).seq, strict=True):
        if pieces[0] not in seq:
            continue
        pos = 0
        for piece in pieces:
            i = seq.find(piece, pos)
            if i < 0:
                break
            pos = i + len(piece) - 1  # its closing space opens the next piece
        else:
            out.append(b.record_id)
    return tuple(sorted(out))


def facts(conn: sqlite3.Connection, record_ids: list[str]) -> dict[str, Facts]:
    if not record_ids:
        return {}
    marks = ",".join("?" * len(record_ids))
    rows = conn.execute(
        f"SELECT id, thread_id, source_id, body, ts_utc FROM messages WHERE id IN ({marks})",  # noqa: S608
        record_ids,
    )
    return {r[0]: Facts(r[0], r[1], r[2], " ".join(r[3].split()), parse_utc(r[4])) for r in rows}


def same_message(a: Facts, b: Facts) -> bool:
    """Two records are copies of one message: on different sources, the same text, and times
    within COPY_WINDOW. A record with no usable time is never called a copy."""
    return (
        a.source_id != b.source_id
        and a.body == b.body
        and a.utc is not None
        and b.utc is not None
        and abs(a.utc - b.utc) <= COPY_WINDOW
    )


def place(conn: sqlite3.Connection, found: list[Found]) -> tuple[Place, ...]:
    """Where one quote lands, from every verified match: on all of them when they are one
    message (a single record, or copies on different sources), otherwise nowhere."""
    if not found or len(found) > MAX_PLACES:
        return ()
    info = facts(conn, [f.record_id for f in found])
    if not all(
        same_message(info[x.record_id], info[y.record_id]) for x, y in combinations(found, 2)
    ):
        return ()
    return tuple(
        sorted(
            (Place(f.record_id, info[f.record_id].thread_id, f.spans, f.method) for f in found),
            key=lambda p: (info[p.record_id].source_id, p.thread_id, p.record_id),
        )
    )


def look_up(
    conn: sqlite3.Connection, words: str, seq: int, index: Index, whole: bool = False
) -> Lookup:
    """One quote looked up in every message, with every method and as the same words with other
    punctuation. With whole (a document's quote), only the whole quote is looked for that way,
    and a match on only the words after a colon or dash (the matcher reads what comes before as
    a printed label) is not placed. Without it (an exhibit's quoted message), the words after
    each printed label are looked for too."""
    outcome = find_every(words, index)
    matched = {f.record_id for f in outcome.found}
    fullest = [group[0] for group in core_groups(words)]  # from each start: as pasted, labels
    nets = fullest[:1] if whole else fullest
    loose = set().union(*(same_words(words[a:b], index) for a, b in nets)) - matched
    hits = tuple(sorted(matched | loose))
    text = " ".join(words.split())
    part = (
        whole and outcome.core is not None and any(ch.isalnum() for ch in words[: outcome.core[0]])
    )
    places = () if part or loose else place(conn, outcome.found)
    return Lookup(text, seq, places, len(matched), len(loose), part=part, hits=hits)


# ---------------------------------------------------------------- the three kinds of pick


def document_lookups(
    conn: sqlite3.Connection, paragraph_text: str, index: Index, names: set[str]
) -> list[Lookup]:
    """Every quote in one paragraph, looked up in the case's messages unless it is a name or a
    single word."""
    out = []
    for seq, (a, b, words) in enumerate(paragraph_quotes(paragraph_text), start=1):
        skipped = skip_reason(words, names)
        if skipped:
            hits = whole_messages(words, index)
            out.append(Lookup(words, seq, skipped=skipped, span=(a, b), hits=hits))
        else:
            out.append(replace(look_up(conn, words, seq, index, whole=True), span=(a, b)))
    return out


def exhibit_lookups(conn: sqlite3.Connection, exhibit_id: str, index: Index) -> list[Lookup]:
    """Each quoted message of a pasted exhibit, as Context Restore split it, looked up again.
    Empty when Context Restore has not searched the exhibit yet."""
    return [look_up(conn, x.text, x.seq, index) for x in load_excerpts(conn, exhibit_id)]


def exhibit_ids(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(id, label) of each exhibit, in the order they were added."""
    return [(ex.id, ex.label) for ex in load_exhibits(conn)]


def tagged(conn: sqlite3.Connection) -> list[Place]:
    """Every message a report marks with an examiner tag."""
    return [
        Place(rid, tid)
        for rid, tid in conn.execute(
            "SELECT id, thread_id FROM messages WHERE bookmarked = 1 ORDER BY source_id, id"
        )
    ]
