"""Model rationales withheld from the screen and the report because they use a forbidden word.

The word check (core/audit/invariants.check_report_text) refuses any page whose own text says
guilty, innocent, leader or deleted. A stance rationale is the model's wording, kept with each
evidence item. Before report 0.16.0, one rationale with such a word refused the whole report and
the case screen, and the examiner had no way forward.

Now the text is checked by where it comes from:
- Mabillon's own text (headings, coverage lines, templates) is checked as before: a forbidden
  word in it still refuses the page.
- Each stance rationale is checked on its own, before it is shown. One with a forbidden word is
  withheld: the screen and the report show its item with "Rationale withheld", naming the word,
  and mark the item "needs expert review". The stance, the quote, the quote check and the
  review status stay as stored. No verdict rule reads a rationale, so no verdict changes.
- Before the expert confirms or overrides a claim's verdict (core/review/actions.py), they
  acknowledge each withheld rationale on its evidence. Each acknowledgment is an audit-log entry
  (action `rationale.acknowledge`) naming the evidence item, the word and the SHA-256 of the
  stored rationale, never its text. It counts only for the rationale it names: a later run that
  stores a different rationale for the item needs a new acknowledgment.

The screen and the report both read the list from ClaimState.withheld (core/review/status.py),
so they show the same items and the same count.
"""

from __future__ import annotations

import hashlib
import html
import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from core.audit.invariants import FORBIDDEN_WORDS
from core.contracts import EvidenceItem
from core.ingest import forwarded
from core.review import audit_log
from core.review.actions import ReviewError, _expert

ACTION = "rationale.acknowledge"

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Withheld:
    """One evidence item whose rationale is not shown. `word` is the first forbidden word in it,
    in lower case; `sha256` is over the stored rationale (UTF-8). `acknowledged_by` and
    `acknowledged_seq` name the expert and the audit-log entry of the first acknowledgment of
    this rationale, or are None."""

    evidence_id: str
    word: str
    sha256: str
    acknowledged_by: str | None = None
    acknowledged_seq: int | None = None

    @property
    def acknowledged(self) -> bool:
        return self.acknowledged_seq is not None


def forbidden_word(rationale: str) -> str | None:
    """The first forbidden word in a rationale as the screen and the report would print it
    (forwarded.shown_rationale, then HTML-escaped, which is what the word check reads), in lower
    case, or None. The unescaped text is checked too, so nothing the check could see slips by."""
    shown = forwarded.shown_rationale(rationale)
    for text in (html.escape(shown), shown):
        m = FORBIDDEN_WORDS.search(text)
        if m:
            return m.group(0).lower()
    return None


def rationale_sha256(rationale: str) -> str:
    return hashlib.sha256(rationale.encode("utf-8")).hexdigest()


def acknowledgments(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[int, str]]:
    """(evidence id, rationale SHA-256) -> (seq, expert) of the first logged acknowledgment."""
    out: dict[tuple[str, str], tuple[int, str]] = {}
    for seq, actor, payload in conn.execute(
        "SELECT seq, actor, payload_json FROM audit_log WHERE action = ? ORDER BY seq", (ACTION,)
    ):
        try:
            p = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(p, dict):
            continue
        eid, sha = p.get("evidence_id"), p.get("rationale_sha256")
        if isinstance(eid, str) and isinstance(sha, str):
            out.setdefault((eid, sha), (seq, actor))
    return out


def check(item: EvidenceItem, acks: dict[tuple[str, str], tuple[int, str]]) -> Withheld | None:
    """The item's withheld rationale, with its acknowledgment if one is logged, or None when its
    rationale can be shown."""
    word = forbidden_word(item.rationale)
    if word is None:
        return None
    sha = rationale_sha256(item.rationale)
    seq, who = acks.get((item.id, sha), (None, None))
    return Withheld(item.id, word, sha, who, seq)


def for_items(conn: sqlite3.Connection, items: Iterable[EvidenceItem]) -> list[Withheld]:
    """The withheld rationales among these items, in their order. Reads the log once."""
    items = list(items)
    if not any(forbidden_word(x.rationale) for x in items):
        return []
    acks = acknowledgments(conn)
    return [w for w in (check(x, acks) for x in items) if w is not None]


def for_item(conn: sqlite3.Connection, item: EvidenceItem) -> Withheld | None:
    found = for_items(conn, [item])
    return found[0] if found else None


def summary(withheld: list[Withheld]) -> str:
    """One sentence, the same on the case overview and in the report. Empty when none."""
    if not withheld:
        return ""
    n = len(withheld)
    done = sum(1 for w in withheld if w.acknowledged)
    return (
        f"{n} model rationale{'' if n == 1 else 's'} withheld: each uses a word Mabillon does "
        f"not print, so the item shows a notice instead and needs expert review. {done} "
        f"acknowledged by the expert, {n - done} not yet."
    )


def waiting(conn: sqlite3.Connection, claim_id: str) -> list[Withheld]:
    """The withheld rationales on a claim's evidence, in the run the screen shows, that no
    expert has acknowledged."""
    from core.review import status  # status reads this module

    st = status.claim_state(conn, claim_id)
    return [w for w in (st.withheld if st else []) if not w.acknowledged]


def acknowledge(
    conn: sqlite3.Connection, evidence_id: str, actor: str, clock: Clock | None = None
) -> tuple[Withheld, bool]:
    """Record that the expert has seen that this item's rationale is withheld. Returns the item's
    Withheld and whether a new audit-log entry was written (False if this rationale was already
    acknowledged). The entry names the item, the word and the rationale's SHA-256, not its text."""
    _expert(actor)
    row = conn.execute(
        "SELECT rationale FROM evidence_items WHERE id = ?", (evidence_id,)
    ).fetchone()
    if row is None:
        raise ReviewError(f"no evidence item {evidence_id}")
    rationale = row[0]
    word = forbidden_word(rationale)
    if word is None:
        raise ReviewError("this item's rationale is not withheld; nothing to acknowledge")
    sha = rationale_sha256(rationale)
    with conn:
        logged = acknowledgments(conn).get((evidence_id, sha))
        if logged is not None:
            return Withheld(evidence_id, word, sha, logged[1], logged[0]), False
        entry = audit_log.append(
            conn,
            (clock or (lambda: datetime.now(UTC)))(),
            actor,
            ACTION,
            {"evidence_id": evidence_id, "word": word, "rationale_sha256": sha},
        )
    return Withheld(evidence_id, word, sha, actor, entry.seq), True
