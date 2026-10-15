# Pilot gates

"Pilot-ready" means every gate below passes. A pilot is the first time a defense expert runs Baker
on real case data. Until then Baker is shown only on the synthetic demo.

Each gate is pass or fail. Partial progress is "not met". A gate passes only when its evidence
exists on `main` (or, for a human step, in a recorded result someone can open). Update this file in
the same PR that changes a gate's state, along with `docs/PRODUCT_STATUS.md` section 11.

- **As of:** 2026-10-15, main `8ed89f9`. Open PRs are named but not counted.
- **Result today:** 0 of 12 gates met on main; gate 12 passes when this PR merges. **Not pilot-ready.**

## The gates

| # | Gate | Pass when | State (2026-10-15) | Evidence or what's missing |
|---|---|---|---|---|
| 1 | CI green 3 times | The `checks` workflow (Ubuntu and Windows) passes on 3 consecutive pushes to `main`, with no re-runs | **Not met** | 1 green: `8ed89f9` (run 327). The run before it on `ae8f24e` was cancelled, and main was red earlier the same day until #65 |
| 2 | Quote check matches what the model sees (issue #69) | Contacts and calls render the same way for the labeler and the quote check, on main | **Not met** | Contacts fixed in PR #76 (open). Calls still differ. A dropped "contradicts" could in theory let a claim go SUPPORTED |
| 3 | Versions stamped on every result | `RULE_VERSION` on main includes every merged rule-reading change (0.2.2, PR #75), and each stored result also records the quote-check version | **Not met** | Main says 0.2.1 although #66 merged. `core/audit/quotes.py` has `VERSION = "1.1.0"`, but no result or report records it (Grok #80 item 3) |
| 4 | Forwarded and quoted messages | The UFDR importer stores original author, forwarder and text as separate fields with `source_ref`; the sender check never credits forwarded content to the forwarder; until then affected claims fail closed to Unproven with a visible warning | **Not met** | Main does not read forwarded content. PR #73 only lists it in coverage. Grok #80 item 1 |
| 5 | Real exports checked | A pilot examiner's UFDR from a public image passes `baker ufdr-check`, and an AXIOM XML and Excel export of one closed case import with counts compared to the vendor tool | **Not met** | Readers built from documentation and synthetic samples. #73 checked 27 records on two non-Cellebrite files. UFDR and AXIOM stay "unverified" on screen and in reports |
| 6 | Reproducible reports | A test shows the screen and the report agree, and the same inputs, versions and expert decisions give the same report | **Not met** | Built in PR #72 (open) |
| 7 | Audit-log chain enforced | The hash chain is checked when a case opens, before a report and before export, and a broken chain blocks review | **Not met** | Main checks it at report build (the report prints "FAILED VERIFICATION") and before encryption. PR #74 (open) adds the check on open. Truncating the newest entries still verifies (no outside anchor) |
| 8 | Cloud decision recorded | Arsh's decision on #68 (merge, hold or close) is written in `docs/PRODUCT_STATUS.md` and `docs/CHANGELOG_AI.md` | **Not met** | #68 is a draft. Opus scored 73% contradicts precision on the signed set (bar 90%), so the branch now lets no model label in the cloud until a signed prompt fix passes on new items |
| 9 | Local runtime measured | A full local case01 run on current main, timed with `eval/probe/time_case.py` on the 24 GB Mac, with commit, hardware and date recorded | **Not met** | Last full run predates today's pipeline. Per-call figures are from 2026-10-09 and 2026-10-12 |
| 10 | Signed Windows installer | The Windows installer is code-signed (only for a Windows pilot) | **Not met** | Unsigned. Azure code signing pending (`docs/code-signing.md`) |
| 11 | Outside install test | One person outside the project installs Baker on a clean Mac, runs the demo and opens a case using only `docs/PILOT_ONBOARDING.md`, without help, and the result is written down | **Not met** | Needs a person. The kit exists (this PR); nobody outside the project has tried it |
| 12 | Buyer documents | Onboarding kit, methods note and security and privacy pack are on main and match the code | **Met when this PR merges** | `docs/PILOT_ONBOARDING.md`, `docs/METHODS.md`, `docs/SECURITY_PRIVACY.md` |

Also required on the release commit, as for every merge: `make check` passes (lint, tests, the
model-free eval with 0 false supported on case01, hostile red-team PASS).

## What the gates don't cover

- **Accuracy on real data.** No gate claims a number. Baker publishes no accuracy or speed figure
  until it is measured on real exports (Grok #80, Defer).
- **Paid pilots and case02.** Whether a pilot is paid, and the hidden case02 result, are business
  gates in the pilot kit's go/kill scorecard, not product gates.
- **Gate 8 is a decision, not a pass.** Recording "hold #68" passes it. Pilots then run local only.

## Order

Gates 2, 3, 6 and 7 are open PRs (#76, #75, #72, #74) waiting on review and merge. Gate 4 needs
new work. Gates 5, 9 and 11 need a person: a pilot examiner, a run on the Mac and an outside tester.
Gates 1 and 12 follow from merging.
