## 2026-11-04: Fixes from the first-time-user review of the demo pages
- Changed: six first-time readers (forensic expert, defense lawyer, non-technical reviewer) and
  Grok's list found screens that read wrong. Fixed, in the app's own pages (not demo-only code): a
  source outside the tested set now reads "Untested export format: ..." instead of "Not tested:
  ...", so it is not read as the claim-level "Unproven, not tested" (tested-set wording 1.1.0); the
  demo or test-run banner shows on every case page, and the demo's says the expert decisions are
  scripted, not made by a person; Identities pick lists start on "Choose…" and are required, so one
  click no longer adds a name to, or links an account to, the first person in the list; the claim
  counts on Case and Claims add up to every claim ("Needs you" counts across the verdicts, and such
  a claim is listed under its verdict too, tagged); Contradicted stays open on Claims; Audit
  progress shows findings when the verdicts on screen were re-run from that audit; a contradicted
  claim lists the records its failed check cites instead of "No relevant evidence items"; an
  untested claim leads with the plain sentence, folds code's refusals and names the other claims
  from its paragraph; an absence gap shows what was searched and each source's coverage in the
  verdict box; a bug in the Timeline note "A phone in this case does not state its time zone" (it
  compared the number of distinct zones with the number of phones, so it printed on every row when
  two phones share a zone) is fixed, and the note now names the phone (each label cited, as source
  text); Gaps says the pace is a rate, not a count of missing records, gives times beside record
  ids, and the strip gives each app the same pace as the cards (records after the first over the
  time from first to last; it was records per strip day, so 8.6 a day on the strip read against 8.7
  on the card); Selection says each quote not placed is listed with its paragraph and counts the
  ones listed above the table, so "5 not looked up" no longer reads against a table of 4; purpose
  lines on Selection, Exhibits, Audit log, Activity and Flags; a "Request letter" tab; Help defines
  the verdicts, tiers and labels; Add a claim explains each claim type; `reportlab` is a base
  dependency, so a bare `pip install -e .` no longer crashes `mabillon demo`; the scripted demo adds
  one synthetic exhibit ("Government Exhibit 4 (synthetic demo)", two Item 1 messages next to
  paragraph 6). The report (REPORT_VERSION 0.37.0): each claim gives its verdict's reasons in plain
  lines (core/report/why.py, as on the claim page) and links to an appendix that holds, per claim,
  the rules' exact words with every id, the rule version and run, and the verdict trace; Limitations
  open with what the five tiers mean (the same words as Help) and define only the verdict labels the
  report uses, while the sentence that AI review alone never makes a claim supported always stays.
  The screen's banner lookup no longer stops a request when the case's run cannot be read.
- Where: branch claude/project-thread-rjmej3 (PR #216)
- Verified: tests/test_first_read_fixes.py (14 tests) and updated test_demo, test_tested_formats,
  test_ufdr, test_report_consistency (it reads a claim's appendix entry with its block); full `make
  check` on a cloud Linux box (numbers in the PR).
- Open: a record cited by two assumptions on one claim page is drawn once by #222 (each item keeps
  its own label and decision), so this change adds nothing there. The report's Save button came with
  #223 ("Save this report (HTML)"), so none is added here. An audited case opens on its Case page,
  as #223 set; this change no longer moves it to Claims. Verdicts, rules, checks and stored data are
  unchanged.
- Affects: customer-facing claims (screen and report wording and layout only; no verdict, rule or
  check changes); capabilities: the Timeline note no longer claims a phone states no zone when both
  do.
- Status doc: no change
