## 2026-11-02: Simpler app: fewer labels and helper lines on every page but Set up and run (PR pending)
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
  One claim: the side list shows each claim's name, status and two lines of text (no tally or
  "Claims ledger" heading); the Verdict card drops the standing "not yet confirmed" reminder
  (the Confirm fold is it) and, on an untested claim, the lines the Evidence section shows in
  full; two or more format notices fold under one line that counts them (every word stays);
  "Why", "Rules' working", "Flag this verdict" and "Messages around it" replace longer labels;
  reason fields say "Reason"; flag forms drop their help line (the flags list keeps it); no
  tagline under "What has to be true"; a "Quoted:" line shows only when the verified quote is
  part of the highlighted message, not all of it; the agent card keeps "Nothing here is used
  until you accept it" and drops the rest; "Sources in this case" heads the untested claim's
  source list (the report keeps its sentence). Evidence page: no helper line over the context.
  A row's status that repeats its group's heading stays in the markup, visually hidden, so the
  screen and report still agree word for word (tests/test_report_consistency.py).
  Tools: page titles are the sidebar names (Identities, Timeline, Gaps); no intro paragraphs on
  Identities, Exhibits, Timeline or Gaps (Gaps keeps its not-found caveat, Identities keeps how
  links work in its fold, now with "Nothing is merged" first); no hints in the exhibit, person,
  alias and timeline settings forms; an unplaced name says "Used in C18 · no person yet". Record
  pages: Audit log says "Hash chain verified" and "Flags", drops the flag how-to and the page-view
  note (the Shown (N) control says it); Activity drops its intro and the report switch says
  "In the report: left out." or "included."; Help drops the tagline and the one-pager pointer and
  shortens the bug report steps (the never-send-case-content line stays). Set up and run and the
  audit progress page are left to their own thread.
  Kept on purpose: demo banner, "not tested" notices, verdict and review-state names, provenance
  tiers, the claim page's gap sentences and absence coverage.
- Where: PR pending (branch claude/project-thread-01u5i7)
- Verified: ruff; `make check` (numbers in the PR); screenshots of the demo at 1280 px before and
  after in /mnt/project-files/baker/simplify/.
- Open: Set up and run, and splitting ui/pages.py per page, follow (plan: plans/simplify-app.md
  in the project files). Windows browsers not looked at.
- Affects: none (wording and layout of the local screen; no verdict, rule or label change)
- Status doc: pending: section on the review screen (the `/claims` paragraph): replace "opens
  with how many claims need the expert and a progress bar" with "opens with how many claims need
  the expert and one count per group"; replace "with a plain gap line per unproven claim for
  each kind of core assumption not covered" with "with each unproven claim's gap topics as tags
  (the claim page and the report print the full gap line for each kind of core assumption not
  covered)"; replace "The top tabs (#110) come in three groups (review; tools to look closer;
  set-up)" with "The sidebar's links come in three groups (review; tools to look closer; set-up
  and record), with Cases on the case card and Help in the sidebar's foot".
