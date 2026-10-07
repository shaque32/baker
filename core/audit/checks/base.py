"""Base class for checks that read an assumption's template parameters."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import ClassVar

from core.audit.assumptions import template_of
from core.audit.checks._common import CaseData, result
from core.contracts import Assumption, AssumptionParams, CheckOutcome, CheckResult


class TemplateCheck:
    """DeterministicCheck over the parameters of the templates that name it.

    An assumption whose template does not name this check, or whose parameters no longer fit
    its template, gets an inconclusive result that says so: a check never guesses from text.
    Checks only read the database.
    """

    name: ClassVar[str]
    version: ClassVar[str]

    def run(self, assumption: Assumption, conn: sqlite3.Connection) -> CheckResult:
        template = template_of(assumption)
        if template is None or self.name not in template.checks:
            return self.done(
                assumption.id,
                CheckOutcome.INCONCLUSIVE,
                "Nothing: the check does not apply to this assumption's template.",
                f"Not checked: template {assumption.template_id!r} with these parameters is not "
                f"one the {self.name} check tests.",
            )
        return self.evaluate(assumption.id, assumption.params, CaseData(conn))

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        raise NotImplementedError

    def done(
        self,
        assumption_id: str,
        outcome: CheckOutcome,
        searched: str,
        detail: str,
        record_ids: Iterable[str] = (),
        source_ids: Iterable[str] = (),
    ) -> CheckResult:
        return result(
            assumption_id,
            self.name,
            self.version,
            outcome,
            searched,
            detail,
            record_ids,
            source_ids,
        )
