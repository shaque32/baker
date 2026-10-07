"""Sender check: who sent the message with these exact words, judged by account identifier."""

from __future__ import annotations

from core.audit.checks._common import (
    CaseData,
    channel_ok,
    fmt_key,
    messages_with_text,
    parties,
    sentences,
)
from core.audit.checks.base import TemplateCheck
from core.contracts import AssumptionParams, CheckOutcome, CheckResult


class SenderCheck(TemplateCheck):
    """Pass if every message carrying the words came from the party's accounts. Fail if every
    one came from someone else. Mixed or unknown senders are inconclusive. Display names are
    never compared: two handles on one user id are one sender, one name on two numbers is two.
    The check speaks about accounts; whether a person typed the words is a separate question.
    """

    name = "sender"
    version = "1.0.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        sources = data.sources_for(p.device_ids)
        (party,) = parties(data, p)
        sender_ids = data.account_ids(party.keys)
        rows = [
            r
            for r in messages_with_text(data, p.quoted_text or "")
            if r.source_id in sources and channel_ok(r, p.channels)
        ]
        on = f" on {', '.join(p.channels)}" if p.channels else ""
        searched = (
            f"Messages{on} containing {p.quoted_text!r} verbatim in {', '.join(sources)}; "
            f"expected sender {party.describe()}."
        )
        if not party.keys:
            return self.done(
                assumption_id,
                CheckOutcome.INCONCLUSIVE,
                searched,
                sentences("Could not resolve the expected sender to accounts", party.notes),
                [r.id for r in rows],
                sources,
            )
        if not rows:
            return self.done(
                assumption_id,
                CheckOutcome.INCONCLUSIVE,
                searched,
                "None found. Not found does not mean the message was never sent.",
                [],
                sources,
            )

        good, bad, unknown, lines = [], [], [], []
        for row in rows:
            acc = data.accounts.get(row.sender or "")
            if acc is None:
                unknown.append(row.id)
                lines.append(f"{row.id} on {row.app} has no recorded sender")
                continue
            (good if row.sender in sender_ids else bad).append(row.id)
            lines.append(
                f"{row.id} on {row.app} was sent by {fmt_key(acc.key)} "
                f"({acc.display_name or 'no name'})"
            )
        if good and not bad and not unknown:
            outcome, verdict = CheckOutcome.PASS, f"Every copy came from {party.label}"
        elif bad and not good and not unknown:
            outcome, verdict = CheckOutcome.FAIL, f"No copy came from {party.label}"
        else:
            outcome = CheckOutcome.INCONCLUSIVE
            verdict = "The words match messages with different or unknown senders"
        detail = sentences(lines, verdict, party.notes)
        return self.done(assumption_id, outcome, searched, detail, [r.id for r in rows], sources)
