"""The dated events the government document defines (case_events, core/schema.sql 0.7.0).

An affidavit defines an event once, `On Thursday, March 26, 2026, officers searched FERRO's
storage unit (the "SEARCH")`, and dates later claims only by it: "Two days before the SEARCH,
the BUYER offered ...". The expert records each such event with
core/review/actions.add_event: its name as the document writes it, the first and last
wall-clock day it covers, and the paragraph and words that define it, which code checks
verbatim against the paragraph. Only an expert enters one, never a model. Code matches a name
whole, in any case, as it matches a person's alias (core/identity/aliases.spans). A name that
would also match a person or another event is refused when entered; if one ever does (a person
added later), it matches nothing (`readable`). Every report lists each event as an expert
statement. Which ties to an event the assumption filler reads is its allow list
(core/audit/assumption_filler.event_windows).
"""

from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date

from core.identity import aliases

ADD_ACTION = "case.event.add"
REMOVE_ACTION = "case.event.remove"
MAX_NAME = 120
MAX_WORDS = 2000


@dataclass(frozen=True)
class CaseEvent:
    name: str
    first_day: date
    last_day: date
    paragraph_id: str
    defined_as: str
    created_by: str
    created_at_utc: str

    @property
    def one_day(self) -> bool:
        return self.first_day == self.last_day


def key(name: str) -> str:
    """How an event's name is compared: as an alias is (aliases.key), so "KEDZIE YARD theft"
    and "Kedzie Yard Theft" are one, in any script."""
    return aliases.key(name)


def spans(name: str, text: str) -> list[tuple[int, int]]:
    """Where the text writes the event's name, whole, as aliases.spans finds an alias."""
    return aliases.spans(name, text)


def plain(text: str) -> str:
    """Text as the verbatim check compares it: NFC, each run of whitespace one space, so a
    definition a PDF wrapped over two lines is still the paragraph's words."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def stored(conn: sqlite3.Connection) -> list[CaseEvent]:
    """Every stored event, by name. A case database made before schema 0.7.0 has no
    case_events table and reads as having none."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'case_events'"
    ).fetchone():
        return []
    return [
        CaseEvent(n, date.fromisoformat(a), date.fromisoformat(b), p, d, by, at)
        for n, a, b, p, d, by, at in conn.execute(
            "SELECT name, first_day, last_day, paragraph_id, defined_as, created_by,"
            " created_at_utc FROM case_events ORDER BY name"
        )
    ]


def taken(conn: sqlite3.Connection, but: str = "") -> dict[str, str]:
    """Every form a person or another event is already matched by -> what it names ("a person,
    Owen Halloran" or "the event SEARCH"): each person's name forms (aliases.name_keys), each
    alias's forms and each other event's. `but` is an event name to leave out."""
    out: dict[str, str] = {}
    for pid, name in conn.execute("SELECT id, name FROM persons ORDER BY id"):
        for f in aliases.name_keys(name):
            out.setdefault(f, f"the person {name} ({pid})")
    people = dict(conn.execute("SELECT id, name FROM persons"))
    for a in aliases.stored(conn):
        for f in aliases.forms(a.alias):
            out.setdefault(f, f"the person {people.get(a.person_id, a.person_id)}")
    for ev in stored(conn):
        if key(ev.name) != key(but):
            for f in aliases.forms(ev.name):
                out.setdefault(f, f"the event {ev.name}")
    return out


def readable(conn: sqlite3.Connection) -> list[CaseEvent]:
    """The events code may read a claim's time by: every stored one whose name no person, alias
    or other event is also matched by. An event that clashes with any of them matches
    nothing, so no claim is dated by a name that could mean someone or something else."""
    out = []
    for ev in stored(conn):
        others = taken(conn, but=ev.name)
        if key(ev.name) and not (aliases.forms(ev.name) & others.keys()):
            out.append(ev)
    return out
