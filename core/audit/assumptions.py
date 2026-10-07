"""Fixed assumption templates over typed parameters (AssumptionBuilder).

Every assumption Baker tests is an instance of one template below. A template fixes the kind,
the claim types it may serve, which AssumptionParams fields it needs and which deterministic
checks can test it. Whoever fills a template (the local model, or the expert in the CLI)
supplies only typed parameters: people, accounts, handles, a phone, a time window with its
zone, an expected count, channels, quoted words. Checks read those parameters, never the
sentence, so a misread "March 20 to 23" cannot turn into a confident pass or fail.

Conventions every template and check shares:
- Parties. Each person_id is one party: the owner accounts of the phone a device_owner
  stipulation ties to that person, plus accounts an expert linked to them. All account_ids
  together are one more party. So "PETROV and @northstar" is person_ids=(PETROV,) plus
  account_ids=(the @northstar accounts,), and "PETROV and REYES" is two person_ids.
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

PARTY_FIELDS = ("person_ids", "account_ids")  # fields that name who an assumption is about
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
    return len(p.person_ids) + (1 if p.account_ids else 0)


# ---------------------------------------------------------------- templates


@dataclass(frozen=True)
class Template:
    id: str
    kind: AssumptionKind
    claim_types: frozenset[ClaimType]
    checks: tuple[str, ...]  # deterministic checks that test it; () = model stance only
    required: frozenset[str]  # AssumptionParams fields that must be set
    allowed: frozenset[str]  # fields that may be set (required included)
    rule: Callable[[AssumptionParams], str | None]  # extra shape rule; returns the problem
    render: Callable[[AssumptionParams], str]

    def problems(self, p: AssumptionParams) -> list[str]:
        out = []
        given = {name for name in _FIELDS if getattr(p, name) not in (None, (), "")}
        missing = sorted(self.required - given)
        extra = sorted(given - self.allowed)
        if missing:
            out.append(f"{self.id} needs {', '.join(missing)}")
        if extra:
            out.append(f"{self.id} does not take {', '.join(extra)}")
        if not out and (why := self.rule(p)):
            out.append(f"{self.id}: {why}")
        return out


def _who(p: AssumptionParams) -> str:
    parts = list(p.person_ids)
    if p.account_ids:
        parts.append("/".join(p.account_ids))
    return " and ".join(parts) or "anyone"


def _when(p: AssumptionParams) -> str:
    return f'"{p.window.raw}" ({p.window.tz})' if p.window else "at any time"


def _on(p: AssumptionParams) -> str:
    return f" on {', '.join(p.channels)}" if p.channels else ""


def _phones(p: AssumptionParams) -> str:
    return ", ".join(p.device_ids) or "every phone"


def _one_party(p: AssumptionParams) -> str | None:
    return None if party_count(p) == 1 else "name exactly one party (one person, or accounts)"


def _two_parties(p: AssumptionParams) -> str | None:
    return None if party_count(p) == 2 else "name exactly two parties"


def _time_rule(p: AssumptionParams) -> str | None:
    if p.quoted_text:
        return None
    if "call" not in p.channels:
        return "pick a message by its quoted text, or a call by its parties with channel 'call'"
    return None if party_count(p) >= 1 else "a call is picked by its parties; name at least one"


def _count_rule(p: AssumptionParams) -> str | None:
    if len(p.device_ids) != 1:
        return "a count is about one phone; name exactly one device"
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
_FREE = _FIELDS - {"expected_count", "count_op"}

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
            lambda p: f'The message "{p.quoted_text}" was sent by {_who(p)}{_on(p)}',
        ),
        Template(
            "record_time",
            AssumptionKind.TIME,
            _ALL,
            ("time",),
            frozenset({"window"}),
            frozenset({"window", "quoted_text", "channels", "device_ids", *PARTY_FIELDS}),
            _time_rule,
            lambda p: (
                f'The message "{p.quoted_text}" ({_who(p)}) was sent {_when(p)}'
                if p.quoted_text
                else f"A call between {_who(p)} happened {_when(p)}"
            ),
        ),
        Template(
            "message_count",
            AssumptionKind.COMPLETENESS,
            frozenset({ClaimType.COUNT, ClaimType.COMMUNICATION}),
            ("count",),
            frozenset({"window", "expected_count", "count_op", "device_ids"}),
            frozenset(
                {"window", "expected_count", "count_op", "device_ids", "channels", *PARTY_FIELDS}
            ),
            _count_rule,
            lambda p: (
                f"{_phones(p)} holds {p.count_op} {p.expected_count} messages between "
                f"{_who(p)}{_on(p)} {_when(p)}"
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
            lambda p: f"No contact between {_who(p)}{_on(p)} {_when(p)} on {_phones(p)}",
        ),
        Template(
            "same_account",
            AssumptionKind.IDENTITY,
            frozenset({ClaimType.IDENTITY, ClaimType.TIMING, ClaimType.COUNT}),
            ("same_account",),
            frozenset({"channels", "handles"}),
            frozenset({"channels", "handles", "device_ids"}),
            _same_account_rule,
            lambda p: f"On {', '.join(p.channels)}, {', '.join(p.handles)} are one account",
        ),
        Template(
            "contact_entry",
            AssumptionKind.IDENTITY,
            _ALL,
            ("contact",),
            frozenset({"device_ids", "quoted_text", "account_ids"}),
            frozenset({"device_ids", "quoted_text", "account_ids"}),
            _contact_rule,
            lambda p: (
                f'{_phones(p)} has a contact "{p.quoted_text}" with the number of '
                f"{p.account_ids[0]}"
            ),
        ),
        Template(
            "meaning",
            AssumptionKind.MEANING,
            _ALL,
            (),
            frozenset({"quoted_text"}),
            _FREE,
            _none,
            lambda p: f'The words "{p.quoted_text}" mean what the claim says they mean',
        ),
        Template(
            "authorship",
            AssumptionKind.IDENTITY,
            _ALL,
            (),
            frozenset({"person_ids", "account_ids"}),
            _FREE,
            _none,
            lambda p: (
                f"{' and '.join(p.person_ids)} personally wrote what {'/'.join(p.account_ids)} sent"
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
            lambda p: (
                f"{'/'.join(p.account_ids) or ', '.join(p.handles) or 'The account'} belongs "
                f"to {' and '.join(p.person_ids)}"
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
            lambda p: f"{' and '.join(p.person_ids)} played the role the claim states",
        ),
        Template(
            "event",
            AssumptionKind.EVENT,
            _ALL,
            (),
            frozenset(),
            _FREE,
            _none,
            lambda p: f"The event the claim states happened, involving {_who(p)} {_when(p)}",
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


@dataclass(frozen=True)
class Proposal:
    """One filled template, as proposed by the local model or typed by the expert."""

    template_id: str
    params: Mapping[str, Any] | AssumptionParams
    is_core: bool = True


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

    def build(self, claim: Claim) -> list[Assumption]:
        allowed = templates_for(claim.claim_type)
        allowed_ids = {t.id for t in allowed}
        out: dict[str, Assumption] = {}
        for proposal in self._filler(claim, allowed):
            if proposal.template_id not in allowed_ids:
                why = f"template {proposal.template_id!r} is not allowed for {claim.claim_type}"
                self.rejected.append(Rejected(proposal, why))
                continue
            try:
                a = instantiate(claim.id, proposal.template_id, proposal.params, proposal.is_core)
            except (ValidationError, ValueError) as e:
                self.rejected.append(Rejected(proposal, str(e)))
                continue
            out.setdefault(a.id, a)
        return list(out.values())


def _no_proposals(claim: Claim, allowed: list[Template]) -> list[Proposal]:
    return []


def create(conn: sqlite3.Connection, filler: Filler | None = None) -> TemplateAssumptionBuilder:
    """Pipeline hook: the AssumptionBuilder.

    The filler (the local model, or the expert's entries) is passed in. With none, no
    assumptions are proposed, so every claim stays unproven: the safe default, never a guess.
    """
    return TemplateAssumptionBuilder(filler or _no_proposals)
