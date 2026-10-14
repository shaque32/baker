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
from dataclasses import dataclass, field, replace
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
_WINDOW_TEMPLATES = frozenset({"message_count", "no_contact"})
_SILENCE_TEMPLATES = frozenset({"no_contact", "event"})
_TIMED_QUOTES = frozenset({"record_time", "weekday_date"})
_QUOTE_TEMPLATES = frozenset({"sender", "authorship", "record_time", "weekday_date", "meaning"})

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
_CREDENTIALS = r"(?:account|acct|login|log-?in|password)"
_WHOSE = r"(?:ur|your|his|her|their|my|[^\W\d_]+'s|[^\W\d_]+’s)"
_HANDOFF = re.compile(
    r"\b(?:using|used|use|borrow(?:ed|ing)?|took|take|taking|grab(?:bed)?|gave|shared|"
    rf"lent|give)\s+(?:me\s+)?(?P<whose1>{_WHOSE})\s+(?P<thing>{_THINGS})\b"
    # Leaving a login with someone hands it over; leaving a phone somewhere ("he left his phone
    # at home") says nothing about who used it, so "left" counts only for a login or account.
    rf"|\bleft\s+(?:me\s+)?(?P<whose3>{_WHOSE})\s+(?P<thing3>{_CREDENTIALS})\b"
    # A login counts only on someone else's phone or account ("logged in on his ipad"); "logged
    # in from home" or "signed in as Daniel" names no one else's.
    r"|\b(?:logged|signed)\s+(?:in(?:to)?|on)\s+(?:(?:on|to|with|from|as|into)\s+)?"
    rf"(?P<whose>{_WHOSE})\s+(?P<thing2>{_THINGS})\b",
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
    local: bool = False  # True only when `when` is a local time derived from the phone's zone


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
    phone_rows: dict[str, list[Row]] = field(default_factory=dict)  # source id -> its records

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
    """A record's fit. Its locator is looked up later, only for the fits a lead shows."""
    when = local_str(case.data, row) if row.ts_utc is not None else ""  # no time, none derived
    local = row.ts_utc is not None and case.data.tz_for(row.source_id) is not None
    return Fit(row.id, row.source_id, "", _row_text(row), when, note, local)


def _located(case: Case, alt: Alternative) -> Alternative:
    """The shown fits with their locators: one lookup per shown record, not per match."""
    out = []
    for f in alt.fits:
        if not f.locator:
            src, loc = case.locator(f.record_id)
            f = replace(f, source_id=src or f.source_id, locator=loc) if loc else f
        out.append(f)
    return replace(alt, fits=tuple(out))


def _row_text(row: Row) -> str:
    if row.kind == "call":
        dur = f", {row.duration_s} s" if row.duration_s is not None else ""
        return f"{row.app} call{dur}"
    return row.text or ""


def _who(data: CaseData, account_id: str | None) -> str:
    """An account as both phones would name it (app and identifier), not by its per-phone id."""
    if account_id is None:
        return ""
    acct = data.accounts.get(account_id)
    return repr(acct.key) if acct else account_id


def _recipients(case: Case, message_id: str) -> tuple[str, ...]:
    """A message's recipient accounts, so copies are told apart by who they went to."""
    return tuple(
        r[0]
        for r in case.conn.execute(
            "SELECT account_id FROM message_recipients WHERE message_id = ? ORDER BY account_id",
            (message_id,),
        )
    )


def _copy_key(data: CaseData, row: Row) -> tuple[str, ...]:
    """What two copies of one message or call on two phones share: kind, app, words or length,
    time, sender and recipients. Only rows from different sources are ever taken as copies;
    two rows on one phone are two records."""
    when = row.ts_utc.isoformat() if row.ts_utc else row.id
    to = sorted(_who(data, x) for x in row.recipients)
    return (
        row.kind,
        row.app.strip().casefold(),
        row.text or "",
        str(row.duration_s),
        when,
        _who(data, row.sender),
        "|".join(to),
    )


def _dedupe(data: CaseData, rows: Iterable[Row]) -> list[Row]:
    """The same record held on two phones shows once. For each copy key the phone holding the
    most such rows is kept (the first seen on a tie), so two identical replies on one phone stay
    two, whichever phone comes first."""
    rows = list(rows)
    counts: dict[tuple[str, ...], dict[str, int]] = {}
    for r in rows:
        per = counts.setdefault(_copy_key(data, r), {})
        per[r.source_id] = per.get(r.source_id, 0) + 1
    keep = {k: max(per, key=lambda sid: per[sid]) for k, per in counts.items()}
    return [r for r in rows if keep[_copy_key(data, r)] == r.source_id]


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


def _quoted_rows(case: Case, a: Assumption) -> list[Row]:
    """Messages holding the assumption's quote, verbatim and word-aligned, within its scope: the
    phones and apps it names, and messages its parties sent or received. For a time statement
    every named party must be on the message, as in the time checks. Otherwise, when no copy
    involves a party (the claim may name the wrong sender), every copy in scope is kept."""
    p = a.params
    if not p.quoted_text:
        return []
    rows = messages_with_text(case.data, p.quoted_text)
    if p.device_ids:
        srcs = set(case.data.sources_for(p.device_ids))
        rows = [r for r in rows if r.source_id in srcs]
    apps = [c for c in p.channels if c.strip().lower() != CALL_CHANNEL]
    if p.channels and not apps:
        return []  # calls only: a quote names no message in that scope
    if apps:
        rows = [r for r in rows if channel_ok(r, apps)]
    party_ids = [case.data.account_ids(x.keys) for x in parties(case.data, p)]
    if a.template_id in _TIMED_QUOTES:
        # The time checks' rule: every named party on the message, or no party named.
        return [r for r in rows if not party_ids or involves_all(r, party_ids)]
    if a.template_id == "sender":
        return rows  # the sender check weighs every copy in scope, the wrong sender's too
    accounts = set().union(*party_ids) if party_ids else set()
    involved = [r for r in rows if r.accounts & accounts]
    return involved or rows


def _claimed_rows(case: Case, assumptions: list[Assumption]) -> dict[str, list[Row]]:
    """For each assumption that cites a quote, the messages it points to (by assumption id)."""
    return {
        a.id: _quoted_rows(case, a)
        for a in assumptions
        if a.template_id in _QUOTE_TEMPLATES and a.params.quoted_text
    }


def _persons(case: Case, assumptions: list[Assumption]) -> list[idl.Person]:
    seen: dict[str, idl.Person] = {}
    for a in assumptions:
        if a.template_id in _IDENTITY_TEMPLATES:
            for pid in a.params.person_ids:
                p = case.person(pid)
                if p is not None and p.words:
                    seen.setdefault(p.id, p)
    return list(seen.values())


def _same_word(a: str, b: str) -> bool:
    """Equal, or one is a short form of the other (its start, three letters or more)."""
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    return a == b or (len(lo) >= 3 and hi.startswith(lo))


def _shares_word(person: idl.Person, words: Iterable[str]) -> bool:
    """A saved name shares a part of the person's name: any word of it, middle names too."""
    return any(_same_word(w, pw) for w in words for pw in person.words)


def _intro_conflicts(person: idl.Person, words: list[str]) -> bool:
    """A self-introduction names someone else: no word in common with the person's name, or
    the same first name with a different surname ("Daniel Jones" for Daniel Petrov)."""
    if not _shares_word(person, words):
        return True
    if len(words) > 1 and len(person.words) > 1:
        first_ok = _same_word(words[0], person.words[0])
        # The introduction may be cut after two words ("John Michael" of John Michael Smith),
        # so its second word conflicts only when it is no part of the person's name.
        return first_ok and not any(_same_word(words[-1], w) for w in person.words[1:])
    return False


# ---------------------------------------------------------------- someone else used it


def _intro_fits(
    case: Case, keys: set[Key], persons: list[idl.Person]
) -> tuple[list[tuple[Row, str]], str]:
    accounts = case.data.account_ids(keys)
    found: list[tuple[Row, str]] = []
    for row in _dedupe(
        case.data, [r for r in messages_for_accounts(case.data, accounts) if r.sender in accounts]
    ):
        for m in _INTRO.finditer(row.text or ""):
            if (row.text or "")[m.end() : m.end() + 1] in ("'", "’"):
                continue  # "this is Daniel's phone" names whose phone, not who is writing
            w1 = m.group(1).casefold()
            w2 = (m.group(2) or "").casefold()
            if w1 not in case.ids.known_words:
                continue
            # The second word is read as a surname only when the case knows it as a name word,
            # so "I'm Daniel working today" stays "Daniel".
            known = w2 and w2 not in _NOT_SURNAME and w2 in case.ids.known_words
            words = [w1] + ([w2] if known else [])
            named = " ".join(words)
            if persons and not all(_intro_conflicts(p, words) for p in persons):
                continue  # this one fits the claimed person; a later one may not
            if persons:
                who = " or ".join(cite(p.name) for p in persons)
                note = (
                    f"The account's user gives the name “{cite(named)}”, which does not match "
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
    seen: set[tuple[Key, str]] = set()  # per account: its copies on both phones show once
    for k in sorted(keys):
        g = case.ids.groups.get(k)
        if g is None:
            continue
        for s in g.names:
            text = s.text.strip()
            if s.kind == "user name" or "@" in text or not s.words or (k, text.casefold()) in seen:
                continue
            if any(_shares_word(p, s.words) for p in persons):
                continue
            seen.add((k, text.casefold()))
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


_NEGATED = re.compile(
    r"\b(?:never|not|no|cannot|didn'?t|didn’t|dont|don'?t|don’t|wont|won'?t|cant|can'?t|can’t|"
    r"havent|haven'?t|wasnt|wasn'?t|couldnt|couldn'?t|couldn’t|wouldnt|wouldn'?t|wouldn’t|"
    r"shouldnt|shouldn'?t|shouldn’t|won’t|didnt)\b"
    # Up to five words between the denial and the verb ("did not have a chance to use"), but
    # not across a word that starts a new clause ("no idea but i used his phone").
    r"(?:\s+(?!(?:but|and|so|then|yet|because|though|although|or|until|unless|since|when|"
    r"while|after|before)\b)[^\W\d_]+){0,5}\s*$",
    re.IGNORECASE,
)


# "his phone number", "her phone call": a contact detail or a call, not the device.
_NUMBER_AFTER = re.compile(
    r"\s*(?:number|num|no\b|nr\b|#|(?:a\s+)?(?:calls?|ring)\b)", re.IGNORECASE
)


def _handoff(body: str, app: str, claimed_app: str) -> re.Match[str] | None:
    """The first words in a message about using another person's phone, account or login that
    bear on a message sent on claimed_app."""
    for m in _HANDOFF.finditer(body):
        if _NEGATED.search(body[max(0, m.start() - 60) : m.start()]):
            continue  # "i never used his account" denies a hand-off
        if (m.group("whose1") or m.group("whose") or m.group("whose3") or "").casefold() == "my":
            continue  # logging in on one's own phone or account names no one else's
        thing = (m.group("thing") or m.group("thing2") or m.group("thing3") or "").casefold()
        if thing in _APP_WORDS:
            ok = _APP_WORDS[thing] == claimed_app.strip().casefold()
        elif thing in _DEVICE_WORDS:
            ok = True
        else:  # an account, a login, signed in: only in a conversation on the same app
            ok = app.strip().casefold() == claimed_app.strip().casefold()
        if ok and _NUMBER_AFTER.match(body, m.end()) is None:
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
        # SQL narrows by julianday(), to the millisecond, with a second's slack; the exact
        # bounds are checked on the parsed times below.
        slack = timedelta(seconds=1)
        rows = case.conn.execute(
            "SELECT m.id, m.source_id, t.app, m.sender_account_id, m.ts_utc, m.ts_raw, m.body"
            " FROM messages m JOIN threads t ON t.id = m.thread_id"
            " WHERE m.source_id = ? AND julianday(m.ts_utc) BETWEEN julianday(?) AND julianday(?)"
            " ORDER BY julianday(m.ts_utc), m.id",
            (c.source_id, _iso(lo - slack), _iso(hi + slack)),
        )
        for mid, sid, app, sender, ts, raw, body in rows:
            if mid in out:
                continue  # found already, near another claimed message
            at = _parse(ts)
            if at is None or not lo <= at <= hi:
                continue
            m = _handoff(body or "", app, c.app)
            if m is None:
                continue
            row = Row(mid, "message", sid, app, sender, _recipients(case, mid), at, raw, body)
            out[mid] = (
                row,
                f"The message itself speaks of using another person's phone, account or login "
                f"(“{cite(m.group(0))}”)."
                if mid in claimed_ids
                else f"Speaks of using another person's phone, account or login "
                f"(“{cite(m.group(0))}”), on the same phone near the message.",
            )
    anchor = claimed[0].ts_utc if claimed else None
    rows = _by_time(_dedupe(case.data, [r for r, _ in out.values()]), anchor)
    found = [out[r.id] for r in rows]
    searched = (
        "messages on " + "; ".join(dict.fromkeys(spans)) + " for words about using another "
        "person's phone, account or login"
        if spans
        else ""
    )
    return found, searched


def _iso(t: datetime) -> str:
    """UTC with microseconds kept. SQL compares it through julianday(), so a stored time with
    fractional seconds is ordered as a time, not as text."""
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def _multi_owner_fits(case: Case, keys: set[Key], persons: list[idl.Person]) -> list[Fit]:
    out: list[Fit] = []
    # Phones an expert confirmed as the named people's: a proposed stipulation is not ownership.
    named = {p.id for p in persons}
    theirs = {
        d for _, d, pid, status in case.data.stipulations if status == "confirmed" and pid in named
    }
    for k in sorted(keys):
        g = case.ids.groups.get(k)
        if g is None or len(set(g.owner_devices)) < 2:
            continue
        if theirs and set(g.owner_devices) <= theirs:
            continue  # every phone belongs to the people the claim names: no one else
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
    fits: list[Fit] = []
    searched: list[str] = []
    against: list[str] = []  # one sentence per statement that found something
    about_account = all(a.template_id == "person_identity" for a in mine)
    hand_pairs: list[tuple[Row, str]] = []  # collapsed across statements, as copies may repeat
    for a in mine:
        before = len(fits)
        # Each statement on its own: its accounts against its own people, so a name another
        # statement gives for another account never hides a conflict here.
        claimed = claimed_by_quote.get(a.id, [])
        keys: set[Key] = set()
        for r in claimed:
            acc = case.data.accounts.get(r.sender or "")
            if acc is not None:
                keys.add(acc.key)
        for aid in a.params.account_ids:
            acc = case.data.accounts.get(aid)
            if acc is not None:
                keys.add(acc.key)
        if a.params.handles:
            for p in parties(case.data, a.params)[len(a.params.person_ids) :]:
                keys |= p.keys
        persons = _persons(case, [a])
        if keys:
            if persons or a.template_id == "person_identity":  # a name, or a claim about it
                intros, s = _intro_fits(case, keys, persons)
                searched.append(s)
                fits += [_fit(case, r, n) for r, n in _sorted_pairs(intros)]
            if persons:
                fits += _name_fits(case, keys, persons)
                searched.append(f"names saved for {_account_label(case, keys)}")
            fits += _multi_owner_fits(case, keys, persons)
            searched.append("which phones hold each account as their own")
        hands: list[tuple[Row, str]] = []
        if claimed:
            hands, s = _handoff_fits(case, claimed)
            if s:
                searched.append(s)
            hand_pairs += hands
        found = len({f.record_id for f in fits[before:]} | {r.id for r, _ in hands})
        if found and persons:
            who = " or ".join(cite(p.name) for p in persons)
            against.append(
                f"For the statement naming {who}: {found} record(s) point to someone else "
                "using the account or phone."
            )
        elif found:
            against.append(
                f"{found} record(s) give the account's user a name, or point to another person "
                "using the account or phone; compare them with the person the claim names."
            )
    # A hand-off message held on both phones, found by statements about each, shows once.
    fits = _merge(fits + _collapse(case, hand_pairs))
    if not fits:
        return None
    title = (
        "Someone else may be behind the account"
        if about_account
        else "Someone else may have written it"
    )
    summary = " ".join(dict.fromkeys(against))
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
            if f.note in prev.note:
                continue  # the same finding from another statement
            out[f.record_id] = Fit(
                prev.record_id, prev.source_id, prev.locator, prev.quote, prev.when,
                f"{prev.note} {f.note}", prev.local,
            )  # fmt: skip
        else:
            out[f.record_id] = f
    return list(out.values())


def _collapse(case: Case, pairs: Iterable[tuple[Row, str]], name_copies: bool = False) -> list[Fit]:
    """One line per record across every statement. A record found again adds its note to its
    line. Copies on different phones share lines: the n-th identical row on a phone joins the
    n-th line of that copy key, so a key shows as many lines as the phone holding the most such
    rows (as in _dedupe), whichever phone comes first. name_copies prefixes a note that a copy
    on another phone adds with that phone, for notes that read the copy on its own phone."""
    fits: list[Fit] = []
    lines: dict[tuple[str, ...], list[int]] = {}  # copy key -> its lines, as indexes in fits
    count: dict[tuple[tuple[str, ...], str], int] = {}  # (copy key, phone) -> rows placed
    at: dict[str, int] = {}  # record id -> index in fits
    for r, note in pairs:
        i = at.get(r.id)
        if i is None:
            key = _copy_key(case.data, r)
            n = count.get((key, r.source_id), 0)
            count[(key, r.source_id)] = n + 1
            slots = lines.setdefault(key, [])
            if n >= len(slots):
                slots.append(len(fits))
                at[r.id] = len(fits)
                fits.append(_fit(case, r, note))
                continue
            i = at[r.id] = slots[n]
        old = fits[i]
        if name_copies and r.source_id != old.source_id:
            note = f"{cite(r.source_id)}'s copy: {note}"
        if note not in old.note:
            fits[i] = replace(old, note=f"{old.note} {note}")
    return fits


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
        return claimed.get(a.id, [])
    if CALL_CHANNEL in p.channels:
        # The same scope as the time check: the named phones, and every named party on the call.
        party_ids = [case.data.account_ids(x.keys) for x in parties(case.data, p)]
        if not party_ids or not all(party_ids):
            return []
        sources = set(case.data.sources_for(p.device_ids))
        rows = calls_for_accounts(case.data, set().union(*party_ids))
        if p.duration_s:
            lo, hi = p.duration_s
            rows = [r for r in rows if r.duration_s is not None and lo <= r.duration_s <= hi]
        return [
            r
            for r in rows
            if r.source_id in sources and channel_ok(r, p.channels) and involves_all(r, party_ids)
        ]
    return []


def _clock(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    # Only record_time: a weekday_date window is the day a message refers to, counted from its
    # send date, so another clock would move the target day too. Reading the send time alone on
    # another clock against the old target would mislead.
    mine = [a for a in assumptions if a.template_id == "record_time" and a.params.window]
    if not mine:
        return None
    claimed = _claimed_rows(case, mine)
    pairs: list[tuple[Row, str]] = []
    used: list[str] = []
    # Every copy is read on its own phone's clocks (phones can print different offsets). A
    # record shows once, from the first copy whose reading fits, across every statement; a copy
    # on another phone that fits too adds its own reading to that line.
    for a in mine:
        window = a.params.window
        wall = _wall(window) if window is not None else None
        if window is None or wall is None:
            continue
        rows = _clock_rows(case, a, claimed)
        offsets = case.offsets(r.id for r in rows)
        for r in rows:
            at = r.ts_utc
            if at is None or in_window(at, window):
                continue  # no usable time, or inside the stated time on the real clock
            tz = case.data.tz_for(r.source_id)
            if tz is None:
                continue  # the phone's own zone is unknown, so no reading is "another" clock
            if wall[0] <= at.astimezone(tz).replace(tzinfo=None) <= wall[1]:
                continue  # the stated time fits on the phone's own clock too; no other clock needed
            own = at.astimezone(tz).utcoffset()
            readings: list[tuple[str, datetime]] = []
            off = offsets.get(r.id)
            if off is not None and timedelta(minutes=off) != own:
                printed = (at + timedelta(minutes=off)).replace(tzinfo=None)
                readings.append((f"the clock the report printed ({_offset_text(off)})", printed))
            if own != timedelta(0) and off != 0:
                readings.append(("UTC", at.replace(tzinfo=None)))
            for label, t in readings:
                if wall[0] <= t <= wall[1]:
                    phone = (
                        f"on the phone's own clock ({case.data.sources[r.source_id].tz}) it is "
                        f"{local_str(case.data, r)}"
                    )
                    pairs.append(
                        (
                            r,
                            f"Read on {label}, this record is at {_day(t)}, inside the stated "
                            f"time {cite(window.raw)}; {phone}.",
                        )
                    )
                    used.append(a.id)
                    break
    fits = _collapse(case, pairs, name_copies=True)  # each record once, every copy's reading
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
    summaries: list[str] = []
    pairs: list[tuple[Row, str]] = []
    for a in assumptions:
        window = a.params.window
        if a.template_id not in _WINDOW_TEMPLATES or window is None or window.tz == "UTC":
            continue
        wall = _wall(window)
        got = _party_rows(case, a)
        if wall is None or got is None:
            continue
        # A message count counts messages only, so a call cannot move it; no_contact covers calls.
        msgs_only = a.template_id == "message_count"
        srcs = set(case.data.sources_for(a.params.device_ids))
        rows = _dedupe(
            case.data,
            [
                r
                for r in got[0]
                if r.source_id in srcs
                and channel_ok(r, a.params.channels)
                and not (msgs_only and r.kind == "call")
            ],
        )
        lo, hi = wall[0].replace(tzinfo=UTC), wall[1].replace(tzinfo=UTC)
        stated = {r.id for r in rows if r.ts_utc and in_window(r.ts_utc, window)}
        as_utc = {r.id for r in rows if r.ts_utc and lo <= r.ts_utc <= hi}
        moved = [r for r in rows if (r.id in stated) != (r.id in as_utc)]
        if not moved:
            continue
        used.append(a.id)
        summaries.append(
            f"Read in UTC instead of {cite(window.tz)}, the stated dates {cite(window.raw)} "
            f"hold {len(as_utc)} record(s) between these parties instead of {len(stated)}."
        )
        for r in _by_time(moved):
            zone = cite(window.tz)
            side = (
                f"inside them read in the stated zone {zone}, outside them in UTC"
                if r.id in stated
                else f"outside them read in the stated zone {zone}, inside them in UTC"
            )
            pairs.append((r, f"For the stated dates {cite(window.raw)}, this record is {side}."))
    fits = _collapse(case, pairs)  # a record two statements both move shows once
    if not fits:
        return None
    return Alternative(
        "day_boundary",
        "timing",
        "The day boundary depends on the time zone",
        " ".join(dict.fromkeys(summaries)),
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Searched messages (and calls, for a statement of no contact) between the parties the "
        "claim names, on the apps it names, and compared the stated dates in the stated zone "
        "with the same dates in UTC.",
        tuple(used),
    )


# ---------------------------------------------------------------- another app


def _other_app(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    fits: list[Fit] = []
    used: list[str] = []
    summaries: list[str] = []
    pairs: list[tuple[Row, str]] = []
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
        srcs = set(case.data.sources_for(p.device_ids))
        others = [
            r
            for r in got[0]
            if r.source_id in srcs
            and r.ts_utc
            and in_window(r.ts_utc, window)
            and not channel_ok(r, p.channels)
        ]
        others = _dedupe(case.data, others)
        if not others:
            continue
        used.append(a.id)
        # One sentence per statement, so each names only its own apps and window.
        summaries.append(
            f"Inside {cite(window.raw)} the same people were in contact outside "
            f"{_joined(apps)}: {len(others)} record(s) on other apps or calls."
        )
        for r in _by_time(others):
            what = "A call" if r.kind == "call" else f"A {cite(r.app)} message"
            pairs.append(
                (
                    r,
                    f"{what} between the same people inside {cite(window.raw)}, outside "
                    f"{_joined(apps)}.",
                )
            )
    fits = _collapse(case, pairs)
    if not fits:
        return None
    return Alternative(
        "other_app",
        "completeness",
        "The conversation may have gone on another app",
        " ".join(dict.fromkeys(summaries)),
        tuple(fits[:MAX_FITS]),
        len(fits),
        "Searched messages and calls between the parties the claim names, inside its window, on "
        "every app it does not name.",
        tuple(used),
    )


# ---------------------------------------------------------------- a whole app gone quiet

# Every message and call on one phone. Times are compared in Python as datetimes, to the
# microsecond, never as text or through SQLite's millisecond julianday().
_PHONE_RECORDS = (
    "SELECT m.id, 'message', m.source_id, t.app, m.sender_account_id, m.ts_utc, m.ts_raw,"
    " m.body, NULL, NULL FROM messages m JOIN threads t ON t.id = m.thread_id"
    " WHERE m.source_id = ?"
    " UNION ALL"
    " SELECT c.id, 'call', c.source_id, c.app, c.from_account_id, c.ts_utc, c.ts_raw, NULL,"
    " c.duration_s, c.to_account_id FROM calls c WHERE c.source_id = ?"
)


def _phone_rows(case: Case, sid: str) -> list[Row]:
    """Read once per phone and kept on the case, so a report reads each phone's records once."""
    if sid not in case.phone_rows:
        case.phone_rows[sid] = [
            # A call's callee is read here; a message's recipients only for the edges shown.
            Row(
                r[0],
                r[1],
                r[2],
                r[3],
                r[4],
                (r[9],) if r[9] else (),
                _parse(r[5]),
                r[6],
                r[7],
                r[8],
            )
            for r in case.conn.execute(_PHONE_RECORDS, (sid, sid))
        ]
    return case.phone_rows[sid]


def _app_quiet(case: Case, assumptions: list[Assumption]) -> Alternative | None:
    pairs: list[tuple[Row, str]] = []
    used: list[str] = []
    # Per app and window, the phones where that app is quiet: one sentence each, so no sentence
    # joins an app to a window it was not found quiet in.
    quiet: dict[tuple[str, str, datetime, datetime], list[str]] = {}
    for a in assumptions:
        p = a.params
        apps = [c for c in p.channels if c.strip().lower() != CALL_CHANNEL]
        if a.template_id not in _SILENCE_TEMPLATES or p.window is None or not apps:
            continue
        window = p.window
        for app in apps:
            for sid in case.data.sources_for(p.device_ids):
                rows = _phone_rows(case, sid)
                mine_ = [r for r in rows if r.app.strip().casefold() == app.strip().casefold()]
                holds = len(mine_)
                untimed = sum(1 for r in mine_ if r.ts_utc is None)
                inside = sum(1 for r in mine_ if r.ts_utc and in_window(r.ts_utc, window))
                rest = sum(
                    1
                    for r in rows
                    if r.app.strip().casefold() != app.strip().casefold()
                    and r.ts_utc
                    and in_window(r.ts_utc, window)
                )
                if not holds:
                    continue  # this phone holds no records of the app at all
                if inside or untimed:
                    continue  # the app has records in the window, or some that cannot be placed
                if not rest:
                    continue  # the whole phone is quiet; the gaps view covers that
                used.append(a.id)
                # Keyed by the resolved window too: one wording can mean different periods.
                key = (app, window.raw, window.start_utc, window.end_utc)
                phones = quiet.setdefault(key, [])
                phones.append(f"{cite(sid)} ({rest} other record(s))")
                timed = [r for r in mine_ if r.ts_utc is not None]
                before = [r for r in timed if r.ts_utc < window.start_utc]  # type: ignore[operator]
                after = [r for r in timed if r.ts_utc > window.end_utc]  # type: ignore[operator]
                edges = (
                    ("last before", max(before, key=lambda r: (r.ts_utc, r.id), default=None)),
                    ("first after", min(after, key=lambda r: (r.ts_utc, r.id), default=None)),
                )
                for edge, row in edges:
                    if row is None:
                        continue
                    if row.kind == "message":  # copies are told apart by who they went to
                        row = replace(row, recipients=_recipients(case, row.id))
                    pairs.append(
                        (
                            row,
                            f"The {edge} {cite(window.raw)} on {cite(sid)}: its nearest "
                            f"{cite(app)} record in any conversation.",
                        )
                    )
    # An edge two windows share, or its copy on the other phone, shows once with each note.
    fits = _collapse(case, pairs)
    if not fits:
        return None
    return Alternative(
        "app_quiet",
        "completeness",
        "The whole app is quiet, not one conversation",
        " ".join(
            f"{cite(app)} has no record in any conversation in {cite(window)} on "
            f"{'; '.join(dict.fromkeys(phones))}, while the phone's other apps and calls go on."
            for (app, window, _, _), phones in quiet.items()
        )
        + " A silence across a whole app can come from the app or the extraction, not only from "
        "one conversation.",
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
    pairs: list[tuple[Row, str]] = []
    used: list[str] = []
    # Copy key -> seconds from the nearest quoted message. Keyed by copy, not record id: copies
    # share a line, and each copy's distance from its own phone's quote counts for the line.
    near: dict[tuple[str, ...], float] = {}
    for a in mine:
        qt = a.params.quoted_text or ""
        words = _words(qt)
        claimed = _quoted_rows(case, a)
        if not words or not claimed:
            continue
        copies = {_copy_key(case.data, r) for r in claimed}
        claimed_ids = {r.id for r in claimed}
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
                row = Row(
                    mid, "message", sid, app, sender, _recipients(case, mid), _parse(ts), raw, body
                )
                if row.id in claimed_ids or _copy_key(case.data, row) in copies:
                    continue  # the claimed message, or its copy on the other phone
                found.append((row, f"Uses “{cite(m.group(0))}” in the same conversation."))
        rows = _dedupe(case.data, [r for r, _ in found])
        notes = {r.id: n for r, n in found}
        anchor = claimed[0].ts_utc
        pairs += [(r, notes[r.id]) for r in _by_time(rows, anchor)]
        # From every quoted message: one quote can stand in several messages.
        quoted_at = [c.ts_utc for c in claimed if c.ts_utc is not None]
        for r in rows:
            gap = min(
                (abs((r.ts_utc - t).total_seconds()) for t in quoted_at if r.ts_utc),
                default=float("inf"),
            )
            k = _copy_key(case.data, r)
            near[k] = min(gap, near.get(k, gap))
        if rows:
            used.append(a.id)
    fits = _collapse(case, pairs)  # a message, or its copies, two statements share shows once
    # Nearest in time first across every statement, so one quote's far matches never crowd
    # out another quote's near ones.
    key_of = {r.id: _copy_key(case.data, r) for r, _ in pairs}
    fits.sort(key=lambda f: near.get(key_of[f.record_id], float("inf")))
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
    return [_located(case, alt) for find in finders if (alt := find(case, assumptions)) is not None]
