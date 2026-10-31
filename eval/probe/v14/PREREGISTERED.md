# Stance prompt v1.4 for the local 14B: test plan, written before any call (2026-10-30)

Thread "Plan a faster, sharper audit engine", step 3 of
`/mnt/project-files/baker/plans/fast-sharp-engine.md`. Arsh said "alr run it" to the plan on
2026-10-30 23:34Z. Synthetic data only. The prompt change waits for Arsh's signature.

## Why
Speed, with the same labels. On Arsh's case04 Mac run (main 67dabdb, 2026-10-29) stance
labelling took about 3.6 of 4.9 hours of model time: 283 calls, mean 46 s
(`python -m eval.run_profile`). In the signed v1.1 the fixed instructions sit after the record
and its context, so llama.cpp, which keeps only the part a call shares with the call before it
from the start, re-reads them on every call: 40% of an average case04 stance prompt was fixed
text at the end, and 13% was shared from the start.

## The candidate (written once, before any call; not edited after answers)
`eval/probe/stance_v1_4_draft.md`: the signed v1.1 lines, every one kept and none reworded, in a
new order. The "How names read" paragraph, the stance definitions, the "unsure" line and the
quote and rationale rules move ahead of the claim; then the claim, the assumption, the record
and its context; the JSON line stays last (tests/test_stance_v14_order.py). The same reorder of
v1.0 cut probe calls from 22.5 to 15.1 s on 2026-10-12, but lowered contradicts precision (77%,
bar 90%), so it was not signed. Since rules 0.3.0 a model's "contradicts" no longer decides a
verdict without an expert, and v1.1 itself misses that bar (58% on 2026-10-19), so the test
below asks that v1.4 be no worse than v1.1, not that it clear bars v1.1 misses.

## Item sets (first answer scored, layout product_members, stance only, the product's quote check)
The four sets of the v1.3 test (`eval/probe/v13/PREREGISTERED.md`), with the same left-out
items: the signed probe set (`eval/gold/probe/probe.jsonl`, 95 gated items), the fresh set
(`v13/heldout.jsonl`), told-frame 24 (`v13/told_frame_24.jsonl`, T022 and T023 left out) and
rules 12 and 23 (`v13/rules_12_23_26.jsonl`). The 14B answered all four under v1.1 and the two
v1.3 drafts on 2026-10-22; nothing about v1.4 was designed from those answers.

## Runs (Arsh's Mac, `bash eval/probe/mac_v14.sh`, one sitting, the product's flash runtime)
1. v1.1 on all four sets, then v1.4 on all four sets.
2. A timed audit of case01 claims C02, C05 and C12 (the claims speed round 2 timed) with v1.1,
   then with v1.4 (`eval.probe.time_case`, the case01 assumption sheet, cold run counted).
v1.4 always runs after v1.1, so a Mac that slows as it warms counts against v1.4, not for it.

## v1.4 is recommended for Arsh's signature only if all hold (first answers, same sitting)
1. Both prompts ran on all four sets and both timed audits, all on one model file.
2. Valid output 100% on every set.
3. Signed set: every Expert-confirms bar v1.1 meets, v1.4 meets (supports recall >= 90%,
   contradicts precision >= 90%, 0 gold contradicts shown as supports); on each bar v1.1
   misses, v1.4 is no worse than v1.1.
4. All four sets together: gold complicates or irrelevant items shown as supports no more than
   v1.1's. No slack: this is the direction that can end in a false supported.
5. All four sets together: supports recall and contradicts recall each at least v1.1's, less
   one item (the order of floating-point sums can flip a near tie).
6. Timed audit: mean seconds per stance call at least 15% below v1.1's.
If any fails, no prompt change is proposed and every number goes to Arsh as it is.

Reported beside the criteria, never changing them: each item whose first answer differs
between the prompts, Wilson intervals, mean probe seconds per call and prompt tokens, the
audits' stance calls, wall time, verdicts and stored items.

## After a pass, before pilots use v1.4
Signing copies the body into `core/audit/prompts/stance.md` as v1.4. The 14B repeat check
(`eval/probe/repeat_check.py`) then runs again with v1.4, because the report states the repeat
result for the tested prompt. The cloud prompt (`stance_cloud.md`, v1.2) is not part of this.

## Commitments
No label, criterion or candidate edit after seeing any answer. All numbers published, including
any that get worse. $0 API spend: everything runs on the Mac's local model.

## Addendum, before any answer of this test was seen (2026-10-31)
Written after the reviews on PR #182 (Codex, and the Baker Eval gate's six flags), with no v1.1
or v1.4 answer of this test seen. If the Mac run started before this commit, its outputs are
scored under these criteria; RESULTS.md names the commit that ran.
- Criterion 4 now holds on each of the four sets, not only over all four together: on every
  set, gold complicates or irrelevant items shown as supports are no more than v1.1's on that
  set. This is stricter: a rise on one set can no longer hide behind a drop on another (the
  v1.3 test checked the signed set on its own).
- The probe runs get the same context size as the timed audits (`mac_v14.sh` passes `--n-ctx`
  to both; on a 24 GB Mac both were already 8192).
- Reported beside the criteria, never changing them: every item's first answer under both
  prompts, set by set (RESULTS.md, committed with the results as
  `v14/RESULTS-<date>-mac.md`); the model's full SHA-256; each step's seed, context size,
  runtime, tokens per second and peak resident memory; and for the timed audits the per-call
  spread (mean, SD, median, middle half) and the call-by-call ratio of v1.4's time to v1.1's.
  Criterion 6 rests on one cold run of three case01 claims: a go/no-go, not a product runtime
  figure.
- The four sets are not fresh: the 14B answered all of them on 2026-10-22, so a pass is not a
  held-out result. After signing and before pilots use v1.4, it also runs on fresh items
  (written after this test, never answered by the 14B), held to the signed bars and to no
  more traps shown as supports than v1.1.
- The times under "Why" come from `eval/run_profile.py`, which takes a call's time as the gap
  between the end of the call before it and its own end (each call is logged when its answer
  is back), so a gap also holds the code between calls: estimates, not per-call measurements.
- Added later on 2026-10-31, after a further Codex review on PR #182 and still before any
  answer was seen: criterion 6 also needs every stance call of both timed audits answered, with
  no runtime error and no invalid output (`model_calls` outcomes `error` and
  `invalid_output`). This is stricter: a failed call returns at once and still counts in the
  mean, so failures can no longer pass as a speedup. A quote the product's check discards is a
  full answer: reported beside the criteria, not counted as failed, as on the probe sets.
  `time_case` now records each pass's call outcomes; for a folder written before that, the
  scorer reads them from the timed audit's own case database (its first stance model run is
  the cold run). Outcomes recorded in neither place fail the criterion.
- Added after one more Codex review on PR #182, still before any answer was seen: criterion 2
  holds for both prompts' runs, as its words say ("valid output 100% on every set"); the scorer
  had checked only v1.4's. An invalid or missing v1.1 answer lowers v1.1's recall and can make
  it miss a bar, which would hold v1.4 only to "no worse than v1.1" (criteria 3 and 5), so an
  unusable v1.1 run now stops the comparison instead of easing it. This is stricter.
