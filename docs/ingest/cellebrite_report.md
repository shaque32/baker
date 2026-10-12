# Cellebrite report import (Excel and PDF)

Importers: `core/ingest/cellebrite_excel.py` and `core/ingest/cellebrite_pdf.py`.
Both implement `EvidenceImporter` and share one row mapper (`core/ingest/cellebrite_common.py`).
UFDR is out of scope here.

## What we know and what we assumed

Cellebrite does not publish the Excel or PDF report layout, and it varies with Physical
Analyzer / Reader version, language and the examiner's column choices. Public sources describe
the report sections (extraction summary, device info, analyzed data by category such as chats,
calls, contacts, user accounts) but not exact column names. So the importer is **header driven**:
it finds the header row on each sheet by matching known column names (and aliases), maps columns
by name, never by position, and records every sheet and column it did not understand.

Everything below is an assumption to confirm against a real export (an expert can open one
from a closed or training case and compare; do not put it in the repo).

### Workbook

| Sheet (aliases, case-insensitive) | Imported as |
|---|---|
| `Summary`, `Extraction Summary`, `Case Information`, `Device Information` | `sources` metadata, `devices` row |
| `Chats`, `Chat Messages`, `Instant Messages` | `threads`, `messages`, `message_recipients`, `attachments` |
| `SMS Messages`, `SMS`, `MMS Messages`, `Text Messages`, `Messages` | `threads` (one per counterpart), `messages` |
| `Call Log`, `Calls`, `Call History` | `calls` |
| `Contacts`, `Address Book` | `contacts` |
| `User Accounts`, `Accounts` | `accounts` (device-owner accounts) |
| a kind plus a known app: `Chats - WhatsApp`, `Instant Messages (Telegram)`, `Signal Chats`, `WhatsApp Messages` | that kind, with the app taken from the title when the sheet has no `Source` column. Only listed apps count, so `Chat Statistics` is not read as chats |
| `Timeline`, `Locations`, `Web History`, `Emails`, ... | not imported; listed in coverage as a category Baker does not import, with its row count |
| anything else | not imported; listed in coverage for review, with its row count and first row. An unrecognised sheet is never classified by its columns, because `Timeline` repeats messages and calls |

Data sheets: one or more title or filter rows may sit above the header row. The header row is the
first row (within the first 10) where at least two cells match known column names for that sheet
**and** the columns that kind cannot do without are there (a message body or attachment column for
messages, a duration or party column for calls, a number or email column for contacts, a username
for accounts). So a sheet titled `Chats` that holds locations is reported, not misread.
Header names are matched case-insensitively, with no-break spaces, invisible marks and a trailing
`:` or `*` ignored. Every row below the header is one record, except:
- a row whose cells are all empty (skipped, counted);
- the header repeated mid-sheet (skipped, counted);
- a row with values only in columns Baker does not read, such as a footer `Total: 45` or a row
  number alone (skipped, counted, and its locator listed for review);
- a row holding only column names, such as a second header row Baker could not join (same).

Merged cells (Excel). Read-only workbooks do not expose merges, so the importer reads them from
the sheet XML. A header written on two rows, with a group name merged over its columns
(`Timestamp` over `Date` and `Time`), is joined into one header row (`Timestamp: Date`,
`Timestamp: Time`) when the joined name is a known column. In data rows, a merged cell's value is
copied down its range only for columns that label a group of rows (chat id, chat name,
participants, app, from, to, parties). It is never copied for message text, times,
attachments, flags or durations; coverage names those columns for review instead.

Hidden sheets are read like the others and listed in coverage.

Summary sheet: key-value pairs, key in column A, value in column B. Keys read (aliases accepted):
`Extraction start date/time`, `Extraction type`, `Device` / `Model`, `OS version`,
`UFED Physical Analyzer version` / `Report version` / `Tool version`, `Tool`,
`Report time zone` / `Time zone` (applied to times only if a fixed offset), `Device time zone`
(stored on the device). `Extraction end` is accepted for the extraction time.

### Columns

| Field | Accepted headers |
|---|---|
| chat id | `Chat #`, `Chat ID`, `Identifier`, `Thread`, `Conversation`, `Conversation ID` |
| chat name | `Name`, `Chat Name`, `Description`, `Conversation Name`, `Group Name` (Chats only) |
| app | `Source`, `Application`, `App`, `Service`, `App Name` |
| from | `From`, `Sender`, `Author` |
| to | `To`, `Recipients`, `Receiver`, `Participants`/`Members` (To only if `To` is absent: means all participants other than the sender) |
| body | `Body`, `Message`, `Text`, `Content`, `Message Body`, `Message Text`. Never `Snippet`, `Preview` or `Body (Translated)`: those are listed as columns Baker does not read |
| time | `Timestamp`, `Date/Time`, `Date & Time`, `Datetime`, `Time Stamp`, `Timestamp: Time` alone (full value), `Timestamp: Date` + `Timestamp: Time`, separate `Date` and `Time` columns (read together), `Time`, `Date`. A fixed offset in the column name (`Timestamp (UTC+3)`, `Time - UTC`) applies to values with no offset of their own; a zone name there (`Time (Device local)`) is recorded and not applied |
| direction | `Direction`, `Message Direction`, `Type`, `Folder`, `Status` (values `Incoming`, `Outgoing`, `Sent`, `Received`, `Inbox`, `Missed`, `Read`, `Unread`) |
| deleted | `Deleted`, `Deleted - Instant Message`, `Deleted - Chat`, `Deleted - Call`, `Record status` |
| attachment | `Attachment #1`..`Attachment #N`, `Attachment 1`, `Attachments`, `Attached files`, `Attachment #1: File name` |
| examiner tag | `Tag`, `Tags`, `Bookmark` (any text sets `bookmarked = 1`; blank stays NULL) |
| duration (calls) | `Duration`, `Call Duration` (`HH:MM:SS`, `MM:SS` or seconds) |
| party (calls) | `Parties`, `Number`, `Phone Number`, `From`, `To`; `Name` |
| contact | `Name`; `Entries`, `Phone`, `Phone Number`, `Email`, `Identifier`, `Username` |
| account | `Username`, `User ID`, `Identifier`, `Entries`; `Name`, `Display name`; `Source` / `Service` |

Party cells look like `<identifier> <display name>`, for example `+15551230001 Alex` or
`alex92@s.whatsapp.net Alex`. The first whitespace-free token is the identifier; the rest is the
display name. A lone token with a dot, underscore or digit (an Instagram username such as
`m.reyes.auto`) is an identifier. A trailing ` (owner)` marks the device owner. Several parties are
separated by new lines, `;`, or `, ` when the next party starts with an identifier (so `Smith, John`
stays one name).

### Times

Accepted: `M/D/YYYY h:mm:ss AM(UTC-5)`, `DD/MM/YYYY HH:MM:SS(UTC+3)`, `DD.MM.YYYY`, ISO 8601 with
offset or `Z`, English month names (`13-Mar-2026 18:05:00 GMT-4`, `Mar 13, 2026 6:05 PM`), a
leading weekday (`Fri, ...`), offsets written `(UTC-4)`, `(UTC-04:00)`, `GMT-4`, `UTC+0300`,
`[UTC+3]`, a bare `-0400` or `+03:00`, an Excel date cell, and split date + time columns.
The importer handles them as follows:
- An offset written in the value: offset kept, time converted to UTC.
- No offset in the value: a fixed offset in the column name is used; else the report-level
  `Time zone` from the Summary sheet, if it is a fixed `UTC±H[:MM]` offset. Coverage records
  which one each time came from.
- Neither: `ts_utc` and `ts_offset_min` are NULL, `ts_raw` keeps the value. The importer never
  guesses a zone. A zone name (`EST`, `(Eastern Standard Time)`, `Europe/Moscow`) is never
  applied, because its offset depends on daylight saving and on what the tool meant.
- Day/month order. A value whose first number is above 12 is day first; whose second number is
  above 12 is month first; whose day equals its month reads the same either way. Each table's
  order comes from its own deciding values; a table with none takes the order the rest of the
  report shows (one report, one date format). **When nothing in the report decides, ambiguous
  values such as 3/4/2026 are left without a UTC time and listed for review. Nothing is assumed**
  (until importer 0.1.0, US order was assumed). A person who knows the report's date format can
  re-import with the order stated (`date_order="mdy"` or `"dmy"` on the importer); coverage
  records that it was stated, and counts any value that can only be read the other way.
- Never read: two-digit years, a date with no time, a bare number (an Excel serial date shown as
  a number). Each is counted per reason, with the rows to open.
`ts_raw` always holds the exact cell text (for split columns, `date + " " + time`).

### Deleted flag

`Deleted`, `Yes`, `Trash`, `True`, `1` set `deleted_flag = 1`. `Intact`, `No`, `False`, `0` set 0.
Blank or a missing column gives NULL (the source did not say). Reports often omit the column, so
NULL is common. Baker never reports that a message was deleted; this flag only records what the
report said.

## Stable ids and source_ref

- Source id: caller-supplied, else the file stem (`item1.xlsx` -> `item1`) when it is a plain
  token, else `src_<first 12 hex of SHA-256>`.
- Excel locator: `<sheet>!<row>` using the 1-based spreadsheet row, e.g. `Chats!14`.
- PDF locator: `p<page>:t<table>:r<row>`, all 1-based, e.g. `p12:t1:r4`.
- Message id `msg:<source_id>:<locator>`; calls `call:<source_id>:<locator>`; contacts
  `contact:<source_id>:<locator>#<entry n>`; attachments `att:<source_id>:<locator>:<n>`;
  threads `thr:<source_id>:<app>:<chat key>` (chat key = `Chat #`; else the participants; for
  SMS sheets `sms:<counterpart>`), located at the chat's first row; accounts
  `acct:<source_id>:<app as spelled in the report>:<identifier>`; device `dev:<source_id>`,
  located at the summary's Device row. These match the synthetic case generator's expected database
  and are fixed: gold labels point at them.
- A party shown with a name only (no number, handle or email) gets an account scoped to its chat:
  `acct:<source_id>:<app>:name:<chat key>:<name>`, so two people called "Alex" in different chats
  are never collapsed. Coverage counts these.
- An account seen with more than one display name keeps the first; coverage lists the ids.
- Accounts are per source. The same phone number on two devices gives two accounts; linking them
  is an identity link an expert confirms, never the importer.

## Fidelity and coverage

Both report kinds import with `fidelity = curated_report`: an examiner chooses what goes into a
report, so a report cannot support an absence claim. Each import writes one `source_coverage` row
and the same payload as one `import` entry in the audit log, in the same transaction as the rows.
What the payload holds and how it is summarised for the expert: `docs/ingest/coverage.md`. In
short: every sheet, page or table that was not imported (with its row count), every row skipped
and why (with locators), columns Baker does not read, key columns missing, time values it could
not read with confidence (per reason, with locators), where offsets and the date order came from,
merged cells, and categories the report does not include.

For PDF: cell text is reflowed by PDF layout (line breaks may not match the original), so quotes
that span a line break may fail verbatim verification and be dropped (safe direction).

## PDF

The PDF report is read with `pdfplumber` ruled-table extraction, then mapped with the same rules
as Excel. Assumed layout: summary lines `Key: value` (or a two-column key/value table), then one
section per category with a heading (`Chats (45)`, `Call Log`, ...) above a ruled table whose first
row is the column header.

- The heading above a table picks its record kind (the same titles as Excel sheets, including
  `WhatsApp Chats (4)`). Headings for sections Baker does not import (`Timeline`, `Locations`,
  `Web History`, ...) skip their tables, since the timeline repeats messages and calls.
- A heading Baker does not know (a line set larger than the body text, or short and all bold)
  ends the current section. Its tables are **not** imported, even when their columns look like
  messages (a social media post list does), and coverage lists each one for review with its
  first row. A smaller heading inside a section (one chat's title) is a sub-heading: the section
  goes on. A heading naming the report or its summary (`Extraction Report`) starts no section.
- A table before any heading is classified by its columns, and coverage counts how often that
  happened.
- A table that continues on the next page without repeating its header is joined to the
  previous table when the column count matches.
- Cell text is reflowed by the page layout. In party cells (`From`, `To`, `Parties`), a line that
  does not start with an identifier is joined to the line above (`+1555... Dana` / `(owner)`).
  Message bodies are stored exactly as extracted, line breaks included, so a quote that spans
  a wrap may fail verbatim verification and be dropped (the safe direction). Coverage says so.
- Pages without a ruled table (for example chat-bubble layouts) are not parsed; coverage lists them.
  Text inside a message or call section that has no ruled table beside it on its page (a table
  drawn without lines, a chat-bubble page) is listed for review with its line count, never
  dropped silently.
- Cell overflow in a badly laid-out PDF can garble text; that cannot be detected from the PDF.

## Not imported yet

Locations, timeline, web history, media and other categories; examiner bookmarks and tags
beyond the Tag column; attachment hashes and MIME types; message language.

## Layout variants

`eval/synthetic/variants/` renders one small synthetic phone in 25 report layouts (20 Excel,
5 PDF): other column names and orders, split and day-first dates, offset styles, report-level
zones, ambiguous dates, extra and missing sheets, missing columns, merged cells, multi-line and
non-Latin text, attachment-only rows, junk rows, unreadable headers, duplicate columns, Excel's
cell limit, a 20,000-message sheet, hidden sheets, PDF sections per app, page breaks, unruled
tables and unknown sections. Each either imports exactly the phone's records or reports what it
did not read: `python -m eval.synthetic.variants.check -v`. tests/test_ingest_variants.py runs
the same set. These are built from public descriptions of Cellebrite reports, not from real
exports; a real report can still differ (see the plan's risk list).

## Checked against the synthetic case

The synthetic case generator (`make synth --db`) writes the rows a correct import of its two
reports should produce. This importer matches it exactly on all nine evidence tables
(sources, devices, accounts, threads, messages, recipients, attachments, calls, contacts),
except `imported_at_utc`.
The generator adopted these importer rules: `curated_report`; blank cells give NULL;
`accounts.device_id` only on the phone's own accounts; first-seen display name; no language,
MIME type or attachment hash from a report; device label from the Device field.
