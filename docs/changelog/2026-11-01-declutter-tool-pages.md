## 2026-11-01: Identities, Exhibits, Selection, Timeline and Gaps pages decluttered (#PR)
- Changed: after an Impeccable audit of each page (findings and before/after screenshots in
  /mnt/project-files/baker/declutter/), the "look closer" pages show less at once. Identities:
  counts and "Look for links again" in one bar; each link card on one header row with its
  records for and against as quiet rows (first 3 per side open; a decided link folds its
  records; a proposed or unresolved link keeps them open, so nothing is decided on folded
  evidence); reason field and Confirm/Reject on one line. Exhibits: one primary action, no cards
  inside cards, the exhibit name as the page heading, related threads folded with a count, the
  request letter on one sheet. Selection: definitions and the "What this can show" notice fold
  to their first sentence; findings as ledger rows; flat message bubbles whose chips still name
  each state. Timeline and Gaps: one ledger panel per section instead of a card per row; each
  phone's chart and quiet stretches in one panel; the method sentences fold. Every caveat stays
  on the page, folded at most (searched lines, "not found does not mean...", provenance tiers,
  "does not change any verdict"); no wording, form action, field, verdict or label change.
  Page CSS lives in ui/css/{identities,exhibits,selection,timeline}.py; core/ and the exported
  report are unchanged.
- Where: PR #PR
- Verified: per-page pytest selections (identities 161, exhibits/selection 141, timeline/gaps
  209 passed), ruff, and `make check` on the combined branch (numbers in the PR). Impeccable
  detect, before to after: /identities 3 to 1, /exhibit 18 to 2, /selection 113 to 15,
  /timeline 2 to 1, /gaps 2 to 1 (25 to 1 at 390 px); the finding left on each page is the warm
  paper palette Arsh chose.
- Open: two heading-level skips come from core/report markup (selection, restore) and need a
  report change; the gaps day chart still scrolls inside its panel at 390 px; Windows not
  looked at.
- Affects: none (look of the local screen only)
- Status doc: no change
