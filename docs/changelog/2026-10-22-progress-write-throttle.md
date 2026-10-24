## 2026-10-22: Pipeline progress count saved at most every 0.5 s; Windows CI timings (#122)
- Changed: product code, `core/pipeline.py` (`_Progress.labeled`, new `PROGRESS_EVERY_S = 0.5`).
  The run screen's labeled count (`run_claims.candidates_labeled`) was saved and committed once
  per labeled item; it is now saved at most every 0.5 s, and always for a claim's last label and
  in the claim's `done` row. Why: with a fast labeler (model-free, rules-only, tests) those
  commits cost more than the labels, and on Windows they pushed main's CI past its 30-minute
  limit. Only how often the screen's progress count is saved changes: verdicts, evidence items,
  checks, the audit log and each claim's final progress row are written as before. Also CI
  only: `make check` runs as lint, test and eval steps with the 40 slowest tests listed, and the
  Windows job limit is 45 minutes.
- Where: PR #122
- Verified: `tests/test_pipeline.py::test_progress_throttle_changes_only_how_often_the_screen_count_is_saved`
  runs the fake audit with no throttle and with a one-hour throttle and finds identical
  decisions, predictions, evidence rows and final progress rows, with only each claim's last
  label saved when throttled. case01 model-free run: 1,076 commits down to 110 (Linux cloud
  container, 2026-10-22). Windows CI job 19 min 20 s down to 16 min 46 s; encrypted audit test
  139.6 s down to 54.4 s (GitHub windows-latest runners, 2026-10-22). Eval gate unchanged.
- Open: Windows per-commit cost (about 18 ms plain, 50 ms encrypted) is estimated from test
  timings, not measured directly. Windows run times vary up to 2x on the same tree.
- Affects: performance (fewer commits during an audit; the screen's labeled count can lag by up
  to 0.5 s while a claim is labeled)
- Status doc: no change
