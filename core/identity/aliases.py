"""The other names an expert gives a person (person_aliases, core/schema.sql 0.6.0).

An affidavit calls Owen Halloran "SUBJECT-1" and "HAL"; a person in the case has one name. The
expert records the document's other names for a person with core/review/actions.set_aliases,
and only an expert does: no model proposes one. Code matches an alias whole, in any case, the
way the assumption filler matches a whole name. The surname rule (a bare "HALLORAN" for "Owen
Halloran") is for the person's name only, never for an alias, so "Big Owen" never matches a
bare "Owen". An alias that would also match another person is refused when entered; if one
ever does (an owner renamed later), it matches neither person (`person_names`). Every report
lists each alias as an expert statement.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

ADD_ACTION = "person.alias.add"
REMOVE_ACTION = "person.alias.remove"
MAX_LEN = 120


def key(text: str) -> str:
    """How a name or an alias is compared: its letters and digits, lowercased, in order, as the
    assumption filler's whole-name match reads them ("SUBJECT-1" and "subject 1" are one)."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFC", text).lower()).split())


def name_keys(name: str) -> set[str]:
    """The keys a person's name is matched by: the whole name and, for a name of more than one
    word, its last word (the filler's surname rule)."""
    parts = name.split()
    return {k for k in (key(name), key(parts[-1]) if len(parts) > 1 else "") if k}


@dataclass(frozen=True)
class Alias:
    person_id: str
    alias: str
    created_by: str
    created_at_utc: str


def _rows(conn: sqlite3.Connection) -> list[Alias]:
    """Every stored alias, by person and alias. A case database made before schema 0.6.0 has no
    person_aliases table and reads as having none."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'person_aliases'"
    ).fetchone():
        return []
    return [
        Alias(*r)
        for r in conn.execute(
            "SELECT person_id, alias, created_by, created_at_utc FROM person_aliases"
            " ORDER BY person_id, alias"
        )
    ]


def stored(conn: sqlite3.Connection) -> list[Alias]:
    """Every alias as recorded, shared ones included: what the report and the screens list."""
    return _rows(conn)


def person_names(conn: sqlite3.Connection) -> dict[str, tuple[str, list[str]]]:
    """Person id -> (name, aliases), by person id: the one reader the filler and the
    testability step match names with. The name keeps the surname rule; the aliases are matched
    whole only. An alias that would also match another person (their name, surname or an alias
    of theirs) is left out for both, so it matches neither."""
    persons = list(conn.execute("SELECT id, name FROM persons ORDER BY id"))
    aliases: dict[str, list[str]] = {pid: [] for pid, _ in persons}
    for a in _rows(conn):
        aliases.setdefault(a.person_id, []).append(a.alias)
    owners: dict[str, set[str]] = {}
    for pid, name in persons:
        for k in name_keys(name) | {key(a) for a in aliases[pid]}:
            owners.setdefault(k, set()).add(pid)
    return {
        pid: (name, [a for a in aliases[pid] if key(a) and owners.get(key(a)) == {pid}])
        for pid, name in persons
    }
