## 2026-10-26: The validation scorer reports coverage: claims tested, why the rest were not, and measures over tested claims
- Changed: Validation run 1 tested none of its 106 claims, and the scorer's measures still read
  as rates over all claims ("0 of 69"). Run 2's signed plan (eval/validation/PREREGISTERED_v2.md,
  low-coverage rule) requires that k, the claims tested out of 106, is always reported, along
  with each refusal reason that left a claim untested and how many claims it hit. It also
  requires that verdict measures are counted only over tested claims, with untested claims
  listed by id and never counted as correct or wrong. Below 30 tested claims, the result reads
  "insufficient coverage, no accuracy claim".
  eval/validation/score_hickman.py now writes a `coverage` section to score.json and score.md,
  which contains:
  - k tested of all claims and the minimum. A claim is tested when the run did not mark it
    "Not tested", which is the run's own `not_tested` record.
  - Refusal kinds and their claims. Each refusal in an untested claim's "Not tested" sentence
    is read on its own and grouped by fixed patterns that follow the assumption filler's
    wording. A claim counts once per kind it has. A refusal that matches no kind is counted as
    unclassified, even beside recognized ones. The filler's closing summary ("no usable …
    assumption; the claim stays unproven") says what was missing, not why, so it is not a
    kind; a claim with nothing else is counted on its own line.
  - Each untested claim with its sentence.
  - Primary measures 1 to 3, and the R2 card (measure 4), again over tested claims only.
  The existing measures over all claims, and score.json's existing keys, are unchanged. The
  only change to existing output is that an empty base now prints "0 of 0" instead of "n/a".
  This must merge before the tag `validation-v1-run2`, so that it exists before run 2's
  results do, as blind analysis requires.
- Where: main (#142, merged 2026-10-27)
- Verified: tests/test_validation_score.py:
  - coverage on the synthetic run (3 of 3 tested, under the minimum, same bases);
  - refusal kinds from real filler wording: the closing summary ignored, a refusal's own
    "; " kept inside it, unclassified text beside a recognized refusal, a summary-only claim,
    and a sentence cut short at four refusals;
  - untested claims kept out of every base;
  - the minimum boundary at 30 and 29.

  Rescoring run 1's own results.zip with this code gives 0 of 106 tested, and phone, time zone,
  people and account counts identical to run 1's findings. Those counts are already reported
  as run 1's null result, so this is not a new result. make check passes, and the synthetic
  eval numbers are unchanged.
- Open: A "Not tested" sentence shows at most four refusals. A claim with more is flagged as cut
  short, and its later kinds are not counted. The refusal kinds are a fixed reading of the
  filler's wording at this commit: a new refusal message would show as unclassified, not be
  dropped.
- Affects: performance reporting (validation measures; no product behaviour, privacy or
  customer-facing claim changes)
- Status doc: no change
