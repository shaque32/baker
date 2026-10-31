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
shorter context, not for it. Each replay folder holds one replay: a stopped replay resumes only
when the model file, its settings, the prompt, the context size, the recorded calls and the
exact prompts to send are all the same (`identity.json`), and anything else is refused.

## 8 messages either side is recommended only if all hold (signed_w8 against signed_w20)
1. Both ran the same calls of the same recorded audit and sample, on the recorded model file,
   with the same settings and the same replay version.
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
7. Supports lost on at most 5% of the calls the 20-message replay labels supports (2 of the
   sample's 49 recorded supports). This is the supports-recall direction: a lost label is
   evidence the expert no longer sees. Gold key records may not change at all (criterion 5).
8. No assumption loses every supports label it had with 20 messages.
If any fails, the context stays at 20 messages and every number goes to Arsh as it is.

A pass is not evidence of no effect. The sample is one already-spent case, one sitting and a
few dozen calls in each direction that matters. With the sample's recorded labels, zero new
supports on the 116 calls that were not supports still allows a rate up to about 3.2% (95%
Wilson upper bound), zero changes on the 23 complicates or contradicts calls up to about 14%,
and zero changes on the 20 key-record calls up to about 16%. The report prints each count out
of the calls it could move, with its upper bound.

Reported beside the criteria, never changing them: each count with its 95% Wilson upper bound;
every call where the 20-message replay's answer is not the recorded one, byte for byte, and
every label change between the two replays (calls by seq, claim and record id, no text); the
label changes by direction; the per-call spread and the call-by-call time ratio; and the run
record (the model's SHA-256, seed, context size, runtime, tokens per second and peak resident
memory).

## After a pass
A PR shows 8 messages either side in the local stance prompt only (the `render_for` call in
`core/audit/stance.py`, which the cloud labeler shares today, so the PR separates them).
Retrieval (`DEFAULT_WINDOW`), the cloud labeler and everything else keep 20: nothing here
tested them. The eval gate (`make check`) must still pass, and the 14B repeat check runs again,
because the report states the repeat result for the prompts the product sends. It is a
meaningful change with its own changelog entry; no signed file changes.

That PR is a labeling change, so it needs the eval gate on its own evidence, not on this
replay's: the signed probe set on the 14B (whose 2 to 6 line contexts do not exercise the
window, so it shows only that nothing else moved) and a fresh synthetic audit case that is not
case04, both reported with every failed item, Wilson intervals, the model's SHA-256, seed,
tokens per second and peak memory.

## Commitments
No criterion edit after seeing any replayed answer. All numbers published, including any that
get worse.

## Edits before any replay (2026-10-31, review of PR #185)
Made before any replay ran, each one stricter: criterion 1 also needs the same recorded audit,
sample, settings and replay version; criteria 7 and 8 (supports lost) were added; each count
is reported with its 95% Wilson upper bound; the report lists every call behind criterion 2
and every label change; a stopped replay resumes only as the same replay; and the PR that
adopts a pass needs the eval gate on a fresh synthetic case.
