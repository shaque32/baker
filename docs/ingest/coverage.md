# Import coverage

Every phone report import (Cellebrite Excel, PDF or UFDR; Magnet AXIOM XML or Excel) records what it read and what it did not, so a real
report that Mabillon only partly understands is never mistaken for a complete one. The rule: the
importer either reads a record correctly or says exactly what it skipped and why. It never drops
records silently and never guesses a value it cannot read with confidence.

## Where it is stored

One `source_coverage` row per source (`core/schema.sql`; `SourceCoverage` in
`core/contracts.py`), written in the same transaction as the source's rows. The same payload is
also appended to the audit log as the `import` entry, as before. Imports made with importer
0.1.0 have only the audit-log entry; `core.ingest.coverage.load` falls back to it.

Since UFDR importer 0.3.2, Cellebrite Excel and PDF 0.3.2 and AXIOM 0.2.1 the payload also holds
`format_check` (`core/ingest/tested.py`): the format, the tool version the export states, as
written (`stated_version`, null when it states none; a UFDR's `reportVersion`), whether that is
in the tested set (`tested`), the tested set's version and the notice. The same object is
appended to the audit log as an `import.format` entry. For an import made before then,
`tested.for_source` reads the version from the UFDR's `ufdr.report_version` or the source row's
`tool_version`.

## Reading it

```python
from core.ingest.coverage import summaries, format_text

for s in summaries(conn):  # one CoverageSummary per evidence source
    s.status  # "complete" or "needs_review"
    s.headline  # "Imported all 1,061 rows read from 4 tables. Nothing needs review."
    s.attention  # items the expert must look at
    s.info  # assumptions and notes
    print(format_text(s))  # the plain-text block the CLI prints
```

Each `CoverageItem` has a `level` ("attention" or "info"), a stable `code`, `parts` and
`locators` (where to look, such as `Chats!14` or `p3:t1:r4`, capped at 50). `parts` is a list of
`(text, quoted)` segments: quoted segments are text taken from the report (sheet, column and
heading names, raw values, the report's time zone setting); the others are Mabillon's own words.
**Renderers pass quoted segments through their quote helper** (`q()` in the report and the
screen), so the forbidden-word check never mistakes an examiner's sheet name, such as
"Deleted Messages", for Mabillon's words. `item.plain` joins the segments for plain text.

**Record state** is what the extraction says about a record's status on the phone: whether
the tool marks it deleted or intact (for a UFDR, the `deleted_state` attribute; for a
Cellebrite or AXIOM report, its Deleted or Record Status column). Coverage lines say "record
state" because the report's word check keeps "deleted" out of Mabillon's own words; the
package's own values (such as `Deleted` or `Intact`) are printed as cited text. Mabillon stores
the state as the package gives it and never says itself that a record was deleted.

`needs_review` means at least one attention item: records may be missing, or values were left
unread. It is not an error; the import still holds everything it could read.

## Attention codes

| Code | Meaning |
|---|---|
| `not_imported` | A sheet, page or table was not imported: sheet not recognised, no recognised header row, columns do not fit the sheet's kind, a heading Mabillon does not recognise, or text with no ruled table (PDF). Row or line count and first row given |
| `missing_time`, `missing_body`, `missing_from`, `missing_name` | A table has no column for that field |
| `rows_skipped_no_values_in_known_columns` | Rows with values only in columns Mabillon does not read (footers, sub-headings, a row number alone) |
| `rows_skipped_header_like_row` | Rows holding only column names that could not be joined to the header |
| `rows_skipped_account_without_identifier` | Account rows with no username or identifier |
| `times_ambiguous_day_month` | Dates like 3/4/2026 with nothing in the report deciding the order; re-import with the order stated |
| `times_no_offset` | Times with no offset in the value, the column name or the report settings |
| `times_named_zone` | Times that name a zone (`EST`) instead of an offset; never applied |
| `times_unparsed`, `times_date_only`, `times_two_digit_year`, `times_numeric` | Values that are not a readable point in time |
| `duplicate_column` | A second column for a time, text, party or duration field; only the first was read |
| `merged_cells_not_filled` | Merged cells down text, time, attachment or flag columns; only the first row has the value |
| `body_at_excel_cell_limit` | Text exactly 32,767 characters long, Excel's cell limit; it may be cut off |
| `calls_with_extra_parties_dropped`, `messages_with_multiple_senders_first_kept`, `calls_party_unattributed`, `values_contradicting_stated_date_order` | Information a row held that the canonical record cannot carry |

Info codes include `category_not_imported` (Timeline, Locations and other categories Mabillon does
not import), `categories_not_found` (the report has no section for chats, SMS, calls, contacts
or accounts; that means only that the report does not include them), `unknown_columns`,
`header_offset`, `header_zone_name`, `date_order`, `date_order_stated`, `merged_cells_filled`,
`header_note`, `app_from_title`, `hidden_sheets`, `no_summary`, `report_time_zone_not_fixed`,
`accounts_with_multiple_display_names`, `no_body_or_attachment` and the PDF layout notes.

## Payload (importer 0.2.0)

Keys kept from 0.1.0: `importer`, `importer_version`, `source_id`, `sha256`, `file_name`,
`fidelity`, `fidelity_reason`, `report_time_zone_raw`, `report_offset_min_applied`, `tables`,
`not_imported`, `counts`, `unmapped_direction_values`, `notes`.

New in 0.2.0:
- top level: `report_date_order`, `date_order_stated_at_import`, `summary_found`,
  `hidden_sheets`, `accounts_with_multiple_display_names`, `categories_read`,
  `categories_not_found`;
- each `not_imported` entry: `rows` (non-empty rows, header included) or `lines` (PDF text),
  `columns` (its first row, up to 12 cells cut to 40 characters), `section` (PDF heading);
- each table: `skipped_locators`, `duplicate_columns` (`column`, `field`, `used`),
  `missing_key_fields`, `header_offsets`, `header_zone_names`, `date_order_basis` (`this table`,
  `other tables in the report`, `stated at import`, `field name` (AXIOM), `none`), `time_problems` and
  `time_problem_locators`, `app_from_title`, `merged_cells_filled`,
  `merged_columns_not_filled`, `header_notes`, `flagged_locators`.

Invariant, checked by tests/test_ingest_variants.py on every variant: for each table,
`rows_read == rows_imported + sum(rows_skipped)`, and every data row written to a sheet is
either imported, skipped with a reason, or inside a sheet listed in `not_imported` with its count.

UFDR imports add their own codes and a `ufdr` block to the payload, and list record types
instead of sheets: docs/ingest/ufdr.md. AXIOM imports list one table per artifact type and add an
`axiom` block: docs/ingest/axiom.md.

## Where it is shown

- `mabillon import` prints `format_text` after each import and takes `--date-order mdy|dmy`.
- The case screen's Files table shows each report's headline and its attention items, and the
  report upload form offers the date order (left to Mabillon by default).
- The report lists, under Limitations, every source whose status is `needs_review`, with its
  attention items.

All three render items with `coverage.render(item, q, e)`, so text from the report is quoted.
A file already in a case cannot be imported into it again, so to state the order for a report
that came back with `times_ambiguous_day_month`, import it into a new case (or a new case
database on the command line). `python -m eval.synthetic.variants.check -v` shows what each
variant's summary says.
