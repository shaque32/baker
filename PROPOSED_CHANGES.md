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
