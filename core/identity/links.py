"""Proposed identity links, and what the data says for and against each one. Code only.

A person is a name in the case: a phone owner from a device_owner stipulation, or a name the
expert added because the government document uses it ("ALEXANDER SOKOLOV"). An account is
grouped with its copies on other phones by app and identifier (the checks' key()).

Proposing. A link (account -> person) is proposed only where a record in the extraction puts a
form of the person's name on the account:
- a saved contact with the account's phone number (a contact entry that is not a phone number
  counts only when it is exactly the account's identifier, and says the app is not stated);
- the account name the report printed, a one-to-one thread titled with it, or the sender text
  printed on its messages;
- the letters of a user name or handle ("@alex92" holds "alex").
The form is one of: the full name, the one-word name, the surname, the first name alone, or a
short form of the first name (one is the start of the other, three letters or more: "Alex",
"Alexander"). Nicknames, transliteration and spelling variants are not guessed. Accounts on a
phone stipulated to the same person are skipped: the stipulation already ties them.

What counts against a link, shown beside it (never weighed by code):
- other names the same account carries that share no part of the person's name ("Sasha N");
- the account's user naming themselves in a message ("hey its alex turner") with a different
  surname, or with another name that the case's contact or account names use;
- the account being an owner account of a phone stipulated to someone else;
- other accounts that carry the same name at least as well.
Messages in the account's conversations that use the name are listed as context, unlabeled.

Nothing here confirms anything. A proposal is status 'proposed', tier 'inferred'. It widens
what retrieval searches for the person (core/audit/retrieval.py) and nothing else: checks use
a link only after an expert confirms it (core/review/actions.py), and every report lists each
confirmed link as a limitation. A claim that states the link itself ("@northstar is ALEXANDER
SOKOLOV") is flagged: confirming the link does not decide that claim.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum

from core.audit.checks._common import CaseData, Key, key
from core.contracts import Fidelity, short_hash
from core.review import audit_log

PROPOSER_VERSION = "1.0.0"
PROPOSER = f"system:identity-names@{PROPOSER_VERSION}"
PROPOSE_ACTION = "identity.propose"
MENTION_LIMIT = 12
SHORT_MIN = 3  # letters in a short form ("Al" is too short to mean Alexander)

Clock = Callable[[], datetime]


class Level(IntEnum):
    """How a name seen on an account matches a person's name. Higher is closer."""

    SHORT = 1
    FIRST = 2
    SURNAME = 3
    NAME = 4
    FULL = 5


LEVEL_TEXT = {
    Level.FULL: "the full name",
    Level.NAME: "the name",
    Level.SURNAME: "the surname",
    Level.FIRST: "the first name alone",
    Level.SHORT: "a short form of the first name",
}


def level_phrase(level: Level, name: str) -> str:
    """'a short form of the first name of ALEXANDER SOKOLOV'."""
    who = cite(name)
    return f"{LEVEL_TEXT[level]} of {who}" if level is not Level.NAME else f"the name {who}"


# Words that follow "its <name>" without being a surname.
_NOT_SURNAME = frozenset(
    "btw here again now from bro man lol new too ok okay haha the and dont not just with at in "
    "on calling texting speaking again sorry hi hey yo".split()
)
_INTRO = re.compile(
    r"(?:^|[^\w])(?:it'?s|it’s|this is|i am|i'm|i’m|im)\s+([^\W\d_]+)(?:[ \t]+([^\W\d_]+))?",
    re.IGNORECASE,
)
# Runs of capitalised words in a claim: affidavits print names in capitals ("SOKOLOV").
_CAPS_RUN = re.compile(r"\b[A-ZА-ЯЁ][A-ZА-ЯЁ'’\-]{2,}(?:\s+[A-ZА-ЯЁ][A-ZА-ЯЁ'’\-]{2,})*\b")
_CAPS_STOP = frozenset(
    "SMS MMS UTC GMT EST EDT CST PST GPS DEA FBI ATF HSI NYPD USA LLC INC IMEI IMSI ICCID PDF "
    "CSV URL WIFI NOTE UFED UFDR AXIOM APP IOS RCS VOIP CDR ESN MEID SIM USB IP".split()
)


CITE_OPEN, CITE_CLOSE = "\x02", "\x03"


def cite(value: object) -> str:
    """Mark text taken from the case (names, record text) inside a note, so a screen can show
    it as cited text and never as the tool's own words."""
    text = str(value).replace(CITE_OPEN, "").replace(CITE_CLOSE, "")
    return f"{CITE_OPEN}{text}{CITE_CLOSE}"


def plain(note: str) -> str:
    """A note with its citation marks removed, for storing (identity_links.basis)."""
    return note.replace(CITE_OPEN, "").replace(CITE_CLOSE, "")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def tokens(text: str | None) -> list[str]:
    """Name words: runs of letters, two or more, casefolded. '@alex92' -> ['alex']."""
    if not text:
        return []
    return [t for t in re.findall(r"[^\W\d_]+", _nfc(text).casefold()) if len(t) >= 2]


def _short(a: str, b: str) -> bool:
    """One word is a short form of the other: the start of it, three letters or more."""
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    return lo != hi and len(lo) >= SHORT_MIN and hi.startswith(lo)


def match_level(person: list[str], name: Iterable[str]) -> Level | None:
    """How the words of a name seen in the data match a person's name words."""
    if not person:
        return None
    seen = set(name)
    first, last = person[0], person[-1]
    if len(person) > 1 and set(person) <= seen:
        return Level.FULL
    if len(person) == 1 and first in seen:
        return Level.NAME
    if len(person) > 1 and last in seen:
        return Level.SURNAME
    if len(person) > 1 and first in seen:
        return Level.FIRST
    if any(_short(first, t) for t in seen):
        return Level.SHORT
    return None


def person_id_for(name: str, taken: Iterable[str] = ()) -> str:
    """A readable, stable id for a person the expert adds: 'person:alexander-sokolov'."""
    slug = "-".join(tokens(name)) or "unnamed"
    pid = f"person:{slug}"
    return pid if pid not in set(taken) else f"{pid}-{short_hash(_nfc(name).casefold())[:8]}"


def link_id(account_id: str, person_id: str) -> str:
    return f"link:{account_id}|{person_id}"


# ---------------------------------------------------------------- what the data holds


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    created_by: str
    words: tuple[str, ...]
    devices: tuple[str, ...]  # phones stipulated to this person (not withdrawn)


@dataclass(frozen=True)
class Seen:
    """A name the extraction puts on an account: the text exactly as the record holds it."""

    text: str
    kind: str  # 'saved contact', 'account name', 'thread title', 'printed sender', 'user name'
    record_id: str
    source_id: str
    locator: str
    note: str = ""  # e.g. the contact list does not say which app

    @property
    def words(self) -> list[str]:
        return tokens(self.text)


@dataclass(frozen=True)
class Signal:
    """One record for or against a link, or a message that uses the name."""

    record_id: str
    source_id: str
    locator: str
    quote: str  # verbatim from the record
    note: str


@dataclass
class AccountGroup:
    """An account and its copies on other phones (same app and identifier)."""

    key: Key
    account_ids: list[str]
    app: str
    identifier: str
    owner_devices: list[str]  # phones this is an owner account on
    names: list[Seen] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.app} {self.identifier}"


@dataclass
class Candidate:
    group: AccountGroup
    person: Person
    level: Level
    account_id: str  # the representative account the link row points at
    support: list[Signal] = field(default_factory=list)
    against: list[Signal] = field(default_factory=list)
    mentions: list[Signal] = field(default_factory=list)
    basis: str = ""


@dataclass
class Case:
    """Everything the proposer and the identity screen read, loaded once."""

    conn: sqlite3.Connection
    data: CaseData
    persons: list[Person]
    groups: dict[Key, AccountGroup]
    device_labels: dict[str, str]
    stipulated: dict[str, str]  # device id -> person id, stipulations not withdrawn
    known_words: set[str]  # every word of every name in the case
    account_refs: dict[str, tuple[str, str]]  # account id -> (source id, locator)

    def account_signal(self, account_id: str, quote: str, note: str) -> Signal:
        sid, loc = self.account_refs.get(account_id, ("", ""))
        return Signal(account_id, sid, loc, quote, note)

    def where(self, source_id: str) -> str:
        """How the screen names a source: its id, as record lines do ('item1')."""
        return source_id


def load(conn: sqlite3.Connection) -> Case:
    data = CaseData(conn)
    device_labels = {
        did: label for did, label in conn.execute("SELECT id, label FROM devices ORDER BY id")
    }
    stipulated: dict[str, str] = {}
    by_person: dict[str, list[str]] = defaultdict(list)
    for _sid, device_id, pid, status in data.stipulations:
        if status != "rejected":
            stipulated[device_id] = pid
            by_person[pid].append(device_id)
    persons = [
        Person(pid, name, created_by, tuple(tokens(name)), tuple(by_person.get(pid, ())))
        for pid, name, created_by in conn.execute(
            "SELECT id, name, created_by FROM persons ORDER BY id"
        )
    ]

    groups: dict[Key, AccountGroup] = {}
    acc_rows = list(
        conn.execute(
            "SELECT id, source_id, locator, device_id, app, identifier, display_name"
            " FROM accounts ORDER BY id"
        )
    )
    for aid, sid, loc, dev, app, ident, display in acc_rows:
        k = key(app, ident)
        g = groups.setdefault(k, AccountGroup(k, [], app, ident, []))
        g.account_ids.append(aid)
        if dev:
            g.owner_devices.append(dev)
        if display:
            g.names.append(Seen(display, "account name", aid, sid, loc))
        if k[0] != "tel" and tokens(ident) and not ident.strip().isdigit():
            g.names.append(Seen(ident, "user name", aid, sid, loc))
    by_account = {aid: key(app, ident) for aid, _s, _l, _d, app, ident, _n in acc_rows}

    for cid, sid, loc, name, ident in conn.execute(
        "SELECT id, source_id, locator, name, identifier FROM contacts ORDER BY id"
    ):
        if not name or not name.strip():
            continue
        if ident.strip().startswith("+"):
            k = key("Phone", ident)
            if k in groups:
                groups[k].names.append(Seen(name, "saved contact", cid, sid, loc))
            continue
        for k, g in groups.items():  # same identifier on another app: the list does not say
            if k[0] != "tel" and k[1] == ident.strip():
                g.names.append(
                    Seen(
                        name,
                        "saved contact",
                        cid,
                        sid,
                        loc,
                        f"the entry {cite(ident.strip())} matches this {cite(g.app)} id; the "
                        "contact list does not say which app it is for",
                    )
                )

    for tid, sid, loc, title in conn.execute(
        "SELECT id, source_id, locator, title FROM threads WHERE title IS NOT NULL ORDER BY id"
    ):
        parts = {
            by_account[a]
            for (a,) in conn.execute(
                "SELECT sender_account_id FROM messages WHERE thread_id = ?"
                " AND sender_account_id IS NOT NULL"
                " UNION SELECT r.account_id FROM message_recipients r"
                " JOIN messages m ON m.id = r.message_id WHERE m.thread_id = ?",
                (tid, tid),
            )
            if a in by_account
        }
        others = [k for k in parts if not groups[k].owner_devices]
        if len(others) == 1:  # a one-to-one thread names the other side
            groups[others[0]].names.append(Seen(title, "thread title", tid, sid, loc))

    if data.has_sender_raw:
        firsts: dict[tuple[Key, str], tuple[str, str, str]] = {}
        for mid, sid, loc, aid, raw in conn.execute(
            "SELECT id, source_id, locator, sender_account_id, sender_raw FROM messages"
            " WHERE sender_raw IS NOT NULL AND sender_account_id IS NOT NULL ORDER BY id"
        ):
            k = by_account.get(aid)
            if k is not None and raw.strip():
                firsts.setdefault((k, raw.strip()), (mid, sid, loc))
        for (k, raw), (mid, sid, loc) in firsts.items():
            groups[k].names.append(Seen(raw, "printed sender", mid, sid, loc))

    known = {w for g in groups.values() for s in g.names if s.kind != "user name" for w in s.words}
    known |= {w for p in persons for w in p.words}
    refs = {aid: (sid, loc) for aid, sid, loc, *_ in acc_rows}
    return Case(conn, data, persons, groups, device_labels, stipulated, known, refs)


# ---------------------------------------------------------------- one candidate link


def _sig(s: Seen, note: str) -> Signal:
    return Signal(s.record_id, s.source_id, s.locator, s.text, note)


def _best(person: Person, group: AccountGroup) -> list[tuple[Level, Seen]]:
    out = []
    for s in group.names:
        lvl = match_level(list(person.words), s.words)
        if lvl is not None:
            out.append((lvl, s))
    return sorted(out, key=lambda x: (-x[0], x[1].record_id))


def _intros(case: Case, group: AccountGroup) -> list[tuple[str, str, str, str, str, str]]:
    """Messages where the account's user names themselves: (id, source, locator, body, w1, w2)."""
    if not group.account_ids:
        return []
    marks = ",".join("?" * len(group.account_ids))
    out = []
    for mid, sid, loc, body in case.conn.execute(
        f"SELECT id, source_id, locator, body FROM messages WHERE sender_account_id IN ({marks})"  # noqa: S608
        " ORDER BY ts_utc, id",
        group.account_ids,
    ):
        for m in _INTRO.finditer(_nfc(body)):
            w1 = m.group(1).casefold()
            w2 = (m.group(2) or "").casefold()
            if w1 in case.known_words:
                out.append((mid, sid, loc, body, w1, w2 if w2 not in _NOT_SURNAME else ""))
                break
    return out


def _intro_side(person: Person, w1: str, w2: str) -> tuple[str, str] | None:
    """('for' | 'against', note) for a self-introduction, or None if it says nothing."""
    words = list(person.words)
    first, last = words[0], words[-1]
    named = cite(f"{w1} {w2}".strip())
    who = cite(person.name)
    first_ok = w1 == first or _short(first, w1)
    if len(words) > 1:
        if first_ok and w2 and w2 == last:
            return "for", f"The account's user gives the name {named}."
        if first_ok and w2:
            return (
                "against",
                f"The account's user gives the name {named}: the same first name, but a "
                f"different surname from {who}.",
            )
        if w1 == last:
            return "for", f"The account's user gives the name {named}."
        if first_ok:
            return None  # a first name alone is already counted from the account's names
    elif first_ok:
        return "for", f"The account's user gives the name {named}."
    return (
        "against",
        f"The account's user gives the name {named}, which is not part of {who} as written.",
    )


def _mentions(case: Case, group: AccountGroup, words: set[str], skip: set[str]) -> list[Signal]:
    """Messages in the account's conversations that use one of these words. Context only."""
    if not group.account_ids or not words:
        return []
    marks = ",".join("?" * len(group.account_ids))
    threads = [
        r[0]
        for r in case.conn.execute(
            f"SELECT DISTINCT thread_id FROM messages WHERE sender_account_id IN ({marks})"  # noqa: S608
            " UNION SELECT DISTINCT m.thread_id FROM message_recipients r"
            f" JOIN messages m ON m.id = r.message_id WHERE r.account_id IN ({marks})",
            [*group.account_ids, *group.account_ids],
        )
    ]
    sent = _sent_by(case, group)
    out: list[Signal] = []
    for tid in sorted(threads):
        for mid, sid, loc, body in case.conn.execute(
            "SELECT id, source_id, locator, body FROM messages WHERE thread_id = ?"
            " ORDER BY ts_utc, id",
            (tid,),
        ):
            if mid in skip or not (set(tokens(body)) & words):
                continue
            mine = mid in sent
            out.append(
                Signal(
                    mid,
                    sid,
                    loc,
                    body,
                    "Sent by this account." if mine else "Sent to this account's conversation.",
                )
            )
    return out[:MENTION_LIMIT]


def _sent_by(case: Case, group: AccountGroup) -> set[str]:
    marks = ",".join("?" * len(group.account_ids))
    return {
        r[0]
        for r in case.conn.execute(
            f"SELECT id FROM messages WHERE sender_account_id IN ({marks})",  # noqa: S608
            group.account_ids,
        )
    }


def _describe(case: Case, s: Seen, lvl: Level, person: Person) -> str:
    where = case.where(s.source_id)
    extra = f" ({s.note})" if s.note else ""
    return f"{cite(where)} {s.kind} {cite(s.text)} matches {level_phrase(lvl, person.name)}{extra}."


def candidate(case: Case, person: Person, group: AccountGroup) -> Candidate | None:
    """The proposal for one person and one account, or None if no record names them."""
    if not person.words or any(d in person.devices for d in group.owner_devices):
        return None
    matched = _best(person, group)
    intros = _intros(case, group)
    intro_sides = [(i, _intro_side(person, i[4], i[5])) for i in intros]
    if not matched and not any(side and side[0] == "for" for _, side in intro_sides):
        return None
    level = matched[0][0] if matched else Level.NAME
    rep = matched[0][1].record_id if matched else group.account_ids[0]
    rep = rep if rep in group.account_ids else sorted(group.account_ids)[0]
    c = Candidate(group, person, level, rep)
    for lvl, s in matched:
        c.support.append(_sig(s, _describe(case, s, lvl, person)))
    matched_ids = {s.record_id for _, s in matched}
    seen_other: set[str] = set()
    for s in group.names:
        if s.record_id in matched_ids or s.kind == "user name" or "@" in s.text:
            continue  # a handle is a pseudonym, not another name
        if _nfc(s.text).casefold() in seen_other:
            continue
        seen_other.add(_nfc(s.text).casefold())
        if not s.words:
            continue
        extra = f" ({s.note})" if s.note else ""
        c.against.append(
            _sig(
                s,
                f"{cite(case.where(s.source_id))} {s.kind} {cite(s.text)} shares no part of "
                f"{cite(person.name)}{extra}.",
            )
        )
    for (mid, sid, loc, body, _w1, _w2), side in intro_sides:
        if side is None:
            continue
        sig = Signal(mid, sid, loc, body, side[1])
        (c.support if side[0] == "for" else c.against).append(sig)
    for dev in sorted(set(group.owner_devices)):
        owner = case.stipulated.get(dev)
        if owner and owner != person.id:
            name = next((p.name for p in case.persons if p.id == owner), owner)
            owned = next(a for a in group.account_ids if case.data.accounts[a].device_id == dev)
            c.against.append(
                case.account_signal(
                    owned,
                    group.label,
                    f"This is an owner account of {cite(case.device_labels.get(dev, dev))}, which "
                    f"the expert stipulated as the phone of {cite(name)}.",
                )
            )
    words = set(person.words)
    for _lvl, s in matched:
        words |= set(s.words)
    words |= {w for s in group.names if s.kind != "user name" for w in s.words if len(w) >= 3}
    shown = {s.record_id for s in [*c.support, *c.against]}
    c.mentions = _mentions(case, group, words, shown)
    first = matched[0][1] if matched else None
    c.basis = (
        f"{cite(case.where(first.source_id))} {first.kind} {cite(first.text)} matches "
        f"{level_phrase(level, person.name)}."
        if first
        else f"The account's user gives a name matching {cite(person.name)}."
    ) + f" Proposed by code ({PROPOSER}) from names in the data; not confirmed."
    return c


def candidates(case: Case, person: Person) -> list[Candidate]:
    out = [c for g in case.groups.values() if (c := candidate(case, person, g)) is not None]
    out.sort(key=lambda c: (-c.level, c.group.label))
    for c in out:  # other accounts that carry the name at least as well
        rivals = [o for o in out if o is not c and o.level >= c.level]
        for o in rivals:
            c.against.append(
                case.account_signal(
                    o.account_id,
                    o.group.label,
                    f"Another account also matches {level_phrase(o.level, c.person.name)}: "
                    f"{cite(o.group.label)}.",
                )
            )
    return out


# ---------------------------------------------------------------- storing proposals


@dataclass
class ProposeResult:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def propose_links(conn: sqlite3.Connection, clock: Clock | None = None) -> ProposeResult:
    """Store a 'proposed' link for every candidate that has no link row yet, and remove
    proposals whose names are no longer in the data (a person renamed or removed). A link an
    expert decided (confirmed, rejected, left unresolved) is never touched."""
    case = load(conn)
    wanted: dict[str, Candidate] = {}
    for p in case.persons:
        for c in candidates(case, p):
            wanted[link_id(c.account_id, p.id)] = c
    existing = {
        lid: (status, decided_by)
        for lid, status, decided_by in conn.execute(
            "SELECT id, status, decided_by FROM identity_links"
        )
    }
    by_pair = {
        (aid, pid) for aid, pid in conn.execute("SELECT account_id, person_id FROM identity_links")
    }
    result = ProposeResult()
    for lid, c in sorted(wanted.items()):
        same_group = any((a, c.person.id) in by_pair for a in c.group.account_ids)
        if lid in existing or same_group:
            continue
        result.added.append(lid)
    for lid, (status, decided_by) in sorted(existing.items()):
        if status == "proposed" and decided_by is None and lid not in wanted:
            result.removed.append(lid)
    if not result.added and not result.removed:
        return result
    now = (clock or (lambda: datetime.now(UTC)))()
    with conn:
        for lid in result.added:
            c = wanted[lid]
            conn.execute(
                "INSERT INTO identity_links (id, account_id, person_id, status, tier, basis)"
                " VALUES (?, ?, ?, 'proposed', 'inferred', ?)",
                (lid, c.account_id, c.person.id, plain(c.basis)),
            )
        for lid in result.removed:
            conn.execute("DELETE FROM identity_links WHERE id = ?", (lid,))
        audit_log.append(
            conn,
            now,
            "system",
            PROPOSE_ACTION,
            {"proposer": PROPOSER, "added": result.added, "removed": result.removed},
        )
    return result


# ---------------------------------------------------------------- names in the document


def claims_naming(conn: sqlite3.Connection, person: Person) -> list[tuple[str, str]]:
    """Claims (not removed) that use the person's full name or surname, the way the assumption
    filler resolves names. (claim id, text)."""
    if not person.words:
        return []
    names = {" ".join(person.words), person.words[-1]}
    out = []
    for cid, text in conn.execute(
        "SELECT id, text FROM claims WHERE status != 'removed' ORDER BY id"
    ):
        flat = " ".join(_nfc(text).casefold().split())
        if any(_word_in(n, flat) for n in names):
            out.append((cid, text))
    return out


def claims_stating(case: Case, c: Candidate) -> list[str]:
    """Identity claims that state this very link: they use the person's name and a name, user
    name or number the account carries."""
    names = {_nfc(s.text).casefold() for s in c.group.names} | {c.group.identifier.casefold()}
    out = []
    for cid, _text in claims_naming(case.conn, c.person):
        row = case.conn.execute(
            "SELECT text, claim_type FROM claims WHERE id = ?", (cid,)
        ).fetchone()
        text = _nfc(row[0]).casefold()
        if row[1] == "identity" and any(n and _word_in(n, text) for n in names):
            out.append(cid)
    return out


def _word_in(needle: str, hay: str) -> bool:
    return re.search(r"(?<![\w@])" + re.escape(needle) + r"(?!\w)", hay) is not None


def resolves(persons: Iterable[Person], name: str) -> list[str]:
    """Persons a name resolves to, by the assumption filler's rule (whole name or surname)."""
    n = " ".join(tokens(name))
    return [p.id for p in persons if p.words and (n == " ".join(p.words) or n == p.words[-1])]


@dataclass(frozen=True)
class UnplacedName:
    name: str
    claim_ids: tuple[str, ...]
    matches: int  # persons it resolves to: 0, or 2+ (ambiguous)


def unplaced_names(conn: sqlite3.Connection, persons: list[Person]) -> list[UnplacedName]:
    """Names the claims use that resolve to no person, or to several. Capitalised runs of words
    in the claim text, plus the names the assumption filler's model output proposed for a claim
    and that appear verbatim in it. Suggestions for the expert; nothing is created."""
    found: dict[str, set[str]] = defaultdict(set)
    shown: dict[str, str] = {}
    claims = dict(conn.execute("SELECT id, text FROM claims WHERE status != 'removed'"))

    def add(name: str, cid: str) -> None:
        words = [w for w in name.split() if w.strip("'’-").upper() not in _CAPS_STOP]
        name = " ".join(words).strip(" '’-")
        if not tokens(name):
            return
        k = " ".join(tokens(name))
        found[k].add(cid)
        shown.setdefault(k, name)

    for cid, text in claims.items():
        for m in _CAPS_RUN.finditer(text):
            add(m.group(0), cid)
    for cid, name in _filler_people(conn):
        if cid in claims and _word_in(_nfc(name).casefold(), _nfc(claims[cid]).casefold()):
            add(name, cid)
    out = []
    for k, cids in found.items():
        hits = resolves(persons, shown[k])
        if len(hits) != 1:
            out.append(UnplacedName(shown[k], tuple(sorted(cids)), len(hits)))
    return sorted(out, key=lambda u: (-len(u.claim_ids), u.name.casefold()))


def _filler_people(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(claim id, name) from stored assumption-filler outputs. Model output: only names that
    also appear verbatim in the claim are used, by the caller."""
    import json

    out = []
    for subject, raw in conn.execute(
        "SELECT c.subject_json, c.raw_output FROM model_calls c"
        " JOIN model_runs r ON r.id = c.model_run_id WHERE r.purpose = 'assumptions'"
        " AND c.outcome = 'ok'"
    ):
        try:
            ids = json.loads(subject)
            props = json.loads(raw).get("assumptions", [])
        except (ValueError, AttributeError):
            continue
        cid = ids[0] if isinstance(ids, list) and len(ids) == 1 else None
        if not isinstance(cid, str) or not isinstance(props, list):
            continue
        for p in props:
            people = p.get("people", []) if isinstance(p, dict) else []
            out += [(cid, n) for n in people if isinstance(n, str) and n.strip()]
    return out


def searched_note(case: Case) -> str:
    """What a search for a person's name on accounts covered, for a person with no candidate."""
    parts = []
    for sid, info in sorted(case.data.sources.items()):
        cover = {
            Fidelity.FULL_EXTRACTION: "a full extraction",
            Fidelity.CURATED_REPORT: "an examiner-curated report, so names left out of it "
            "were not searched",
            Fidelity.UNKNOWN: "of unknown coverage",
        }[info.fidelity]
        parts.append(f"{cite(case.where(sid))}, {cover}")
    return (
        "Searched saved contacts, account names, one-to-one thread titles, printed senders, "
        "user names and messages where the user names themselves, on " + "; ".join(parts) + "."
    )
