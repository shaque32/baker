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

One workbook per phone, named `<source_id>.xlsx`. The importer should take the source id from
the file stem. Every sheet has its title on row 1, column headers on row 2 and data from row 3.
A record's locator is `<sheet>!<row>`, with the row as Excel shows it, and its id is
`<kind>:<source_id>:<locator>`, for example `msg:item1:Chats!412`.

**Case Information**: two columns, `Field` and `Value`. Fields: Case number, Evidence number,
Device (the device locator is this row), OS version, Extraction type (`Advanced Logical` or
`Full File System`), Extraction end, Report time zone, Device time zone, Report scope, Tool,
Tool version.

**Contacts**: `#`, `Name`, `Entries`, `Source`, `Deleted`. `Entries` holds one
`<Label>: <value>` per line, for example `Phone-Mobile: +12125550147` and
`User ID-Telegram: 5551234`. Each entry becomes one `contacts` row with id
`contact:<source_id>:Contacts!<row>:<entry number from 1>`.

**Chats**: `#`, `Chat #`, `Source` (app: SMS, WhatsApp, Telegram, Instagram), `Identifier`
(the other party), `Participants`, `Timestamp: Time`, `Direction` (Incoming or Outgoing),
`From`, `To`, `Body`, `Attachment #1`, `Deleted` (`Yes` or blank), `Tag` (examiner tag, e.g.
`Evidence`). Rows are grouped by chat, then ordered by time. A thread's id uses its first row:
`thread:<source_id>:Chats!<first row>`.

**Call Log**: `#`, `Source` (`Phone`), `Direction` (Incoming, Outgoing, Missed),
`Timestamp: Time`, `Duration` (`HH:MM:SS`), `From`, `To`, `Deleted`.

Party cells read `<identifier> <name>`. The identifier is an E.164 number, a WhatsApp JID,
a Telegram user id or an Instagram username. The name is the contact name or the Telegram
display name at that message's time (so a renamed handle changes between rows), and the
phone's own account reads `<identifier> (owner)`.

Timestamps look like `3/14/2026 9:50:20 PM(UTC-4)`. Store `ts_raw` exactly as printed,
`ts_offset_min` as the printed offset, and `ts_utc` converted from both. The printed offset is
the report's display setting, not proof of the phone's zone; the phone's zone is the
`Device time zone` field.

The expected database (`--db`) holds exactly the rows a correct importer should produce from
the two reports, so an importer test can compare against it table by table.
