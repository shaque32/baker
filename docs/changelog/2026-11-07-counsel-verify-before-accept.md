## 2026-11-07: counsel must open an item's record before accepting it (#PR)
- Changed: lawyer-checker plan (`/mnt/project-files/baker/plans/lawyer-checker-and-examiner-pilot.md`)
  PR 3, first part. `core/review/actions.py` `require_record_opened` is now the one default entry
  in `COUNSEL_CHECKS`. `decide_counsel()` refuses `counsel_accepted` unless the audit log holds a
  `view` of that item's Evidence item page (`/evidence?id=<item>`) by the same `counsel:<name>`
  actor. A view by another lawyer, by an expert of the same name, before a name was entered, of a
  different item, or of a page that only lists the item does not count. A refusal stores and logs
  nothing. Taking an acceptance back needs no view. Why: counsel is not an expert, so their
  acceptance should rest on having looked at the record; this puts ABA Formal Op. 512's duty to
  verify a tool's output into the workflow and on the hash-chained record. No signed file changes.
- Where: PR #PR (stacked on #238; merge after it)
- Verified: `tests/test_counsel_verify_before_accept.py` (10 tests) and the updated
  `tests/test_counsel_review.py` (its helpers now open each record before accepting) on synthetic
  case01. `make check` results are in the PR description. `make eval` writes no counsel review, so
  its numbers are expected unchanged.
- Open: a view proves the page was opened, never that it was read (the screen runs no scripts).
  The app still records views as `expert:<name>` and offers no counsel entry point; the reviewer
  role at case setup (#238's follow-up, plan PR 4 of confirm-rule-b-c.md) must record a counsel's
  views as `counsel:<name>`, or every counsel acceptance from the screen is refused. Per-claim
  guidance and expert-needed flags are the next PR.
- Affects: capabilities (counsel acceptance now needs an opened record; not yet reachable from the
  app)
- Status doc: pending: in the paragraph on counsel decisions added by #238's entry, add: "Counsel
  can accept an item only after opening its Evidence item page under their own name; the view is
  in the audit log and shows the page was opened, not that it was read."
