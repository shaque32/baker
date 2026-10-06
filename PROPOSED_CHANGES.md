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
("... ocr:tesseract:eng:pages=1,2"). A per-paragraph flag lets claims and the report show it.
