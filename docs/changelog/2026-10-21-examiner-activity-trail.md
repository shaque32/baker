## 2026-10-21: examiner activity trail, every page view in the audit log (#111)
- Changed: each case page the examiner opens on the review screen is written to the case's
  hash-chained audit log as action `view` (core/review/activity.py, hook in ui/app.py): time
  (UTC), examiner name (or "viewer:unnamed" before a name is entered), screen session, page, the
  claim or evidence item, the evidence ids the page linked to, and for an evidence item its
  record id, source id and locator (never record text). New Activity tab (`/activity`, per claim
  and step by step, with time on page), `/activity.csv` (with each entry's hash) and
  `baker activity --db case.db [--claim C01] [--csv out.csv]`. The report (0.12.0, after #104's 0.11.0) gains an
  "Examiner activity" section; its per-claim table (time on page) is opt-in per case and off by
  default (Arsh, 2026-10-21): the expert switches it on the Activity tab or with
  `baker activity --in-report on|off --by expert:<name>`, each change is an audit-log entry
  (`report.activity`), and when off the report says the table is not included. Page views stay
  out of the report's expert-actions table and counts; the Audit log page hides views unless
  `/log?views=1`. A view keeps only the address fields its page reads (the item id, and
  switches such as a claim filter); other fields are counted, not stored. Time on page runs to
  the next page opened on the same screen. Why: Yazen (forensic expert advisor, via Arsh
  2026-10-21) wants a trackable, timed record of what the examiner opened and looked at, to
  answer a "rubber-stamped" challenge. No schema, rules, prompt or contract change.
- Where: main (#111, merged 2026-10-22)
- Verified: tests/test_activity.py (34 tests: logging, evidence location, refresh collapse, time
  on page and the 30-minute away mark, new session, unnamed viewer, verdicts unchanged, report
  section, Activity page, CSV hashes and formula guard, tampered view breaks the chain, a view
  that cannot be written is reported, cross-site requests and posts leave the trail alone, CLI,
  the report switch off by default, logged with the expert's name, from the screen and the CLI).
  Existing tests changed because the screen now writes page views or has one more tab:
  tests/test_chain_on_open.py takes the newest anchored entry before opening the log page;
  tests/test_report_consistency.py now checks the screen adds only `view` entries and the
  report adds none; tests/test_demo.py counts the tabs from `TAB_GROUPS`. Speed (Linux cloud
  container, 2026-10-21): with 20,000 view entries, the per-page log check took 0.17 s and
  reading the trail 0.32 s. make check passed (2479 tests; case01 gate 1.00, 0 false
  supported; eval unchanged).
  The reproducibility bundle (#104) gains an opt-in "activity" part: a view names the evidence
  items and records its page listed, so a scoped bundle keeps only each view's hash in
  withheld.jsonl unless the examiner includes the part (`--include activity`), and its report
  says the page views were left out (tests/test_bundle.py
  `test_page_views_ship_only_in_the_activity_part`).
- Open: time on page is time to the next page opened on the same screen, not reading (no
  scripts); two screens on one case at once each time only their own pages. Views after the
  newest anchor can be cut undetected, like any entry (docs/review-screen.md). CLI commands are
  not logged as views. Unverified with a real examiner.
- Affects: capabilities (activity trail, report section); privacy (new data kept: page views,
  local only, in the case database, encrypted with an encrypted case, never sent);
  customer-facing claims (Baker can show which claims and records the examiner opened, and when;
  not that they were read)
- Status doc: applied 2026-10-27
