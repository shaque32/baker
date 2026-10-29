"""Count check: how many messages, or calls, one phone holds between two parties in a window."""

from __future__ import annotations

from core.audit.checks._common import (
    CALL_CHANNEL,
    CaseData,
    Row,
    calls_for_accounts,
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
    there. "At most" can only pass on a full extraction. When any matching message is one the
    extraction tool numbered as a copy of another row, the count neither passes nor fails.

    With 'call' among the channels it counts calls instead, on the other apps named if any
    (validation fill f). A call count never fails: a call log keeps calls that did not connect,
    and an extraction can hold one call twice (two databases, a few seconds apart). It passes
    only when the rows match the claim and no two counted calls with the same party fall
    within DUPLICATE_S of each other; otherwise it is inconclusive.
    """

    name = "count"
    version = "1.1.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        if p.window is None or p.expected_count is None or p.count_op is None:
            raise ValueError("the count check needs a window, expected_count and count_op")
        sources = data.sources_for(p.device_ids)
        a, b = parties(data, p)
        a_ids, b_ids = data.account_ids(a.keys), data.account_ids(b.keys)
        calls = CALL_CHANNEL in {c.strip().lower() for c in p.channels}
        if calls:
            return self._calls(assumption_id, p, data)
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
            lines.append(f"{deleted} of them carry the source's deletion flag")
        if no_time:
            lines.append(f"{len(no_time)} matching messages have no usable time")
        full = source.fidelity is Fidelity.FULL_EXTRACTION
        if not full:
            lines.append(f"{source_id} is a curated report, so it may omit messages")

        copies = sum(1 for r in counted + no_time if r.id in data.numbered_copies)
        if copies:
            lines.append(
                f"{copies} of the matching messages {'is' if copies == 1 else 'are'} numbered "
                "by the extraction tool as a copy of another row, so the count may hold one "
                "message twice; an expert must decide which rows are the same message"
            )

        if copies:
            outcome = CheckOutcome.INCONCLUSIVE
        elif op in ("eq", "le") and n > want:
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

    def _calls(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        if p.window is None or p.expected_count is None or p.count_op is None:
            raise ValueError("the count check needs a window, expected_count and count_op")
        sources = data.sources_for(p.device_ids)
        a, b = parties(data, p)
        a_ids, b_ids = data.account_ids(a.keys), data.account_ids(b.keys)
        apps = {c.strip().lower() for c in p.channels} - {CALL_CHANNEL}
        on = ", ".join(sorted(apps)) if apps else "every app"
        searched = (
            f"Calls on {on} between {a.describe()} and {b.describe()} on "
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
        rows = [
            r
            for r in calls_for_accounts(data, a_ids | b_ids)
            if r.source_id == source_id
            and (not apps or r.app.strip().lower() in apps)
            and involves_all(r, [a_ids, b_ids])
        ]
        counted = [r for r in rows if r.ts_utc is not None and in_window(r.ts_utc, p.window)]
        no_time = [r for r in rows if r.ts_utc is None]
        n, want, op = len(counted), p.expected_count, p.count_op
        lines = [f"Counted {n} calls; the claim says {_OPS[op]} {want}"]
        twins = _possible_twins(counted)
        if twins:
            pairs = "; ".join(f"{x} and {y}" for x, y in twins)
            lines.append(
                f"{len(twins)} pairs of counted calls are within {DUPLICATE_S} seconds of each "
                f"other ({pairs}), so the count may hold one call twice; an expert must decide "
                "which rows are the same call"
            )
        if no_time:
            lines.append(f"{len(no_time)} matching calls have no usable time")
        # A row with no length, or a zero length, may be a call that never connected, so it
        # cannot count toward "spoke N times".
        unconnected = sum(1 for r in counted if not r.duration_s)
        if unconnected:
            lines.append(
                f"{unconnected} counted calls have no length or a zero length, so they may not "
                "have connected"
            )
        deleted = sum(1 for r in counted if r.deleted)
        if deleted:
            lines.append(f"{deleted} of them carry the source's deletion flag")
        full = data.sources[source_id].fidelity is Fidelity.FULL_EXTRACTION
        if not full:
            lines.append(f"{source_id} is a curated report, so it may omit calls")
        if twins or no_time or unconnected:
            outcome = CheckOutcome.INCONCLUSIVE
        elif op == "eq":
            outcome = CheckOutcome.PASS if n == want else CheckOutcome.INCONCLUSIVE
        elif op == "ge":
            outcome = CheckOutcome.PASS if n >= want else CheckOutcome.INCONCLUSIVE
        else:
            outcome = CheckOutcome.PASS if full and n <= want else CheckOutcome.INCONCLUSIVE
        if outcome is CheckOutcome.INCONCLUSIVE:
            lines.append(
                "A call count never fails: the log keeps calls that did not connect, and one call"
                " can be stored twice"
            )
        ids = [r.id for r in counted + no_time]
        return self.done(
            assumption_id, outcome, searched, sentences(lines, notes), ids, [source_id]
        )


DUPLICATE_S = 60  # two rows of one call from two databases fall seconds apart


def _possible_twins(rows: list[Row]) -> list[tuple[str, str]]:
    """Pairs of counted calls (all between the same two parties) DUPLICATE_S seconds apart or
    less."""
    timed = sorted((r.ts_utc, r.id) for r in rows if r.ts_utc is not None)
    out = []
    for i, (tx, x) in enumerate(timed):
        j = i + 1  # by index, so a sparse log is one pass, not a copy per call (Codex on #169)
        while j < len(timed) and (timed[j][0] - tx).total_seconds() <= DUPLICATE_S:
            out.append((x, timed[j][1]))
            j += 1
    return out
