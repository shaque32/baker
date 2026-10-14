"""Other explanations for one claim, found by code in the case's own records. Read-only.

Each alternative is tied to the claim through its assumptions (core/audit/assumptions.py): the
words the document quotes, the people and accounts it names, the time window it states and the
apps it names. An alternative is shown only when a record, a saved name or a source fact in the
case fits it; Baker never offers a bare "maybe". What each one searched is stated with it.

- Someone else used the account or phone (claims about who sent something or who is behind an
  account): the account's user naming themselves as someone other than the person the claim
  names; names saved for the account that share no part of that person's name; words about
  using another person's phone, account or login on the same phone near the message; the
  account signed in as an owner account on more than one phone.
- Another clock (claims that state a time): records the document's time fits only when they
  are read on the clock the report printed, or in UTC, instead of on the phone's own clock.
- The day boundary (counts and no-contact claims over stated dates): records that move in or
  out of the stated dates when the same dates are read in UTC instead of the stated zone.
- Another app (claims about one app over a window): contact between the same people on other
  apps or calls inside the window.
- A whole app gone quiet (claims about silence or an event on one app): a phone with no record
  of that app in any conversation inside the window, while its other apps go on.
- A curated report (absence, count and event claims): sources that are examiner-curated or of
  unknown coverage, and logical extractions.
- The same words elsewhere (claims about what words mean): other messages in the same
  conversation that use the quoted words.

Nothing here says which explanation is right, and nothing here touches a verdict.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.audit.checks._common import (
    CALL_CHANNEL,
    CaseData,
    Key,
    Row,
    calls_for_accounts,
    channel_ok,
    in_window,
    involves_all,
    local_str,
    messages_for_accounts,
    messages_with_text,
    parties,
)
from core.contracts import Assumption, Fidelity, TimeWindow
from core.identity import links as idl
from core.identity.links import cite

VERSION = "1.0.0"
MAX_FITS = 6  # records shown per alternative; the total is always given
HANDOFF_DAYS = 2  # how far either side of a message the hand-off search looks, on its phone

Kind = Literal[
    "other_user", "clock", "day_boundary", "other_app", "app_quiet", "curated", "same_words"
]
Family = Literal["authorship", "timing", "completeness", "meaning"]

FAMILY_TEXT: dict[Family, str] = {
    "authorship": "Who wrote it or who is behind the account",
    "timing": "When it happened",
    "completeness": "What the record holds",
    "meaning": "What the words mean",
}

_IDENTITY_TEMPLATES = frozenset({"sender", "authorship", "person_identity"})
_TIME_TEMPLATES = frozenset({"record_time", "weekday_date"})
_WINDOW_TEMPLATES = frozenset({"message_count", "no_contact"})
_SILENCE_TEMPLATES = frozenset({"no_contact", "event"})
_QUOTE_TEMPLATES = frozenset({"sender", "record_time", "weekday_date", "meaning"})

# The user of an account naming themselves: "hey its alex turner", "its ilya btw". Only at the
# start of a message or a sentence, or after a greeting, so "the gym is ..." is not read as one.
_INTRO = re.compile(
    r"(?:^|[.!?,;:]\s*|\b(?:hey|hi|hello|yo|ok|okay)[\s,]+)"
    r"(?:it'?s|it’s|this is|i am|i'm|i’m|im)\s+([^\W\d_]+)(?:[ \t]+([^\W\d_]+))?",
    re.IGNORECASE,
)
_NOT_SURNAME = frozenset(
    "btw here again now from bro man lol new too ok okay haha the and dont not just with at in "
    "on calling texting speaking sorry hi hey yo".split()
)
# Words about using another person's phone, account or login. An app named in them must be the
# message's app; an account or login must be spoken of in a conversation on that app; a phone or
# other device counts for every app on it.
_APP_WORDS = {
    "insta": "instagram",
    "instagram": "instagram",
    "ig": "instagram",
    "whatsapp": "whatsapp",
    "telegram": "telegram",
}
_DEVICE_WORDS = frozenset("phone cell ipad tablet laptop computer pc iphone samsung".split())
_THINGS = "|".join(
    ["account", "acct", "login", "log-?in", "password", *_APP_WORDS, *sorted(_DEVICE_WORDS)]
)
_WHOSE = r"(?:ur|your|his|her|their|my|[^\W\d_]+'s|[^\W\d_]+’s)"
_HANDOFF = re.compile(
    r"\b(?:using|used|use|borrow(?:ed|ing)?|took|take|taking|grab(?:bed)?|left|gave|shared|"
    rf"lent|give)\s+(?:me\s+)?{_WHOSE}\s+(?P<thing>{_THINGS})\b"
    r"|\b(?:logged|signed)\s+in\s+(?:as|on|to|with|from)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[^\W\d_]{4,}")
_STOP = frozenset(
    "that this with from have will what when where there their they them then than your yours "
    "about would could should been were just like into over only some more most very also back "
    "here dont didnt cant wont aint gonna wanna gotta tonight today tomorrow okay yeah sure "
    "need know want come going said tell call text later still really thing things time".split()
)


@dataclass(frozen=True)
class Fit:
    """One thing in the case that fits an alternative: a record, a saved name or a source."""

    record_id: str  # messages.id, calls.id, contacts.id, accounts.id, threads.id or sources.id
    source_id: str
    locator: str
    quote: str  # exactly as the case holds it: a message body, a name, a file name
    when: str  # the record's time on its phone's own clock; '' for names and sources
    note: str  # Baker's words; text from the case inside is marked with cite()


@dataclass(frozen=True)
class Alternative:
    kind: Kind
    family: Family
    title: str
    summary: str  # one plain sentence in Baker's words; case text marked with cite()
    fits: tuple[Fit, ...]  # at most MAX_FITS, most relevant first
    total: int  # everything that fits, shown or not
    searched: str  # what code searched, so a short list is never read as "nothing else"
    assumption_ids: tuple[str, ...] = ()


@dataclass
class Case:
    """Lookups every claim's alternatives share, loaded once per screen or report."""

    conn: sqlite3.Connection
    data: CaseData
    ids: idl.Case  # names on accounts, persons and every name word in the case
    files: dict[str, tuple[str, str, str]]  # source id -> (file name, fidelity, extraction)

    def person(self, person_id: str) -> idl.Person | None:
        return next((p for p in self.ids.persons if p.id == person_id), None)

    def offsets(self, ids: Iterable[str]) -> dict[str, int | None]:
        """The UTC offset the report printed on each message or call."""
        out: dict[str, int | None] = {}
        for rid in ids:
            table = "calls" if rid.startswith("call") else "messages"
            r = self.conn.execute(
                f"SELECT ts_offset_min FROM {table} WHERE id = ?",  # noqa: S608
                (rid,),
            ).fetchone()
            out[rid] = None if r is None else r[0]
        return out

    def locator(self, record_id: str) -> tuple[str, str]:
        for table in ("messages", "calls", "contacts", "accounts", "threads"):
            r = self.conn.execute(
                f"SELECT source_id, locator FROM {table} WHERE id = ?",  # noqa: S608
                (record_id,),
            ).fetchone()
            if r is not None:
                return r[0], r[1]
        return "", ""


def load(conn: sqlite3.Connection) -> Case:
    files = {
        sid: (name, fid, ext)
        for sid, name, fid, ext in conn.execute(
            "SELECT id, file_name, fidelity, extraction_type FROM sources WHERE kind != 'govdoc'"
            " ORDER BY id"
        )
    }
    ids = idl.load(conn)
    return Case(conn, ids.data, ids, files)


# ---------------------------------------------------------------- shared helpers


def _fit(case: Case, row: Row, note: str) -> Fit:
    src, loc = case.locator(row.id)
    return Fit(row.id, src or row.source_id, loc, _row_text(row), local_str(case.data, row), note)


def _row_text(row: Row) -> str:
    if row.kind == "call":
        dur = f", {row.duration_s} s" if row.duration_s is not None else ""
        return f"{row.app} call{dur}"
    return row.text or ""


def _copy_key(row: Row) -> tuple[str, str]:
    """The same message held on two phones shows once."""
    return (row.text or row.kind, row.ts_utc.isoformat() if row.ts_utc else row.id)


def _dedupe(rows: Iterable[Row]) -> list[Row]:
    seen: dict[tuple[str, str], Row] = {}
    for r in rows:
        seen.setdefault(_copy_key(r), r)
    return list(seen.values())


def _by_time(rows: Iterable[Row], anchor: datetime | None = None) -> list[Row]:
    far = datetime.max.replace(tzinfo=UTC)

    def k(r: Row) -> tuple:
        if anchor is not None and r.ts_utc is not None:
            return (0, abs((r.ts_utc - anchor).total_seconds()), r.id)
        return (1 if r.ts_utc is None else 0, r.ts_utc or far, r.id)

    return sorted(rows, key=k)


def _zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _wall(window: TimeWindow) -> tuple[datetime, datetime] | None:
    """The window as wall-clock times (naive) in the zone it was stated in."""
    z = _zone(window.tz)
    if z is None:
        return None
    return (
        window.start_utc.astimezone(z).replace(tzinfo=None),
        window.end_utc.astimezone(z).replace(tzinfo=None),
    )


def _offset_text(minutes: int) -> str:
    sign = "-" if minutes < 0 else "+"
    h, m = divmod(abs(minutes), 60)
    return f"UTC{sign}{h:02d}:{m:02d}"


def _day(t: datetime) -> str:
    return f"{t:%Y-%m-%d %H:%M}"


def _account_label(case: Case, keys: Iterable[Key]) -> str:
    labels = []
    for k in sorted(set(keys)):
        g = case.ids.groups.get(k)
        labels.append(cite(g.label if g else f"{k[0]} {k[1]}"))
    return ", ".join(labels) or "no account"


def _claimed_rows(case: Case, assumptions: list[Assumption]) -> dict[str, list[Row]]:
    """Messages holding each quote the claim's assumptions cite, verbatim and word-aligned."""
    out: dict[str, list[Row]] = {}
    for a in assumptions:
        qt = a.params.quoted_text
        if a.template_id in _QUOTE_TEMPLATES and qt and qt not in out:
            out[qt] = messages_with_text(case.data, qt)
    return out


def _persons(case: Case, assumptions: list[Assumption]) -> list[idl.Person]:
    seen: dict[str, idl.Person] = {}
    for a in assumptions:
        if a.template_id in _IDENTITY_TEMPLATES:
            for pid in a.params.person_ids:
                p = case.person(pid)
                if p is not None and p.words:
                    seen.setdefault(p.id, p)
    return list(seen.values())


def _names_person(person: idl.Person, words: list[str]) -> bool:
    return idl.match_level(list(person.words), words) is not None


# ---------------------------------------------------------------- someone else used it


def _intro_fits(
    case: Case, keys: set[Key], persons: list[idl.Person]
) -> tuple[list[tuple[Row, str]], str]:
    accounts = case.data.account_ids(keys)
    found: list[tuple[Row, str]] = []
    for row in _dedupe(
        r for r in messages_for_accounts(case.data, accounts) if r.sender in accounts
    ):
        for m in _INTRO.finditer(row.text or ""):
            w1 = m.group(1).casefold()
            w2 = (m.group(2) or "").casefold()
            if w1 not in case.ids.known_words:
                continue
            words = [w1] + ([w2] if w2 and w2 not in _NOT_SURNAME else [])
            named = " ".join(words)
            if persons and any(_names_person(p, words) for p in persons):
                break
            if persons:
                who = " or ".join(cite(p.name) for p in persons)
                note = (
                    f"The account's user gives the name “{cite(named)}”, which is not part of "
                    f"{who} as written."
                )
            else:
                note = (
                    f"The account's user gives the name “{cite(named)}”; compare it with the "
                    "person the claim names."
                )
            found.append((row, note))
            break
    searched = f"messages sent by {_account_label(case, keys)} for a user naming themselves"
    return found, searched


def _name_fits(case: Case, keys: set[Key], persons: list[idl.Person]) -> list[Fit]:
    out: list[Fit] = []
    seen: set[str] = set()
    for k in sorted(keys):
        g = case.ids.groups.get(k)
        if g is None:
            continue
        for s in g.names:
            text = s.text.strip()
            if s.kind == "user name" or "@" in text or not s.words or text.casefold() in seen:
                continue
            if any(_names_person(p, s.words) for p in persons):
                continue
            seen.add(text.casefold())
            who = " or ".join(cite(p.name) for p in persons)
            extra = f" ({s.note})" if s.note else ""
            out.append(
                Fit(
                    s.record_id,
                    s.source_id,
                    s.locator,
                    s.text,
                    "",
                    f"{cite(s.source_id)} {s.kind} for {cite(g.label)} shares no part of "
                    f"{who}{extra}.",
                )
            )
    return out


def _handoff(body: str, app: str, claimed_app: str) -> re.Match[str] | None:
    """The first words in a message about using another person's phone, account or login that
    bear on a message sent on claimed_app."""
    for m in _HANDOFF.finditer(body):
        thing = (m.group("thing") or "").casefold()
        if thing in _APP_WORDS:
            ok = _APP_WORDS[thing] == claimed_app.strip().casefold()
        elif thing in _DEVICE_WORDS:
            ok = True
        else:  # an account, a login, signed in: only in a conversation on the same app
            ok = app.strip().casefold() == claimed_app.strip().casefold()
        if ok:
            return m
    return None


def _handoff_fits(case: Case, claimed: list[Row]) -> tuple[list[tuple[Row, str]], str]:
    pad = timedelta(days=HANDOFF_DAYS)
    out: dict[str, tuple[Row, str]] = {}
    claimed_ids = {r.id for r in claimed}
    spans: list[str] = []
    for c in claimed:
        if c.ts_utc is None:
            continue
        lo, hi = c.ts_utc - pad, c.ts_utc + pad
        spans.append(f"{cite(c.source_id)} from {_day(lo)} to {_day(hi)} UTC")
        rows = case.conn.execute(
            "SELECT m.id, m.source_id, t.app, m.sender_account_id, m.ts_utc, m.ts_raw, m.body"
            " FROM messages m JOIN threads t ON t.id = m.thread_id"
            " WHERE m.source_id = ? AND m.ts_utc >= ? AND m.ts_utc <= ? ORDER BY m.ts_utc, m.id",
            (c.source_id, _iso(lo), _iso(hi)),
        )
        for mid, sid, app, sender, ts, raw, body in rows:
            if mid in claimed_ids or mid in out:
                continue
            m = _handoff(body or "", app, c.app)
            if m is None:
                continue
            row = Row(mid, "message", sid, app, sender, (), _parse(ts), raw, body)
            out[mid] = (
                row,
                f"Speaks of using another person's phone, account or login "
                f"(“{cite(m.group(0))}”), on the same phone near the message.",
            )
    anchor = claimed[0].ts_utc if claimed else None
    rows = _by_time(_dedupe(r for r, _ in out.values()), anchor)
    found = [out[r.id] for r in rows]
    searched = (
        "messages on " + "; ".join(dict.fromkeys(spans)) + " for words about using another "
        "person's phone, account or login"
        if spans
        else ""
    )
    return found, searched


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def _multi_owner_fits(case: Case, keys: set[Key]) -> list[Fit]:
    out: list[Fit] = []
    for k in sorted(keys):
        g = case.ids.groups.get(k)
        if g is None or len(set(g.owner_devices)) < 2:
            continue
        devices = sorted(set(g.owner_devices))
        rep = next(a for a in g.account_ids if case.data.accounts[a].device_id == devices[0])
        src, loc = case.ids.account_refs.get(rep, ("", ""))
        phones = ", ".join(cite(case.ids.device_labels.get(d, d)) for d in devices)
        out.append(
            Fit(
                rep,
                src,
                loc,
                g.label,
                "",
                f"{cite(g.label)} is an owner account on more than one phone ({phones}); a "
                "message from it may have been written on any of them.",
            )
        )
    return out


def _other_user(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    mine = [a for a in assumptions if a.template_id in _IDENTITY_TEMPLATES]
    if not mine:
        return None
    claimed_by_quote = _claimed_rows(case, mine)
    claimed = [r for rows in claimed_by_quote.values() for r in rows]
    keys: set[Key] = set()
    for r in claimed:
        acc = case.data.accounts.get(r.sender or "")
        if acc is not None:
            keys.add(acc.key)
    for a in mine:
        for aid in a.params.account_ids:
            acc = case.data.accounts.get(aid)
            if acc is not None:
                keys.add(acc.key)
        if a.params.handles:
            for p in parties(case.data, a.params)[len(a.params.person_ids) :]:
                keys |= p.keys
    persons = _persons(case, mine)
    fits: list[Fit] = []
    searched: list[str] = []
    about_account = all(a.template_id == "person_identity" for a in mine)
    if keys:
        if persons or about_account:  # a name to set it against, or a claim about the account
            intros, s = _intro_fits(case, keys, persons)
            searched.append(s)
            fits += [_fit(case, r, n) for r, n in _sorted_pairs(intros)]
        if persons:
            fits += _name_fits(case, keys, persons)
            searched.append(f"names saved for {_account_label(case, keys)}")
        fits += _multi_owner_fits(case, keys)
        searched.append("which phones hold each account as their own")
    if claimed:
        hands, s = _handoff_fits(case, claimed)
        if s:
            searched.append(s)
        fits += [_fit(case, r, n) for r, n in hands]
    fits = _merge(fits)
    if not fits:
        return None
    title = (
        "Someone else may be behind the account"
        if about_account
        else "Someone else may have written it"
    )
    if persons:
        who = " or ".join(cite(p.name) for p in persons)
        summary = (
            f"Records in the case point to someone other than {who} using the account or phone."
        )
    else:
        summary = (
            "Records in the case give the account's user a name, or point to another person "
            "using the account or phone; compare them with the person the claim names."
        )
    return Alternative(
        "other_user",
        "authorship",
        title,
        summary,
        tuple(fits[:MAX_FITS]),
        len(fits),
        _searched(searched),
        tuple(a.id for a in mine),
    )


def _merge(fits: list[Fit]) -> list[Fit]:
    """One line per record: a record that fits twice shows once, with both notes."""
    out: dict[str, Fit] = {}
    for f in fits:
        if f.record_id in out:
            prev = out[f.record_id]
            out[f.record_id] = Fit(
                prev.record_id, prev.source_id, prev.locator, prev.quote, prev.when,
                f"{prev.note} {f.note}",
            )  # fmt: skip
        else:
            out[f.record_id] = f
    return list(out.values())


def _sorted_pairs(pairs: list[tuple[Row, str]]) -> list[tuple[Row, str]]:
    notes = {r.id: n for r, n in pairs}
    return [(r, notes[r.id]) for r in _by_time(r for r, _ in pairs)]


def _joined(values: list[str]) -> str:
    return ", ".join(cite(v) for v in dict.fromkeys(values))


def _searched(parts: list[str]) -> str:
    parts = [p for p in dict.fromkeys(parts) if p]
    return ("Searched " + "; ".join(parts) + ".") if parts else ""


# ---------------------------------------------------------------- another clock


def _clock_rows(case: Case, a: Assumption, claimed: dict[str, list[Row]]) -> list[Row]:
    p = a.params
    if p.quoted_text:
        return claimed.get(p.quoted_text, [])
    if CALL_CHANNEL in p.channels:
        accounts = set().union(*(case.data.account_ids(x.keys) for x in parties(case.data, p)))
        rows = calls_for_accounts(case.data, accounts) if accounts else []
        if p.duration_s:
            lo, hi = p.duration_s
            rows = [r for r in rows if r.duration_s is not None and lo <= r.duration_s <= hi]
        return rows
    return []


def _clock(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    mine = [a for a in assumptions if a.template_id in _TIME_TEMPLATES and a.params.window]
    if not mine:
        return None
    claimed = _claimed_rows(case, mine)
    fits: list[Fit] = []
    used: list[str] = []
    for a in mine:
        window = a.params.window
        wall = _wall(window) if window is not None else None
        if window is None or wall is None:
            continue
        rows = _clock_rows(case, a, claimed)
        offsets = case.offsets(r.id for r in rows)
        for r in _dedupe(rows):
            at = r.ts_utc
            if at is None or in_window(at, window):
                continue  # no usable time, or inside the stated time on the real clock
            tz = case.data.tz_for(r.source_id)
            own = at.astimezone(tz).utcoffset() if tz else None
            readings: list[tuple[str, datetime]] = []
            off = offsets.get(r.id)
            if off is not None and (own is None or timedelta(minutes=off) != own):
                printed = (at + timedelta(minutes=off)).replace(tzinfo=None)
                readings.append((f"the clock the report printed ({_offset_text(off)})", printed))
            if (own is None or own != timedelta(0)) and off != 0:
                readings.append(("UTC", at.replace(tzinfo=None)))
            for label, t in readings:
                if wall[0] <= t <= wall[1]:
                    phone = (
                        f"on the phone's own clock ({case.data.sources[r.source_id].tz}) it is "
                        f"{local_str(case.data, r)}"
                        if tz
                        else "the phone's own zone is not recorded"
                    )
                    fits.append(
                        _fit(
                            case,
                            r,
                            f"Read on {label}, this record is at {_day(t)}, inside the stated "
                            f"time {cite(window.raw)}; {phone}.",
                        )
                    )
                    used.append(a.id)
                    break
    if not fits:
        return None
    return Alternative(
        "clock",
        "timing",
        "The stated time may come from another clock",
        "The time the document states fits these records only when they are read on the clock "
        "the report printed, or in UTC, instead of on the phone's own clock.",
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Searched the records each time statement names (by its quoted words, or the call's "
        "parties and length) and read each on the phone's own clock, the report's printed clock "
        "and UTC.",
        tuple(dict.fromkeys(used)),
    )


# ---------------------------------------------------------------- the day boundary


def _party_rows(case: Case, a: Assumption) -> tuple[list[Row], list[set[str]]] | None:
    ps = parties(case.data, a.params)
    sets = [case.data.account_ids(p.keys) for p in ps]
    if len(sets) < 2 or not all(sets):
        return None
    accounts = set().union(*sets)
    rows = messages_for_accounts(case.data, accounts) + calls_for_accounts(case.data, accounts)
    return [r for r in rows if r.ts_utc is not None and involves_all(r, sets)], sets


def _day_boundary(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    fits: list[Fit] = []
    used: list[str] = []
    summary = ""
    for a in assumptions:
        window = a.params.window
        if a.template_id not in _WINDOW_TEMPLATES or window is None or window.tz == "UTC":
            continue
        wall = _wall(window)
        got = _party_rows(case, a)
        if wall is None or got is None:
            continue
        rows = _dedupe(r for r in got[0] if channel_ok(r, a.params.channels))
        if a.params.device_ids:
            srcs = set(case.data.sources_for(a.params.device_ids))
            rows = [r for r in rows if r.source_id in srcs]
        lo, hi = wall[0].replace(tzinfo=UTC), wall[1].replace(tzinfo=UTC)
        stated = {r.id for r in rows if r.ts_utc and in_window(r.ts_utc, window)}
        as_utc = {r.id for r in rows if r.ts_utc and lo <= r.ts_utc <= hi}
        moved = [r for r in rows if (r.id in stated) != (r.id in as_utc)]
        if not moved:
            continue
        used.append(a.id)
        if not summary:
            summary = (
                f"Read in UTC instead of {cite(window.tz)}, the stated dates "
                f"{cite(window.raw)} hold {len(as_utc)} record(s) between these parties instead "
                f"of {len(stated)}."
            )
        for r in _by_time(moved):
            side = (
                "inside the stated dates only on the phone's zone, outside them in UTC"
                if r.id in stated
                else "outside the stated dates on the phone's zone, inside them in UTC"
            )
            fits.append(_fit(case, r, f"This record is {side}."))
    if not fits:
        return None
    return Alternative(
        "day_boundary",
        "timing",
        "The day boundary depends on the time zone",
        summary,
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Searched messages and calls between the parties the claim names, on the apps it "
        "names, and compared the stated dates in the stated zone with the same dates in UTC.",
        tuple(used),
    )


# ---------------------------------------------------------------- another app


def _other_app(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    fits: list[Fit] = []
    used: list[str] = []
    named: list[str] = []
    for a in assumptions:
        p = a.params
        apps = [c for c in p.channels if c.strip().lower() != CALL_CHANNEL]
        if (
            p.window is None
            or not apps
            or a.template_id not in {*_SILENCE_TEMPLATES, "message_count"}
        ):
            continue
        got = _party_rows(case, a)
        if got is None:
            continue
        window = p.window
        others = [
            r
            for r in got[0]
            if r.ts_utc and in_window(r.ts_utc, window) and not channel_ok(r, p.channels)
        ]
        others = _dedupe(others)
        if not others:
            continue
        used.append(a.id)
        named += apps
        for r in _by_time(others):
            what = "A call" if r.kind == "call" else f"A {cite(r.app)} message"
            fits.append(_fit(case, r, f"{what} between the same people inside {cite(window.raw)}."))
    if not fits:
        return None
    apps_text = ", ".join(cite(x) for x in dict.fromkeys(named))
    return Alternative(
        "other_app",
        "completeness",
        "The conversation may have gone on another app",
        f"Inside the stated window the same people were in contact outside {apps_text}: "
        f"{len(fits)} record(s) on other apps or calls.",
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Searched messages and calls between the parties the claim names, inside its window, on "
        "every app it does not name.",
        tuple(used),
    )


# ---------------------------------------------------------------- a whole app gone quiet

_EDGE = (
    "SELECT m.id, m.source_id, t.app, m.sender_account_id, m.ts_utc, m.ts_raw, m.body"
    " FROM messages m JOIN threads t ON t.id = m.thread_id"
    " WHERE m.source_id = ? AND lower(t.app) = lower(?) AND m.ts_utc"
)
_LAST_BEFORE = _EDGE + " < ? ORDER BY m.ts_utc DESC, m.id LIMIT 1"
_FIRST_AFTER = _EDGE + " > ? ORDER BY m.ts_utc ASC, m.id LIMIT 1"


def _app_quiet(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    fits: list[Fit] = []
    used: list[str] = []
    lines: list[str] = []
    windows: list[str] = []
    quiet_apps: list[str] = []
    for a in assumptions:
        p = a.params
        apps = [c for c in p.channels if c.strip().lower() != CALL_CHANNEL]
        if a.template_id not in _SILENCE_TEMPLATES or p.window is None or not apps:
            continue
        lo, hi = _iso(p.window.start_utc), _iso(p.window.end_utc)
        for app in apps:
            for sid in case.data.sources_for(p.device_ids):
                holds = case.conn.execute(
                    "SELECT COUNT(*) FROM messages m JOIN threads t ON t.id = m.thread_id"
                    " WHERE m.source_id = ? AND lower(t.app) = lower(?)",
                    (sid, app),
                ).fetchone()[0]
                if not holds:
                    continue  # this phone holds no records of the app at all
                inside = case.conn.execute(
                    "SELECT COUNT(*) FROM messages m JOIN threads t ON t.id = m.thread_id"
                    " WHERE m.source_id = ? AND lower(t.app) = lower(?)"
                    " AND m.ts_utc >= ? AND m.ts_utc <= ?",
                    (sid, app, lo, hi),
                ).fetchone()[0]
                if inside:
                    continue
                rest = case.conn.execute(
                    "SELECT (SELECT COUNT(*) FROM messages m JOIN threads t ON t.id = m.thread_id"
                    "  WHERE m.source_id = ? AND lower(t.app) != lower(?)"
                    "  AND m.ts_utc >= ? AND m.ts_utc <= ?)"
                    " + (SELECT COUNT(*) FROM calls"
                    "  WHERE source_id = ? AND ts_utc >= ? AND ts_utc <= ?)",
                    (sid, app, lo, hi, sid, lo, hi),
                ).fetchone()[0]
                if not rest:
                    continue  # the whole phone is quiet; the gaps view covers that
                used.append(a.id)
                lines.append(f"{cite(sid)} ({rest} other record(s))")
                windows.append(p.window.raw)
                quiet_apps.append(app)
                for edge, sql, bound in (
                    ("last before", _LAST_BEFORE, lo),
                    ("first after", _FIRST_AFTER, hi),
                ):
                    r = case.conn.execute(sql, (sid, app, bound)).fetchone()
                    if r is None:
                        continue
                    row = Row(r[0], "message", r[1], r[2], r[3], (), _parse(r[4]), r[5], r[6])
                    fits.append(
                        _fit(
                            case,
                            row,
                            f"The {edge} the window on {cite(sid)}: its nearest {cite(app)} "
                            "record in any conversation.",
                        )
                    )
    if not fits:
        return None
    return Alternative(
        "app_quiet",
        "completeness",
        "The whole app is quiet, not one conversation",
        f"{_joined(quiet_apps)} has no record in any conversation on "
        f"{'; '.join(dict.fromkeys(lines))} in the stated window ({_joined(windows)}), while "
        "the phone's other apps and calls go on. A silence across a whole app can come from the "
        "app or the extraction, not only from one conversation.",
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Searched every conversation of the app the claim names on each phone that holds the "
        "app, inside the claim's window, and counted the phone's other records then.",
        tuple(dict.fromkeys(used)),
    )


# ---------------------------------------------------------------- a curated report


def _curated(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    mine = [
        a
        for a in assumptions
        if a.template_id in {*_SILENCE_TEMPLATES, "message_count"} and a.params.window
    ]
    if not mine:
        return None
    sids: list[str] = []
    for a in mine:
        sids += case.data.sources_for(a.params.device_ids)
    fits: list[Fit] = []
    for sid in dict.fromkeys(sids):
        name, fid, ext = case.files.get(sid, (sid, "unknown", "unknown"))
        notes = []
        if fid == Fidelity.CURATED_REPORT.value:
            notes.append(
                "is an examiner-curated report: records the examiner left out are not in it"
            )
        elif fid == Fidelity.UNKNOWN.value:
            notes.append("does not say whether it holds the full extraction")
        if ext == "logical":
            notes.append(
                "comes from a logical extraction, which holds what the phone's apps still showed "
                "when it was extracted"
            )
        if notes:
            fits.append(Fit(sid, sid, "", name, "", f"{cite(name)} " + "; it ".join(notes) + "."))
    if not fits:
        return None
    return Alternative(
        "curated",
        "completeness",
        "The report may not hold every record",
        "A count, a silence or an event read from these sources rests on what they hold, and "
        "they may not hold everything the phone did.",
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Read each source's recorded coverage and extraction type.",
        tuple(a.id for a in mine),
    )


# ---------------------------------------------------------------- the same words elsewhere


def _words(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.casefold()):
        if w not in _STOP and w not in out:
            out.append(w)
    return out


def _same_words(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    mine = [a for a in assumptions if a.template_id == "meaning" and a.params.quoted_text]
    fits: list[Fit] = []
    used: list[str] = []
    for a in mine:
        qt = a.params.quoted_text or ""
        words = _words(qt)
        claimed = messages_with_text(case.data, qt)
        if not words or not claimed:
            continue
        copies = {_copy_key(r) for r in claimed}
        threads = list(
            dict.fromkeys(
                case.conn.execute(
                    "SELECT thread_id FROM messages WHERE id = ?", (r.id,)
                ).fetchone()[0]
                for r in claimed
            )
        )
        pattern = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.I)
        found: list[tuple[Row, str]] = []
        for tid in threads:
            for mid, sid, app, sender, ts, raw, body in case.conn.execute(
                "SELECT m.id, m.source_id, t.app, m.sender_account_id, m.ts_utc, m.ts_raw, m.body"
                " FROM messages m JOIN threads t ON t.id = m.thread_id WHERE m.thread_id = ?"
                " ORDER BY m.ts_utc, m.id",
                (tid,),
            ):
                m = pattern.search(body or "")
                if m is None:
                    continue
                row = Row(mid, "message", sid, app, sender, (), _parse(ts), raw, body)
                if _copy_key(row) in copies:
                    continue
                found.append((row, f"Uses “{cite(m.group(0))}” in the same conversation."))
        rows = _dedupe(r for r, _ in found)
        notes = {r.id: n for r, n in found}
        anchor = claimed[0].ts_utc
        for r in _by_time(rows, anchor):
            fits.append(_fit(case, r, notes[r.id]))
        if rows:
            used.append(a.id)
    if not fits:
        return None
    return Alternative(
        "same_words",
        "meaning",
        "The words may mean something else here",
        f"The same words appear in {len(fits)} other message(s) of the conversation. How they "
        "are used there may point to another meaning; nearest in time first.",
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Searched every message in the conversation that holds the quoted words, for the "
        "longer words of the quote (four letters or more, common words left out).",
        tuple(used),
    )


# ---------------------------------------------------------------- one claim


def alternatives(case: Case, assumptions: list[Assumption]) -> list[Alternative]:
    """Every alternative the records raise for one claim's assumptions, in a fixed order.
    Read-only: nothing is written, and the claim's verdict is never read or changed."""
    finders = (_other_user, _clock, _day_boundary, _other_app, _app_quiet, _curated, _same_words)
    return [alt for find in finders if (alt := find(case, assumptions)) is not None]
