# Proposed changes to frozen files

Agents write here instead of editing `core/contracts.py`, `core/schema.sql`,
`core/audit/rules.py`, prompts or gold data. A human reviews each entry and applies it on `main`.

Format for each entry:

```
## <date> <branch>: <one-line summary>
File: <frozen file>
Why: <what you could not do without it>
Diff:
<exact change>
```



## 2026-10-06 claude/cellebrite-report-ingest-xw3itp: a table for import coverage
File: core/schema.sql
Why: Cellebrite reports are lossy (no deleted column, no time zone, examiner-filtered), and the
absence check and selection audit need to read what an import covered. With no table for it, the
importer writes the coverage record as an `import` entry in `audit_log` (payload_json). That works
and is tamper-evident, but other modules then have to parse audit-log payloads to find coverage.
Diff:
```
+CREATE TABLE source_coverage (
+    source_id     TEXT PRIMARY KEY REFERENCES sources(id),
+    importer      TEXT NOT NULL,     -- 'cellebrite_excel', 'cellebrite_pdf', ...
+    importer_version TEXT NOT NULL,
+    payload_json  TEXT NOT NULL      -- tables read, rows skipped, unknown columns, time-zone
+                                    -- handling, deleted-flag coverage, notes
+);
```

## 2026-10-06 claude/cellebrite-report-ingest-xw3itp: keep the party text as the report showed it
File: core/schema.sql
Why: reports show each sender and recipient as text like `+15550000002 Alex`. The importer keeps
the identifier on the account and the first display name seen, so a display name that changes
over time (the handle_change trap) is only visible in the coverage note, not per message.
Keeping the raw text lets the identity check cite exactly what the report showed for each message.
Also add `sender_raw: str | None = None` to `Message` in core/contracts.py.
Diff:
```
 CREATE TABLE messages (
     ...
     sender_account_id TEXT REFERENCES accounts(id),
+    sender_raw      TEXT,            -- sender cell text as it appeared in the source
     ...
 CREATE TABLE message_recipients (
     message_id TEXT NOT NULL REFERENCES messages(id),
     account_id TEXT NOT NULL REFERENCES accounts(id),
+    raw        TEXT,                 -- recipient text as it appeared in the source
     PRIMARY KEY (message_id, account_id)
 );
```
