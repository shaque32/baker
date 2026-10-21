## 2026-10-20: Claims overview grouped by what waits on the expert, with a plain gap line per unproven claim (PR pending)
- Changed: Arsh found the claims queue read as an old-school ledger where most claims looked
  "Unproven" and unfinished. The queue (`/claims`) now opens with how many claims need the expert,
  a progress bar, one tile per group and a "Next up" card, then groups the claims: Needs you,
  Contradicted, Unproven, Supported (and Not audited when there are any). Each unproven claim
  gets one plain line per kind of core assumption the rules found not covered (meaning of words,
  who is behind an account, event or role, time, search coverage), from
  `ClaimState.explain_lines()` in `core/review/status.py`; a fully covered claim held by another
  rule gets one line pointing to that rule. The lines are read from the stored verdict's
  coverage and decide nothing; each says only that a part "is not established". When
  anything the verdict rests on changed after the run, one "Not current" line asks for a
  re-run (the full audit after a claim edit or an identity or person change, including a proposed link, which widens the search) and the claim counts as Needs you. AI-reviewed support and unseen AI-dismissed support count as Needs you. The overview no longer repeats "Verdict not yet
  confirmed or overridden by you" on every row (the claim page still shows it). The report
  (0.10.0) prints the same gap lines under each unproven claim. Verdicts, rules, labels,
  contracts and schema are unchanged. Plan: /mnt/project-files/baker/plans/ui-redesign.md (PR 1 of 3).
- Where: branch claude/project-thread-6l17lv
- Verified: `make check` (see the PR); a new demo test checks the groups, the gap lines on the
  screen and in the report, and that no verdict changes; screen and report consistency tests
  read every group. Headless-Chromium screenshot of the demo overview.
- Open: claim page and navigation redesign are PRs 2 and 3. The search-coverage line points to
  the claim page for what was searched; it does not restate the coverage itself.
- Affects: customer-facing claims (how the screen and report explain unproven claims); no change
  to capabilities, privacy or performance.
- Status doc: pending: in the review screen section, say the claims queue groups claims (Needs
  you, Contradicted, Unproven, Supported) with a progress count and a plain gap line per unproven
  claim, and that the report is 0.10.0 and prints the same gap lines.
