## 2026-10-19: Expert flags on the claim page and a pilot error log (#81)
- Changed: an expert can flag a wrong label, a missed record or a verdict they disagree with, right
  on the claim page (one click to open, one to save; no reason required). Flags are `flag.add` and
  `flag.withdraw` entries in the hash-chained audit log, so no schema change. They never change a
  verdict, an evidence status or anything the rules read. The case page downloads a redacted
  summary (counts, enum labels, versions; no text, ids, names, notes or record references);
  `baker flags export` writes the same file and `baker flag-log` combines summaries into a
  per-pilot error log (only flags on the run on screen count, one per target, read from one run
  snapshot; a missed-record flag survives a rules-only re-run; label pairs are kept per model and
  prompt; a summary from a case with a broken audit-log chain, or exported before its audit
  finished, is left out). Records labeled irrelevant are listed on the claim page and can be
  flagged on their own page. A flag needs a verdict on the audit on screen and is refused if that
  audit changed since the page opened; after an override it records Baker's verdict, not the
  expert's. A verdict flag must name a verdict other than Baker's, and a label flag an item in the
  audit on screen and a label other than its own; a removed claim takes no flags and its earlier
  flags don't count. The report lists flags without the expert's note. Why: Grok Product review
  #80 item 12; pilots need a measured error record. Details in `docs/flags.md`.
- Where: main (PR #81, merge 0dc55dc, 2026-10-19).
- Verified: 17 new tests (`tests/test_flags.py`): no verdict, review or claim row changes, chain
  still verifies, redaction checked against claim text, quotes, ids, names, file names and hashes,
  refused cross-site posts, report hides notes, CLI export and log. Headless-Chromium smoke on
  synthetic case01: flag, list, withdraw, download; no outside requests, Referrer-Policy
  same-origin. `make check` results are in the PR description.
- Open: no pilot has used it; rates are lower bounds because flagging is optional. Notes stay in
  the case database and audit log, which are case content.
- Affects: capabilities (expert feedback, error log). Privacy: nothing sent; the summary is
  shared only by hand. Performance: none. Customer-facing claims: may say experts can flag
  errors locally; no error-rate figure exists yet.
- Status doc: applied 2026-10-19
