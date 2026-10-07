"""Weekday check: which date does a weekday named in a message point to?

"lets meet monday" sent on Friday March 6 points to Monday March 9, counted forward from the
send date in the phone's own zone. The check passes when every copy of the message points to
the claimed day. Language is loose ("monday" can mean the one after), so anything else is
inconclusive, never a fail: a different reading is the model's and the expert's question.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.audit.checks._common import (
    CaseData,
    channel_ok,
    involves_all,
    local_str,
    messages_with_text,
    parties,
    sentences,
)
from core.audit.checks.base import TemplateCheck
from core.contracts import AssumptionParams, CheckOutcome, CheckResult

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_NAME = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b", re.IGNORECASE)
_QUALIFIED = re.compile(
    r"\b(next|this|last|coming|following|every)\s+(" + "|".join(WEEKDAYS) + r")\b", re.IGNORECASE
)


class WeekdayCheck(TemplateCheck):
    name = "weekday"
    version = "1.0.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        if p.window is None or not p.quoted_text:
            raise ValueError("the weekday check needs quoted_text and a window")
        sources = data.sources_for(p.device_ids)
        found = parties(data, p)
        party_ids = [data.account_ids(x.keys) for x in found]
        text = p.quoted_text
        searched = (
            f"Messages containing {text!r} verbatim in {', '.join(sources)}; the weekday it "
            f'names, counted forward from the send date on the phone, against "{p.window.raw}".'
        )
        notes = [n for x in found for n in x.notes]

        def inconclusive(why: str, ids: tuple[str, ...] = ()) -> CheckResult:
            return self.done(
                assumption_id, CheckOutcome.INCONCLUSIVE, searched, sentences(why, notes), ids,
                sources,
            )  # fmt: skip

        try:
            zone = ZoneInfo(p.window.tz)
        except (ZoneInfoNotFoundError, ValueError):
            return inconclusive(f"The window's zone {p.window.tz!r} is unknown")
        first = p.window.start_utc.astimezone(zone).date()
        last = p.window.end_utc.astimezone(zone).date()
        if first != last:
            return inconclusive("The claimed window is not a single day")
        names = {m.lower() for m in _NAME.findall(text)}
        if len(names) != 1:
            return inconclusive("The quoted words must name exactly one weekday")
        if _QUALIFIED.search(text):
            return inconclusive(
                "The weekday is qualified (next, this, last...), so the date is open"
            )
        (weekday,) = names
        target = WEEKDAYS.index(weekday)

        rows = [
            r
            for r in messages_with_text(data, text)
            if r.source_id in sources
            and channel_ok(r, p.channels)
            and (not party_ids or involves_all(r, party_ids))
        ]
        if not rows:
            return inconclusive("None found. Not found does not mean the message was never sent")

        lines, resolved = [], set()
        for r in rows:
            tz = data.tz_for(r.source_id)
            if r.ts_utc is None or tz is None:
                return inconclusive(f"{r.id} has no usable time or phone zone", (r.id,))
            sent = r.ts_utc.astimezone(tz).date()
            if sent.weekday() == target:
                return inconclusive(
                    f"{r.id} was sent on a {weekday.capitalize()} itself, so the day is open",
                    (r.id,),
                )
            day = _forward(sent, target)
            resolved.add(day)
            lines.append(
                f"{r.id} sent {local_str(data, r)}, a {sent:%A}: '{weekday}' is {day:%A %Y-%m-%d}"
            )
        ids = [r.id for r in rows]
        if resolved == {first}:
            lines.append(f"That is the claimed day, {first:%A %Y-%m-%d}")
            return self.done(
                assumption_id, CheckOutcome.PASS, searched, sentences(lines, notes), ids, sources
            )
        lines.append(
            f"The claimed day is {first:%A %Y-%m-%d}; another reading is a question of meaning"
        )
        return self.done(
            assumption_id, CheckOutcome.INCONCLUSIVE, searched, sentences(lines, notes), ids,
            sources,
        )  # fmt: skip


def _forward(sent: date, target: int) -> date:
    return sent + timedelta(days=(target - sent.weekday()) % 7)
