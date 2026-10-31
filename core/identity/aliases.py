"""The other names an expert gives a person (person_aliases, core/schema.sql 0.6.0).

An affidavit calls Owen Halloran "SUBJECT-1" and "HAL"; a person in the case has one name. The
expert records the document's other names for a person with core/review/actions.set_aliases,
and only an expert does: no model proposes one. Code matches an alias whole, in any case, the
way the assumption filler matches a whole name (`spans`, `written`). The surname rule (a bare
"HALLORAN" for "Owen Halloran") is for the person's name only, never for an alias, so "Big
Owen" never matches a bare "Owen". An alias that would also match another person is refused
when entered; if one ever does (an owner renamed later), it matches neither person
(`person_names`). Every report lists each alias as an expert statement.
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
    """How a name or an alias is compared: its letters and digits, in any script, casefolded,
    in order ("SUBJECT-1" and "subject 1" are one). For a name in plain Latin letters this is
    how the assumption filler's whole-name match reads it."""
    return " ".join(re.sub(r"[\W_]+", " ", unicodedata.normalize("NFC", text).casefold()).split())


def forms(text: str) -> set[str]:
    """Every form a reader compares a name or an alias by: its key, and its name words as the
    Identities page reads them (core/identity/links.tokens drops initials and numbers, so
    "John Q Smith" reads as "john smith")."""
    from core.identity.links import tokens  # links reads this module, so not at the top

    return {f for f in (key(text), " ".join(tokens(text))) if f}


def name_keys(name: str) -> set[str]:
    """Every form a person's name is matched by, in every reader: the whole name (`forms`);
    for a name of more than one word, its last word (the filler's surname rule, "Brown-Smith"
    for "John Brown-Smith"); and its last name word as the Identities page reads one ("Smith",
    core/identity/links.tokens). An alias any of whose `forms` is one of these could reach the
    person."""
    from core.identity.links import tokens

    parts = name.split()
    last = tokens(name)[-1:]
    surname = key(parts[-1]) if len(parts) > 1 else ""
    return {k for k in (*forms(name), surname, *last, *map(key, last)) if k}


def _folded(text: str) -> tuple[str, list[int]]:
    """The text casefolded as `key` folds it, and for each folded character the index of the
    character it came from ("ß" folds to "ss", two characters from one)."""
    out: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(text):
        f = ch.casefold()
        out.append(f)
        where += [i] * len(f)
    return "".join(out), where


def spans(alias: str, text: str) -> list[tuple[int, int]]:
    """Where the text writes the alias, as (start, end) in the text after NFC: whole, in any
    case, with the spacing and punctuation between its words not counting, compared as `key`
    compares both sides ("SUBJECT 1" is "SUBJECT-1", "the DRIVER's" holds "the DRIVER",
    "GROSS" is "Groß"). Never inside a longer name or a handle: "SUBJECT-12", "Subject-1A" and
    "@hal" do not write "SUBJECT-1" or "HAL"."""
    words = key(alias).split()
    if not words:
        return []
    folded, where = _folded(unicodedata.normalize("NFC", text))
    pattern = r"(?<![\w@+])" + r"[\W_]+".join(map(re.escape, words)) + r"(?!\w)"
    return [(where[m.start()], where[m.end() - 1] + 1) for m in re.finditer(pattern, folded)]


def written(alias: str, text: str) -> str | None:
    """The alias as the text writes it (`spans`, the first place), or None."""
    found = spans(alias, text)
    return unicodedata.normalize("NFC", text)[slice(*found[0])] if found else None


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
        for k in name_keys(name).union(*map(forms, aliases[pid])):
            owners.setdefault(k, set()).add(pid)
    return {
        pid: (
            name,
            [a for a in aliases[pid] if key(a) and all(owners[f] == {pid} for f in forms(a))],
        )
        for pid, name in persons
    }
