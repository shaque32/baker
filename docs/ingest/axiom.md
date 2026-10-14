# Magnet AXIOM import (unverified)

Importer: `core/ingest/axiom.py` (`AxiomImporter`, importer `axiom` 0.1.0). It implements
`EvidenceImporter` and writes the same canonical rows as the Cellebrite importers, through the
same record mapping in `core/ingest/cellebrite_common.py`, so retrieval, checks, rules, the
review screen and the report work unchanged. `core/ingest/pick.py` chooses it for a `.xml` file
and for an `.xlsx` that carries AXIOM's marks (below); every other `.xlsx` stays a Cellebrite
report.

**Format support is unverified.** Baker has never been given a real AXIOM export. This importer
was built from public descriptions only (Magnet's documentation of the export formats, and the
open-source AXIOM XML parser casework/CASE-Implementation-AXIOM, which names the artifact types
and fragments of AXIOM XML reports) and tested on synthetic exports only
(`eval/synthetic/axiom.py`). Until a real export has been checked (last section), every import:

- records `"format_support": "unverified"` in its coverage record;
- shows, first among the items to review, that the reader is unverified and that each record
  should be compared with AXIOM Examine before it is relied on (`format_unverified`). The
  coverage headline starts "Unverified format." on the case screen and in `baker import`;
- adds a line to the report's Limitations saying the file was read with an unverified reader.

A report export holds what the examiner chose to export, so it imports with
`fidelity = curated_report`: no absence or count finding can rest on it.

## Which exports

| Export | File | Read as |
|---|---|---|
| XML report | `.xml` | `Artifact` (name) / `Hits` / `Hit` / `Fragment` (name) text |
| Excel report | `.xlsx` | a case sheet (key, value rows), then one sheet per artifact type: a header row of fragment names, one row per hit |

Not read: CSV exports (Magnet itself advises Excel over CSV for multi-line or non-English
message text), HTML and PDF reports, and the portable case (its database layout is not public).

An `.xlsx` is taken as an AXIOM export when a header in its first rows names a time with its
zone (`... Date/Time - UTC+00:00 (M/d/yyyy)`) or `Recovery method`, or a sheet is named as an
AXIOM artifact type with its platform (`Android Contacts`). Cellebrite reports carry none of
these.

An XML hit is read only in its place: `Artifact` / `Hits` / `Hit` / `Fragment`. Elements with
those names anywhere else are not read.

## What we assumed

Everything below is an assumption to confirm against a real export.

### Artifact names give the record kind and the app

The kind comes from the end of the name; the app is what is left once a platform word
(`Android`, `iOS`, `Apple`, `Windows`, or `- iOS` after a dash) is removed.

| Name ends with | Kind | App |
|---|---|---|
| `Device Information` | the phone's own details | |
| `Accounts Information`, `User Accounts`, `Accounts` | the phone's own accounts | the rest (`WhatsApp`) |
| `Call Logs`, `Calls`, `Call History` | calls | the rest, else `Phone` |
| `Contacts` | contacts | |
| `Messages`, `Chat Messages`, `Direct Messages`, `Chats` | chat messages | the rest (`WhatsApp`, `Facebook Messenger`) |
| `SMS`, `MMS`, `iMessage` anywhere (`Android SMS`, `iOS iMessage/SMS/MMS`) | SMS | `SMS` |

An SMS artifact with a thread id field is grouped into threads by it, as chats are; without
one, it gets one thread per counterpart. Known kinds Baker does not import (email, web history,
locations, media, ...: `NOT_IMPORTED_WORDS`) are listed in coverage with their counts; any other
artifact is listed for review as not recognised. Excel cuts sheet names at 31 characters
(`Android WhatsApp Accounts Infor`); such a name is matched on the start of its last word and
noted in coverage.

### Fields

Field names are matched case-insensitively, with a time field's zone and format removed. The
first name present wins; a second field for the same thing is listed in coverage.

| Kind | Fields read |
|---|---|
| chats, SMS | `Sender` + `Sender Name`; `Recipient(s)`/`Receiver` + their name fields; `Partner` + `Partner Name` (chat participants, or the SMS counterpart); `Chat ID`/`Conversation ID`/`Thread ID` (thread key); `Conversation Name` (title); `Message`/`Message Body`/`Text`; the time (below); `Direction`/`Message Direction` (SMS also `Type`); `Message Status`; `Deleted`; `Tags` (examiner tag); `Attachment(s)` (file names, one per line) |
| calls | `Partner` + `Partner Name`; `Direction`/`Call Type`; `Call Date/Time`; `Call Duration` (`hh:mm:ss`, `d.hh:mm:ss`, `mm:ss` or seconds) |
| contacts | `Display Name` (else `First Name` + `Last Name`); `Phone Number(s)`, `Email`, `User Name` (one identifier per line; a `Label:` prefix is dropped) |
| accounts | `Phone Number`/`User Name`/`Account ID`/`Email`; `WhatsApp Name`/`Display Name`/`Name` |
| device | `Device Name`/`Model`; `Manufacturer`; `OS Version`; `Time Zone` |

Every artifact may carry `Source` (the file inside the image the hit came from, never the app),
`Location`, `Evidence number`, `Item ID` and `Comments`; they are known and not read into the
record. `Recovery method` is read for flags (below). Any other field is listed in coverage as a
field Baker does not read.

A message's time comes from `Message Date/Time`, `Message Sent Date/Time`, `Sent Date/Time`,
`Message Received Date/Time`, `Received Date/Time`, `Created Date/Time` or `Date/Time`, in that
order of preference, per hit: a hit whose first field is blank takes the next filled one, read
with that field's own zone and date format. Coverage names the fields and the order.

A hit with nothing in any field Baker reads is not imported; it is listed for review
(`no_values_in_known_columns`). A device details artifact with no field Baker knows is listed as
not imported, and device fields Baker does not read are named in the coverage record.

### Times

A time field's name states its zone and date format:
`Message Sent Date/Time - UTC-05:00 (M/d/yyyy)`. The stated UTC offset is applied to values that
have none of their own (counted as times read with the offset in their column name), the value
as written is kept in `ts_raw`, and the time is stored in UTC. A zone that is not a UTC offset
(`- Eastern Standard Time`) is never applied: those times get no UTC time and are listed. A
field with no zone gives no UTC time.

Day and month order comes from, in order: the order the expert states at import
(`date_order`), the date format in the field's name (`M/d/yyyy` month first, `d/M/yyyy` or
`dd.MM.yyyy` day first), then the values that decide it. It is never assumed. Values that can
only be read the other way round from the stated order, or from the field's date format, are
counted for review, each under its own heading. The case sheet's acquisition time key may carry
a zone and format too, and they are applied the same way.

### Parties and the phone's own accounts

A sender, recipient or partner comes as an identifier field and a name field; one name goes
with one identifier, a name alone is a name-only party (scoped to its thread), and several
parties in one field are split as in the Cellebrite reports. The phone's own accounts come from
the accounts artifacts: an identifier they name for the same app is the phone's own. Direction
is the stated one first, else derived from the owner, as for Cellebrite. AXIOM call logs name
only the partner, so a call's other side (the phone itself) stays empty: incoming and missed
calls have the partner as caller, outgoing calls as callee.

### Record flags

A hit whose `Recovery method` mentions carving is imported and listed for review by locator
(`carved`); every recovery method value seen is counted in coverage. A record with no time
(`no_time`) and a call duration Baker cannot read (`duration_unread`) are listed. Baker never
says a record was deleted; a `Deleted` field, when present, is stored as stated.

## Ids and locators

Ids follow the frozen scheme with the source id as file stem: `msg:`, `call:`, `contact:` ...
`#<entry>`, `att:` ... `:<n>`, `thr:<source>:<app>:<chat key>`, `acct:<source>:<app>:<identifier>`,
`dev:<source>`. The locator is `Artifact[n]/Hit[m]` for an XML report (1-based, in document
order: the m-th hit of the n-th Artifact element) and `<sheet>!<row>` for an Excel report.

## Reading

The XML report is parsed in 1 MiB chunks through expat and hashed as it is read; only the
hits' fragment values are kept, never the document. A document type or entity declaration is
refused. The file is hashed again before the transaction commits; if it changed, nothing is
stored. The Excel report is read once into memory and hashed (as the Cellebrite Excel report).
Records are written in one transaction.

## Coverage

The payload is the reports' (docs/ingest/coverage.md), one table per artifact type, with
`format_support`, per-table `flag_counts`, `date_order_basis` `field name` when the order came
from a time field's name, and an `axiom` block: `format` (`xml` or `xlsx`), the XML root and its
child elements, hits per artifact, recovery method values seen, and where the device details and
case sheet values were read.

## Not imported yet

Examiner comments, media and files, locations, emails, web history and the other kinds above,
message language, the link from a hit to its evidence item, and the extraction time of an XML
report (no public description says where an XML report keeps case details).

## Before calling it verified

1. Get one real AXIOM export (XML and Excel report of the same case) from a closed or training
   case, with the artifacts exported in full (never into the repo or a prompt).
2. Import both on the expert's machine and read the coverage: every artifact and field Baker did
   not read is listed there.
3. Open 20 hits of each imported artifact in AXIOM Examine (or the portable case) and compare
   sender, recipients, time and offset, text, direction and attachments with Baker's records.
4. Fix what differs, add a synthetic variant that reproduces each difference, then set
   `FORMAT_SUPPORT = "verified"` in `core/ingest/axiom.py` in the same change and say which
   AXIOM versions were checked.
