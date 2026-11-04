## 2026-11-04: Fixes from the first-time-user review of the demo pages
- Changed: six first-time readers (forensic expert, defense lawyer, non-technical reviewer) and
  Grok's list found screens that read wrong. Fixed, in the app's own pages (not demo-only code):
  a source outside the tested set now reads "Untested export format: ..." instead of "Not
  tested: ...", so it is not read as the claim-level "Unproven, not tested" (tested-set wording
  1.1.0, REPORT_VERSION 0.36.0); the demo or test-run banner shows on every case page, and the
  demo's says the expert decisions are scripted, not made by a person; Identities pick lists
  start on "Choose…" and are required, so one click no longer adds a name to, or links an
  account to, the first person in the list; the claim counts on Case and Claims add up to every
  claim ("Needs you" counts across the verdicts, and such a claim is listed under its verdict
  too, tagged); Contradicted stays open on Claims; Audit progress shows findings when the
  verdicts on screen were re-run from that audit; a contradicted claim lists the records its failed check cites instead of "No relevant evidence
  items"; a record shown twice on a claim page says so; an untested claim leads with the plain
  sentence, folds code's refusals and names the other claims from its paragraph; an absence gap
  shows what was searched and each source's coverage in the verdict box; a bug in the Timeline
  note "A phone in this case does not state its time zone" (it compared the number of distinct
  zones with the number of phones, so it printed on every row when two phones share a zone) is
  fixed, and the note now names the phone; Gaps says the pace is a rate, not a count of missing
  records, and gives times beside record ids; purpose lines on Selection, Exhibits, Audit log,
  Activity and Flags; a "Request letter" tab; Help defines the verdicts, tiers and labels; Add a
  claim explains each claim type; `reportlab` is a base dependency, so a bare `pip install -e .`
  no longer crashes `mabillon demo`; the scripted demo adds one synthetic exhibit
  ("Government Exhibit 4 (synthetic demo)", two Item 1 messages next to paragraph 6).
- Where: branch claude/project-thread-rjmej3 (PR #216)
- Verified: tests/test_first_read_fixes.py (13 tests) and updated test_demo, test_tested_formats,
  test_ufdr; full `make check` on a cloud Linux box 2026-11-04 (numbers in the PR).
- Open: not done here: the report's own reading changes (a tier legend, listing only the labels
  that occur, moving ids to an appendix, a Download button); grouping one record's cards into one
  card; the Selection summary count against its table; the Gaps strip rate (per strip unit)
  against the card's rate. Verdicts, rules, checks and stored data are unchanged.
- Affects: customer-facing claims (screen wording only; no verdict, rule or check changes);
  capabilities: the Timeline note no longer claims a phone states no zone when both do.
- Status doc: no change
