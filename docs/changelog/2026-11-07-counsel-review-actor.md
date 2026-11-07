## 2026-11-07: counsel review actor, the B follow-up to rules 0.5.0 (#PR)
- Changed: PR 3 of `/mnt/project-files/baker/plans/confirm-rule-b-c.md`. Rules 0.5.0 (#228) let a
  named defense lawyer's acceptance support a claim as "Supported (reviewed by counsel)", but
  nothing could write a counsel review. This adds the code path. No signed file changes.
  - `core/review/actions.py` `decide_counsel()`: actor `counsel:<name>`. Counsel can accept an
    evidence item (`counsel_accepted`) or take back their own acceptance (`open`). Counsel cannot
    dismiss, cannot accept as an expert, and cannot change any item an expert has decided, even
    after the expert reopened it. A reason is required. Counsel overrides the AI reviewer, as any
    human does. Each decision is a new append-only `evidence_reviews` row and an
    `evidence.decide` audit log entry, the same action the expert's decisions use, so the log
    and bundle consistency checks cover it.
  - `COUNSEL_CHECKS`: a precondition hook, empty by default. A check refuses a counsel decision
    by raising `ReviewError`, and then nothing is stored or logged. The lawyer-checker work adds
    its "cited record opened" lock here (`plans/lawyer-checker-and-examiner-pilot.md`).
  - `decide_evidence()` (the expert) now refuses any status other than accepted, dismissed or
    open, instead of failing on the schema CHECK.
  - `core/db.py` `upgrade_evidence_reviews()`: a case made under schema 0.7.0 or earlier has an
    `evidence_reviews` CHECK that refuses counsel rows. The first counsel decision on such a case
    rebuilds that table to the 0.8.0 definition inside one savepoint, every row and column kept,
    and remakes its append-only triggers and the `evidence_status` view from `core/schema.sql`.
  - Counsel decisions count wherever expert decisions are cross-checked: the audit log's
    decision check (`audit_log.decision_problem`), bundle verify's review replay and its "expert
    reviews" check (which now also requires the stored reviewer kind to match the actor, so a
    counsel decision cannot pass as an expert's), and the "decisions made after this run" banner
    on the report, claim page and status.
  - Activity trail: counsel's steps show as "<name> (counsel)". Report: the review column says
    "Accepted by counsel:<name> ... Reviewed by counsel, not an expert.", and the verdict trace
    says "Counsel accepted, not an expert". The banner now reads "evidence decisions by the
    expert or counsel were made after this run".
- Where: branch claude/project-thread-qw0rxu
- Verified: `make check` (lint, tests, eval) on this branch, run 2026-11-07 in a Linux x86_64
  cloud container (4 vCPU, Python 3.13.18, no GPU); results in the PR description. `make eval` is
  model-free and nothing in it writes a counsel review, so its numbers are expected unchanged
  from #228. New `tests/test_counsel_review.py` (25 tests) on synthetic case01 audited with the
  AI reviewer accepting everything: counsel acceptance of C05's key evidence makes it "Supported
  (reviewed by counsel)", never confirmed; an expert's later acceptance makes it confirmed and an
  expert's dismissal overrides counsel; every refusal above; a refusing hook stores and logs
  nothing; the audit log and a bundle with counsel rows verify with no FAIL; a counsel row
  rewritten by hand as an expert's is refused at export; the old-schema table upgrade keeps rows,
  triggers and view and runs once.
- Open: still nothing in the app or CLI calls `decide_counsel()`. The reviewer role at case setup
  and the review-screen labels are the next PR (plan PR 4). Until then the review screen groups a
  counsel-accepted item with unreviewed support, and the claim page's step column is headed
  "Expert step" even when counsel took the step. Flags needed no change (they record the last
  reviewer kind as stored). The lock, per-claim guidance, expert-needed flags, report split and
  expert-needed export belong to the lawyer-checker thread.
- Affects: capabilities (counsel reviews can be stored and verified in code; not yet reachable
  from the app)
- Status doc: pending: after the #228 edits are applied, in the paragraph that adds
  counsel_reviewed, add: "Counsel decisions are written by `core/review/actions.py`
  `decide_counsel()` (accept or take back their own acceptance; never dismiss, never change an
  item an expert decided), logged as `evidence.decide` and checked by bundle verify. The app does
  not offer counsel review yet (reviewer role at case setup is the next PR)." Remove "the counsel
  actor" from any open item that lists it as not built.
