## 2026-10-26: Report no longer refuses packages with related copies (#PR)
- Changed: Two import-coverage lines for UFDR related copies (Cellebrite RelatedModels) said
  "deleted state". The report's word check (tool text never says deleted) then refused the
  whole report, and the case screen's page, for any package with related copies, which public
  Cellebrite Reader 7.48 packages have. The validation-v1 run on the public iOS 15 phone
  stopped there twice, after its audit had finished. The lines now say "record state", as the
  record-states line already did; the ufdr-check worksheet's wording matches. The validation
  run driver (eval/validation/hickman_run.py) now keeps the audit's results when the report is
  refused: run.json and progress.log say why and results.zip goes out without report.html.
- Where: PR #PR
- Verified: tests/test_coverage_display.py: every coverage wording passes the word check, and a
  synthetic package with related copies (one matching no record) renders a report that passes
  it; both tests fail on the old wording. tests/test_validation_run.py: a refused report leaves
  case.db, run.json and progress.log in results.zip. make check passes.
- Open: The report's word check also applies to a model's stance rationale; a local model that
  writes "deleted" despite the prompt's instruction would still stop the report. Not seen on
  the synthetic cases; unverified on real exports.
- Affects: capabilities (reports on real UFDRs with related copies)
- Status doc: no change
