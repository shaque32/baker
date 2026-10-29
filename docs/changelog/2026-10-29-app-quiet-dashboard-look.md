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
  From a skeptic-checked demo audit (2026-10-29), screen wording only: a claim page names the
  people, phones and accounts in its assumptions (Daniel Petrov, Telegram 5551234) with the
  id on hover, and count operators as words ("exactly 13"); an assumption a failed check
  contradicts says "Contradicted by the records", not "Not established"; a claim the rules
  contradict on a failed check says so in one sentence instead of the run's engine note and
  CLI hint (the report keeps the run's note); the header says "wording accepted by the
  expert" so it no longer reads as the verdict; "Evidence the expert already decided" replaces
  "Decided by an expert"; the highlighted message reads "This record"; claim types without
  underscores; counts in the right number on the screen and in the report's next steps.
  `mabillon demo` without reportlab now says how to install it instead of a traceback.
- Where: PR #167
- Verified: make check (lint, tests, eval); demo case screens rendered in Chromium at 1440x900
  and 390x844 before and after (preview images shared with Arsh, who approved the look).
- Open: from the same audit, left for Arsh or later: one record shown once per assumption it
  supports (grouping it changes what one Accept does); the per-file "Not tested" lines (the
  claim page and report must show the same notices, tests/test_tested_formats.py); ids and
  raw format names in the report (report wording); verdict names (Arsh's wording). Dark mode not done; the pilot installers in the R2 bucket predate this and #149
  and need a fresh upload after merge.
- Affects: none (look only; no capability, privacy, performance or claim change)
- Status doc: pending: in the review-screen paragraph, replace "The top tabs (#110) come in
  three groups (review; tools to look closer; set-up)" with "The sidebar navigation (#110,
  moved from top tabs by #167) comes in three groups (review; tools to look closer; set-up)".
