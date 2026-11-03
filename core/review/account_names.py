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


def identifier_key(identifier: str) -> str:
    """How an identifier is compared: a number by its digits (a WhatsApp id by the number it
    holds), anything else by its alias key."""
    jid = re.fullmatch(r"(\d{8,15})@s\.whatsapp\.net", identifier.strip())
    d = jid.group(1) if jid else number_digits(identifier)
    return f"tel:{d}" if d is not None else f"id:{aliases.key(identifier)}"


def holders(conn: sqlite3.Connection, identifier: str) -> list[str]:
    """The ids of the accounts in the case whose identifier is this number or id, on any app,
    by account id."""
    want = identifier_key(identifier)
    return [
        aid
        for aid, ident in conn.execute("SELECT id, identifier FROM accounts ORDER BY id")
        if identifier_key(ident or "") == want
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
        newest[identifier_key(ident)] = (ident, actor, at, [str(n) for n in p.get("names") or []])
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
    skip = identifier_key(but) if but else ""
    for ident, names in logged_names(conn).items():
        if identifier_key(ident) == skip:
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
