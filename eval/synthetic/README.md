# Synthetic case generator

Everything here is fictional. No real case data, ever.

```
make synth   # writes eval/synthetic/case01/ and the expected database eval/out/case01/case01.db
```

The generator is seeded and deterministic: the same code gives byte-identical reports on any
machine. `case.json` pins each report's SHA-256, and the tests regenerate the case and compare
it with the committed files, so a stale or non-deterministic output fails `make check`.

| File | What it is |
|---|---|
| `case01_story.py` | People, accounts, devices, contacts and every hand-placed message and call |
| `case01_key.py` | Mock affidavit layout, the 20 claims and the **draft** verdicts with reasoning |
| `filler.py` | Seeded background chatter; never touches trap threads or reserved words |
| `generate.py` | Renders the reports, the expected database, the affidavit and the draft key |
| `xlsx.py` | Minimal deterministic .xlsx writer |
| `case01/` | Generated outputs (the `.xlsx` reports are rebuilt, not committed) |

## Case01 at a glance

Two phones, about 2,000 messages, English and Russian, Feb 16 to Apr 5 2026.

- **item1**: iPhone seized from Daniel Petrov. Report prints every time in UTC+0.
- **item2**: Galaxy S22 seized from Marcus Reyes. Report prints device local time (EST, then
  EDT after 2026-03-08).

Planted traps (full detail in `case01/case.json`): `handle_change`, `shared_account`,
`timezone`, `gap`, `decoy_thread`, `second_alex`, `meeting_place`.

## Draft answer key

`case01/ANSWER_KEY_DRAFT.md` is for Arsh's line-by-line review. `case01/draft_gold.jsonl` is
the same key in `GoldClaim` format with `labeled_by` set to a DRAFT marker. Neither is gold.
`eval/gold/` is human-owned: approved lines are copied there by a human.

## Report layout (for importers)

Agreed with the Cellebrite report import thread; its importer maps columns by header name.
Full importer spec: `/mnt/project-files/baker/wave1/cellebrite-report-layout.md`.

One workbook per phone, named `<source_id>.xlsx`; `case.json` lists each source id, to pass
as `--source-id`. Data sheets have a title on row 1, headers on row 2 and data from row 3.
A record's locator is `<sheet>!<row>` with the 1-based spreadsheet row.

| Sheet | Columns |
|---|---|
| `Summary` | Key in column A, value in column B: Case number, Evidence number, Device, OS version, Extraction type, Extraction start date/time, Time zone (the report's display setting), Device time zone (the phone's zone), Report version, Tool, Tool version |
| `User Accounts` | `#`, `Source`, `Username`, `Name` (the phone's own accounts) |
| `Contacts` | `#`, `Name`, `Entries` (one `<Label>: <value>` per line), `Source`, `Deleted` |
| `Chats` | `#`, `Chat #`, `Name`, `Source` (SMS, WhatsApp, Telegram, Instagram), `Identifier`, `Participants` (one per line), `From`, `To`, `Body`, `Timestamp`, `Direction`, `Deleted`, `Attachment #1`, `Tag` |
| `Call Log` | `#`, `Source`, `Type` (Incoming, Outgoing, Missed), `Timestamp`, `Duration` (`HH:MM:SS`), `From`, `To`, `Deleted` |

- Party cells read `<identifier> <name>`; the phone's own account reads `<identifier> (owner)`.
  The name is the contact name, or the Telegram display name at that row's time, so a renamed
  handle changes between rows.
- `Deleted` is always `Deleted` or `Intact`.
- Timestamps look like `3/14/2026 9:50:20 PM(UTC-4)`. Item 1 prints UTC+0 for a phone set to
  America/New_York; the phone's zone is the `Device time zone` summary key.

Expected ids in the `--db` database: `msg:` and `call:<source_id>:<locator>`,
`contact:<source_id>:Contacts!<row>#<entry>`, threads `thr:<source_id>:<app>:<Chat #>`,
accounts `acct:<source_id>:<app>:<identifier>` (first sighting sets locator and display name;
the owner's come from `User Accounts`, and only those carry a `device_id`), device
`dev:<source_id>` labeled with the report's Device field. Sources import as
`curated_report`. A `Tag` cell sets `bookmarked = 1`; a blank one leaves it NULL. Language,
attachment hashes and MIME types are not in the report, so they are NULL. The expected database is exactly what a correct importer should produce, so an
importer test can compare against it table by table.
