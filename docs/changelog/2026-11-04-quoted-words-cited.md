## 2026-11-04: A claim that quotes a forbidden word no longer stops the report
- Changed: The report refused to write when a claim quoted a message using a word the tool
  never says ("It's been deleted."). The claim's words came back inside the tool's own
  sentences (an assumption's text, a check's search line, a verdict reason) without the cited
  mark, so the forbidden-word check read them as the tool's words and the whole report failed.
  `core/report/names.Names.html` now marks words inside double quotes as cited when they stand
  verbatim in one of the case's claims (case, curly quotes and runs of spaces not counted).
  Quoted words no claim holds stay the tool's own and are still checked. Report 0.33.0. Found
  on a validation run on a public test phone, where the report for the run was not written.
- Where: PR (branch claude/project-thread-ds0ify)
- Verified: 4 new tests in `tests/test_report_names.py`; 3 fail without the fix. The run's
  own case database renders and passes the forbidden-word check with the fix, and failed
  without it. make check (see the PR).
- Open: The app screens use the same names helper, so they gain the same marking; no screen
  test for it.
- Affects: customer-facing behavior (a report that could not be written now is)
- Status doc: no change
