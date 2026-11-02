## 2026-11-02: Simpler app shell, Case, Claims, Add a claim and Cases pages (PR pending)
- Changed: first step of the "simplify the app" plan (Arsh: cut taglines, helper text and
  secondary labels; fix the layout where a screen needs them). Sidebar: 14 links to 11. Cases
  is the case card at the top (a link with a cases folder), Help sits in the sidebar's foot,
  Add a claim is a button on Claims; no "case open on this computer" sublabel; the footer says
  "Offline" (or "Cloud labels on") with the full sentence as a tooltip, then the reviewer's name.
  Claims: no tagline, no progress bar (the counts already say it), count tiles without
  subtitles, no gap-topic summary row; a row shows its most urgent need only and its gap topics
  as small tags, and a status that repeats its group's heading is left to the heading. The
  claim page still says each gap in full, as the report does. Case: no stipulation note under
  Case setup (a Change link instead), the Record drops the "Full audit" helper row and says the
  audit log and flags in a few words. Add a claim: paragraph, text, then id and type; no hint
  line. Cases: no folder explanation or name placeholder; the passphrase line keeps the length
  rule, the no-recovery warning and "The case name is not encrypted". Name forms ask "Your
  name" only (the flash after it still says the name goes with every decision).
  Kept on purpose: demo banner, "not tested" notices, verdict and review-state names, provenance
  tiers, the claim page's gap sentences and absence coverage.
- Where: PR pending (branch claude/project-thread-01u5i7)
- Verified: ruff; `make check` (numbers in the PR); screenshots of the demo at 1280 px before and
  after in /mnt/project-files/baker/simplify/.
- Open: the claim page, tools, record pages and Set up and run follow in later PRs (plan:
  plans/simplify-app.md in the project files). Windows browsers not looked at.
- Affects: none (wording and layout of the local screen; no verdict, rule or label change)
- Status doc: pending: section on the review screen (the `/claims` paragraph): replace "opens
  with how many claims need the expert and a progress bar" with "opens with how many claims need
  the expert and one count per group"; replace "with a plain gap line per unproven claim for
  each kind of core assumption not covered" with "with each unproven claim's gap topics as tags
  (the claim page and the report print the full gap line for each kind of core assumption not
  covered)"; replace "The top tabs (#110) come in three groups (review; tools to look closer;
  set-up)" with "The sidebar's links come in three groups (review; tools to look closer; set-up
  and record), with Cases on the case card and Help in the sidebar's foot".
