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
| `Summary`, `Extraction Summary`, `Case Information` | `sources` metadata, `devices` row |
| `Chats`, `Instant Messages` | `threads`, `messages`, `message_recipients`, `attachments` |
| `SMS Messages`, `SMS`, `MMS Messages` | `threads` (one per counterpart), `messages` |
| `Call Log`, `Calls` | `calls` |
| `Contacts` | `contacts` |
| `User Accounts`, `Accounts` | `accounts` (device-owner accounts) |
| anything else (`Locations`, `Timeline`, `Web History`, ...) | not imported; listed in coverage. An unrecognised sheet is never classified by its columns, because `Timeline` repeats messages and calls |

Data sheets: one or more title or filter rows may sit above the header row. The header row is the
first row (within the first 10) where at least two cells match known column names for that sheet.
Every row below it is one record. A row whose cells are all empty is skipped and counted.

Summary sheet: key-value pairs, key in column A, value in column B. Keys read (aliases accepted):
`Extraction start date/time`, `Extraction type`, `Device` / `Model`, `OS version`,
`UFED Physical Analyzer version` / `Report version` / `Tool version`, `Tool`,
`Report time zone` / `Time zone` (applied to times only if a fixed offset), `Device time zone`
(stored on the device). `Extraction end` is accepted for the extraction time.

### Columns

| Field | Accepted headers |
|---|---|
| chat id | `Chat #`, `Chat ID`, `Identifier`, `Thread` |
| chat name | `Name`, `Chat Name`, `Description` (Chats only) |
| app | `Source`, `Application`, `App`, `Service` |
| from | `From`, `Sender` |
| to | `To`, `Recipients`, `Participants` (To only if `To` is absent: means all participants other than the sender) |
| body | `Body`, `Message`, `Text`, `Content` |
| time | `Timestamp`, `Timestamp: Time` alone (full value), `Timestamp: Date` + `Timestamp: Time`, `Time`, `Date`, `Date/Time` |
| direction | `Direction`, `Type`, `Folder`, `Status` (values `Incoming`, `Outgoing`, `Sent`, `Received`, `Inbox`, `Missed`, `Read`, `Unread`) |
| deleted | `Deleted`, `Deleted - Instant Message`, `Deleted - Chat`, `Deleted - Call`, `Record status` |
| attachment | `Attachment #1`..`Attachment #N`, `Attachments` |
| examiner tag | `Tag`, `Tags`, `Bookmark` (any text sets `bookmarked = 1`; blank stays NULL) |
| duration (calls) | `Duration` (`HH:MM:SS`, `MM:SS` or seconds) |
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

Accepted: `M/D/YYYY h:mm:ss AM(UTC-5)`, `DD/MM/YYYY HH:MM:SS(UTC+3)`, ISO 8601 with offset,
an Excel date cell, and split date + time columns. The importer handles them as follows:
- An explicit `(UTC±H[:MM])` suffix or ISO offset: offset kept, time converted to UTC.
- No offset in the value: the report-level `Time zone` from the Summary sheet is used if it is a
  fixed `UTC±H[:MM]` offset, and coverage records that offsets came from report settings.
- Neither: `ts_utc` and `ts_offset_min` are NULL, `ts_raw` keeps the value. The importer never guesses a zone.
- Ambiguous day/month order (both 12 or below with no other row disambiguating): the sheet's
  order is chosen once from the rows that disambiguate; if none do, US order (M/D) is assumed and
  coverage records it.
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
  `contact:<source_id>:<locator>:<entry n>`; attachments `att:<source_id>:<locator>:<n>`;
  threads `thread:<source_id>:<locator of the chat's first row>`; accounts
  `acct:<source_id>:<app as spelled in the report>:<identifier>`; device `device:<source_id>`,
  located at the summary's Device row. These match the synthetic case generator's expected database.
- A party shown with a name only (no number, handle or email) gets an account scoped to its chat:
  `acct:<source_id>:<app>:name:<chat key>:<name>`, so two people called "Alex" in different chats
  are never collapsed. Coverage counts these.
- An account seen with more than one display name keeps the first; coverage lists the ids.
- Accounts are per source. The same phone number on two devices gives two accounts; linking them
  is an identity link an expert confirms, never the importer.

## Fidelity and coverage

Both report kinds import with `fidelity = curated_report`: an examiner chooses what goes into a
report, so a report cannot support an absence claim. Each import appends one `import` entry to the
audit log with a coverage payload:

- sheets/pages read, sheets not imported, unknown columns per sheet;
- row counts per table, rows skipped and why;
- whether the deleted column was present, and how many rows had no time zone;
- which date order was assumed; whether offsets came from report settings;
- for PDF: that cell text is reflowed by PDF layout (line breaks may not match the original), so
  quotes that span a line break may fail verbatim verification and be dropped (safe direction).

## PDF

The PDF report is read with `pdfplumber` ruled-table extraction, then mapped with the same rules
as Excel. Assumed layout: summary lines `Key: value` (or a two-column key/value table), then one
section per category with a heading (`Chats (45)`, `Call Log`, ...) above a ruled table whose first
row is the column header.

- The heading above a table picks its record kind. Headings for sections Baker does not import
  (`Timeline`, `Locations`, `Web History`, ...) skip their tables, since the timeline repeats
  messages and calls. A table under no recognised heading is classified by its columns, and
  coverage counts how often that happened.
- A table that continues on the next page without repeating its header is joined to the
  previous table when the column count matches.
- Cell text is reflowed by the page layout. In party cells (`From`, `To`, `Parties`), a line that
  does not start with an identifier is joined to the line above (`+1555... Dana` / `(owner)`).
  Message bodies are stored exactly as extracted, line breaks included, so a quote that spans
  a wrap may fail verbatim verification and be dropped (the safe direction). Coverage says so.
- Pages without a ruled table (for example chat-bubble layouts) are not parsed; coverage lists them.
- Cell overflow in a badly laid-out PDF can garble text; that cannot be detected from the PDF.

## Not imported yet

Locations, timeline, web history, media and other categories; examiner bookmarks and tags
beyond the Tag column; attachment hashes and MIME types; message language.

## Checked against the synthetic case

The synthetic case generator (`make synth --db`) writes the rows a correct import of its two
reports should produce. This importer matches it row for row on all nine evidence tables
(sources, devices, accounts, threads, messages, recipients, attachments, calls, contacts),
apart from `sources.tool_name` and `tool_version`, which record what the report's Summary says.
The generator adopted these importer rules: `curated_report`; blank cells give NULL;
`accounts.device_id` only on the phone's own accounts; first-seen display name; no language,
MIME type or attachment hash from a report; device label from the Device field.
