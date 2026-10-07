"""Count check: how many messages one phone holds between two parties in a window."""

from __future__ import annotations

from core.audit.checks._common import (
    CaseData,
    channel_ok,
    in_window,
    involves_all,
    messages_for_accounts,
    parties,
    sentences,
    window_str,
    zone_notes,
)
from core.audit.checks.base import TemplateCheck
from core.contracts import AssumptionParams, CheckOutcome, CheckResult, Fidelity

_OPS = {"eq": "exactly", "ge": "at least", "le": "at most"}


class CountCheck(TemplateCheck):
    """Parties are matched by account identifier, so a renamed handle is still one party.

    A report can leave records out, and phones lose them, so finding fewer than claimed is
    never a fail. Finding more than "exactly" or "at most" allows is a fail: those records are
    there. "At most" can only pass on a full extraction.
    """

    name = "count"
    version = "1.0.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        if p.window is None or p.expected_count is None or p.count_op is None:
            raise ValueError("the count check needs a window, expected_count and count_op")
        sources = data.sources_for(p.device_ids)
        a, b = parties(data, p)
        a_ids, b_ids = data.account_ids(a.keys), data.account_ids(b.keys)
        on = ", ".join(p.channels) if p.channels else "every channel"
        searched = (
            f"Messages on {on} between {a.describe()} and {b.describe()} on "
            f"{', '.join(p.device_ids)} ({', '.join(sources) or 'no source'}); window "
            f"{window_str(p.window)}."
        )
        notes = a.notes + b.notes + zone_notes(data, p.window, sources)
        if len(sources) != 1 or not a_ids or not b_ids:
            why = (
                "the device is in no single evidence source"
                if len(sources) != 1
                else "a party has no accounts in the data"
            )
            return self.done(
                assumption_id,
                CheckOutcome.INCONCLUSIVE,
                searched,
                sentences(f"Cannot count: {why}", notes),
                [],
                sources,
            )
        (source_id,) = sources
        source = data.sources[source_id]
        rows = [
            r
            for r in messages_for_accounts(data, a_ids | b_ids)
            if r.source_id == source_id
            and channel_ok(r, p.channels)
            and involves_all(r, [a_ids, b_ids])
        ]
        counted = [r for r in rows if r.ts_utc is not None and in_window(r.ts_utc, p.window)]
        no_time = [r for r in rows if r.ts_utc is None]
        n, want, op = len(counted), p.expected_count, p.count_op
        lines = [f"Counted {n}; the claim says {_OPS[op]} {want}"]
        deleted = sum(1 for r in counted if r.deleted)
        if deleted:
            lines.append(f"{deleted} of them are flagged deleted")
        if no_time:
            lines.append(f"{len(no_time)} matching messages have no usable time")
        full = source.fidelity is Fidelity.FULL_EXTRACTION
        if not full:
            lines.append(f"{source_id} is a curated report, so it may omit messages")

        if op in ("eq", "le") and n > want:
            outcome = CheckOutcome.FAIL
        elif no_time:
            outcome = CheckOutcome.INCONCLUSIVE
        elif op == "eq":
            outcome = CheckOutcome.PASS if n == want else CheckOutcome.INCONCLUSIVE
        elif op == "ge":
            outcome = CheckOutcome.PASS if n >= want else CheckOutcome.INCONCLUSIVE
        else:
            outcome = CheckOutcome.PASS if full else CheckOutcome.INCONCLUSIVE
        if outcome is CheckOutcome.INCONCLUSIVE and n < want:
            lines.append("Finding fewer than claimed does not mean the others never existed")
        ids = [r.id for r in counted + no_time]
        return self.done(
            assumption_id, outcome, searched, sentences(lines, notes), ids, [source_id]
        )
