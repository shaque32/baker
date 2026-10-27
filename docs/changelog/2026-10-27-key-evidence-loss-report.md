## 2026-10-27: Key-evidence loss report, one stage per gold key record (#PR)
- Changed: new eval-only tool `eval/loss_report.py` (version 1.0.0; `python -m eval.loss_report
  --db <case.db>`). It opens a finished run's case database read-only, with the signed gold key,
  and puts each gold key record at the furthest stage it reached: refused (the claim has no
  assumptions), not retrieved (split into "settled by a failed core check", where retrieval is
  skipped by design, and "retrieval missed"), labelled irrelevant, invalid output, quote dropped,
  or surfaced. It also splits a run's dropped labels by reason from the stored model calls. An
  irrelevant label carries no quote, so the pipeline drops it at the quote check and stores the
  call as `quote_failed`; the tool counts that as "irrelevant", and counts "quote_failed" only for
  real labels whose quote did not verify. For a hidden case (case.json says `hidden`) it prints
  aggregate counts only. Step 1 of the agent plan (Arsh, 2026-10-27): it answers whether
  evidence is lost mainly at the stance step or at the quote check before any agent work. It
  needs no model and changes no rule, prompt, pin, contract, schema, gold or scorer file, and
  nothing under `eval/validation/` (run 2).
- Where: branch `claude/project-thread-6i2msb` (PR to open)
- Verified: `tests/test_loss_report.py` (synthetic rows: every stage, the furthest stage across
  assumptions, the last call per pair, stored irrelevant items, the main-leak line, choosing a
  stance run, the hidden-case output, the database left unchanged). Run on the stored synthetic
  case01 database of the Opus 5.5 medium, cloud prompt v1.2 run (2026-10-20, commit cc3c43f,
  /mnt/project-files/baker/cloud-bench/2026-10-20-case01-v12/case01-opus-med-v12/case01.db): of
  71 gold key records, 44 surfaced, 18 not retrieved (all 18 on the 5 claims a failed core check
  settles, 0 missed by retrieval), 8 labelled irrelevant, 1 quote dropped, 0 refused, 0 invalid
  output. Main leak: the stance step (8 vs 1). The 374 dropped labels are 373 irrelevant answers
  and 1 quote failure (a "complicates" label quoting a message whose whole text is "?", which
  quote check 1.2.0 cannot verify because it holds no letter or digit). The surfaced and
  retrieved counts match that run's run.json (0.6197 and 0.7465).
- Open: the local Qwen3-14B is not measured here, because no 14B case01 database is in the
  container (it would be produced by `make eval-real` on the Mac). Real data waits on run 2
  (the case01 half only, per Arsh). One case, one run.
- Affects: none (eval tool; no product behaviour changes)
- Status doc: pending: section 7, "Opus case01 detail": replace "381 of 493 labels were dropped
  before storage (this count includes "irrelevant" answers, which carry no quote; the split is not
  broken out, inferred from `core/pipeline.py`)" with "In the 2026-10-20 Opus v1.2 case01 run,
  374 labels were dropped: 373 irrelevant answers and 1 quote failure. Of 71 gold key records,
  44 surfaced, 18 were on claims a failed core check settles (retrieval skipped by design), 8
  were labelled irrelevant and 1 was dropped at the quote check; retrieval missed none where it
  ran (`eval/loss_report.py` 1.0.0, #PR)"; section 9 item 5: add "Where it ran, the fixed
  retrieval found every key record on case01; the loss is at the stance step (#PR)"
