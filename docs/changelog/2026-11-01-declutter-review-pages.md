## 2026-11-01: Case, Claims, Add a claim, one-claim and evidence pages decluttered (#PR)
- Changed: after an Impeccable audit of each page (findings and before/after screenshots in
  /mnt/project-files/baker/declutter/), the review pages show less at once. Case: one column;
  the notices in one panel, folded to their first sentence; Case setup and Record as hairline
  rows, "no stipulated user" as a small tag; the custody table no longer breaks words. Claims:
  rows like the site's ledger (id, claim, one status, small lines under it); gap lines are muted
  lines, not boxes inside each row; the four tiles are one strip; a status that repeats its
  group's heading shows as plain text, still in words. One claim: decided evidence cards fold
  their thread, "Change your decision", source note and flag form onto one line, while cards
  waiting on the expert keep their thread open; Accept/Dismiss and the reason field on one
  line; "What has to be true" as rows with one tag each (a row backed only by AI review never
  gets the green tag); "Other explanations" folded under its heading; selection notes as muted
  lines; the claim's own C05 page is about a quarter shorter, C16 about 40% shorter. Evidence
  page: names instead of raw ids, compact thread. The demo banner now folds to its first
  sentence on every page (it already did on the case page); every word stays. No form action,
  field, value, verdict, label or caveat removed.
- Where: PR #PR
- Verified: per-page pytest selections (overview 270, claims 95, claim/evidence 441 passed),
  tests/test_demo.py, test_review_screen.py and test_report_consistency.py (62 passed), ruff,
  and `make check` on the combined branch (numbers in the PR). Impeccable detect, before to
  after: /claims 4 to 2; claim pages 109 to 18 across C05, C04, C16, D03, D02, C01 and one
  evidence page; the findings left are the warm paper palette Arsh chose and long prose lines.
- Open: Windows not looked at; "FAILED VERIFICATION" in the case page's record line stays
  uppercase (shared wording, left for a wording pass).
- Affects: none (look of the local screen only)
- Status doc: no change
