## 2026-10-26: A model rationale with a forbidden word is withheld per item, not the whole report (#138)
- Changed: A stance rationale that used a forbidden word (guilty, innocent, leader, deleted)
  made the word check refuse the whole report and the case screen, leaving the examiner no way
  forward (found while reviewing #137; spec from the Grok review on PR #100). Each rationale is
  now checked on its own before it is shown (core/review/withheld.py). One with a forbidden word
  is not printed: its item shows "Rationale withheld; needs expert review", naming the word in
  an element the word check passes only around one forbidden word in lower case. The stance,
  the quote, its check and the review status stay as stored; no verdict rule reads a rationale.
  Mabillon's own text is still checked whole and still refuses the page. The expert
  acknowledges each withheld rationale (screen button, or `mabillon acknowledge`) before the
  claim's verdict can be confirmed or overridden; each acknowledgment is an audit-log entry
  `rationale.acknowledge` with the evidence id, the word and the SHA-256 of the stored rationale,
  never its text, and covers only that rationale. The case overview and a new report section
  "Withheld model rationales" list the same items with the same count (irrelevant items too).
  A scoped bundle leaves out acknowledgments of items it leaves out, as it does evidence
  decisions. Report version 0.16.0, which also counts #137's "record state" wording.
  docs/ingest/coverage.md now says what "record state" means (deleted or intact, as the
  extraction states it).
- Where: main (#138, merged 2026-10-26)
- Verified: tests/test_withheld_rationale.py (synthetic case01, stand-in labels): a rationale
  saying "deleted" renders and writes the report with each item flagged and the text absent; a
  forbidden word in Mabillon's own report text still refuses it; the same labels with clean
  rationales give the same verdicts, labels, stances and quotes; overview and report list the
  same items and count; the acknowledgment entry holds exactly the id, word and SHA-256 and the
  chain verifies; confirm and override are refused until every withheld rationale on the claim
  is acknowledged (screen, actions and CLI); a changed rationale needs a new acknowledgment;
  full and scoped bundles verify. tests/test_coverage_display.py now renders every coverage
  line summarize() can build (all codes, both layouts, counts 1 and 2) and checks the printed
  words, closing #137's gap (fails if a forbidden word is put into an f-string there). make
  check passes on Linux, Python 3.13 (2689 passed, 9 skipped); eval unchanged: case01 accuracy
  1.00, 0 false supported; hostile PASS; case02 aggregate accuracy 0.90, 0 false supported.
- Open: Only stance rationales are withheld per item. The local AI reviewer's reason (off by
  default) is still checked with the page, so a forbidden word there would still refuse it.
  Not seen on a real model run: no local or cloud rationale with a forbidden word has been
  recorded; the path is tested with stand-in labels only.
- Affects: capabilities (a report and screen no longer blocked by one model rationale; a new
  expert step before sign-off)
- Status doc: applied 2026-10-27
