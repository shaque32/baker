## 2026-10-31: Stance prompt v1.4 (instructions first) fails on the Mac; no prompt change
- Changed: no code. Records Arsh's Mac run of the preregistered v1.4 test
  (`eval/probe/v14/RESULTS-2026-10-31-mac.md`, criteria in `eval/probe/v14/PREREGISTERED.md`).
  Decision: no prompt change; the signed v1.1 stays. v1.4 puts the signed v1.1 wording's fixed
  instructions first so llama.cpp can reuse them between calls. It was faster but less safe on
  the same 14B: 3 scored gold contradicts items shown as supports (P103 on the signed set, T013
  and T017 on tf24) where v1.1 showed none; gold complicates or irrelevant shown as supports 28
  against 23 on the signed set, and one more on each of fresh, tf24 and r26; contradicts recall
  32 against 36 of 37; contradicts precision on the signed set 9/16 against 11/19. Supports
  recall was 45 of 45 under both. The speed criterion was not counted: one v1.1 timed-audit
  stance call gave invalid output, and the preregistered rule needs every call of both timed
  audits answered.
- Where: branch claude/project-thread-lt1vdp (results file only)
- Verified: Arsh's MacBook Air M4 24 GB, macOS 15.6.1 arm64, llama-cpp-python 0.3.36, flash
  runtime, seed 1234, n_ctx 8192, model SHA-256 500a8806...b6b81f0, commit 6018293 (the same
  tree as main 085c48e), 2026-10-31 06:49Z. Scored by `eval.probe.v14.score`; the criteria
  counts were recounted from the report's item table (same numbers). Time per call on this Mac
  (a go/no-go, not a product runtime figure): probe calls 24.1 s mean under v1.1, 14.9 s under
  v1.4; timed-audit stance calls 47.4 s against 37.5 s, v1.4 faster on 116 of 121 calls
  (median ratio 0.80).
- Open: none of the items is new to the 14B (it answered all four sets on 2026-10-22), and it
  is one sitting on one machine. v1.4's timed audit had 29 quote_failed calls against v1.1's 3;
  the pipeline also stores an "irrelevant" answer with an empty quote as quote_failed, so this
  is unexplained without the run's database. The signed v1.1 baseline itself shows 23 gold
  complicates or irrelevant items as supports on the signed set (unchanged; a claim is never
  SUPPORTED on a model's label alone, since an expert must accept its evidence).
- Affects: none (no prompt, code or claim change). No speed or accuracy claim follows from it.
- Status doc: no change
