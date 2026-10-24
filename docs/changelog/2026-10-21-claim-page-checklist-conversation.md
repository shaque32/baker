## 2026-10-21: Claim page leads with what has to be true and shows records as a conversation (#109)
- Changed: PR 2 of the UI redesign (plan: /mnt/project-files/baker/plans/ui-redesign.md). Under the
  verdict card, the claim page now shows "What has to be true": one line per assumption, core
  ones first, each marked "Records found (tier)", "Not established", "Not computed" or "Not
  current", read from the stored verdict's coverage. Each evidence record now shows among the
  messages either side of it as chat bubbles, with the verified quote under it; the source
  locator and model rationale fold under "Source and model note". The assumption and check
  tables (including what was searched) fold under "Show the rules' working". Decisions, click
  semantics, verdicts, rules, labels, contracts and schema are unchanged.
- Where: main (#109, merged 2026-10-21)
- Verified: `make check` (see the PR); a new demo test checks the checklist, its place above the
  evidence, the conversation view and the folded tables; the screen and report consistency
  tests still find every evidence item once. Headless-Chromium screenshots of the demo claim
  pages at desktop and phone width.
- Open: a record labelled for two assumptions still shows once per assumption, with one
  decision each; merging those needs Arsh's call. Navigation and the case page are PR 3.
- Affects: customer-facing presentation only; no change to capabilities, privacy or performance.
- Status doc: applied 2026-10-21
