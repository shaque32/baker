"""Readable names for generated items in Baker's wording. SYNTHETIC; mechanics only.

A model reads phones, people and accounts by the names the case gives them
(core/audit/readable.py). A generated item keeps Baker's ids in its parameters and sender lines
while it is built, and carries `baker_names`, the name of each person it involves. These helpers
turn that into the core.audit.readable.CaseNames a case database with the same people would
give, so the item's text is the product's own rendering: an expert stipulated each phone owner
it names, and the document named everyone else.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from core.audit.readable import OWNER_PERSON, AccountName, CaseNames

# A sender line's brackets while an item is built: the person ids Baker holds as confirmed.
_BRACKETS = re.compile(r"^(?P<head>.+) \[(?P<ids>person:[^\[\]]+)\]$")
_ACCOUNT = re.compile(r"^acct:item\d+:(?P<app>[A-Za-z]+):(?P<identifier>\S+)$")


def account_name(account_id: str) -> AccountName:
    """The app and identifier of an id that eval.stancedata.bakerform.account_id made."""
    m = _ACCOUNT.match(account_id)
    if m is None:
        raise ValueError(f"not a generated account id: {account_id!r}")
    return AccountName(m["app"], m["identifier"], own=False)


def case_names(people: Mapping[str, str], account_ids: Iterable[str] = ()) -> CaseNames:
    """What core.audit.readable.case_names reads from such a case. people maps each person id
    to a name: 'person:dev:item1:owner' -> 'Daniel Petrov', 'person:vance' -> 'Rita Vance'."""
    users = {}
    for pid in people:
        owner = OWNER_PERSON.match(pid)
        if owner:
            users[pid] = (owner.group(1),)
    return CaseNames(
        phones={},
        people=dict(people),
        users=users,
        account_names={aid: account_name(aid) for aid in account_ids},
        confirmed={},
    )


def bracketed(sender: str) -> tuple[str, ...]:
    """The person ids in a sender line's brackets, while the item is built."""
    m = _BRACKETS.match(sender)
    return tuple(m["ids"].split(", ")) if m else ()


def readable_sender(sender: str, names: CaseNames) -> str:
    """The sender line with its bracketed person ids printed by name, in the order
    core.audit.readable.CaseNames.sender prints them."""
    m = _BRACKETS.match(sender)
    if m is None:
        return sender
    people = sorted(names.person(pid) for pid in m["ids"].split(", "))
    return f"{m['head']} [{', '.join(people)}]"
