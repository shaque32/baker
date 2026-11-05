## 2026-11-05: App look: one badge shape, one frame per item, no periods in titles (#PR)
- Changed: first app fixes from the AI design slop audit (Arsh's "20 AI design slop
  indicators", 2026-11-04), PRs A and B of that audit in one PR. Look and wording only.
  Badges: one shape everywhere (4px corners, a tint, no outline); the round "Records found"
  tags on the claim page, the round "no files" tag on Case, and the outlined flag, challenge and
  agent badges take it. Claims: the gap topics under a claim are one plain line ("Event or role ·
  Meaning of words") instead of round chips; the four counts are a plain row of numbers with no
  frame; Next up has no box (the claim's own accent rule sets it apart). Notices (demo, not
  tested, out of date, Selection's coverage note) are a line behind a thin left rule, not a box;
  a warning's rule is amber; Case's notices leave their shared panel. Selection: the summary is
  hairline rows, time gaps are a centered muted line instead of pills, and messages outside the
  exchange lose their outline (page tint, muted text). Sidebar: no rules and no box around the
  case name; spacing groups the links. Identities: people are separated by space, not a rule.
  Fewer grays: the theme's 12 neutral values become 8 (the extra names are aliases). No
  negative letter-spacing outside the wordmark.
  Periods: titles drop their closing period: "3 claims need you", "Nothing waits on you", a
  folded notice's first line ("Demo case: synthetic data, scripted labels", "What this can
  show"), and the claim page's and Case's format-notice fold lines. The exported report is
  unchanged (same words, same look, no REPORT_VERSION change).
  Kept on purpose: the demo banner, "not tested" notices, verdict and review-state names, every
  provenance tier and source line, the picked-message ring on Selection and the "This record"
  outline on the claim page.
- Where: PR #PR
- Verified: ruff; `make check` (numbers in the PR); the demo at 1280 px before and after, and a
  computed-style count over 16 app pages: round pills and chips outside the Set up step strip
  34 to 0, titles ending in a period 11 to 1 (a two-sentence notice on Case), text with negative
  letter-spacing 48 to 16 (the wordmark on each page). Screenshots and counts in the project
  files, baker/slop-audit/app-ab/.
- Open: raw ids in plain words (audit PR C), a record shown once when two assumptions share it
  (D) and the report's look (E) are not in this PR. Windows browsers and dark mode not looked at.
- Affects: none (look and wording of the local screen; no verdict, rule, label or report change)
- Status doc: pending: section on the review screen (the `/claims` paragraph): where the
  2026-11-02 simplify entry's edit says "with each unproven claim's gap topics as tags", write
  "with each unproven claim's gap topics on one plain line".
