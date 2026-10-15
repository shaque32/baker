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

## The redacted summary

The case page has "Download the redacted summary" (`/flags/summary.json`), and the CLI has
`baker flags --db case.db export --pilot "Pilot A" --out flags.json`. The file holds counts, enum
labels and versions only: flag kinds, the label or verdict at flag time and what the expert says
it should be, claim types, record kinds, model file name and prompt version, and denominators
(claims with a verdict, evidence items shown). It leaves out claim text, quotes, notes, names,
record references, ids, file names, input hashes and every time except the export date.

Nothing is sent. The expert reads the file and decides whether to share it.

## The measured error log

`baker flag-log a.json b.json ... [--out error-log.md]` combines summaries into one row per pilot:
wrong labels per evidence item shown, verdict disagreements per verdict, missed records, plus the
label and verdict pairs flagged. Flagging is optional, so every rate is a lower bound on what the
expert found wrong, not a measured error rate.
