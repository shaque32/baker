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

A message's or attachment's context opens with its chat's members (members_line): every
account seen in the chat's records, printed as its sender line prints it, so a model can tell a
chat between two accounts from a group whose other members say nothing near the record.

No two people of a case read alike: people who share a name also print their id ("Alex Smith
(person:alex-smith-1a2b3c4d)"), except phone users, whom their phone tells apart. Anything Baker
holds no name for prints its id, so a run never fails on a name.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property

from core.audit.assumptions import TEMPLATES, Names
from core.audit.checks._common import CaseData, Key, key, person_party
from core.contracts import Assumption, AssumptionParams

COUNT_WORDS = {"eq": "exactly", "ge": "at least", "le": "at most"}
OWNER_PERSON = re.compile(r"^person:(.+):owner$")  # core.review.actions.stipulate_device_owner
MEMBERS = "Members seen in this chat's records"


def _fold(name: str) -> str:
    return " ".join(unicodedata.normalize("NFC", name).casefold().split())


def members_line(senders: Iterable[str]) -> str:
    """The line a chat record's context opens with: "Members seen in this chat's records: " and
    each member account as its sender line prints it, with no name from the source ("SMS
    +13125550161 (owner) [Daniel Petrov (the user of item1)]; SMS +13125550188"), each once, in
    sorted order. An account is seen when it sent one of the chat's messages or the source lists
    it as a recipient; a member who did neither is missing, so the line shows who was in the
    chat, never who was not. A call or a contact row has no chat and no such line."""
    return f"{MEMBERS}: {'; '.join(sorted(set(senders)))}"


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
        """A person as a model reads them. No two people of one case read alike: people who
        share a name print their id too, except phone users, whom their phone tells apart."""
        label = self._person_labels.get(person_id)
        return label if label is not None else self._person(person_id)

    def _person(self, person_id: str) -> str:
        devices = self.users.get(person_id)
        if devices:
            user = "the user of " + " and ".join(self.phone(d) for d in devices)
            name = self.people.get(person_id)
            return f"{name} ({user})" if name else user
        owner = OWNER_PERSON.match(person_id)
        if owner:  # a phone's user with no confirmed stipulation: the phone, never a name
            return f"the user of {self.phone(owner.group(1))}"
        return self.people.get(person_id, person_id)

    @cached_property
    def _person_labels(self) -> dict[str, str]:
        shown = {  # people whose name is printed
            pid: name
            for pid, name in self.people.items()
            if pid in self.users or not OWNER_PERSON.match(pid)
        }
        shared = Counter(_fold(name) for name in shown.values())
        out = {}
        for pid, name in shown.items():
            label = self._person(pid)
            if shared[_fold(name)] > 1 and pid not in self.users:
                label = f"{label} ({pid})"
            out[pid] = label
        return out

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

    def members(self, account_ids: Iterable[str | None]) -> str:
        """The members line (members_line) for a chat whose member accounts are account_ids; a
        message with no sender account names no member."""
        return members_line(self.sender(aid) for aid in account_ids if aid is not None)

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
    """Read the names from a case database. Read-only. The people on an account are exactly
    the parties Baker's checks tie to it (core.audit.checks._common.person_party)."""
    data = CaseData(conn)
    devices = conn.execute("SELECT id, source_id FROM devices").fetchall()
    per_source = Counter(sid for _, sid in devices)
    phones = {  # a phone is its source; a source holding two phones names each by its id too
        did: sid if per_source[sid] == 1 else f"{sid} ({did})" for did, sid in devices
    }
    people = {pid: name for pid, name in conn.execute("SELECT id, name FROM persons")}
    users: dict[str, set[str]] = defaultdict(set)
    for _sid, device_id, person_id, status in data.stipulations:
        if status == "confirmed":
            users[person_id].add(device_id)
    confirmed: dict[Key, set[str]] = defaultdict(set)
    for person_id in sorted({*users, *(pid for _, _, pid in data.links)}):
        for k in person_party(data, person_id).keys:
            confirmed[k].add(person_id)
    return CaseNames(
        phones=phones,
        people=people,
        users={p: tuple(sorted(d)) for p, d in users.items()},
        account_names={
            aid: AccountName(a.app, a.identifier, a.is_owner) for aid, a in data.accounts.items()
        },
        confirmed={k: tuple(sorted(v)) for k, v in confirmed.items()},
    )
