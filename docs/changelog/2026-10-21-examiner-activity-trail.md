## 2026-10-21: examiner activity trail, every page view in the audit log (#111)
- Changed: each case page the examiner opens on the review screen is written to the case's
  hash-chained audit log as action `view` (core/review/activity.py, hook in ui/app.py): time
  (UTC), examiner name (or "viewer:unnamed" before a name is entered), screen session, page, the
  claim or evidence item, the evidence ids the page linked to, and for an evidence item its
  record id, source id and locator (never record text). New Activity tab (`/activity`, per claim
  and step by step, with time on page), `/activity.csv` (with each entry's hash) and
  `baker activity --db case.db [--claim C01] [--csv out.csv]`. The report (0.11.0) gains an
  "Examiner activity" section; its per-claim table (time on page) is opt-in per case and off by
  default (Arsh, 2026-10-21): the expert switches it on the Activity tab or with
  `baker activity --in-report on|off --by expert:<name>`, each change is an audit-log entry
  (`report.activity`), and when off the report says the table is not included. Page views stay
  out of the report's expert-actions table and counts; the Audit log page hides views unless `/log?views=1`. Why: Yazen (forensic expert
  advisor, via Arsh 2026-10-21) wants a trackable, timed record of what the examiner opened and
  looked at, to answer a "rubber-stamped" challenge. No schema, rules, prompt or contract change.
- Where: PR #111 (branch claude/project-thread-1wfsnn)
- Verified: tests/test_activity.py (33 tests: logging, evidence location, refresh collapse, time
  on page and the 30-minute away mark, new session, unnamed viewer, verdicts unchanged, report
  section, Activity page, CSV hashes and formula guard, tampered view breaks the chain, a view
  that cannot be written is reported, cross-site requests and posts leave the trail alone, CLI,
  the report switch off by default, logged with the expert's name, from the screen and the CLI).
  Existing tests changed because the screen now writes page views or has one more tab:
  tests/test_chain_on_open.py takes the newest anchored entry before opening the log page;
  tests/test_report_consistency.py now checks the screen adds only `view` entries and the
  report adds none; tests/test_demo.py counts the tabs from `TAB_GROUPS`. Speed (Linux cloud
  container, 2026-10-21): with 20,000 view entries, the per-page log check took 0.17 s and
  reading the trail 0.32 s. make check passed (2353 tests; case01 gate 1.00, 0 false
  supported; eval unchanged).
- Open: time on page is time to the next page or action, not reading (no scripts); two screens
  on one case at once would interleave and shorten it. Views after the newest anchor can be cut
  undetected, like any entry (docs/review-screen.md). The reproducibility bundle (#104) carries
  views as plain audit-log entries until a follow-up adds an opt-in "activity" part. CLI commands
  are not logged as views. Unverified with a real examiner.
- Affects: capabilities (activity trail, report section); privacy (new data kept: page views,
  local only, in the case database, encrypted with an encrypted case, never sent);
  customer-facing claims (Baker can show which claims and records the examiner opened, and when;
  not that they were read)
- Status doc: pending: §2 row 13 (Review): add "each page the examiner opens is logged as a page
  view; Activity tab, CSV and `baker activity` (core/review/activity.py)"; §8 item 3: add the
  Activity tab and the report's Examiner activity section (its table opt-in per case, off by
  default); header: report version 0.11.0;
  §12 row 5: add "page views (time, examiner, page, items) are in the same hash-chained log;
  time on page is not proof of reading".
