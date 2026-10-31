## 2026-10-31: Training chats for a fine-tuned local stance model
- Changed: `eval/stancedata/sft.py` 1.0.0, eval only, no model trained or loaded. It turns the
  generated training items (eval/train, ids T...) into chats for fine-tuning the Qwen3-4B LoRA
  arm that `eval/stancedata/GO_BAR.md` (signed 2026-10-14) already names: the user turn is the
  stance prompt `eval.probe.run_probe` sends for the item (layout product_members, the signed
  prompt by default), the assistant turn the product's JSON answer (gold stance, the item's
  quote, the generator's rationale). An item whose answer would fail the product's checks
  (stance output shape, quote verbatim in the record, words the tool never says) is left out
  and counted; held-out items (ids D... and H...) are refused. `--overlap` takes the overlap
  check's report.json and accepts it only if it passed on this exact items file (by SHA-256),
  against the test data and against held-out files; the manifest records it, and a training run
  uses only chats whose manifest has it (GO_BAR.md bar 1). For that, `eval.stancedata.
  contamination` now writes report.json as an object naming every file it checked by SHA-256,
  with the pass and every flag (no code read the old list). Why: Arsh asked on 2026-10-30
  for a fine-tuned, smaller and faster local model; stance labelling is about 74% of local model
  time (case04, estimated from call timestamps).
- Where: PR #185
- Verified: tests/test_stancedata_sft.py (5 tests: generated items and synthetic overlap
  reports, no model). On the full training file
  (`python -m eval.train.generate --n 12000 --seed 1`, eval.train 1.5.0 and eval.train.baker
  1.4.1, 19,250 items): 19,250 chats, none left out (complicates 8,377, supports 5,206,
  contradicts 3,544, irrelevant 2,123); prompts average 4,131 characters, at most 4,661.
- Open: no training run yet, and no hardware chosen. The generated items carry 0 to 7 context
  messages (most 1 to 6) while real audit prompts carry about 23 (case04), and they have no
  told-frame family, where the earlier small model (run 8, 2026-10-16) missed 6 of its 7 traps;
  both are later steps. Any candidate must pass GO_BAR.md (no overlap; on the signed probe set
  and the held-out test split, supports recall and contradicts precision at least 0.90 and no
  contradicting record or moved trap shown as supports) and the repeat check before a swap.
  The overlap check was not re-run on the real files for this change.
- Affects: none (training data only)
- Status doc: no change
