"""Structured and keyword retrieval (the Retriever contract). No model, no index, no network.

An assumption becomes a `RetrievalQuery`. Its typed params (contracts v0.2) set accounts, devices,
channels and the time window; its claim's wording adds keywords, and handles, numbers and quoted
names to search by when the params name nobody. The assumption text itself is never parsed.
Records that pass the structured filters are ranked by the share of keywords they contain. With
no structured filter, a record needs at least one keyword hit. With neither, nothing is
returned: retrieval never dumps the whole case.

Identifiers are matched literally (same identifier, same digits). That is a search aid, not an
identity link: two accounts with the same number on two phones are both returned, each with its
own source_ref, and nothing here says they are one person. The same literal match finds a named
account's other-phone copy (same app, same identifier) and its contact-list entries.

When the params name two or more sides (an account list, and each person), records between two
sides rank above records of one side alone: "PETROV and @northstar" asks for their exchange, not
for everything either of them did.

A record is never shown alone when the evidence around it is part of what it says:
- a time window also returns the nearest record just before and just after it, and any record
  carrying the quoted text within a day of it, because a wrong date, time zone or order is what
  those records contradict;
- a message carrying the quoted text brings the message before and after it in its thread (what it
  answers, and the reply);
- a message brings its attachments;
- a message or call brings its copy on another phone (same app, same text or same numbers, within
  two minutes), even outside a device filter, since the other phone's log corroborates or
  contradicts it.
All of these count within k.

Keyword matching folds case and ё/е and lets words of 4+ letters match as a prefix. It also looks
in stored translations, but a candidate's text is always the original record text.
No FTS5 for the alpha (decided in the Wave 2 plan); case databases are small enough to scan.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from core.audit.context import DEFAULT_WINDOW, context_ids
from core.contracts import Assumption, EvidenceCandidate, ProvenanceTier, SourceRef
from core.enrich.records import call_text
from core.enrich.text import digits, extract_terms, normalize, quoted, term_matches, tokens

RETRIEVER_VERSION = "0.2.0"
ALL_KINDS = ("message", "call", "contact", "attachment")
QUOTE_EDGE = timedelta(hours=24)  # quoted text this close outside a window is still returned
MAX_QUOTE_EDGES = 4
MIRROR_SECONDS = 120  # the same message or call logged on two phones
MIRROR_DURATION_S = 5

PARTY = 1
BETWEEN = 2
_PREFIX_BY_KIND = {"message": "msg", "call": "call", "contact": "contact", "attachment": "att"}


class RetrievalQuery(BaseModel):
    """What to search for. Built from an assumption by `query_for`, or directly by a check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_ids: tuple[str, ...] = ()  # records sent by, sent to, or calling these accounts
    thread_ids: tuple[str, ...] = ()  # records in these threads
    contact_ids: tuple[str, ...] = ()  # contact entries matched by number
    # the accounts of each side the params name; with two or more, records between sides rank
    # first. Every account here is also in account_ids.
    sides: tuple[tuple[str, ...], ...] = ()
    source_ids: tuple[str, ...] = ()  # limit to these sources (phones); empty = all
    apps: tuple[str, ...] = ()  # limit to these channels ('Telegram', 'SMS'); empty = all
    start_utc: datetime | None = None  # inclusive
    end_utc: datetime | None = None  # inclusive, as in contracts.TimeWindow
    keywords: tuple[str, ...] = ()  # normalized words or phrases
    quote: str | None = None  # normalized params.quoted_text
    kinds: tuple[str, ...] = ALL_KINDS
    unresolved: tuple[str, ...] = ()  # identifiers named in the assumption but not found

    def channel_ok(self, app: str | None, is_call: bool = False) -> bool:
        """Channels match apps case-insensitively; 'call' matches any call record."""
        if not self.apps:
            return True
        wanted = {a.casefold() for a in self.apps}
        return (is_call and "call" in wanted) or (app is not None and app.casefold() in wanted)

    @property
    def has_party_filter(self) -> bool:
        return bool(self.account_ids or self.thread_ids or self.contact_ids)

    @property
    def has_window(self) -> bool:
        return self.start_utc is not None or self.end_utc is not None


# ---------------------------------------------------------------- building a query


def _same_number(a: str, b: str) -> bool:
    if len(a) < 7 or len(b) < 7:
        return False
    if a == b:
        return True
    # "+1 (212) 555-0122" vs "2125550122": compare the last 10 digits when both have them.
    return len(a) >= 10 and len(b) >= 10 and a[-10:] == b[-10:]


def _same_identifier(a: str, b: str) -> bool:
    return normalize(a) == normalize(b) or _same_number(digits(a), digits(b))


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


def _accounts_of_persons(conn: sqlite3.Connection, person_ids: tuple[str, ...]) -> list[str]:
    """Accounts a person may use, for searching only: identity links that are not rejected,
    and the phone's own accounts on any device a stipulation (not rejected) ties to the person.
    This finds records to look at. It confirms nothing and raises no tier.
    """
    if not person_ids:
        return []
    marks = ",".join("?" * len(person_ids))
    linked = conn.execute(
        f"SELECT account_id FROM identity_links WHERE person_id IN ({marks})"  # noqa: S608
        " AND status != 'rejected' ORDER BY account_id",
        person_ids,
    ).fetchall()
    owned: list[tuple[str]] = []
    if _has_table(conn, "stipulations"):
        owned = conn.execute(
            "SELECT a.id FROM stipulations s JOIN accounts a ON a.device_id = s.subject_id"  # noqa: S608
            " WHERE s.kind = 'device_owner' AND s.status != 'rejected'"
            f" AND s.person_id IN ({marks}) ORDER BY a.id",
            person_ids,
        ).fetchall()
    return [r[0] for r in [*linked, *owned]]


def same_identifier_accounts(conn: sqlite3.Connection, account_ids: Iterable[str]) -> list[str]:
    """The accounts given, then every account on any phone with the same app and identifier.

    Each phone's report keeps its own account rows, so a person's number on their own phone and
    the same number in the other phone's log are two accounts. This finds both for searching;
    like every identifier match here, it links no identity.
    """
    ids = list(dict.fromkeys(account_ids))
    if not ids:
        return []
    rows = conn.execute("SELECT id, app, identifier FROM accounts ORDER BY id").fetchall()
    wanted = set(ids)
    named = {aid: (app.casefold(), ident) for aid, app, ident in rows if aid in wanted}
    out = list(ids)
    for aid, app, ident in rows:
        if aid not in named and any(
            app.casefold() == napp and _same_identifier(ident, nident)
            for napp, nident in named.values()
        ):
            out.append(aid)
    return out


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _sources_of_devices(conn: sqlite3.Connection, device_ids: tuple[str, ...]) -> tuple[str, ...]:
    if not device_ids:
        return ()
    marks = ",".join("?" * len(device_ids))
    rows = conn.execute(
        f"SELECT DISTINCT source_id FROM devices WHERE id IN ({marks}) ORDER BY source_id",  # noqa: S608
        device_ids,
    ).fetchall()
    return tuple(r[0] for r in rows) or ("(no such device)",)


def claim_text(conn: sqlite3.Connection, claim_id: str) -> str | None:
    row = conn.execute("SELECT text FROM claims WHERE id = ?", (claim_id,)).fetchone()
    return row[0] if row else None


def query_for(
    assumption: Assumption, conn: sqlite3.Connection, claim: str | None = None
) -> RetrievalQuery:
    """Build the query from the assumption's typed params and its claim's wording.

    Params set the filters: accounts (plus those of named persons), devices, channels and the
    time window. The named accounts are one side and each named person another; each side also
    covers its accounts' same-identifier copies on other phones. The assumption text is a
    rendering of its template and is never parsed. The claim text (looked up by claim_id when
    `claim` is not given) adds ranking keywords, and, only when the params name no account or
    person, the handles, numbers and quoted names to search by. params.quoted_text is searched
    as a phrase.
    """
    p = assumption.params
    if claim is None:
        claim = claim_text(conn, assumption.claim_id)
    handles, numbers, keywords = extract_terms(claim or "")
    names = quoted(claim or "")
    quote = normalize(p.quoted_text).strip() if p.quoted_text else None
    if quote:
        keywords = _merge([quote], keywords)
    acc: tuple[str, ...] = ()
    thr: tuple[str, ...] = ()
    con: tuple[str, ...] = ()
    unresolved: list[str] = []
    sides: list[tuple[str, ...]] = []
    if p.account_ids:
        sides.append(tuple(same_identifier_accounts(conn, p.account_ids)))
    for person in p.person_ids:
        found = _accounts_of_persons(conn, (person,))
        if found:
            sides.append(tuple(same_identifier_accounts(conn, found)))
        else:
            unresolved.append(person)  # a named person with no account to search by
    if sides:
        acc = _uniq([a for side in sides for a in side])
    elif not p.person_ids:
        acc, thr, con, found_unresolved = resolve_identifiers(conn, handles, numbers, names)
        unresolved += found_unresolved
    window = p.window
    return RetrievalQuery(
        account_ids=acc,
        thread_ids=thr,
        contact_ids=con,
        sides=tuple(sides) if len(sides) > 1 else (),
        source_ids=_sources_of_devices(conn, p.device_ids),
        apps=tuple(p.channels),
        start_utc=window.start_utc.astimezone(UTC) if window else None,
        end_utc=window.end_utc.astimezone(UTC) if window else None,
        keywords=tuple(keywords),
        quote=quote or None,
        unresolved=_uniq(unresolved),
    )


# ---------------------------------------------------------------- searching


@dataclass(frozen=True)
class _Hit:
    id: str
    ref: SourceRef
    text: str
    ts: str | None
    kw: float  # share of keywords matched
    tier: int  # 0 keyword only, PARTY, BETWEEN
    quote_hit: bool = False


def _ts(ts_utc: str) -> datetime:
    return datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))


def _in_window(q: RetrievalQuery, ts_utc: str | None) -> bool:
    if not q.has_window:
        return True
    if ts_utc is None:
        return False  # an unknown time is never inside a window
    ts = _ts(ts_utc)
    if q.start_utc is not None and ts < q.start_utc:
        return False
    return q.end_utc is None or ts <= q.end_utc


def _matches(term: str, texts: Iterable[str]) -> bool:
    norm = [normalize(t) for t in texts if t]
    return any(term_matches(term, tokens(n), n) for n in norm)


def _kw_score(q: RetrievalQuery, texts: Iterable[str]) -> float:
    if not q.keywords:
        return 0.0
    texts = list(texts)
    return sum(1 for kw in q.keywords if _matches(kw, texts)) / len(q.keywords)


def _tier(q: RetrievalQuery, involved: set[str], party_hit: bool) -> int:
    """BETWEEN when the record joins accounts of two different sides, PARTY when it names a
    filtered party, else 0 (kept only on a keyword hit)."""
    if not party_hit:
        return 0
    touched = [set(side) & involved for side in q.sides]
    touched = [t for t in touched if t]
    if len(touched) >= 2 and len(set().union(*touched)) >= 2:
        return BETWEEN
    return PARTY


def _keep(q: RetrievalQuery, party_hit: bool, kw: float) -> bool:
    if q.has_party_filter:
        return party_hit
    return kw > 0


def _translations(conn: sqlite3.Connection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for mid, text in conn.execute("SELECT message_id, text FROM translations"):
        out.setdefault(mid, []).append(text)
    return out


def _messages(conn: sqlite3.Connection, q: RetrievalQuery) -> list[_Hit]:
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
        if q.source_ids and src not in q.source_ids or not q.channel_ok(app):
            continue
        involved = recips.get(mid, set()) | ({sender} if sender else set())
        party = thread in thrs or bool(involved & accs)
        texts = [body, *trans.get(mid, [])]
        kw = _kw_score(q, texts)
        if _keep(q, party, kw):
            quote_hit = bool(q.quote) and _matches(q.quote, texts)  # type: ignore[arg-type]
            ref = SourceRef(source_id=src, locator=loc)
            out.append(_Hit(mid, ref, body, ts, kw, _tier(q, involved, party), quote_hit))
    return out


def _calls(conn: sqlite3.Connection, q: RetrievalQuery) -> list[_Hit]:
    accs = set(q.account_ids)
    out = []
    rows = conn.execute(
        "SELECT id, source_id, locator, app, direction, from_account_id, to_account_id,"
        " duration_s, ts_utc FROM calls"
    )
    for cid, src, loc, app, direction, frm, to, dur, ts in rows:
        if q.source_ids and src not in q.source_ids or not q.channel_ok(app, is_call=True):
            continue
        text = call_text(conn, app, direction, frm, to, dur)
        involved = {a for a in (frm, to) if a}
        party = bool(involved & accs)
        kw = _kw_score(q, [text])
        if _keep(q, party, kw):
            ref = SourceRef(source_id=src, locator=loc)
            out.append(_Hit(cid, ref, text, ts, kw, _tier(q, involved, party)))
    return out


def _contacts(conn: sqlite3.Connection, q: RetrievalQuery) -> list[_Hit]:
    """Contact entries matched by id, by keyword, or by the identifier of a filtered account.

    A contact card can hold several entries (a number and a messenger id); when one entry
    matches, the whole card is returned.
    """
    if q.has_window or q.apps:
        return []  # contacts carry no time and belong to no channel
    con = set(q.contact_ids)
    idents: list[str] = []
    if q.account_ids:
        marks = ",".join("?" * len(q.account_ids))
        idents = [
            r[0]
            for r in conn.execute(
                f"SELECT identifier FROM accounts WHERE id IN ({marks})",  # noqa: S608
                q.account_ids,
            )
        ]
    rows = conn.execute(
        "SELECT id, source_id, locator, name, identifier FROM contacts ORDER BY id"
    ).fetchall()
    party_cards = {
        (src, loc)
        for cid, src, loc, _, ident in rows
        if cid in con or any(_same_identifier(ident, a) for a in idents)
    }
    out = []
    for cid, src, loc, name, ident in rows:
        if q.source_ids and src not in q.source_ids:
            continue
        text = f"{name or '(no name)'}: {ident}"
        party = (src, loc) in party_cards
        kw = _kw_score(q, [text])
        if _keep(q, party, kw):
            ref = SourceRef(source_id=src, locator=loc)
            out.append(_Hit(cid, ref, text, None, kw, PARTY if party else 0))
    return out


def _attachments(conn: sqlite3.Connection, q: RetrievalQuery) -> list[_Hit]:
    """Attachments found by file name. Any attachment also comes with its message."""
    if not q.keywords:
        return []
    out = []
    rows = conn.execute(
        "SELECT a.id, a.source_id, a.locator, a.file_name, m.ts_utc, t.app FROM attachments a"
        " LEFT JOIN messages m ON m.id = a.message_id LEFT JOIN threads t ON t.id = m.thread_id"
    )
    for aid, src, loc, fname, ts, app in rows:
        if not fname or q.source_ids and src not in q.source_ids or not q.channel_ok(app):
            continue
        kw = _kw_score(q, [fname])
        if kw > 0:
            out.append(_Hit(aid, SourceRef(source_id=src, locator=loc), fname, ts, kw, 0))
    return out


FINDERS = {
    "message": _messages,
    "call": _calls,
    "contact": _contacts,
    "attachment": _attachments,
}


def _rank_key(h: _Hit) -> tuple[object, ...]:
    # Between sides, then keyword share; contacts (few, and about the account itself) before
    # timed records; then time, then id, so ties are stable.
    return (-h.tier, -h.kw, not h.id.startswith("contact:"), h.ts is None, h.ts or "", h.id)


def _edges(q: RetrievalQuery, outside: list[_Hit]) -> list[_Hit]:
    """Records just outside the window: the nearest before and after, and the quoted text."""
    timed = [h for h in outside if h.ts is not None and not h.id.startswith("att:")]
    out: list[_Hit] = []
    if q.has_party_filter:
        top = BETWEEN if q.sides else PARTY
        pool = [h for h in timed if h.tier >= top]
        before = [h for h in pool if q.start_utc is not None and _ts(h.ts) < q.start_utc]  # type: ignore[arg-type]
        after = [h for h in pool if q.end_utc is not None and _ts(h.ts) > q.end_utc]  # type: ignore[arg-type]
        if before:
            out.append(max(before, key=lambda h: (h.ts, h.id)))
        if after:
            out.append(min(after, key=lambda h: (h.ts, h.id)))
    if q.quote:

        def gap(h: _Hit) -> timedelta:
            ts = _ts(h.ts)  # type: ignore[arg-type]
            if q.start_utc is not None and ts < q.start_utc:
                return q.start_utc - ts
            return ts - q.end_utc if q.end_utc is not None else timedelta(0)

        near = sorted(
            (h for h in timed if h.quote_hit and gap(h) <= QUOTE_EDGE),
            key=lambda h: (gap(h), h.id),
        )
        out += [h for h in near[:MAX_QUOTE_EDGES] if h not in out]
    return out


def _companions(conn: sqlite3.Connection, q: RetrievalQuery, h: _Hit) -> list[_Hit]:
    """Records that come with a hit: its attachments, its copy on another phone, and the
    messages either side of a quoted message."""
    out: list[_Hit] = []
    if h.id.startswith("msg:"):
        if "attachment" in q.kinds:
            for aid, src, loc, fname in conn.execute(
                "SELECT id, source_id, locator, file_name FROM attachments WHERE message_id = ?"
                " ORDER BY id",
                (h.id,),
            ):
                out.append(
                    _Hit(
                        aid, SourceRef(source_id=src, locator=loc), fname or "", h.ts, h.kw, h.tier
                    )
                )
        out += [_message_hit(conn, mid, h) for mid in _message_mirrors(conn, h.id)]
        if h.quote_hit:
            out += [_message_hit(conn, mid, h) for mid in context_ids(conn, h.id, window=1)]
    elif h.id.startswith("call:"):
        out += [_call_hit(conn, cid, h) for cid in _call_mirrors(conn, h.id)]
    return out


def _message_hit(conn: sqlite3.Connection, mid: str, anchor: _Hit) -> _Hit:
    src, loc, body, ts = conn.execute(
        "SELECT source_id, locator, body, ts_utc FROM messages WHERE id = ?", (mid,)
    ).fetchone()
    return _Hit(mid, SourceRef(source_id=src, locator=loc), body, ts, anchor.kw, anchor.tier)


def _call_hit(conn: sqlite3.Connection, cid: str, anchor: _Hit) -> _Hit:
    src, loc, app, direction, frm, to, dur, ts = conn.execute(
        "SELECT source_id, locator, app, direction, from_account_id, to_account_id, duration_s,"
        " ts_utc FROM calls WHERE id = ?",
        (cid,),
    ).fetchone()
    text = call_text(conn, app, direction, frm, to, dur)
    return _Hit(cid, SourceRef(source_id=src, locator=loc), text, ts, anchor.kw, anchor.tier)


def _near(ts_utc: str) -> tuple[str, str]:
    ts = _ts(ts_utc)
    span = timedelta(seconds=MIRROR_SECONDS)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (ts - span).astimezone(UTC).strftime(fmt), (ts + span).astimezone(UTC).strftime(fmt)


def _message_mirrors(conn: sqlite3.Connection, mid: str) -> list[str]:
    """The same message on another phone: same app, same non-empty text, within two minutes."""
    row = conn.execute(
        "SELECT m.source_id, m.ts_utc, m.body, t.app FROM messages m"
        " JOIN threads t ON t.id = m.thread_id WHERE m.id = ?",
        (mid,),
    ).fetchone()
    if row is None or row[1] is None or not (row[2] or "").strip():
        return []
    src, ts, body, app = row
    lo, hi = _near(ts)
    rows = conn.execute(
        "SELECT m.id, t.app FROM messages m JOIN threads t ON t.id = m.thread_id"
        " WHERE m.source_id != ? AND m.body = ? AND m.ts_utc BETWEEN ? AND ? ORDER BY m.id",
        (src, body, lo, hi),
    ).fetchall()
    return [r[0] for r in rows if (r[1] or "").casefold() == (app or "").casefold()]


def _call_mirrors(conn: sqlite3.Connection, cid: str) -> list[str]:
    """The same call on another phone: same app, same two numbers, within two minutes, and
    about the same duration."""
    row = conn.execute(
        "SELECT c.source_id, c.ts_utc, c.app, c.duration_s, f.identifier, t.identifier"
        " FROM calls c LEFT JOIN accounts f ON f.id = c.from_account_id"
        " LEFT JOIN accounts t ON t.id = c.to_account_id WHERE c.id = ?",
        (cid,),
    ).fetchone()
    if row is None or row[1] is None or row[4] is None or row[5] is None:
        return []
    src, ts, app, dur, frm, to = row
    lo, hi = _near(ts)
    rows = conn.execute(
        "SELECT c.id, c.app, c.duration_s, f.identifier, t.identifier FROM calls c"
        " LEFT JOIN accounts f ON f.id = c.from_account_id"
        " LEFT JOIN accounts t ON t.id = c.to_account_id"
        " WHERE c.source_id != ? AND c.ts_utc BETWEEN ? AND ? ORDER BY c.id",
        (src, lo, hi),
    ).fetchall()
    return [
        r[0]
        for r in rows
        if (r[1] or "").casefold() == (app or "").casefold()
        and r[3] is not None
        and r[4] is not None
        and _same_identifier(r[3], frm)
        and _same_identifier(r[4], to)
        and (dur is None or r[2] is None or abs(r[2] - dur) <= MIRROR_DURATION_S)
    ]


def _score(q: RetrievalQuery, h: _Hit) -> float:
    if not q.has_party_filter:
        return round(h.kw, 6)
    if q.sides:
        return round(0.5 + (0.25 if h.tier == BETWEEN else 0.0) + 0.25 * h.kw, 6)
    return round(0.5 + 0.5 * h.kw, 6)


def search(
    conn: sqlite3.Connection, q: RetrievalQuery, k: int, window: int = DEFAULT_WINDOW
) -> list[EvidenceCandidate]:
    """Top-k candidates: in-window records ranked by side, keyword share, then time and id;
    the window's edge records; and the records that come with each (see the module notes)."""
    if k <= 0 or not (q.has_party_filter or q.keywords):
        return []
    hits = [h for kind in q.kinds for h in FINDERS[kind](conn, q)]
    inside = sorted((h for h in hits if _in_window(q, h.ts)), key=_rank_key)
    edges = _edges(q, [h for h in hits if not _in_window(q, h.ts)]) if q.has_window else []
    allowed = {_PREFIX_BY_KIND[kind] for kind in q.kinds}
    picked: list[_Hit] = []
    seen: set[str] = set()

    def take(h: _Hit, limit: int) -> None:
        for r in [h, *(_companions(conn, q, h) if h.id not in seen else [])]:
            if len(picked) >= limit:
                return
            if r.id not in seen and r.id.split(":", 1)[0] in allowed:
                seen.add(r.id)
                picked.append(r)

    budget = k - min(len(edges), k // 2)
    for h in inside:
        if len(picked) >= budget:
            break
        take(h, budget)
    for h in edges:
        take(h, k)
    return [
        EvidenceCandidate(
            record_id=h.id,
            ref=h.ref,
            text=h.text,
            tier=ProvenanceTier.OBSERVED,
            context_ids=context_ids(conn, h.id, window),
            retrieval_score=_score(q, h),
        )
        for h in picked
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


def create(conn: sqlite3.Connection) -> SqlRetriever:
    """Pipeline entry point (core.pipeline.real_components)."""
    return SqlRetriever()
