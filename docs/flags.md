# Expert flags and the pilot error log

An expert can flag three things on a claim page, all optional:

| Flag | Where | Asks for |
|---|---|---|
| Wrong label | "Flag this label" under any evidence item | what the label should be (or "not sure"), an optional note |
| Missed record | "Flag a record Baker missed" under the evidence | where the record is (optional), an optional note |
| Disagree with the verdict | "Flag: I disagree with this verdict" in the verdict card | what the verdict should be (or "not sure"), an optional note |

One click opens the form, one click saves it. No reason is required and nothing waits on a flag.

## What a flag does and does not do

- It is written to the case's hash-chained audit log (`flag.add`, `flag.withdraw`), so it needs no
  new table and is tamper-evident like every other expert action. `core/review/flags.py` replays
  those entries to list the current flags.
- It never changes a verdict, an evidence status, a claim or anything `core/audit/rules.py` reads.
  To change a verdict the expert still accepts or dismisses evidence, or overrides the verdict.
- Each flag keeps a snapshot of what the expert saw: the verdict, the item's stance and review
  status, the rule version, and the stance model and prompt version.
- The report lists each flag in its audit-log table with its kind, claim and evidence item, but
  leaves out the expert's note and the record they named.
- Withdrawing a flag adds a `flag.withdraw` entry; the original entry stays in the log.
- A flag needs a claim with a verdict on the audit on screen. Each form carries the run it
  showed; if the audit on screen changed before the expert saved, the flag is refused with
  "reload and flag again", so it is never counted against output the expert did not see.
- After an expert override, a verdict flag records Baker's verdict (the one the rules gave,
  from the `verdict.override` log entry), not the expert's replacement. The verdict form does not
  offer Baker's own verdict, and a flag naming it is refused.
- A label flag must name a label other than the item's own. A claim the expert removed takes no
  new flags, and flags made on it before it was removed are not counted.
- A label flag needs an item in the audit on screen. An item a later audit dropped still opens on
  its evidence page, but without the flag form, and a flag on it is refused.

## The redacted summary

The case page has "Download the redacted summary" (`/flags/summary.json`), and the CLI has
`baker flags --db case.db export --pilot "Pilot A" --out flags.json`. The file holds counts, enum
labels and versions only: flag kinds, the label or verdict at flag time and what the expert says
it should be, claim types, record kinds, model file name and prompt version, and denominators
(claims with a verdict, evidence items labeled, irrelevant ones included). It leaves out claim text, quotes, notes, names,
record references, ids, file names, input hashes and every time except the export date.

The summary counts only flags that belong to the run on screen, so no rate can pass 100%: a
wrong-label flag counts while its item is still in that run (a rules-only re-run keeps the
items); a verdict or missed-record flag counts only on the run it was made on; of several flags
on one item or one claim's verdict, the latest counts. The rest are reported as `not_counted`.

Records the model labeled irrelevant are folded under "N retrieved records were labeled
irrelevant" on the claim page; each opens on its own evidence page, which has the same "Flag this
label" form.

Nothing is sent. The expert reads the file and decides whether to share it.

## The measured error log

`baker flag-log a.json b.json ... [--out error-log.md]` combines summaries into one row per pilot:
wrong labels per evidence item labeled, verdict disagreements per verdict, missed records, plus
the label pairs flagged per stance model and prompt version, the verdict pairs, and the versions
and models each pilot ran (printed for every pilot). Verdict pairs carry the rule version.
Summaries with no pilot name are never pooled: each gets its own row. A summary whose case audit log failed its hash-chain check is left
out, and the log says how many were. So is a summary exported while an audit was still running
(`audit_complete` is false), since it counts only the claims that audit had finished. Flagging is optional, so every rate is a lower bound on what the
expert found wrong, not a measured error rate.
