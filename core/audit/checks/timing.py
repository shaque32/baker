"""Time-zone check: did the record happen inside the claimed window?

Windows arrive resolved to UTC, so the comparison is exact. The detail shows each record in
its phone's own zone (devices.timezone) next to the time the report printed. A report can
print UTC+0 for a phone set to New York, and reading that printed date is the classic mistake
this check exists to catch.
"""

from __future__ import annotations

from core.audit.checks._common import (
    CaseData,
    Row,
    calls_for_accounts,
    channel_ok,
    in_window,
    involves_all,
    local_str,
    messages_with_text,
    parties,
    sentences,
    window_str,
    zone_notes,
)
from core.audit.checks.base import TemplateCheck
from core.contracts import AssumptionParams, CheckOutcome, CheckResult


class TimeCheck(TemplateCheck):
    """Pass if a picked record falls in the window. Fail only for messages picked by their
    exact words, when every copy has a known time outside the window: the record the claim
    describes exists, at another time. Calls are picked by their parties, not their content,
    so a call outside the window could be a different call, and is never a fail."""

    name = "time"
    version = "1.0.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        if p.window is None:
            raise ValueError("the time check needs a window")
        sources = data.sources_for(p.device_ids)
        found = parties(data, p)
        party_ids = [data.account_ids(x.keys) for x in found]
        by_text = bool(p.quoted_text)
        if by_text:
            rows = messages_with_text(data, p.quoted_text or "")
            what = f"messages containing {p.quoted_text!r} verbatim"
        else:
            rows = calls_for_accounts(data, set().union(*party_ids))
            what = "calls"
            if p.duration_s is not None:
                lo, hi = p.duration_s
                # A call with no recorded duration never matches a stated duration.
                rows = [r for r in rows if r.duration_s is not None and lo <= r.duration_s <= hi]
                what += f" lasting {lo} to {hi} s"
        if found:
            what += " between " + " and ".join(x.describe() for x in found)
        rows = [
            r
            for r in rows
            if r.source_id in sources
            and channel_ok(r, p.channels)
            and (not party_ids or involves_all(r, party_ids))
        ]
        searched = f"{what.capitalize()} in {', '.join(sources)}; window {window_str(p.window)}."
        notes = [n for x in found for n in x.notes] + zone_notes(data, p.window, sources)
        if not rows:
            return self.done(
                assumption_id,
                CheckOutcome.INCONCLUSIVE,
                searched,
                sentences("None found. Not found does not mean it did not happen", notes),
                [],
                sources,
            )

        inside: list[Row] = []
        outside: list[Row] = []
        unknown: list[Row] = []
        for row in rows:
            if row.ts_utc is None:
                unknown.append(row)
            elif in_window(row.ts_utc, p.window):
                inside.append(row)
            else:
                outside.append(row)

        def show(label: str, group: list[Row]) -> str:
            if not group:
                return ""
            return f"{label}: " + "; ".join(f"{r.id} at {local_str(data, r)}" for r in group)

        lines = [
            show("Inside the window", inside),
            show("Outside the window", outside),
            show("No usable time", unknown),
        ]
        # record_ids are the records the outcome rests on.
        ids = [r.id for r in inside + outside + unknown]
        if inside:
            outcome, ids = CheckOutcome.PASS, [r.id for r in inside]
        elif outside and not unknown and by_text:
            outcome = CheckOutcome.FAIL
        else:
            outcome = CheckOutcome.INCONCLUSIVE
            if outside and not by_text:
                lines.append("Calls are matched by their parties only, so these may be other calls")
        return self.done(assumption_id, outcome, searched, sentences(lines, notes), ids, sources)
