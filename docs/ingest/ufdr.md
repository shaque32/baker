# Cellebrite UFDR import (unverified)

Importer: `core/ingest/ufdr.py` (`UfdrImporter`, importer `ufdr` 0.1.0). It implements
`EvidenceImporter` and writes the same canonical rows as the Excel and PDF importers, through
the same record mapping in `core/ingest/cellebrite_common.py`, so retrieval, checks, rules, the
review screen and the report work unchanged.

**Format support is unverified.** Cellebrite does not publish a full UFDR specification. This
importer was built from public descriptions of the package and of `report.xml`, and tested on
synthetic packages only (`eval/synthetic/ufdr.py`). Until a real UFDR has been checked (see the
last section), every import:

- records `"format_support": "unverified"` in its coverage record;
- shows, first among the items to review, that the reader is unverified and that each record
  should be compared with Cellebrite Reader before it is relied on (`format_unverified`). The
  coverage headline starts "Unverified format." on the case screen and in `baker import`;
- adds a line to the report's Limitations saying the file was read with an unverified reader;
- imports with `fidelity = unknown`, so no absence or count finding can rest on it, whatever the
  package says about how complete it is.

## What we assumed

Everything below is an assumption to confirm against a real package.

### The package

A zip file (`.ufdr`, or `.zip` if renamed) holding one `report.xml` and the extracted files it
points to (pictures, attachments, databases). `report.xml` is the shallowest member with that
name, case-insensitive; two at the same level are refused. Nothing in the package is extracted
to disk. Encrypted members are not read.

### report.xml

```
project (xmlns http://pa.cellebrite.com/report/2.0, reportVersion, ...)
  sourceExtractions/extractionInfo (type, deviceName, IsPartialData, ...)
  sections/section/metadata/item (name) value           device and extraction details
  decodedData/modelType (type)/model (type, id, deleted_state, decoding_confidence, ...)
    field (name, type)/value                             one simple value (first value read)
    multiField (name)/value*                             several simple values
    modelField (name)/model                              one nested model (a Party)
    multiModelField (name)/model*                        nested models (Participants, Messages)
  taggedFiles/file                                        counted, not imported
```

Element names are matched without their namespace; an unfamiliar namespace is read the same
way and noted. A document type or entity declaration is refused (no external or expanding
entities are ever read). Field names are matched case-insensitively.

| Model type | Imported as | Fields read |
|---|---|---|
| `Chat` | thread + its messages (`Messages`, or any other field holding message models: none is left unread) | `Source` (app), `Id` (thread key), `Name` (title), `Participants` |
| `InstantMessage` (in a chat, or on its own) | `messages`, `message_recipients`, `attachments` | `Source`, `From`, `To`, `Body`, `TimeStamp`, `Direction`, `Folder`, `Status`, `Attachments` |
| `SMS`, `MMS` | `messages` in one thread per counterpart | `Source` (else `SMS`), `Parties` with `Role` From/To, `Folder` (Inbox, Sent), `Status`, `Body`, `TimeStamp`, `Attachments` |
| `Call` | `calls` | `Source` (else `unknown`), `Type` (Incoming, Outgoing, Missed), `Direction`, `Status`, `TimeStamp`, `Duration` (`[d.]hh:mm:ss[.fff]` or seconds; fractions dropped), `Parties` with `Role` |
| `Contact` | `contacts`, one row per entry | `Name`, `Entries` (each entry's `Value`) |
| `UserAccount` | the phone's own `accounts` | `Source`, `Username` (else the first entry), `Name` |
| `Party` | accounts | `Identifier`, `Name`, `IsPhoneOwner`, `Role` |
| `Attachment` | `attachments` | `Filename`, `ContentType` (MIME type), a path to the file in the package (`attachment_extracted_path`, `LocalPath`), a stated `SHA256` |

A message's `Type` is not read for direction (it names the content kind), nor is an MMS
`Subject`. Other field names are listed in coverage as fields Baker does not read.
Known types not imported yet (`Location`, `Email`, `WebBookmark`, ... see `NOT_IMPORTED_TYPES`)
are listed with their counts; any other type is listed for review as not recognised.

Metadata items read (by name, letters and digits only, case-insensitive):
`DeviceInfoExtractionStartDateTime` (extraction time), `DeviceInfoSelectedDeviceName` or
`DeviceInfoDetectedModel` (device, with `DeviceInfoSelectedManufacturer` in front when it is not
already there), `DeviceInfoOSVersion`, `DeviceInfoTimeZone` (stored on the device), and a
Physical Analyzer version item when present. The extraction type comes from `extractionInfo`
`type`; several different types give `unknown`. Extractions naming more than one device are
refused: Baker imports one device per file and cannot attribute the records.

### Mapping

Parties come with their own identifier, name, owner flag and role, so nothing is parsed out of a
display string. From there the rules are the Excel importer's (docs/ingest/cellebrite_report.md):
direction from a stated value first, else from the owner flag; recipients from `To`, else the
chat's participants other than the sender; an SMS thread per counterpart; a name-only party is
scoped to its chat; first display name seen is kept; the phone's own accounts come from
`UserAccount` and `IsPhoneOwner`.

Times: UFDR times are ISO 8601 with an offset (`2026-03-05T21:31:00.000-05:00`); the offset is
kept, the time stored in UTC, and the value as written kept in `ts_raw`. A time with no offset
gets no UTC time. Any other form goes through the same parser as the reports, so a day/month
order is never assumed: it is read only when the package decides it or the expert states it
(`date_order`). XML readers turn a raw carriage return into a line feed, so a body keeps a CR
only when report.xml writes it as `&#13;`.

Record states: the `deleted_state` attribute (`Intact` gives 0; `Deleted` or `Trash` gives 1;
anything else, or none, gives NULL). Every value seen is counted in coverage. Baker never says a
record was deleted; the flag records what the package stated.

A record with no time value is listed (`no_time`), as the reports' missing time column is.
A message or call whose model `id` repeats an earlier record's (the same record listed twice,
say inside a chat and on its own) is imported once; the repeat is listed for review.

Recovered records: a model marked `carved` (attribute or field) or with a `decoding_confidence`
other than `High` is imported and listed for review by locator, with a count per record type.
The canonical tables have no per-record recovery flag, so the evidence screen does not mark
these records one by one; the coverage list is where the expert finds them.

Attachments: when the attachment names a path that exists in the package, that file is SHA-256
hashed (streamed) and the hash stored. A stated hash that differs from the file is listed for
review; a path missing from the package is listed; an attachment with neither a name nor a file
is listed and not recorded. No other file in the package is read.

## Ids and locators

Ids follow the frozen scheme with the source id as file stem: `msg:`, `call:`, `contact:` ...
`#<entry>`, `att:` ... `:<n>`, `thr:<source>:<app>:<chat key>`, `acct:<source>:<app>:<identifier>`,
`dev:<source>`. Account and thread ids are identical to the Excel importer's for the same phone.

The locator is a short XML path, 1-based, counted in document order per model type across
`decodedData`: `Chat[3]/Messages[17]` is the 17th message of the 3rd Chat, which is
`(//decodedData/modelType/model[@type='Chat'])[3]/multiModelField[@name='Messages']/model[17]`
with the namespace ignored. Top-level records read `SMS[12]`, `Call[4]`, `Contact[2]`.
Metadata items are located as `metadata[<n>]`. No new locator kind was needed: the contract
already says the UFDR locator is an XML path.

## Streaming

The package is hashed in 1 MiB chunks. report.xml is read twice through expat, in chunks: first
for metadata, extractions, the phone's own accounts, per-type counts and the date order; then for
the records, which go to the database in batches of 5,000 rows inside one transaction. A chat's
messages are held until the chat closes (so a chat's own fields can come after its messages);
nothing else is held but the account and thread lists. A 263 MB report.xml with 200,000 messages
imported in about 40 seconds on the build machine; a 26 MB one peaked at about 11 MB of memory.
The package is hashed again before the transaction commits; if it changed, nothing is stored.
Both reads must count the same records of each type, or nothing is stored.

## Coverage

The payload is the reports' (docs/ingest/coverage.md) with `layout: "xml"` (record types, not
sheets), `format_support`, per-type `flag_counts`, and a `ufdr` block: the report member and its
SHA-256 and size, namespace, report version, extractions (and which say partial data), metadata
read and where, tagged files, package files and how many were hashed, model counts per type, and
the record states seen. Codes added: `format_unverified`, `carved`,
`decoding_confidence_not_high`, `attachment_file_not_in_package`, `attachment_hash_differs`,
`attachment_without_name`, `duration_unread`, `no_time`, `partial_extraction`,
`rows_skipped_same_id_as_an_earlier_record` (attention);
`several_extractions`, `unknown_namespace`, `package_files`, `tagged_files`, `record_states`,
`attachment_files_hashed`, `attachment_files_encrypted_not_hashed`, `chats_without_messages`
(info).

## Not imported yet

Tagged files and examiner tags or bookmarks (`bookmarked` stays NULL), locations, emails, web
history and the other types above, message language, files not attached to a message, and the
`source_index`/`extractionId` link from a record to its extraction.

## Before calling it verified

1. Get one real UFDR from a closed or training case (never into the repo or a prompt).
2. Import it on the expert's machine and read the coverage: every record type, field and
   metadata item Baker did not read is listed there.
3. Open 20 records of each imported type in Cellebrite Reader and compare sender, recipients,
   time and offset, text, record state and attachments with Baker's records.
4. Fix what differs, add a synthetic variant that reproduces each difference, then set
   `FORMAT_SUPPORT = "verified"` in `core/ingest/ufdr.py` in the same change and say which
   package versions were checked. Deciding whether a UFDR can count as a full extraction (and
   support absence findings) is a separate, explicit decision.
