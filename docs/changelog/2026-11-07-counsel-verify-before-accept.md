## 2026-11-07: counsel opens the record before accepting; plain guidance on every claim (#239)
- Changed: lawyer-checker plan (`/mnt/project-files/baker/plans/lawyer-checker-and-examiner-pilot.md`)
  PR 3. `core/review/actions.py` `require_record_opened` is now the one default entry
  in `COUNSEL_CHECKS`. `decide_counsel()` refuses `counsel_accepted` unless the audit log holds a
  `view` of that item's Evidence item page (`/evidence?id=<item>`) by the same `counsel:<name>`
  actor. A view by another lawyer, by an expert of the same name, before a name was entered, of a
  different item, or of a page that only lists the item does not count. A refusal stores and logs
  nothing. Taking an acceptance back needs no view. Why: counsel is not an expert, so their
  acceptance should rest on having looked at the record; this puts ABA Formal Op. 512's duty to
  verify a tool's output into the workflow and on the hash-chained record. No signed file changes.
  - Plain guidance (`core/review/guidance.py`, report 0.39.0): every claim, on the claim page
    and in the report in the same block, says what its verdict means, what it does not mean, and
    what needs an expert before anyone relies on it in court. Expert-needed lines: phone ownership
    proposed but not confirmed by an expert (the same test as rules.py), and identity, role,
    content-meaning, absence and event claims (left out once an expert confirmed or overrode the
    verdict). Unproven always says "not found never means it did not happen". Read-only: it never
    changes a verdict, a label or the review queue. Why: a lawyer without an expert needs to know
    what each verdict can and cannot carry.
- Where: PR #239 (stacked on #238; merge after it)
- Verified: `tests/test_counsel_verify_before_accept.py` (10 tests), `tests/test_guidance.py` (8)
  and the updated `tests/test_counsel_review.py` (its helpers now open each record before
  accepting) on synthetic case01. `make check` results are in the PR description. `make eval` writes no counsel review, so
  its numbers are expected unchanged.
- Open: a view proves the page was opened, never that it was read (the screen runs no scripts).
  The app still records views as `expert:<name>` and offers no counsel entry point; the reviewer
  role at case setup (#238's follow-up, plan PR 4 of confirm-rule-b-c.md) must record a counsel's
  views as `counsel:<name>`, or every counsel acceptance from the screen is refused. The guidance
  wording is unreviewed by a lawyer. The report split and the expert-needed export are the next PR.
- Affects: capabilities (counsel acceptance needs an opened record, not yet reachable from the app);
  customer-facing claims (new plain wording on every claim page and report)
- Status doc: pending: in the paragraph on counsel decisions added by #238's entry, add: "Counsel
  can accept an item only after opening its Evidence item page under their own name; the view is
  in the audit log and shows the page was opened, not that it was read." In the report section,
  add: "Report 0.39.0: every claim says what its verdict means and does not mean, and what needs an
  expert before anyone relies on it in court (core/review/guidance.py)."
