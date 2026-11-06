## 2026-11-04: Quoted words are cited only as whole words and only for their own claim
- Changed: Report 0.33.0 marked words inside double quotes as cited when they stood anywhere in
  any of the case's claims. That was wider than it needs to be: a quote could match inside a
  longer word, and one claim's quote could excuse the same words in another claim's lines.
  `core/report/names.Names` now cites quoted words only as whole words, and `Names.for_claim`
  scopes the lines that belong to one claim (its assumptions, check lines and verdict reasons)
  to that claim's own text. The report and the app's claim page use it. The claim page's
  Technical details (the stored reasons) and Rules' working tables (assumption text, what was
  searched, check detail) now mark the claim's quoted words as cited too, with ids left as
  written (`Names.cite`), so the page is no longer withheld for such a claim. Report 0.34.0.
- Where: branch claude/project-thread-ds0ify
- Verified: 2 new tests in `tests/test_report_names.py` (whole words; own claim only). New
  `tests/test_cited_quotes_page.py` renders the report and GETs the claim page for a synthetic
  case01 claim that quotes "ok. it was deleted"; it fails without the fix, and fails again if
  either the assumption table or the search line goes back to plain escaping. make check (see
  the PR). `tests/test_demo.py` now reads the stored reasons with the cited marks stripped.
- Open: Other screens that show assumption text (review list) still cite against all of the
  case's claims, not only their own.
- Affects: customer-facing behavior (a claim page that was withheld now shows)
- Status doc: no change
