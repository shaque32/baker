## 2026-10-27: The validation scorer counts a claim as tested only when it has a verdict (scorer 1.2.0)
- Changed: In eval/validation/score_hickman.py as merged in #142, a claim counted as tested
  whenever the run had not marked it "Not tested". A gold claim with no first-pass verdict and
  no "Not tested" mark would therefore count as tested: for example, a claim missing from the
  run, or one left undecided because the run stopped short. In measure 1 it would then count as
  a claim not wrongly contradicted. The scorer now fails closed:
  - A claim is tested only when it has a first-pass verdict and is not marked "Not tested".
  - A claim with neither is untested under its own kind, "no verdict recorded". It is listed
    by id and never scored right or wrong.
  - Coverage must account for every gold claim exactly once (106 for the iOS 15 keys), or the
    scorer stops.
  - The time-range and count/duration refusal kinds now match the assumption filler's whole
    refusal phrases instead of bare words such as "window", "range" or "duration". A refusal
    they no longer match counts as unclassified, never as another kind.
  - score.json and score.md record `scorer_version` (1.2.0).

  The measures over all claims are unchanged. Found by a Grok review spec on PR #100. The
  change lands before the tag `validation-v1-run2` and before run 2 runs.
- Where: main (#143, merged 2026-10-27)
- Verified: tests/test_validation_score.py:
  - a claim with no verdict and no mark is untested and outside measure 1's base;
  - a gold claim without a first-pass row stops the scorer;
  - bare words fall to unclassified, while whole phrases, including a template-prefixed one,
    still classify;
  - the version is recorded.

  Rescoring run 1's own results.zip gives 0 of 106 tested and the same refusal counts as
  scorer 1.1.0. Those counts are already reported as run 1's null result. make check passes,
  and the synthetic eval numbers are unchanged.
- Open: A "Not tested" sentence still shows at most four refusals per claim, and such claims
  are flagged as cut short.
- Affects: performance reporting (validation measures; no product behaviour, privacy or
  customer-facing claim changes)
- Status doc: no change
