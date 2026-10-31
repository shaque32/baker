# A shorter context in the stance prompt: replay test plan, written before any replay (2026-10-31)

Thread "Plan a faster, sharper audit engine", steps 2 and 3 of
`/mnt/project-files/baker/plans/fast-sharp-engine.md`. Arsh said "alr run it" to the plan on
2026-10-30 23:34Z. Synthetic data only. $0 API spend: everything runs on the Mac's local model.

## Why
The stance prompt shows the record with 20 messages either side (`core/audit/context.py`). On
the recorded case04 audit the context is about 46% of an average stance prompt. Showing 8
messages either side cuts the prompt by about 18% (5 either side: about 24%), measured with
`python -m eval.probe.replay check` on the recorded prompts, no model. The probe sets cannot
test this: their contexts are 2 to 6 lines. Only real audit prompts can, so this test replays
them.

## What is replayed
The first pass of Arsh's case04 go/no-go Mac run (main 67dabdb, 2026-10-29,
`eval/out/case04/rubber_stamp/testability/case04.db`). case04 was spent as a held-out case on
2026-10-30, so a result here is not a held-out result. Only calls whose signed 20-message prompt
today's code rebuilds byte for byte are replayed (279 of 283 on 2026-10-31). `--sample 2`
keeps every second assumption, in the order the run first labelled it, with all of its calls:
9 of 17 assumptions on 8 claims, 167 calls, of which 165 rebuild. Their recorded labels: 49
supports, 19 complicates, 4 contradicts, 93 irrelevant; 20 of the calls are on gold key records.

## Runs (Arsh's Mac, `bash eval/probe/mac_replay.sh`, one sitting, flash runtime)
1. `signed_w20`: the signed prompt, 20 messages either side. This is the recorded audit itself:
   the same-sitting timing baseline, and a repeat check on real audit prompts.
2. `signed_w8`: the signed prompt, 8 messages either side.
The calls keep the recorded order, so llama.cpp's prefix reuse works as it did in the audit.
`signed_w8` always runs after `signed_w20`, so a Mac that slows as it warms counts against the
shorter context, not for it.

## 8 messages either side is recommended only if all hold (signed_w8 against signed_w20)
1. Both ran the same calls on the recorded model file.
2. The 20-message replay repeats the recorded answer, byte for byte, on at least 99% of calls.
   Otherwise the replay is not a faithful baseline and nothing is decided.
3. No call newly labelled supports. No slack: this is the direction that can end in a false
   supported.
4. No call leaves complicates or contradicts (a label that holds a claim back until an expert
   dismisses it).
5. No gold key record (`eval/gold/case04/gold.jsonl`, key_evidence) changes its label.
6. Every call of both replays answered (no runtime error, no invalid output), and mean
   seconds per call at least 10% below the 20-message replay's. A failed call comes back at
   once and still counts in the mean, so it must never pass as speed.
If any fails, the context stays at 20 messages and every number goes to Arsh as it is.

Reported beside the criteria, never changing them: every label change by direction (calls by
seq and record id, no text), supports lost, the per-call spread and the call-by-call time
ratio, and the run record (the model's SHA-256, seed, context size, runtime, tokens per second
and peak resident memory).

## After a pass
A PR shows 8 messages either side in the local stance prompt only (the `render_for` call in
`core/audit/stance.py`, which the cloud labeler shares today, so the PR separates them).
Retrieval (`DEFAULT_WINDOW`), the cloud labeler and everything else keep 20: nothing here
tested them. The eval gate (`make check`) must still pass, and the 14B repeat check runs again,
because the report states the repeat result for the prompts the product sends. It is a
meaningful change with its own changelog entry; no signed file changes.

## Commitments
No criterion edit after seeing any replayed answer. All numbers published, including any that
get worse.
