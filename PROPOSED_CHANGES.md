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

## 2026-10-06 claude/synthetic-case-rlcgrj: point case01 at the generated files
File: eval/gold/case01/README.md, eval/gold/case01/case.json, eval/gold/case01/affidavit.md
Why: the generator cannot write into eval/gold/ (frozen), so its outputs live in
eval/synthetic/case01/. The README still says reports go in eval/gold/case01/sources/, and
case.json and affidavit.md are stubs.
Diff:
1. Once Arsh has reviewed them, copy the generated files over the stubs:
   cp eval/synthetic/case01/case.json eval/gold/case01/case.json
   cp eval/synthetic/case01/affidavit_draft.md eval/gold/case01/affidavit.md
2. Copy only the approved lines of eval/synthetic/case01/draft_gold.jsonl into
   eval/gold/case01/gold.jsonl, with labeled_by and labeled_at set to the approver and date.
3. In eval/gold/case01/README.md:
-| `sources/` | generator | Synthetic extraction reports to import (Cellebrite-style Excel/PDF, later UFDR) |
+| `../../synthetic/case01/` | generator | Synthetic extraction reports (`make synth` rebuilds `item1.xlsx`, `item2.xlsx`; `case.json` pins their SHA-256) |
-The eval goes through an importer: the generator emits report files in `sources/`, and the
+The eval goes through an importer: the generator emits report files in `eval/synthetic/case01/`, and the

## 2026-10-06 claude/synthetic-case-rlcgrj: say what ts_offset_min means for report-level offsets
File: core/schema.sql
Why: Cellebrite-style reports print every time with the report's display offset (item1 prints
UTC+0 for a phone set to America/New_York). Storing that as "the original UTC offset" invites
the exact timezone mistake case01 tests. The generator stores the printed offset and keeps the
phone's zone in devices.timezone; the comment should say so, so importers and checks agree.
Diff:
---   * times: ts_utc is ISO 8601 UTC ('2026-03-05T02:31:00Z'); ts_offset_min is the original
---     UTC offset in minutes (NULL if the source did not say); ts_raw is the value as it appeared.
+--   * times: ts_utc is ISO 8601 UTC ('2026-03-05T02:31:00Z'); ts_offset_min is the UTC offset
+--     printed with the value (NULL if none). For reports this can be a display setting, not the
+--     phone's zone; the phone's zone is devices.timezone. ts_raw is the value as it appeared.

## 2026-10-06 claude/govdoc-ingest-wzjw4p: keep the printed paragraph number
File: core/contracts.py, core/schema.sql
Why: `para_no` has to be unique and at least 1, so the ingester stores the paragraph's
position in the document (1, 2, 3 ...). Affidavits print their own numbers, and the title,
caption and "I, ..., being duly sworn" lines come before paragraph 1, so position and printed
number differ (printed paragraph 7 is position 10 in the synthetic affidavit). Experts cite
the printed number. Today it survives only inside the text ("7.  On March 7 ..."). A `label`
field lets the UI and report cite "para. 7" exactly as printed, while `para_no` stays a
unique ordinal. Gold labels should then say which one they mean.
Diff:
```diff
--- core/contracts.py
 class GovDocParagraph(Model):
     id: str
     govdoc_id: str
     page: int = Field(ge=1)
     para_no: int = Field(ge=1)
+    label: str | None = None  # paragraph number as printed ("7", "12(a)"); None if unnumbered
     char_start: int = Field(ge=0)
     char_end: int = Field(ge=0)
     text: str
+    ocr: bool = False  # see the next entry
--- core/schema.sql
 CREATE TABLE govdoc_paragraphs (
     id         TEXT PRIMARY KEY,
     govdoc_id  TEXT NOT NULL REFERENCES govdocs(id),
     page       INTEGER NOT NULL,
     para_no    INTEGER NOT NULL,
+    label      TEXT,
     char_start INTEGER NOT NULL,
     char_end   INTEGER NOT NULL,
-    text       TEXT NOT NULL
+    text       TEXT NOT NULL,
+    ocr        INTEGER NOT NULL DEFAULT 0 CHECK (ocr IN (0, 1))
 );
```

## 2026-10-06 claude/govdoc-ingest-wzjw4p: mark paragraphs that came from OCR
File: core/contracts.py, core/schema.sql (same diff as the entry above: the `ocr` field)
Why: OCR text is not verbatim source text (Tesseract reads "I" as "|", for example). A claim
quoted from an OCR'd page should be flagged, and a quote check against it is weaker. Today
the ingester records OCR only at document level, in `sources.tool_version`
("... ocr:tesseract-5.3.4:eng:pages=1,2"). A per-paragraph flag lets claims and the report show it.
