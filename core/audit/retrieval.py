"""Structured and keyword retrieval (the Retriever contract). No model, no index, no network.

An assumption becomes a `RetrievalQuery`: accounts and threads named by handle, number or id,
an optional time window, channels, and keywords. Records that pass the structured filters are
ranked by the share of keywords they contain. With no structured filter, a record needs at least
one keyword hit. With neither, nothing is returned: retrieval never dumps the whole case.

Identifiers are matched literally (same identifier, same digits). That is a search aid, not an
identity link: two accounts with the same number on two phones are both returned, each with its
own source_ref, and nothing here says they are one person.

Keyword matching folds case and ё/е and lets words of 4+ letters match as a prefix. It also looks
in stored translations, but a candidate's text is always the original record text.
No FTS5 for the alpha (decided in the Wave 2 plan); case databases are small enough to scan.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from core.audit.context import DEFAULT_WINDOW, context_ids
from core.contracts import Assumption, EvidenceCandidate, ProvenanceTier, SourceRef
from core.enrich.records import call_text
from core.enrich.text import digits, extract_terms, normalize, quoted, term_matches, tokens

RETRIEVER_VERSION = "0.1.0"
ALL_KINDS = ("message", "call", "contact", "attachment")


class RetrievalQuery(BaseModel):
    """What to search for. Built from an assumption by `query_for`, or directly by a check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_ids: tuple[str, ...] = ()  # records sent by, sent to, or calling these accounts
    thread_ids: tuple[str, ...] = ()  # records in these threads
    contact_ids: tuple[str, ...] = ()  # contact entries matched by number
    source_ids: tuple[str, ...] = ()  # limit to these sources (phones); empty = all
    apps: tuple[str, ...] = ()  # limit to these channels ('Telegram', 'SMS'); empty = all
    start_utc: datetime | None = None  # inclusive
    end_utc: datetime | None = None  # exclusive
    keywords: tuple[str, ...] = ()  # normalized words or phrases
    kinds: tuple[str, ...] = ALL_KINDS
    unresolved: tuple[str, ...] = ()  # identifiers named in the assumption but not found

    @property
    def has_party_filter(self) -> bool:
        return bool(self.account_ids or self.thread_ids or self.contact_ids)


# ---------------------------------------------------------------- building a query


def _same_number(a: str, b: str) -> bool:
    if len(a) < 7 or len(b) < 7:
        return False
    if a == b:
        return True
    # "+1 (212) 555-0122" vs "2125550122": compare the last 10 digits when both have them.
    return len(a) >= 10 and len(b) >= 10 and a[-10:] == b[-10:]


def resolve_identifiers(
    conn: sqlite3.Connection,
    handles: Iterable[str],
    numbers: Iterable[str],
    names: Iterable[str] = (),
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Map handles, numbers and quoted names to (account_ids, thread_ids, contact_ids, unresolved).

    A handle matches an account identifier or display name, or a thread title. A number matches
    an account identifier, the digits of a phone-style identifier, or a contact entry. A quoted
    name ("Катя") matches a thread title, account display name or contact name exactly; quoted
    text that is not a name is just a keyword, so it is never reported as unresolved.
    """
    accounts = conn.execute("SELECT id, identifier, display_name FROM accounts").fetchall()
    threads = conn.execute("SELECT id, title FROM threads").fetchall()
    contacts = conn.execute("SELECT id, identifier FROM contacts").fetchall()
    contact_names = conn.execute("SELECT id, name FROM contacts").fetchall()
    acc: list[str] = []
    thr: list[str] = []
    con: list[str] = []
    unresolved: list[str] = []
    for h in handles:
        bare = normalize(h).lstrip("@")
        forms = {bare, "@" + bare}
        hit_a = [a for a, ident, name in accounts if normalize(ident) in forms]
        hit_a += [a for a, _, name in accounts if name and normalize(name) in forms]
        hit_t = [t for t, title in threads if title and normalize(title) in forms]
        acc += hit_a
        thr += hit_t
        if not hit_a and not hit_t:
            unresolved.append(h)
    for name in names:
        form = normalize(name)
        acc += [a for a, _, dn in accounts if dn and normalize(dn) == form]
        thr += [t for t, title in threads if title and normalize(title) == form]
        con += [c for c, cname in contact_names if cname and normalize(cname) == form]
    for n in numbers:
        hit_a = [a for a, ident, _ in accounts if ident == n or _same_number(digits(ident), n)]
        hit_c = [c for c, ident in contacts if _same_number(digits(ident), n)]
        acc += hit_a
        con += hit_c
        if not hit_a and not hit_c:
            unresolved.append(n)
    return _uniq(acc), _uniq(thr), _uniq(con), _uniq(unresolved)


def _merge(a: list[str], b: list[str]) -> list[str]:
    return list(dict.fromkeys([*a, *b]))


def _uniq(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _as_utc(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"time window bounds must be timezone-aware, got {value!r}")
    return value.astimezone(UTC)


def _param_fields(assumption: Assumption) -> Mapping[str, object]:
    """Structured params, once contracts v0.2 adds them to Assumption; empty before that."""
    params = getattr(assumption, "params", None)
    if params is None:
        return {}
    if isinstance(params, BaseModel):
        return params.model_dump()
    return params if isinstance(params, Mapping) else {}


def claim_text(conn: sqlite3.Connection, claim_id: str) -> str | None:
    row = conn.execute("SELECT text FROM claims WHERE id = ?", (claim_id,)).fetchone()
    return row[0] if row else None


def query_for(
    assumption: Assumption, conn: sqlite3.Connection, claim: str | None = None
) -> RetrievalQuery:
    """Build the query: typed params where the contract has them, plus terms from the text.

    Terms come from the assumption text and from its claim's text (looked up by claim_id when
    `claim` is not given). The claim usually names the accounts and quotes the messages that the
    assumption only refers to ("the outgoing message", "that window").
    """
    p = _param_fields(assumption)
    if claim is None:
        claim = claim_text(conn, assumption.claim_id)
    handles, numbers, keywords = extract_terms(assumption.text)
    names = quoted(assumption.text)
    if claim:
        c_handles, c_numbers, c_keywords = extract_terms(claim)
        handles, numbers = _merge(handles, c_handles), _merge(numbers, c_numbers)
        keywords = _merge(keywords, c_keywords)
        names = _merge(names, quoted(claim))
    for ident in map(str, p.get("accounts") or ()):
        if ident.startswith("@") or not digits(ident):
            handles.append(ident)
        else:
            numbers.append(digits(ident))
    acc, thr, con, unresolved = resolve_identifiers(conn, handles, numbers, names)
    return RetrievalQuery(
        account_ids=acc,
        thread_ids=thr,
        contact_ids=con,
        source_ids=tuple(p.get("sources") or ()),
        apps=tuple(p.get("channels") or ()),
        start_utc=_as_utc(p.get("start_utc")),
        end_utc=_as_utc(p.get("end_utc")),
        keywords=tuple(keywords),
        unresolved=unresolved,
    )


# ---------------------------------------------------------------- searching


def _in_window(q: RetrievalQuery, ts_utc: str | None) -> bool:
    if q.start_utc is None and q.end_utc is None:
        return True
    if ts_utc is None:
        return False  # an unknown time is never inside a window
    ts = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
    if q.start_utc is not None and ts < q.start_utc:
        return False
    return q.end_utc is None or ts < q.end_utc


def _kw_score(q: RetrievalQuery, texts: Iterable[str]) -> float:
    if not q.keywords:
        return 0.0
    norm = [normalize(t) for t in texts if t]
    toks = [tokens(t) for t in norm]
    hits = sum(
        1
        for kw in q.keywords
        if any(term_matches(kw, tk, n) for tk, n in zip(toks, norm, strict=True))
    )
    return hits / len(q.keywords)


def _keep(q: RetrievalQuery, party_hit: bool, kw: float) -> bool:
    if q.has_party_filter:
        return party_hit
    return kw > 0


def _translations(conn: sqlite3.Connection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for mid, text in conn.execute("SELECT message_id, text FROM translations"):
        out.setdefault(mid, []).append(text)
    return out


def _messages(
    conn: sqlite3.Connection, q: RetrievalQuery
) -> list[tuple[str, SourceRef, str, str | None, float]]:
    recips: dict[str, set[str]] = {}
    for mid, aid in conn.execute("SELECT message_id, account_id FROM message_recipients"):
        recips.setdefault(mid, set()).add(aid)
    trans = _translations(conn)
    accs, thrs = set(q.account_ids), set(q.thread_ids)
    out = []
    rows = conn.execute(
        "SELECT m.id, m.source_id, m.locator, m.thread_id, m.sender_account_id, m.ts_utc, m.body,"
        " t.app FROM messages m JOIN threads t ON t.id = m.thread_id"
    )
    for mid, src, loc, thread, sender, ts, body, app in rows:
        if q.source_ids and src not in q.source_ids or q.apps and app not in q.apps:
            continue
        if not _in_window(q, ts):
            continue
        party = thread in thrs or sender in accs or bool(recips.get(mid, set()) & accs)
        kw = _kw_score(q, [body, *trans.get(mid, [])])
        if _keep(q, party, kw):
            out.append((mid, SourceRef(source_id=src, locator=loc), body, ts, kw))
    return out


def _calls(
    conn: sqlite3.Connection, q: RetrievalQuery
) -> list[tuple[str, SourceRef, str, str | None, float]]:
    accs = set(q.account_ids)
    out = []
    rows = conn.execute(
        "SELECT id, source_id, locator, app, direction, from_account_id, to_account_id,"
        " duration_s, ts_utc FROM calls"
    )
    for cid, src, loc, app, direction, frm, to, dur, ts in rows:
        if q.source_ids and src not in q.source_ids or q.apps and app not in q.apps:
            continue
        if not _in_window(q, ts):
            continue
        text = call_text(conn, app, direction, frm, to, dur)
        party = frm in accs or to in accs
        kw = _kw_score(q, [text])
        if _keep(q, party, kw):
            out.append((cid, SourceRef(source_id=src, locator=loc), text, ts, kw))
    return out


def _contacts(
    conn: sqlite3.Connection, q: RetrievalQuery
) -> list[tuple[str, SourceRef, str, str | None, float]]:
    if q.start_utc is not None or q.end_utc is not None:
        return []  # contacts carry no time, so they cannot be inside a window
    con = set(q.contact_ids)
    out = []
    for cid, src, loc, name, ident in conn.execute(
        "SELECT id, source_id, locator, name, identifier FROM contacts"
    ):
        if q.source_ids and src not in q.source_ids:
            continue
        text = f"{name or '(no name)'}: {ident}"
        kw = _kw_score(q, [text])
        if _keep(q, cid in con, kw):
            out.append((cid, SourceRef(source_id=src, locator=loc), text, None, kw))
    return out


def _attachments(
    conn: sqlite3.Connection, q: RetrievalQuery
) -> list[tuple[str, SourceRef, str, str | None, float]]:
    if not q.keywords:
        return []  # attachments are found by file name only
    out = []
    rows = conn.execute(
        "SELECT a.id, a.source_id, a.locator, a.file_name, m.ts_utc, t.app FROM attachments a"
        " LEFT JOIN messages m ON m.id = a.message_id LEFT JOIN threads t ON t.id = m.thread_id"
    )
    for aid, src, loc, fname, ts, app in rows:
        if not fname or q.source_ids and src not in q.source_ids or q.apps and app not in q.apps:
            continue
        if not _in_window(q, ts):
            continue
        kw = _kw_score(q, [fname])
        if kw > 0:
            out.append((aid, SourceRef(source_id=src, locator=loc), fname, ts, kw))
    return out


def search(
    conn: sqlite3.Connection, q: RetrievalQuery, k: int, window: int = DEFAULT_WINDOW
) -> list[EvidenceCandidate]:
    """Top-k candidates, ranked by keyword share; ties broken by time, then id (stable)."""
    if k <= 0 or not (q.has_party_filter or q.keywords):
        return []
    finders = {
        "message": _messages,
        "call": _calls,
        "contact": _contacts,
        "attachment": _attachments,
    }
    hits = [h for kind in q.kinds for h in finders[kind](conn, q)]
    hits.sort(key=lambda h: (-h[4], h[3] is None, h[3] or "", h[0]))
    party_bonus = 0.5 if q.has_party_filter else 0.0
    return [
        EvidenceCandidate(
            record_id=rid,
            ref=ref,
            text=text,
            tier=ProvenanceTier.OBSERVED,
            context_ids=context_ids(conn, rid, window),
            retrieval_score=round(party_bonus + (1 - party_bonus) * kw, 6),
        )
        for rid, ref, text, _, kw in hits[:k]
    ]


class SqlRetriever:
    """Retriever contract implementation: structured + keyword, no semantic stage yet."""

    version = RETRIEVER_VERSION

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self.window = window

    def retrieve(
        self, assumption: Assumption, conn: sqlite3.Connection, k: int
    ) -> list[EvidenceCandidate]:
        return search(conn, query_for(assumption, conn), k, self.window)
