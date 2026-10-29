"""Fixed assumption templates over typed parameters (AssumptionBuilder).

Every assumption Mabillon tests is an instance of one template below. A template fixes the kind,
the claim types it may serve, which AssumptionParams fields it needs and which deterministic
checks can test it. Whoever fills a template (the local model, or the expert in the CLI)
supplies only typed parameters: people, accounts, handles, a phone, a time window with its
zone, an expected count, channels, quoted words. Checks read those parameters, never the
sentence, so a misread "March 20 to 23" cannot turn into a confident pass or fail.

Conventions every template and check shares:
- Parties. Each person_id is one party: the owner accounts of the phone an expert-confirmed
  device_owner stipulation ties to that person, plus accounts an expert linked to them. All
  account_ids and handles together are one more party. A handle counts only if the data
  resolves it to exactly one account (on the one app named in channels, if there is one).
  So "PETROV and @northstar" is person_ids=(PETROV,) plus handles=("@northstar",), and
  "PETROV and REYES" is two person_ids.
- Accounts are matched across phones by app and identifier, never by display name. Handles
  are resolved from the data by the checks, and the detail says how.
- device_ids limits which phones are searched. A count names exactly one phone.
- channels empty means the claim named none, so every channel is searched. 'call' means calls.
- window comes from local_window(): wall-clock bounds in a named zone, resolved to UTC with
  both ends inclusive, as the contract defines. raw keeps the document's own words.
- "After the 10:05 p.m. call" is a window on the later record that starts at 10:05 p.m.
- A new assumption is always tier INFERRED. Nothing here or in a check raises it. rules.py
  decides whether a core assumption is covered, from check results and accepted evidence.
- Proposals that fail validation are dropped, never repaired. A claim left without a usable
  core assumption stays unproven.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from core.contracts import (
    Assumption,
    AssumptionKind,
    AssumptionParams,
    Claim,
    ClaimType,
    ProvenanceTier,
    TimeWindow,
    assumption_id,
)

TEMPLATES_VERSION = "1.0.0"

# Fields that name who an assumption is about.
PARTY_FIELDS = ("person_ids", "account_ids", "handles")
_FIELDS = frozenset(AssumptionParams.model_fields)


def local_window(start: datetime, end_exclusive: datetime, tz: str, raw: str) -> TimeWindow:
    """A half-open wall-clock range [start, end_exclusive) in tz, as the contract's TimeWindow.

    "March 20 to 23" is local_window(datetime(2026, 3, 20), datetime(2026, 3, 24), tz, raw).
    The contract's end is inclusive, so it becomes the last microsecond before end_exclusive.
    """
    if start.tzinfo is not None or end_exclusive.tzinfo is not None:
        raise ValueError("give wall-clock times; the zone goes in tz")
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"unknown time zone {tz!r}") from e
    if end_exclusive <= start:
        raise ValueError("window start must be before its end")
    return TimeWindow(
        start_utc=start.replace(tzinfo=zone).astimezone(UTC),
        end_utc=end_exclusive.replace(tzinfo=zone).astimezone(UTC) - timedelta(microseconds=1),
        tz=tz,
        raw=raw,
    )


def party_count(p: AssumptionParams) -> int:
    """Each person is a party; account_ids and handles together are one more."""
    return len(p.person_ids) + (1 if p.account_ids or p.handles else 0)


# ---------------------------------------------------------------- templates


class Names:
    """How a template's text names phones, people, accounts and counts.

    This base prints Mabillon's own ids ("person:dev:item1:owner", "eq 12"): that is the stored
    Assumption.text, which nothing parses. What a model reads is rendered with
    core.audit.readable.CaseNames instead, so the 14B, the small model and its training data
    see the names the case gives them.
    """

    def person(self, person_id: str) -> str:
        return person_id

    def accounts(self, account_ids: Iterable[str]) -> list[str]:
        return list(account_ids)

    def phone(self, device_id: str) -> str:
        return device_id

    def count(self, op: str, n: int) -> str:
        return f"{op} {n}"


IDS = Names()


@dataclass(frozen=True)
class Template:
    id: str
    kind: AssumptionKind
    claim_types: frozenset[ClaimType]
    checks: tuple[str, ...]  # deterministic checks that test it; () = model stance only
    required: frozenset[str]  # AssumptionParams fields that must be set
    allowed: frozenset[str]  # fields that may be set (required included)
    rule: Callable[[AssumptionParams], str | None]  # extra shape rule; returns the problem
    fmt: Callable[[AssumptionParams, Names], str]

    def render(self, p: AssumptionParams, names: Names | None = None) -> str:
        """The assumption as text; with no names, the stored Assumption.text."""
        return self.fmt(p, names or IDS)

    def problems(self, p: AssumptionParams) -> list[str]:
        out = []
        given = {
            name
            for name in _FIELDS
            if (v := getattr(p, name)) not in (None, (), "") and v is not False  # each_way off
        }
        missing = sorted(self.required - given)
        extra = sorted(given - self.allowed)
        if missing:
            out.append(f"{self.id} needs {', '.join(missing)}")
        if extra:
            out.append(f"{self.id} does not take {', '.join(extra)}")
        if not out and (why := self.rule(p)):
            out.append(f"{self.id}: {why}")
        return out


def _persons(p: AssumptionParams, n: Names) -> str:
    return " and ".join(n.person(x) for x in p.person_ids)


def _who(p: AssumptionParams, n: Names) -> str:
    parts = [n.person(x) for x in p.person_ids]
    if p.account_ids or p.handles:
        parts.append("/".join((*n.accounts(p.account_ids), *p.handles)))
    return " and ".join(parts) or "anyone"


def _when(p: AssumptionParams) -> str:
    return f'"{p.window.raw}" ({p.window.tz})' if p.window else "at any time"


def _on(p: AssumptionParams) -> str:
    return f" on {', '.join(p.channels)}" if p.channels else ""


def _lasting(p: AssumptionParams) -> str:
    return f" lasting {p.duration_s[0]} to {p.duration_s[1]} s" if p.duration_s else ""


def _direction(p: AssumptionParams, n: Names) -> str:
    if p.sent_by:
        who = [n.person(x) for x in p.sent_by if x in p.person_ids]
        return f", counting only messages {' and '.join(who or n.accounts(p.sent_by))} sent"
    return ", with at least one message each way" if p.each_way else ""


def _phones(p: AssumptionParams, n: Names) -> str:
    return ", ".join(n.phone(d) for d in p.device_ids) or "every phone"


def _one_party(p: AssumptionParams) -> str | None:
    return None if party_count(p) == 1 else "name exactly one party (one person, or accounts)"


def _two_parties(p: AssumptionParams) -> str | None:
    return None if party_count(p) == 2 else "name exactly two parties"


def _time_rule(p: AssumptionParams) -> str | None:
    if p.quoted_text:
        return "a duration only applies to calls" if p.duration_s else None
    if "call" not in p.channels:
        return "pick a message by its quoted text, or a call by its parties with channel 'call'"
    return None if party_count(p) >= 1 else "a call is picked by its parties; name at least one"


def _count_rule(p: AssumptionParams) -> str | None:
    if len(p.device_ids) != 1:
        return "a count is about one phone; name exactly one device"
    if (p.sent_by or p.each_way) and "call" in {c.strip().lower() for c in p.channels}:
        return "a count of calls reads no direction; sent_by and each_way are for messages"
    if p.sent_by and not (
        (len(p.sent_by) == 1 and p.sent_by[0] in p.person_ids)
        or (set(p.sent_by) == set(p.account_ids) and not set(p.sent_by) & set(p.person_ids))
    ):
        return "sent_by names one side: one person, or exactly the accounts"
    return _two_parties(p)


def _same_account_rule(p: AssumptionParams) -> str | None:
    if len(p.handles) < 2:
        return "name at least two handles"
    return None if len(p.channels) == 1 else "name the one app the handles are on"


def _contact_rule(p: AssumptionParams) -> str | None:
    if len(p.device_ids) != 1 or len(p.account_ids) != 1:
        return "name one device and the one account that holds the number"
    return None


def _none(_: AssumptionParams) -> str | None:
    return None


_ALL = frozenset(ClaimType)
_FREE = _FIELDS - {"expected_count", "count_op", "duration_s", "sent_by", "each_way"}

TEMPLATES: dict[str, Template] = {
    t.id: t
    for t in [
        Template(
            "sender",
            AssumptionKind.IDENTITY,
            _ALL,
            ("sender",),
            frozenset({"quoted_text"}),
            frozenset({"quoted_text", "channels", "device_ids", *PARTY_FIELDS}),
            _one_party,
            lambda p, n: f'The message "{p.quoted_text}" was sent by {_who(p, n)}{_on(p)}',
        ),
        Template(
            "record_time",
            AssumptionKind.TIME,
            _ALL,
            ("time",),
            frozenset({"window"}),
            frozenset(
                {"window", "quoted_text", "duration_s", "channels", "device_ids", *PARTY_FIELDS}
            ),
            _time_rule,
            lambda p, n: (
                f'The message "{p.quoted_text}" ({_who(p, n)}) was sent {_when(p)}'
                if p.quoted_text
                else f"A call between {_who(p, n)}{_lasting(p)} happened {_when(p)}"
            ),
        ),
        Template(
            "message_count",
            AssumptionKind.COMPLETENESS,
            frozenset({ClaimType.COUNT, ClaimType.COMMUNICATION}),
            ("count",),
            frozenset({"window", "expected_count", "count_op", "device_ids"}),
            frozenset(
                {
                    "window",
                    "expected_count",
                    "count_op",
                    "device_ids",
                    "channels",
                    "sent_by",
                    "each_way",
                    *PARTY_FIELDS,
                }
            ),
            _count_rule,
            lambda p, n: (
                f"{_phones(p, n)} holds {n.count(p.count_op or '', p.expected_count or 0)} "
                f"{'calls' if 'call' in p.channels else 'messages'} between "
                f"{_who(p, n)}{_on(p)} {_when(p)}{_direction(p, n)}"
            ),
        ),
        Template(
            "no_contact",
            AssumptionKind.COMPLETENESS,
            frozenset({ClaimType.ABSENCE, ClaimType.TIMING, ClaimType.EVENT}),
            ("absence",),
            frozenset({"window"}),
            frozenset({"window", "channels", "device_ids", *PARTY_FIELDS}),
            _two_parties,
            lambda p, n: f"No contact between {_who(p, n)}{_on(p)} {_when(p)} on {_phones(p, n)}",
        ),
        Template(
            "same_account",
            AssumptionKind.IDENTITY,
            frozenset({ClaimType.IDENTITY, ClaimType.TIMING, ClaimType.COUNT}),
            ("same_account",),
            frozenset({"channels", "handles"}),
            frozenset({"channels", "handles", "device_ids"}),
            _same_account_rule,
            lambda p, n: f"On {', '.join(p.channels)}, {', '.join(p.handles)} are one account",
        ),
        Template(
            "contact_entry",
            AssumptionKind.IDENTITY,
            _ALL,
            ("contact",),
            frozenset({"device_ids", "quoted_text", "account_ids"}),
            frozenset({"device_ids", "quoted_text", "account_ids"}),
            _contact_rule,
            lambda p, n: (
                f'{_phones(p, n)} has a contact "{p.quoted_text}" with the number of '
                f"{n.accounts(p.account_ids[:1])[0]}"
            ),
        ),
        Template(
            "weekday_date",
            AssumptionKind.TIME,
            _ALL,
            ("weekday",),
            frozenset({"quoted_text", "window"}),
            frozenset({"quoted_text", "window", "channels", "device_ids", *PARTY_FIELDS}),
            _none,
            lambda p, n: f'The weekday in "{p.quoted_text}" means {_when(p)}',
        ),
        Template(
            "meaning",
            AssumptionKind.MEANING,
            _ALL,
            (),
            frozenset({"quoted_text"}),
            _FREE,
            _none,
            lambda p, n: f'The words "{p.quoted_text}" mean what the claim says they mean',
        ),
        Template(
            "authorship",
            AssumptionKind.IDENTITY,
            _ALL,
            (),
            frozenset({"person_ids", "account_ids"}),
            _FREE,
            _none,
            lambda p, n: (
                f"{_persons(p, n)} personally wrote what {'/'.join(n.accounts(p.account_ids))} sent"
            ),
        ),
        Template(
            "person_identity",
            AssumptionKind.IDENTITY,
            _ALL,
            (),
            frozenset({"person_ids"}),
            _FREE,
            _none,
            lambda p, n: (
                f"{'/'.join(n.accounts(p.account_ids)) or ', '.join(p.handles) or 'The account'}"
                f" belongs to {_persons(p, n)}"
            ),
        ),
        Template(
            "role",
            AssumptionKind.EVENT,
            frozenset({ClaimType.ROLE, ClaimType.EVENT}),
            (),
            frozenset({"person_ids"}),
            _FREE,
            _none,
            lambda p, n: f"{_persons(p, n)} played the role the claim states",
        ),
        Template(
            "event",
            AssumptionKind.EVENT,
            _ALL,
            (),
            frozenset(),
            _FREE,
            _none,
            lambda p, n: f"The event the claim states happened, involving {_who(p, n)} {_when(p)}",
        ),
    ]
}


# ---------------------------------------------------------------- building assumptions


def parse_params(
    template_id: str, params: Mapping[str, Any] | AssumptionParams
) -> AssumptionParams:
    """Validate parameters against the contract and the template. Raises ValueError."""
    template = TEMPLATES.get(template_id)
    if template is None:
        raise ValueError(f"unknown template {template_id!r}")
    parsed = (
        params
        if isinstance(params, AssumptionParams)
        else AssumptionParams.model_validate(dict(params))
    )
    problems = template.problems(parsed)
    if problems:
        raise ValueError("; ".join(problems))
    return parsed


def instantiate(
    claim_id: str,
    template_id: str,
    params: Mapping[str, Any] | AssumptionParams,
    is_core: bool = True,
) -> Assumption:
    """One assumption from a template. Always tier INFERRED; the id is content-derived."""
    template = TEMPLATES[template_id]
    parsed = parse_params(template_id, params)
    return Assumption(
        id=assumption_id(claim_id, template_id, parsed),
        claim_id=claim_id,
        kind=template.kind,
        template_id=template_id,
        template_version=TEMPLATES_VERSION,
        params=parsed,
        text=template.render(parsed),
        is_core=is_core,
        tier=ProvenanceTier.INFERRED,
    )


def template_of(assumption: Assumption) -> Template | None:
    """The template an assumption was built from, or None if it is unknown or its parameters
    no longer fit (a check then reports that instead of guessing from the text)."""
    template = TEMPLATES.get(assumption.template_id)
    if template is None or template.problems(assumption.params):
        return None
    return template


# The words a code-made assumption's text ends with, so the expert who accepts it, the report
# and the eval all see that code filled it, not the model (validation fill g).
CODE_MADE_NOTE = " Filled from the claim's wording."


def is_code_made(text: str) -> bool:
    """True when an assumption's text says code filled it from the claim's wording."""
    return text.endswith(CODE_MADE_NOTE)


@dataclass(frozen=True)
class Proposal:
    """One filled template, as proposed by the local model or typed by the expert.
    `code_made`: code filled it, or some of its parameters, from the claim's own words."""

    template_id: str
    params: Mapping[str, Any] | AssumptionParams
    is_core: bool = True
    code_made: bool = False


def from_proposal(claim_id: str, proposal: Proposal) -> Assumption:
    """The assumption a proposal fills, its text ending with CODE_MADE_NOTE when code filled
    it: every path that builds one from a proposal (the builder, the testability step's repair)
    keeps the note. Raises as `instantiate` does."""
    a = instantiate(claim_id, proposal.template_id, proposal.params, proposal.is_core)
    if proposal.code_made:
        a = a.model_copy(update={"text": a.text + CODE_MADE_NOTE})
    return a


@dataclass(frozen=True)
class Rejected:
    proposal: Proposal
    reason: str


type Filler = Callable[[Claim, list[Template]], Iterable[Proposal]]


def templates_for(claim_type: ClaimType) -> list[Template]:
    return [t for t in TEMPLATES.values() if claim_type in t.claim_types]


class TemplateAssumptionBuilder:
    """AssumptionBuilder. The filler proposes; this class validates and fails closed.

    Proposals naming an unknown template, a template not allowed for the claim type, or
    parameters that do not validate are dropped and kept in `rejected` for the run log.
    A duplicate (same template and parameters) is kept once.
    """

    def __init__(self, filler: Filler) -> None:
        self._filler = filler
        self.rejected: list[Rejected] = []
        self._why: dict[str, list[str]] = {}  # claim id -> what was refused, last build

    def build(self, claim: Claim) -> list[Assumption]:
        allowed = templates_for(claim.claim_type)
        allowed_ids = {t.id for t in allowed}
        out: dict[str, Assumption] = {}
        why: list[str] = []
        for proposal in self._filler(claim, allowed):
            if proposal.template_id not in allowed_ids:
                reason = f"template {proposal.template_id!r} is not allowed for {claim.claim_type}"
                self.rejected.append(Rejected(proposal, reason))
                why.append(reason)
                continue
            try:
                a = from_proposal(claim.id, proposal)
            except (ValidationError, ValueError) as e:
                self.rejected.append(Rejected(proposal, str(e)))
                why.append(f"template {proposal.template_id!r}: {e}")
                continue
            out.setdefault(a.id, a)
        drops = getattr(self._filler, "drops", None)  # the local-model filler keeps its refusals
        if isinstance(drops, list):
            why = [d.reason for d in drops if getattr(d, "claim_id", None) == claim.id] + why
        self._why[claim.id] = why
        return list(out.values())

    def refused(self, claim_id: str) -> list[str]:
        """Why proposals for the claim were refused in its last build, model and code
        refusals alike, in order. Empty when nothing was proposed or nothing was refused."""
        return list(self._why.get(claim_id, ()))


def _no_proposals(claim: Claim, allowed: list[Template]) -> list[Proposal]:
    return []


def create(conn: sqlite3.Connection, filler: Filler | None = None) -> TemplateAssumptionBuilder:
    """Pipeline hook: the AssumptionBuilder.

    The filler (the local model, or the expert's entries) is passed in. With none, no
    assumptions are proposed, so every claim stays unproven: the safe default, never a guess.
    """
    return TemplateAssumptionBuilder(filler or _no_proposals)
