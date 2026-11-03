## 2026-11-03: Code structure cleanup: one escape helper, shared source labels, Mabillon download names
- Changed: From the code structure review (plan in the project's plans/code-structure-review.md).
  Downloads from the review screen are named `mabillon-report.html`, `mabillon-activity.csv`,
  `mabillon-request-draft.txt`, `mabillon-flag-summary.json` and
  `mabillon-bug-report-<time>.json` instead of `baker-*`. Their format ids
  (`baker-flag-summary`, `baker-bug-report/1`) are unchanged, as CLAUDE.md requires. The unused
  Instrument Serif italic face and the app's unused `--serif` token are gone (the serif
  wordmark stays). `core/pipeline.py extract_claims` had no callers (claims are proposed by
  `core/claims/propose.py`) and is removed. The report and the screen now share one `e()`
  (escape) and one `q()` (cited span) in `core/report/fmt.py`, in place of eight and five copies, and
  the screen's "Coverage" column on Set up and run reads from the report's `COVERAGE` table
  instead of its own copy. No verdict, rule, prompt, stored value or report byte changes.
- Where: branch claude/project-thread-viahfk
- Verified: `make check` green. Every app page of the paired demo case (85 pages, every claim,
  40 evidence items, report on screen and as a download) rendered before and after: the only
  differences are the italic font line, the removed token, the download names, and the
  "Coverage" words on Set up and run now in the report's sentence case. The report rendered
  by `render_report` is byte-identical, so REPORT_VERSION stays 0.30.0 and existing bundles
  still verify. Eval unchanged: case01 1.00 / 0 false supported; unreviewed 0.55; hostile PASS;
  case02 aggregate 0.90 / 0 false supported.
- Open: The report's own unused `--serif` token stays: removing it changes report bytes, which
  needs a REPORT_VERSION bump, so it waits for the next real report change.
- Affects: none (file names of downloads only; no capability, privacy, performance or claim change)
- Status doc: no change
