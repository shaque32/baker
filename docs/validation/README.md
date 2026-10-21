# Validation

How Mabillon's accuracy is measured, and what can be claimed from it.

**Status (2026-10-21): no error rate on realistic data exists yet.** Every number below and in
`docs/PRODUCT_STATUS.md` comes from synthetic data. Do not quote an error rate, reproducibility
or court readiness until a validation report for a frozen version is published in this folder.

## The validation card

`python -m eval.validation.card` scores one run against a gold key and prints each rate with its
count, its denominator and its Wilson 95% interval. It never gates; the merge gate stays
`eval/run_eval.py`.

| Measure | Counted over | Why it matters |
|---|---|---|
| False supported | claims gold does not call supported | The error that hurts a defendant most |
| False contradicted | claims gold does not call contradicted | A failed deterministic check contradicts without an expert (rules 0.3.0) |
| Missed contradiction, missed support | gold contradicted, gold supported | What the expert still has to find alone |
| By claim type | each claim type | Where errors cluster |
| Checks on core assumptions | each check type (with `--db`) | Claim-level leads: gold is signed per claim, not per assumption |

With `--db` each false contradicted is attributed to what decided it: a failed check (by name),
expert-accepted evidence, or an expert override. A model's "contradicts" never decides a verdict
on its own (rules 0.3.0), so stance precision is reported by the probe, not here.

`make validation-card` runs it on the last `make eval-model-free` output.

## What small samples allow

With zero errors the Wilson 95% upper bound is 24% on case01's 12 non-supported claims. It
reaches 5% at 73 claims, 2% at 189 and 1% at 381 (`claims_for_upper_bound`). A clean result on
one synthetic case is a regression guard, not an error rate.

## Baselines (synthetic case01, report only)

| Run | Accuracy | False supported | False contradicted | Missed contradiction |
|---|---|---|---|---|
| Model-free gate, simulated expert (main `a27cfb9`, Linux container, 2026-10-21) | 20 of 20 [84-100%] | 0 of 12 [0-24%] | 0 of 14 [0-22%] | 0 of 6 [0-39%] |
| Same, unreviewed (no expert) | 11 of 20 [34-74%] | 0 of 12 [0-24%] | 0 of 14 [0-22%] | 1 of 6 [3-56%] |
| Opus 5.5 medium, cloud prompt v1.2, simulated expert (stored run of 2026-10-20, re-scored 2026-10-21) | 19 of 20 [76-99%] | 0 of 12 [0-24%] | 0 of 14 [0-22%] | 1 of 6 [3-56%] |

The model-free rows use a stand-in labeler that follows gold, so they test retrieval, checks and
rules, not a model. The Opus row re-scores the stored database and predictions of the run in
`docs/PRODUCT_STATUS.md` section 7; no model was called.

## Protocol for a validation release (planned)

1. Cases from public forensic images (Digital Corpora, NIST CFReDS), claims written by someone
   who never sees Mabillon's output, labelled blind by independent readers, signed by Arsh.
   Public-image content stays out of the repo; the repo holds the manifest and hashes.
2. A pre-registration committed before any run: metrics, bars, exclusions, analysis code.
3. A frozen version: a git tag naming rule version, prompt hashes, model SHA-256 and runtime build.
   One scoring per tag; a fix means a new tag and a new run, both reported.
4. An outside examiner's blind result on the same cases, and the local model's repeat check.
5. A report in this folder, `v<N>.md`, with every failure listed and what was not tested.
