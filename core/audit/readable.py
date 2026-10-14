"""What a model reads: phones, people and accounts by the names the case gives them.

Stored assumptions keep Baker's ids (Assumption.text, assumption ids, every check). Model input
renders through here instead, so the 14B, the small stance model and the data it is trained on
read one wording. Agreed on 2026-10-14 after case01's paragraph 10.1, where "sent by
person:dev:item1:owner" met a phone that showed the same sender as "Dan P":

- a phone is its source id, as the screens name a source: "item1";
- a phone's stipulated user is "<name> (the user of item1)" while an expert's stipulation of
  that phone stands confirmed, and "the user of item1" otherwise;
- a person the document names is the name as the document writes it: "Rita Vance";
- an account is "<App> <identifier>", as its sender line starts: "Telegram 5550147", printed
  once even when two phones list it;
- a count is "exactly 12", "at least 12" or "at most 12".

A sender line prints the account, the source's own name for the sender if it kept one,
"(owner)" for the phone's own account, then in brackets the people Baker holds as confirmed for
that account, as the signed probe set prints senders: on item1, "SMS +12125550111 (owner)
[Daniel Petrov (the user of item1)]"; on another phone that saved the number, "SMS
+12125550111 Dan P [Daniel Petrov (the user of item1)]". Only confirmed device_owner
stipulations and confirmed identity links count, matched across phones by app and identifier
exactly as the checks match parties. A saved name never links anyone.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.audit.assumptions import TEMPLATES, Names
from core.audit.checks._common import Key, key
from core.contracts import Assumption, AssumptionParams

COUNT_WORDS = {"eq": "exactly", "ge": "at least", "le": "at most"}
OWNER_PERSON = re.compile(r"^person:(.+):owner$")  # core.review.actions.stipulate_device_owner


@dataclass(frozen=True)
class AccountName:
    app: str
    identifier: str
    own: bool  # the phone's own account (accounts.device_id is set)

    @property
    def label(self) -> str:
        return f"{self.app} {self.identifier}"

    @property
    def key(self) -> Key:
        return key(self.app, self.identifier)


@dataclass(frozen=True)
class CaseNames(Names):
    """The names one case gives its phones, people and accounts."""

    phones: Mapping[str, str]  # devices.id -> source id
    people: Mapping[str, str]  # persons.id -> persons.name
    users: Mapping[str, tuple[str, ...]]  # persons.id -> devices a confirmed stipulation gives
    account_names: Mapping[str, AccountName]  # accounts.id -> app, identifier, own
    confirmed: Mapping[Key, tuple[str, ...]]  # account key -> person ids confirmed for it

    def phone(self, device_id: str) -> str:
        return self.phones.get(device_id, device_id.removeprefix("dev:"))

    def person(self, person_id: str) -> str:
        devices = self.users.get(person_id)
        if devices:
            user = "the user of " + " and ".join(self.phone(d) for d in devices)
            name = self.people.get(person_id)
            return f"{name} ({user})" if name else user
        owner = OWNER_PERSON.match(person_id)
        if owner:  # a phone's user with no confirmed stipulation: the phone, never a name
            return f"the user of {self.phone(owner.group(1))}"
        return self.people.get(person_id, person_id)

    def account(self, account_id: str) -> str:
        acc = self.account_names.get(account_id)
        return acc.label if acc else account_id

    def accounts(self, account_ids: Iterable[str]) -> list[str]:
        """Each account once: the same app and identifier on two phones is one account."""
        seen: dict[object, str] = {}
        for aid in account_ids:
            acc = self.account_names.get(aid)
            seen.setdefault(acc.key if acc else aid, self.account(aid))
        return list(seen.values())

    def count(self, op: str, n: int) -> str:
        return f"{COUNT_WORDS.get(op, op)} {n}"

    def people_of(self, account_id: str) -> list[str]:
        """The people Baker holds as confirmed for an account, by name, in a fixed order."""
        acc = self.account_names.get(account_id)
        if acc is None:
            return []
        return sorted(self.person(pid) for pid in self.confirmed.get(acc.key, ()))

    def sender(self, account_id: str | None, shown_as: str | None = None) -> str:
        """A sender line: account, the source's own name for it, (owner), [confirmed people]."""
        if account_id is None:
            return "unknown sender"
        acc = self.account_names.get(account_id)
        out = acc.label if acc else f"account {account_id}"
        if shown_as:
            out += f" {shown_as}"
        if acc and acc.own:
            out += " (owner)"
        people = self.people_of(account_id)
        if people:
            out += f" [{', '.join(people)}]"
        return out

    def assumption(self, template_id: str, params: AssumptionParams) -> str:
        return TEMPLATES[template_id].render(params, self)


def assumption_text(a: Assumption, names: CaseNames) -> str:
    """What a model reads for a stored assumption. A template that no longer fits its
    parameters keeps the stored text rather than guessing."""
    template = TEMPLATES.get(a.template_id)
    if template is None or template.problems(a.params):
        return a.text
    return template.render(a.params, names)


def case_names(conn: sqlite3.Connection) -> CaseNames:
    """Read the names from a case database. Read-only."""
    phones = {did: sid for did, sid in conn.execute("SELECT id, source_id FROM devices")}
    people = {pid: name for pid, name in conn.execute("SELECT id, name FROM persons")}
    accounts = {
        aid: AccountName(app, identifier, device_id is not None)
        for aid, app, identifier, device_id in conn.execute(
            "SELECT id, app, identifier, device_id FROM accounts"
        )
    }
    users: dict[str, set[str]] = defaultdict(set)
    confirmed: dict[Key, set[str]] = defaultdict(set)
    owners = conn.execute(
        "SELECT subject_id, person_id FROM stipulations"
        " WHERE kind = 'device_owner' AND status = 'confirmed'"
    ).fetchall()
    for device_id, person_id in owners:
        users[person_id].add(device_id)
        for app, identifier in conn.execute(
            "SELECT app, identifier FROM accounts WHERE device_id = ?", (device_id,)
        ):
            confirmed[key(app, identifier)].add(person_id)
    for account_id, person_id in conn.execute(
        "SELECT account_id, person_id FROM identity_links WHERE status = 'confirmed'"
    ):
        acc = accounts.get(account_id)
        if acc is not None:
            confirmed[acc.key].add(person_id)
    return CaseNames(
        phones=phones,
        people=people,
        users={p: tuple(sorted(d)) for p, d in users.items()},
        account_names=accounts,
        confirmed={k: tuple(sorted(v)) for k, v in confirmed.items()},
    )
