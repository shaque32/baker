## 2026-10-29: App and report as a quiet dashboard (sidebar, white cards, one sans face) (#167)
- Changed: Arsh found the demo overstimulating (2026-10-29) and asked for the look of the
  Stripe dashboard. Review screen (ui/theme.py): navigation moves from top tabs to a left
  sidebar in the same three groups; light gray page with white cards; every heading in IBM
  Plex Sans (Instrument Serif only in the wordmark); verdict and tier labels as small square
  labels without icons or dashed edges, the words carry the meaning (waiting on the expert in
  navy, unproven in gray); one-number cards for the claim groups instead of a filled navy
  tile; the claims ledger's multicolored bar hidden (the counts beside it stay); prose held to
  about 78 characters; tables as white cards with a light header row; the Timeline and Gaps
  settings as a proper form (labeled fields, the unit inside the field, no
  spinner arrows, a Save settings button, one help line per field); times in tables kept on one
  line; the claim table's Remove, Up and Down buttons on one row. Downloaded report 0.22.0,
  visual only: the title in IBM Plex Sans (no serif), the same cool grays and white cards with
  8px corners, notices as a gray note instead of a yellow box, unproven in gray. Verdict icons
  stay in the report so a black-and-white print still tells verdicts apart. No route, form
  field, audit log entry, fact or report section changed; the settings form gained only the
  two help lines and a title.
- Where: PR #167
- Verified: make check (lint, tests, eval); demo case screens rendered in Chromium at 1440x900
  and 390x844 before and after (preview images shared with Arsh, who approved the look).
- Open: dark mode not done; the pilot installers in the R2 bucket predate this and #149
  and need a fresh upload after merge.
- Affects: none (look only; no capability, privacy, performance or claim change)
- Status doc: pending: in the review-screen paragraph, replace "The top tabs (#110) come in
  three groups (review; tools to look closer; set-up)" with "The sidebar navigation (#110,
  moved from top tabs by #167) comes in three groups (review; tools to look closer; set-up)".
