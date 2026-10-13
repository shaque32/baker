"""Find a quoted exhibit message in the extraction, and verify every match by code.

No model takes part. For one excerpt (one quoted message from the exhibit):

1. Cores. The excerpt as pasted, then, if that finds nothing, the text after a label the
   exhibit printed in front of the message ("3/12/2026 4:15 PM PETROV: ..."), then each of those
   without a closing period, comma or other sentence mark. Wrapping quotation marks and leading or
   trailing ellipses are set aside. A core found after a label must still be at least two words.
2. Methods, in order: exact (character for character), tolerant, then transliteration
   (core/restore/fold.py). The first core and method that finds anything decides the excerpt.
3. An ellipsis inside a core means the exhibit left words out. Each piece must be found, in order,
   in the same message; the words between the pieces are what the exhibit omitted.
4. Every match is re-verified from the stored message body before it is returned: the paired
   spans are compared again under the method's own rule, they must start and end on word
   boundaries, and a transliteration match needs one side written in Cyrillic. A match that fails
   is dropped and counted, never shown.

Message bodies are the only text searched. Translations, attachments, call logs, contacts and
images are not.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from core.contracts import MatchMethod, SourceRef
from core.restore.fold import Folded, fold, has_cyrillic

MATCHER_VERSION = "1.0.0"
MAX_MATCHES = 25  # per excerpt; more than this and the text is too common to place
LABEL_SCAN = 120  # a printed label (time, sender) is looked for in this many leading characters

METHODS = (MatchMethod.EXACT, MatchMethod.TOLERANT, MatchMethod.TRANSLITERATION)
_LEVEL = {MatchMethod.TOLERANT: "tolerant", MatchMethod.TRANSLITERATION: "transliteration"}

ELLIPSIS_RE = re.compile(r"\[\s*(?:…|\.\s?\.\s?\.)\s*\]|…|\.(?:\s?\.){2,}")
LABEL_END_RE = re.compile(r"[:\]\)>|]\s+|\s[-–—]\s+")
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
WRAPPERS = (('"', '"'), ("“", "”"), ("„", "“"), ("«", "»"), ("'", "'"), ("‘", "’"))
CLOSING_MARKS = ".,;:!?"


@dataclass(frozen=True)
class Body:
    record_id: str
    ref: SourceRef
    text: str


@dataclass(frozen=True)
class Found:
    """One verified place where an excerpt appears. Spans are (start, end) character offsets:
    `spans` in the message body, `excerpt_spans` in the excerpt text, paired one to one."""

    record_id: str
    ref: SourceRef
    method: MatchMethod
    spans: tuple[tuple[int, int], ...]
    excerpt_spans: tuple[tuple[int, int], ...]


@dataclass
class Outcome:
    found: list[Found] = field(default_factory=list)
    total: int = 0  # verified matches before the limit (MAX_MATCHES by default)
    dropped: int = 0  # candidate matches that failed verification
    core: tuple[int, int] | None = None  # the part of the excerpt that was searched for, if found


# ---------------------------------------------------------------- the excerpt side


def _word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _trim(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def _unwrap(text: str, a: int, b: int) -> tuple[int, int]:
    a, b = _trim(text, a, b)
    changed = True
    while changed and b - a >= 2:
        changed = False
        for left, right in WRAPPERS:
            if text[a] == left and text[b - 1] == right:
                a, b = _trim(text, a + 1, b - 1)
                changed = True
                break
    return a, b


def segments(text: str, a: int, b: int) -> list[tuple[int, int]]:
    """The pieces of text[a:b] between ellipses, trimmed; pieces with no letter or digit go."""
    out: list[tuple[int, int]] = []
    pos = a
    for m in ELLIPSIS_RE.finditer(text, a, b):
        out.append(_trim(text, pos, m.start()))
        pos = m.end()
    out.append(_trim(text, pos, b))
    return [(x, y) for x, y in out if any(ch.isalnum() for ch in text[x:y])]


def cores(excerpt: str) -> list[tuple[int, int]]:
    """Candidate parts of the excerpt to search for, the fullest first."""
    starts = [0] + [
        m.end() for m in LABEL_END_RE.finditer(excerpt, 0, min(len(excerpt), LABEL_SCAN))
    ]
    out: list[tuple[int, int]] = []
    for n, s in enumerate(starts):
        a, b = _unwrap(excerpt, s, len(excerpt))
        if n and len(WORD_RE.findall(excerpt[a:b])) < 2:
            continue
        variants = [(a, b)]
        while b > a and excerpt[b - 1] in CLOSING_MARKS:
            b -= 1
            a2, b2 = _unwrap(excerpt, a, b)
            variants.append((a2, b2))
        for v in variants:
            if v not in out and segments(excerpt, *v):
                out.append(v)
    return out


# ---------------------------------------------------------------- the search


def _aligned(hay: str, i: int, j: int) -> bool:
    left_ok = i == 0 or not (_word_char(hay[i - 1]) and _word_char(hay[i]))
    right_ok = j == len(hay) or not (_word_char(hay[j]) and _word_char(hay[j - 1]))
    return left_ok and right_ok


def _find_aligned(needle: str, hay: str, start: int) -> int:
    i = hay.find(needle, start)
    while i != -1:
        if _aligned(hay, i, i + len(needle)):
            return i
        i = hay.find(needle, i + 1)
    return -1


def _find_in_order(needles: Sequence[str], hay: str) -> list[tuple[int, int]] | None:
    """Leftmost word-aligned placement of each needle, in order, not overlapping."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for n in needles:
        i = _find_aligned(n, hay, pos)
        if i == -1:
            return None
        spans.append((i, i + len(n)))
        pos = i + len(n)
    return spans


class Index:
    """Every message body in the case, with folded copies made once and reused per excerpt."""

    def __init__(self, bodies: Iterable[Body]) -> None:
        self.bodies = list(bodies)
        self._folded: dict[str, list[Folded]] = {}

    @classmethod
    def from_db(cls, conn: sqlite3.Connection) -> Index:
        rows = conn.execute(
            "SELECT id, source_id, locator, body FROM messages ORDER BY source_id, ts_utc, id"
        )
        return cls(Body(r[0], SourceRef(source_id=r[1], locator=r[2]), r[3]) for r in rows)

    def folded(self, level: str) -> list[Folded]:
        if level not in self._folded:
            self._folded[level] = [fold(b.text, level) for b in self.bodies]  # type: ignore[arg-type]
        return self._folded[level]

    def search(self, excerpt: str, method: MatchMethod, segs: list[tuple[int, int]]) -> list[Found]:
        out: list[Found] = []
        if method is MatchMethod.EXACT:
            needles = [excerpt[a:b] for a, b in segs]
            for body in self.bodies:
                if needles[0] not in body.text:
                    continue
                spans = _find_in_order(needles, body.text)
                if spans:
                    out.append(Found(body.record_id, body.ref, method, tuple(spans), tuple(segs)))
            return out
        level = _LEVEL[method]
        needles = [fold(excerpt[a:b], level).text for a, b in segs]  # type: ignore[arg-type]
        if not all(needles):
            return out
        cyrillic_excerpt = any(has_cyrillic(excerpt[a:b]) for a, b in segs)
        for body, f in zip(self.bodies, self.folded(level), strict=True):
            if needles[0] not in f.text:
                continue
            if method is MatchMethod.TRANSLITERATION and not (
                cyrillic_excerpt or has_cyrillic(body.text)
            ):
                continue  # same script on both sides: not a transliteration
            spans = _find_in_order(needles, f.text)
            if spans:
                mapped = tuple(f.span(i, j) for i, j in spans)
                out.append(Found(body.record_id, body.ref, method, mapped, tuple(segs)))
        return out

    def body_text(self, record_id: str) -> str | None:
        return next((b.text for b in self.bodies if b.record_id == record_id), None)


def find(excerpt: str, index: Index, limit: int | None = MAX_MATCHES) -> Outcome:
    """Search for one excerpt. Only verified matches are returned, at most `limit` of them
    (every one when limit is None); Outcome.total counts them all."""
    texts = {b.record_id: b.text for b in index.bodies}
    for core in cores(excerpt):
        segs = segments(excerpt, *core)
        for method in METHODS:
            candidates = index.search(excerpt, method, segs)
            if not candidates:
                continue
            good = [c for c in candidates if verify(excerpt, texts[c.record_id], c)]
            if not good:
                continue
            return Outcome(
                found=good[:limit],
                total=len(good),
                dropped=len(candidates) - len(good),
                core=core,
            )
    return Outcome()


# ---------------------------------------------------------------- verification


def _valid_spans(spans: Sequence[tuple[int, int]], length: int) -> bool:
    prev = 0
    for a, b in spans:
        if a < prev or b <= a or b > length:
            return False
        prev = b
    return True


def verify(excerpt: str, body: str, m: Found) -> bool:
    """Re-check a match against the stored text, independently of how it was found."""
    if not m.spans or len(m.spans) != len(m.excerpt_spans):
        return False
    if not _valid_spans(m.spans, len(body)) or not _valid_spans(m.excerpt_spans, len(excerpt)):
        return False
    for (a, b), (c, d) in zip(m.excerpt_spans, m.spans, strict=True):
        x, y = excerpt[a:b], body[c:d]
        if not any(ch.isalnum() for ch in x) or not _aligned(body, c, d):
            return False
        if m.method is MatchMethod.EXACT:
            ok = x == y
        elif m.method is MatchMethod.TOLERANT:
            ok = fold(x).text == fold(y).text
        elif m.method is MatchMethod.TRANSLITERATION:
            ok = (has_cyrillic(x) or has_cyrillic(y)) and (
                fold(x, "transliteration").text == fold(y, "transliteration").text
            )
        else:
            ok = False
        if not ok:
            return False
    return True


def omitted(body: str, spans: Sequence[tuple[int, int]]) -> list[str]:
    """The message text between consecutive matched pieces: what the exhibit left out."""
    return [body[spans[i][1] : spans[i + 1][0]] for i in range(len(spans) - 1)]
