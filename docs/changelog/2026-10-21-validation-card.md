## 2026-10-21: Validation card with Wilson intervals (#121)
- Changed: `eval/validation/card.py` scores a run against a gold key and reports verdict accuracy,
  false supported, false contradicted, missed contradiction and missed support, each as k of n with
  a Wilson 95% interval, by claim type, with false contradicted attributed to what decided it and a
  per-check-type outcome table when given the case database. `make validation-card` runs it on the
  model-free case01 output. `docs/validation/README.md` sets out what validation means and the
  planned protocol for a validation release. First step of the validation plan (thread
  "Real-world accuracy validation", which took over Court defensibility PR D). Report only: no
  gate, threshold or verdict path changes.
- Where: PR #121
- Verified: `tests/test_validation_card.py` (9 tests). Run on main `a27cfb9`'s model-free case01:
  accuracy 20 of 20 [84-100%], false supported 0 of 12 [0-24%], false contradicted 0 of 14 [0-22%].
  Re-scored the stored Opus 5.5 medium v1.2 case01 run (2026-10-20): 19 of 20 [76-99%], false
  supported 0 of 12 [0-24%], missed contradiction 1 of 6 [3-56%]. Linux cloud container,
  2026-10-21.
- Open: the check table is a claim-level attribution (gold is signed per claim, not per
  assumption). No realistic-data error rate exists yet; that needs signed public-image cases.
- Affects: customer-facing claims (records that synthetic case01 bounds false supported only to
  0-24%, so it is not an error rate)
- Status doc: pending: section 7, under "Merge gate (model-free, `make eval`)", add "Validation
  card (`python -m eval.validation.card`, `make validation-card`, #121): every rate with a Wilson
  95% interval. On case01 0 false supported of 12 non-supported claims allows up to 24%; 73 such
  claims with zero errors are needed for an upper bound of 5%, 189 for 2%. See
  `docs/validation/README.md`." Section 12, "Claims Baker should not make yet": add "any error
  rate from synthetic case01 (0 of 12 false supported bounds the rate only to 0-24%)".
