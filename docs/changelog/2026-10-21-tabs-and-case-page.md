## 2026-10-21: Top tabs in three groups; the case page leads with what waits on the expert (#110)
- Changed: PR 3 of the UI redesign (plan: /mnt/project-files/baker/plans/ui-redesign.md). The
  eleven top tabs now sit in three groups split by a thin line: the review (Case, Claims,
  Report), tools to look closer (Identities, Exhibits, Selection, Timeline, Gaps) and the
  case's set-up (Add a claim, Set up and run, Audit log). "Claims queue" reads "Claims" in the
  tabs. The case page now opens on the audit: a "N claim(s) need you" button and one verdict
  pill per finding with its count, then the government documents. The source files and their
  SHA-256 hashes fold under "Files and their SHA-256 hashes (chain of custody)". Devices and
  stipulations stay open because the expert acts on them. Every page and every action is still
  there; verdicts, rules, labels, contracts and schema are unchanged.
- Where: main (#110, merged 2026-10-21)
- Verified: `make check` (see the PR); a new demo test checks the tab groups and the case page
  order with the custody table folded. Headless-Chromium screenshot of the demo case page.
- Open: the report layout is unchanged beyond the gap lines from #108.
- Affects: customer-facing presentation only; no change to capabilities, privacy or performance.
- Status doc: applied 2026-10-21
