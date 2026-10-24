## 2026-10-24: Read Physical Analyzer SMS Excel times; flag rows listed twice (#129)
- Changed: Physical Analyzer's per-category SMS Excel export writes `Date` as an Excel serial
  number and `Time` as the full value ("2/14/2020 1:09:03 PM(UTC+0)"). The importer joined the
  two and read no time for any row. When `Time` holds a whole date and time it is now read alone,
  and `Date` must name the same local date (Excel cell, serial number or text); otherwise no time
  is set (`date_column_disagrees`). Rows the tool numbers as copies ("3(1)" after "3", often the
  same database seen through a rooted phone's mirror path) stay separate records and are listed
  in coverage as `numbered_as_copy`, so counts are not trusted blindly. Cellebrite Excel/PDF
  importer version 0.2.0 -> 0.3.0.
- Where: PR #129
- Verified: synthetic tests with the export's layout (tests/test_cellebrite_excel.py). One
  real-format Cellebrite SMS export from a Pixel 3 test phone (believed to be a public test
  image; not committed, not sent anywhere), run locally on 2026-10-24: 52 of 52
  times read (0 before), each within 1 s of its Excel serial value; 26 of 52 rows flagged as
  copies. `make check` numbers in the PR.
- Open: only one real export tested. A workbook in Excel's 1904 date system fails the date
  check and gets no time (safe, not read). Copy rows are flagged, not merged.
- Affects: capabilities (real-format import)
- Status doc: pending: section 8 item 1, after "Cellebrite Excel and PDF", add "(Physical
  Analyzer per-category SMS export read on one real-format sample; rows the tool lists twice are
  flagged, not merged)".
