# Go bar for Baker's own stance model

Frozen 2026-10-09, before any training data existed. The same rule is code in `gobar.py`
(`decide()`); a test keeps the two in step. This file changes only by Arsh's decision, recorded
below with the reason, and never for a candidate whose test result is already known.

## The question it answers

Should Baker replace the prompted Qwen3-14B stance labeler with a model trained on Baker's own
synthetic data (first a small classifier with a span head, mDeBERTa-v3-base or XLM-R; second a
Qwen3-4B LoRA)? Under rules 0.2.0 the expert accepts the evidence of every SUPPORTED claim, so
the model decides which evidence the expert sees. A swap must lose nothing on the bars that
protect that, and must be much faster.

## Go only if all of these hold, for one model file (SHA-256 recorded)

1. **No overlap.** `python -m eval.stancedata.contamination` passes on the exact training file
   the model was trained on, against the probe set, case01, case02 and the held-out set.
2. **Signed probe set.** On the gated items (P001 to P088, signed and undisputed: 78 items, 8
   gold contradicts after the 2026-10-14 relabel), scored by `eval.probe.run_probe
   --stance-only` or `eval.stancedata.score`:
   - valid output 100%;
   - supports recall at least 90% (a label whose quote is not verbatim in the record is dropped
     and counts as a miss);
   - contradicts precision at least 90% (the model must say "contradicts" at least once, so the
     precision exists);
   - zero contradicting records shown as "supports";
   - zero items of the trap families guide v0.3 moved to complicates (time_mismatch,
     sender_mismatch, speaker_mismatch, later_correction) shown as "supports".
3. **Held-out test split.** The same four bars on its gated items: at least 1,000 items with at
   least 420 gold contradicts, so zero contradicting records shown as "supports" bounds that
   error rate under about 0.7% (95% confidence). The held-out items count as gated only after
   Arsh's random 100-item sample passes (LABELING_GUIDE.md, "How the labels are checked");
   until then every held-out score is provisional and cannot produce a go. The moved-trap bar
   applies here too.
4. **At least 5 times faster.** At most 4.52 seconds per stance decision on case01, measured on
   Arsh's 24 GB Mac, against the 14B's measured 22.61 seconds per call on the same Mac
   (2026-10-08).
5. **Baker's real pipeline on the hidden case.** The candidate is Baker's stance labeler
   (eval/stancemodel ClassifierLabeler). It runs on case02 with the case's assumption sheet,
   Baker's retrieval, quote check, checks and rules, then the simulated expert and the
   merge-gate scoring, the same way `make eval-real` scores case01 for the 14B. It must have 0
   false supported, 0 false contradicted (a claim decided contradicted whose gold verdict is
   supported or unproven) and a verdict accuracy of at least 0.80, the case01 merge-gate
   threshold. It is scored once per finished candidate, aggregate numbers only, and logged in
   TEST_LOG.md together with that candidate's test-split scoring, so it shares the
   three-candidate limit. Nobody reads per-claim output.

If any condition fails, the answer is no-go, and Baker keeps the prompted model the "Model speed
and claim proposal" thread picks.

## Reported, never deciding

- **Overreach traps shown as "supports"**, on both test sets. Zero is required later, by
  CLAUDE.md, before anyone may propose AI-only coverage again, and that also needs a signed
  change to `core/audit/rules.py`. It does not decide this swap, because under rules 0.2.0 an
  expert still accepts every piece of supporting evidence.
- Supports precision (how many items the expert has to dismiss), per-family and per-language
  confusion, disputed items, the dev split, `make eval-real` and the small model's pipeline
  run on case01 (a development check).

## Rules

- **Iterate on the dev split** (ids D...). The test split (ids H...) is scored only for a
  go or no-go run of a finished candidate, and each such run is logged in `TEST_LOG.md` (date,
  model SHA-256, training file SHA-256, result). After three logged candidates the test split is
  retired: a new one is generated from a new seed and a new 100-item sample is signed.
- **Never train on test data**: not the probe set, case01, case02, the held-out set, or text
  copied from any of their failures.
- **Labels change only when Arsh decides an answer was wrong**, never because a model got it
  wrong. A changed label is logged with its reason.
- **One model file per decision.** The model that passed is the model that ships, by SHA-256.

## Decisions log

- 2026-10-09: frozen as above (assessment in `/mnt/project-files/baker/roadmap/own-model-assessment.md`,
  Arsh's go-ahead to start in the "Faster than the 14B" thread).
- 2026-10-14 (Arsh, "approved" in the "Custom model for Baker" thread, signing guide v0.3; no
  candidate had a test result): guide v0.3 moved four trap families to complicates, so the
  zero-tolerance bar no longer covered them; a moved trap shown as supports now fails bars 2
  and 3. The probe minimum drops from 16 to 8 gold contradicts with the 8 relabeled items.
  Condition 5 added because the case01 shakedown showed a model can pass bars 2 and 3 and
  still mislabel what Baker really sends it.
