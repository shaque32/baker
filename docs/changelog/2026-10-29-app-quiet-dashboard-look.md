## 2026-10-29: App screens as a quiet dashboard (sidebar, white cards, one sans face) (#167)
- Changed: Arsh found the demo overstimulating (2026-10-29) and asked for the look of the
  Stripe dashboard. Review screen only (ui/theme.py): navigation moves from top tabs to a left
  sidebar in the same three groups; light gray page with white cards; every heading in IBM
  Plex Sans (Instrument Serif only in the wordmark); verdict and tier labels as small square
  labels without icons or dashed edges, the words carry the meaning (waiting on the expert in
  navy, unproven in gray); one-number cards for the claim groups instead of a filled navy
  tile; the claims ledger's multicolored bar hidden (the counts beside it stay); prose held to
  about 78 characters; tables as white cards with a light header row; the gaps page's settings
  fields on one line. Visual only: no wording, route, form, audit log or report change.
- Where: PR #167
- Verified: make check (lint, tests, eval); demo case screens rendered in Chromium at 1440x900
  and 390x844 before and after (preview images shared with Arsh, who approved the look).
- Open: the downloaded report keeps its paper look (report 0.20.0); dark mode not done; the
  pilot installers in the R2 bucket predate this and #149 and need a fresh upload after merge.
- Affects: none (look only; no capability, privacy, performance or claim change)
- Status doc: pending: in the review-screen paragraph, replace "The top tabs (#110) come in
  three groups (review; tools to look closer; set-up)" with "The sidebar navigation (#110,
  moved from top tabs by #167) comes in three groups (review; tools to look closer; set-up)".
