"""Coverage-aware absence check: was there contact between two parties in a window?

"Not found" never means "did not happen". Finding contact fails the assumption. Finding none
passes only when every searched source is a full extraction whose dated records span the
whole window; otherwise the result is inconclusive, and both outcomes state exactly what was
searched and what the sources could and could not show.
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
    messages_for_accounts,
    parties,
    sentences,
    window_str,
    zone_notes,
)
from core.audit.checks.base import TemplateCheck
from core.contracts import AssumptionParams, CheckOutcome, CheckResult, Fidelity, TimeWindow


class AbsenceCheck(TemplateCheck):
    name = "absence"
    version = "1.0.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        if p.window is None:
            raise ValueError("the absence check needs a window")
        sources = data.sources_for(p.device_ids)
        a, b = parties(data, p)
        a_ids, b_ids = data.account_ids(a.keys), data.account_ids(b.keys)
        on = ", ".join(p.channels) if p.channels else "every channel, calls included"
        searched = (
            f"Messages and calls on {on} between {a.describe()} and {b.describe()} in "
            f"{', '.join(sources) or 'no sources'}; window {window_str(p.window)}."
        )
        notes = a.notes + b.notes + zone_notes(data, p.window, sources)
        if not a_ids or not b_ids:
            return self.done(
                assumption_id,
                CheckOutcome.INCONCLUSIVE,
                searched,
                sentences(
                    "A party has no accounts in the data, so contact can be neither found nor "
                    "ruled out",
                    notes,
                ),
                [],
                sources,
            )

        everyone = a_ids | b_ids
        rows: list[Row] = messages_for_accounts(data, everyone) + calls_for_accounts(data, everyone)
        rows = [r for r in rows if r.source_id in sources and channel_ok(r, p.channels)]
        found: list[Row] = []
        unplaced: list[Row] = []
        for r in rows:
            if r.sender is None:
                # A row with a party on it but no sender: it may be contact, it may not.
                if r.ts_utc is None or in_window(r.ts_utc, p.window):
                    unplaced.append(r)
            elif involves_all(r, [a_ids, b_ids]):
                if r.ts_utc is None:
                    unplaced.append(r)
                elif in_window(r.ts_utc, p.window):
                    found.append(r)

        if found:
            shown = "; ".join(
                f"{r.id} ({r.kind} on {r.app}) at {local_str(data, r)}" for r in found
            )
            return self.done(
                assumption_id,
                CheckOutcome.FAIL,
                searched,
                sentences(f"Found {len(found)} inside the window: {shown}", notes),
                [r.id for r in found],
                sources,
            )

        gaps = _coverage_gaps(data, p.window, p.channels, sources)
        lines = ["Found none"]
        if unplaced:
            lines.append(
                f"{len(unplaced)} rows could not be placed in the window or tied to both "
                f"parties: {', '.join(r.id for r in unplaced)}"
            )
        if not unplaced and not gaps:
            lines.append("Every source is a full extraction whose records span the window")
            return self.done(
                assumption_id, CheckOutcome.PASS, searched, sentences(lines, notes), [], sources
            )
        lines += gaps
        lines.append("Not found does not mean there was no contact")
        return self.done(
            assumption_id,
            CheckOutcome.INCONCLUSIVE,
            searched,
            sentences(lines, notes),
            [r.id for r in unplaced],
            sources,
        )


def _coverage_gaps(
    data: CaseData, window: TimeWindow, channels: tuple[str, ...], sources: list[str]
) -> list[str]:
    """Plain statements of why the searched sources cannot show an absence."""
    if not sources:
        return ["No evidence source was searched"]
    gaps: list[str] = []
    start = window.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end = window.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    for sid in sources:
        info = data.sources[sid]
        if info.fidelity is not Fidelity.FULL_EXTRACTION:
            kind = info.fidelity.value.replace("_", " ")
            gaps.append(f"{sid} is a {kind}, which cannot show that something is absent")
        lo, hi = data.conn.execute(
            "SELECT min(t), max(t) FROM (SELECT ts_utc AS t FROM messages WHERE source_id = ?"
            " UNION ALL SELECT ts_utc FROM calls WHERE source_id = ?) WHERE t IS NOT NULL",
            (sid, sid),
        ).fetchone()
        if lo is None or lo > start or hi < end:
            span = f"{lo} to {hi}" if lo else "no dated records"
            gaps.append(f"{sid}'s dated records ({span}) do not span the window")
        for app in channels:
            if app.strip().lower() == "call":
                (n,) = data.conn.execute(
                    "SELECT count(*) FROM calls WHERE source_id = ?", (sid,)
                ).fetchone()
            else:
                (n,) = data.conn.execute(
                    "SELECT (SELECT count(*) FROM messages m JOIN threads t ON t.id = m.thread_id"
                    " WHERE m.source_id = ? AND lower(t.app) = lower(?))"
                    " + (SELECT count(*) FROM calls WHERE source_id = ? AND lower(app) = lower(?))",
                    (sid, app, sid, app),
                ).fetchone()
            if n == 0:
                gaps.append(f"{sid} has no {app} records at all, so {app} may not be covered")
    return gaps
