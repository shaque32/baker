"""Identity checks that need no model: one account behind several handles, saved contacts."""

from __future__ import annotations

from core.audit.checks._common import CaseData, fmt_key, key, resolve_handle, sentences
from core.audit.checks.base import TemplateCheck
from core.contracts import AssumptionParams, CheckOutcome, CheckResult, Fidelity


class SameAccountCheck(TemplateCheck):
    """Resolve each handle from the data (account names, thread titles, the sender text a
    report printed, saved phone contacts). Pass if every handle resolves to exactly one
    account id, the same one for all. Fail if each resolves to exactly one id and the ids
    differ. Anything else is inconclusive. This is about accounts, never about people."""

    name = "same_account"
    version = "1.0.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        (app,) = p.channels
        sources = data.sources_for(p.device_ids)
        resolved = [resolve_handle(data, h, app) for h in p.handles]
        searched = (
            f"Where {', '.join(repr(h) for h in p.handles)} appear on {app}: account names, "
            "thread titles, printed sender text and saved phone contacts, in "
            f"{', '.join(data.sources)}."
        )
        notes = [n for r in resolved for n in r.notes]
        ids = [rid for r in resolved for rid in r.record_ids]
        if any(len(r.keys) != 1 for r in resolved):
            return self.done(
                assumption_id,
                CheckOutcome.INCONCLUSIVE,
                searched,
                sentences("Not every handle resolves to exactly one account", notes),
                ids,
                sources,
            )
        keys = {next(iter(r.keys)) for r in resolved}
        if len(keys) == 1:
            (k,) = keys
            outcome, line = CheckOutcome.PASS, f"Every handle resolves to {fmt_key(k)}"
        else:
            outcome = CheckOutcome.FAIL
            line = "The handles resolve to different accounts: " + ", ".join(
                fmt_key(k) for k in sorted(keys)
            )
        return self.done(assumption_id, outcome, searched, sentences(line, notes), ids, sources)


class ContactCheck(TemplateCheck):
    """Pass if the phone has a contact entry with exactly this name and the account's number.
    A missing entry is inconclusive: contact lists can be filtered or edited."""

    name = "contact"
    version = "1.0.0"

    def evaluate(self, assumption_id: str, p: AssumptionParams, data: CaseData) -> CheckResult:
        sources = data.sources_for(p.device_ids)
        account = data.accounts.get(p.account_ids[0])
        name = p.quoted_text or ""
        number = account.identifier if account else p.account_ids[0]
        searched = f'Contacts named "{name}" on {", ".join(p.device_ids)}, for the number {number}.'
        if account is None or len(sources) != 1:
            why = "the account is not in this case" if account is None else "no single source"
            return self.done(
                assumption_id, CheckOutcome.INCONCLUSIVE, searched, f"Not checked: {why}."
            )
        (source_id,) = sources
        wanted = key("Phone", account.identifier)
        same_name, exact = [], []
        for cid, cname, ident in data.conn.execute(
            "SELECT id, name, identifier FROM contacts WHERE source_id = ? ORDER BY id",
            (source_id,),
        ):
            if (cname or "").strip() != name.strip():
                continue
            same_name.append(f"{cid} ({ident})")
            if key("Phone", ident) == wanted:
                exact.append(cid)
        if exact:
            return self.done(
                assumption_id,
                CheckOutcome.PASS,
                searched,
                f'{source_id} has the contact "{name}" with {number}.',
                exact,
                [source_id],
            )
        found = "; ".join(same_name) if same_name else "no contact with that name"
        lines = [f"Found {found}", "Not found does not mean the entry never existed"]
        if data.sources[source_id].fidelity is not Fidelity.FULL_EXTRACTION:
            lines.append(f"{source_id} is a curated report, so its contact list may be incomplete")
        return self.done(
            assumption_id, CheckOutcome.INCONCLUSIVE, searched, sentences(lines), [], [source_id]
        )
