"""The names a government document gives a number or an account, as the expert recorded them.

An affidavit writes "MERROW also used a second phone number, +1 (720) 555-0186 (the
"BURNER")" and then only "the BURNER". Nothing in the data ties the name to the number, so the
expert says which number or id each name means, with core/review/actions.name_account, as they
name a phone with name_device (core/review/device_names.py). The audit log is the record: each
`account.names` entry gives one identifier's whole list of names, and the newest entry for an
identifier is its list (an empty list clears it). No schema change.

A name means the identifier only: the accounts in the case that hold that number or id. It
never means a person, so it confirms no identity link and adds no party a check did not find
in the data. The assumption filler reads a model's account answer by these names as well as
by the identifier itself, matched whole, with or without a leading "the"
(core/identity/aliases.answers). The report lists each name as an expert statement.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata

from core.identity import aliases

ACTION = "account.names"
MAX_NAME = 80


def number_digits(words: str) -> str | None:
    """A phone number as its digits with the country code, the North American way (a ten-digit
    number takes 1), or None when the words hold a letter or too few digits to be one. Used to
    say which accounts hold the number an expert named; the filler's own number rules decide
    what a claim's number matches."""
    w = words.strip()
    if not w or re.search(r"[A-Za-z@]", w):
        return None
    d = re.sub(r"\D", "", w)
    if len(d) == 10 and not w.startswith("+"):
        d = "1" + d
    return d if 8 <= len(d) <= 15 else None


_JID = re.compile(r"(\d{8,15})@s\.whatsapp\.net")
# The import's app for a phone's own call log (core/audit/assumption_filler.NATIVE_CALL_APP).
_CALL_LOG_APP = "unknown"


def identifier_key(identifier: str) -> str:
    """How an identifier the expert wrote is compared with another the expert wrote: a number
    written as one ("+1 (720) 555-0186", a WhatsApp id) by its digits; bare digits whole, since
    they may be an app's user id ("7185550199" and "17185550199" are two Telegram users; Codex
    on #211); anything else whole, its punctuation kept, as the checks compare account ids
    (core/audit/checks/_common.norm_identifier): "alice.smith@example.com" and
    "alice-smith@example.com" are two accounts (Codex on #210). An address or handle with an
    "@" is compared in any case, as an email or Instagram id is there. Which accounts hold an
    identifier is `holds`."""
    ident = unicodedata.normalize("NFC", identifier.strip())
    if ident.isdigit():
        return f"id:{ident}"
    jid = _JID.fullmatch(ident)
    d = jid.group(1) if jid else number_digits(ident)
    if d is not None:
        return f"tel:{d}"
    return f"id:{ident.casefold() if '@' in ident else ident}"


def holds(identifier: str, account_identifier: str, app: str) -> bool:
    """True when an account with this identifier, on this app, holds the number or id the
    expert wrote: the same identifier, or the same phone number however either is written. An
    account's identifier is a number when it is a WhatsApp id, a number written with "+" or
    formatting, or bare digits on a phone app or the call log; bare digits on any other app are
    a user id, never a number, as the filler reads them (assumption_filler._same_number)."""
    from core.audit.checks._common import namespace

    if identifier_key(identifier) == identifier_key(account_identifier):
        return True
    ident = unicodedata.normalize("NFC", identifier.strip())
    jid = _JID.fullmatch(ident)
    number = jid.group(1) if jid else number_digits(ident)
    if number is None:
        return False
    theirs = unicodedata.normalize("NFC", account_identifier.strip())
    if (their_jid := _JID.fullmatch(theirs)) is not None:
        return their_jid.group(1) == number
    if theirs.isdigit() and not (namespace(app) == "tel" or app == _CALL_LOG_APP):
        return False
    return number_digits(theirs) == number


def entry_key(conn: sqlite3.Connection, identifier: str) -> str:
    """Which of the expert's entries an identifier's names replace: `identifier_key`, except
    that bare digits a phone app's account or the call log holds as a number are that number,
    so "12125550182" and "+1 (212) 555-0182" are one entry. Bare digits nothing holds as a
    number stay whole: two Telegram users "7185550199" and "17185550199" keep their own
    names (Codex on #211)."""
    ident = unicodedata.normalize("NFC", identifier.strip())
    d = number_digits(ident) if ident.isdigit() else None
    if d is not None and holders(conn, f"+{d}"):
        return f"tel:{d}"
    return identifier_key(ident)


def holders(conn: sqlite3.Connection, identifier: str) -> list[str]:
    """The ids of the accounts in the case that hold this number or id (`holds`), on any app,
    by account id."""
    return [
        aid
        for aid, ident, app in conn.execute("SELECT id, identifier, app FROM accounts ORDER BY id")
        if holds(identifier, ident or "", app or "")
    ]


def named_by(conn: sqlite3.Connection) -> list[tuple[str, str, str, list[str]]]:
    """(identifier as the expert wrote it, actor, at_utc, names) for each identifier's newest
    entry that gives it names, in identifier order, for the report."""
    newest: dict[str, tuple[str, str, str, list[str]]] = {}
    for actor, at, payload in conn.execute(
        "SELECT actor, at_utc, payload_json FROM audit_log WHERE action = ? ORDER BY seq",
        (ACTION,),
    ):
        p = json.loads(payload)
        ident = str(p["identifier"])
        names = [str(n) for n in p.get("names") or []]
        newest[entry_key(conn, ident)] = (ident, actor, at, names)
    return [v for _, v in sorted(newest.items()) if v[3]]


def logged_names(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Identifier (as the expert wrote it) -> the names its newest entry gives it."""
    return {ident: names for ident, _actor, _at, names in named_by(conn)}


def designated(conn: sqlite3.Connection, answer: str) -> str | None:
    """The identifier a whole answer names by a name the expert gave it ("BURNER" or "the
    BURNER" for "+1 (720) 555-0186"), or None. A name two identifiers share names neither."""
    hits = {
        ident
        for ident, names in logged_names(conn).items()
        if any(aliases.answers(n, answer) for n in names)
    }
    return next(iter(hits)) if len(hits) == 1 else None


def forms(conn: sqlite3.Connection, but: str = "") -> dict[str, str]:
    """Every form a name the expert gave a number or an account is matched by -> what it names
    ("the number +1 (720) 555-0186"), for the clash checks of persons, phones and events. `but`
    is an identifier to leave out."""
    out: dict[str, str] = {}
    skip = entry_key(conn, but) if but else ""
    for ident, names in logged_names(conn).items():
        if entry_key(conn, ident) == skip:
            continue
        for n in names:
            for f in aliases.forms(n):
                out.setdefault(f, f"the number or account {ident}")
    return out


def written(conn: sqlite3.Connection, text: str) -> list[tuple[str, int, int]]:
    """(identifier as the expert wrote it, start, end) for each place the text writes a name
    the expert gave a number or an account, whole, with or without a leading "the" ("from the
    BURNER", "BURNER called"), the outermost where two overlap, in text order. Code reads each
    as that number or id wherever it reads a party from a claim's own words. A name in
    capitals counts only written in capitals ("a burner phone" is no name: aliases.defined_spans);
    where the text writes one in lower case is `lowered`."""
    found = {
        (ident, s, e)
        for ident, names in logged_names(conn).items()
        for n in names
        for form in {n, aliases.without_the(n)}
        for s, e in aliases.defined_spans(form, text)
    }
    return sorted(
        (m for m in found if not any(o[1] <= m[1] and m[2] <= o[2] and o != m for o in found)),
        key=lambda m: (m[1], m[2]),
    )


def lowered(conn: sqlite3.Connection, text: str) -> list[tuple[str, int, int]]:
    """(identifier, start, end) for each place the text writes, in lower case, a name in
    capitals the expert gave a number or an account ("a burner phone" for "the BURNER"). The
    filler refuses to read such words as the number, or as no number: they may be either."""
    return sorted(
        {
            (ident, s, e)
            for ident, names in logged_names(conn).items()
            for n in names
            for form in {n, aliases.without_the(n)}
            for s, e in aliases.lowered_spans(form, text)
        },
        key=lambda m: (m[1], m[2]),
    )
