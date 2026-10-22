# UFDR self-check

`baker ufdr-check` tells an expert, on their own computer and offline, whether Baker read a real
UFDR the way the package's own `report.xml` says it should be read. It is how Baker's UFDR reader
(docs/ingest/ufdr.md, still **unverified**) gets checked against real packages without anyone
sending a case file anywhere.

```
baker ufdr-check --package "D:\Exports\item1.ufdr" --out "D:\Exports\item1-check"
```

On Windows run it from the "Baker command prompt" in the Start menu; on a Mac, from Terminal
(`~/Baker/app/.venv/bin/baker`). `--out` must be a new or empty folder. `--sample` sets how many
records of each kind go in the private sample (default 20). Nothing is added to any case.

## What it does

1. Reads `report.xml` with its own small reader (`Tally` in `core/ingest/ufdr_check.py`), which
   shares only the XML safety rules and the locator rule with the importer, not its record
   mapping. It counts every model kind, field, attribute and value type, and for every record
   Baker should import it notes the body (as a hash), the time as written, the stated sender and
   recipients, the record state, the attachments, the call duration and the contact entries.
2. Imports the package with Baker's importer into a throwaway database in memory.
3. Compares the two by locator (`Chat[3]/Messages[17]`):
   - **records**: messages (in chats, on their own, SMS and MMS), calls, contacts, the phone's
     own accounts and attachments, with what is missing from Baker, what Baker has that the XML
     does not, and records repeated under the same model id (imported once, on purpose);
   - **fields, record by record**: message text exactly as written; the time as written; the UTC
     time, worked out separately from the importer for every ISO 8601 time with an offset;
     sender; recipients; direction (when the package states it, or the owner sent or received
     it); deleted state; number of attachments and attachment files hashed; call caller,
     callee, direction and duration; contact entries and name; the identifier of each of the
     phone's own accounts.
   A check that cannot be made for a record (no stated sender, a time without an offset) is
   counted as "not checked", never as a match.
   Models under a `RelatedModels` element (copies of other records, as Reader 7.48 writes them)
   are never counted as the holder's messages, attachments or parties. Each copied message must
   say what the message holding it says (app, text, time, Direction, Folder and Status, each
   party with its side and IsPhoneOwner, deleted state, attachments by count and name, a
   Forwarded label, its recovery marks (carved, decoding confidence not High), and any embedded
   message at every level, as written; a copy of an embedded message is matched to it), and a copied chat's messages are matched one to one to the holder chat's messages
   Baker imported, or imported once under an earlier id, when the two chats also say the same
   around their messages (app, id, name and participants); one that does not match must be one Baker lists
   for review (`related_copy_unmatched`), else it is missing (row "message copies under
   RelatedModels"). A copy Baker lists that matches here is a difference too (`extra`); only
   past the importer's capped list of locators does its count stand in. Copies are counted per type
   (`copies_under_related_models`). A second account with the same app and identifier is one
   account in Baker and counts as a repeat, not as missing. Direction is expected from the
   phone's own accounts by identifier only, as the importer links them.

A test plants a wrong value in each field after import and shows the check catches it
(tests/test_ufdr_check.py).

## What it writes

| File | Holds | Send it? |
|---|---|---|
| `ufdr-check.md` | Counts, check results, record locators, field and model names, value shapes (`9999-99-99T99:99:99.999-99:99`), Baker's coverage counts, and blanks for what Cellebrite Reader shows | Yes, after reading it |
| `ufdr-check.json` | The same, for a program | Yes |
| `ufdr-check-private.md` | A fixed-seed sample of records with what Baker read for each (sender, recipients, time, text, attachments), to compare in Cellebrite Reader | **No. Case content. Stays on the computer.** |

The shareable files hold no message text, names, phone numbers, identifiers, file names, hashes,
device details, case numbers or paths. Values of fixed-vocabulary fields (Direction, Type,
Status, Folder, Role, Source) appear only when every word is in a fixed list of Cellebrite terms;
anything else appears as its shape (`Aaaaa`). Schema names that do not look like names appear as
shapes too. A test fills every value of a package with a marker string and checks that neither the
marker nor the identifiers' digits reach the shareable files.

If Baker refuses the package (two devices, malformed XML, ...), the check still describes it; the
shareable files give the kind of refusal, the private file the full message.

## Size

A synthetic 118 MB `report.xml` with 100,000 messages took about 40 seconds and under 300 MB of
memory on the build machine. The imported records are held in memory and dropped at the end.

## After a real package has been checked

1. The expert fills in the Reader table in `ufdr-check.md` and sends it with the JSON.
2. Each difference becomes a synthetic variant in `eval/synthetic/ufdr.py` or the tests that
   reproduces it, and the importer is fixed.
3. Once real packages from the versions in the report check clean, and the Reader comparison
   matches, `FORMAT_SUPPORT` can become `"verified"` (docs/ingest/ufdr.md, last section).
