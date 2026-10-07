"""Deterministic checks (DeterministicCheck implementations).

Each check reads an assumption's template parameters, searches the case database and returns
one CheckResult saying what it searched, what it found and which records the outcome rests
on. Checks never call a model, never write to the database and never change an assumption's
tier: rules.py decides what a result means.

    sender        who sent the message with these exact words (by account id, not name)
    time          a record falls in the claimed window; shown in the phone's own zone
    count         messages between two parties in a window, on one phone
    absence       no contact in a window; passes only on full extractions that cover it
    same_account  several handles resolve to one account id
    contact       a saved contact entry has this name and number
    weekday       a weekday named in a message points to the claimed date
"""

from __future__ import annotations

import sqlite3

from core.audit.assumptions import template_of
from core.audit.checks.absence import AbsenceCheck
from core.audit.checks.base import TemplateCheck
from core.audit.checks.count import CountCheck
from core.audit.checks.identity import ContactCheck, SameAccountCheck
from core.audit.checks.sender import SenderCheck
from core.audit.checks.timing import TimeCheck
from core.audit.checks.weekday import WeekdayCheck
from core.contracts import Assumption, CheckResult

CHECKS: dict[str, TemplateCheck] = {
    c.name: c
    for c in [
        SenderCheck(),
        TimeCheck(),
        CountCheck(),
        AbsenceCheck(),
        SameAccountCheck(),
        ContactCheck(),
        WeekdayCheck(),
    ]
}


def checks_for(assumption: Assumption) -> list[TemplateCheck]:
    """The checks that test this assumption; [] for model-only templates or bad parameters."""
    template = template_of(assumption)
    return [CHECKS[name] for name in template.checks] if template else []


def create(conn: sqlite3.Connection) -> list[TemplateCheck]:
    """Pipeline hook: every check. Each one answers only the templates that name it, and
    returns an inconclusive 'does not apply' result for any other assumption."""
    return list(CHECKS.values())


def run_checks(assumption: Assumption, conn: sqlite3.Connection) -> list[CheckResult]:
    return [check.run(assumption, conn) for check in checks_for(assumption)]


__all__ = [
    "CHECKS",
    "AbsenceCheck",
    "ContactCheck",
    "CountCheck",
    "SameAccountCheck",
    "SenderCheck",
    "TemplateCheck",
    "TimeCheck",
    "WeekdayCheck",
    "checks_for",
    "create",
    "run_checks",
]
