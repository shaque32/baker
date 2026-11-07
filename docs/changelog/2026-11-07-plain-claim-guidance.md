## 2026-11-07: plain guidance on every claim (#PR)
- Changed: `core/review/guidance.py`, shown in the same block on the claim page and in the report
  (report 0.39.0). Every claim says what its verdict means, what it does not mean, and the
  judgment calls the records cannot settle. The calls are phone ownership that is proposed but not
  confirmed by an expert (the same test as rules.py), and identity, role, content-meaning, absence
  and event claims; the type lines drop once an expert confirmed or overrode the verdict. An
  unproven verdict always says "not finding something in these records never means it did not
  happen". Why: the examiner hands the report to defense counsel, who needs to see what each
  status can and cannot carry and which calls to raise with the examiner. Read-only: it never
  changes a verdict, a label or the review queue. Kept from closed #239 after Arsh dropped the
  lawyer-without-expert path on 2026-11-07; the counsel lock in #239 was not kept.
- Where: PR #PR
- Verified: `tests/test_guidance.py` (7 tests) on synthetic case01: every claim gets guidance with
  no forbidden word, labels are unchanged, type calls appear on the right claim types, an
  unconfirmed ownership stipulation adds the ownership call and confirming it removes it, an
  expert-confirmed claim drops its type call, and the claim page and report carry the same block.
  `make check` results are in the PR description.
- Open: the wording is not yet reviewed by an examiner or a lawyer.
- Affects: customer-facing claims (new plain wording on every claim page and report)
- Status doc: pending: in the report section, add: "Report 0.39.0: every claim says what its
  verdict means and does not mean, and the judgment calls the records cannot settle
  (core/review/guidance.py, the same block as the claim page)."
