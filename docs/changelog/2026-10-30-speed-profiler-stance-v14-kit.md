## 2026-10-30: Speed work, step 1: a run profiler and the stance v1.4 test kit (#PR)
- Changed: Two eval-only tools for making the local audit faster without changing what it
  decides; no product behavior changes.
  - `eval/run_profile.py` 1.0.0 (`python -m eval.run_profile --db <case.db>`): read-only, no
    model. For each model job: calls, wall time between consecutive calls (from
    `model_calls.at_utc`; the database stores no per-call seconds, so a gap also holds the code
    between two calls, and a gap over 600 s is not counted), mean and median seconds, and how
    much prompt text a call shares with the one before it (what llama.cpp's prefix reuse can
    skip) or with every prompt of its run at the end (fixed text after the case data, which no
    call can reuse). Stance answers split by the code checks on the assumption, and calls on a
    record a passed check itself cited. Aggregates only; it refuses a case02 path.
  - Stance v1.4 test kit: `eval/probe/stance_v1_4_draft.md` is the signed v1.1 lines, none
    added or reworded, with the fixed instructions moved ahead of the claim, assumption, record
    and context, so calls can reuse them. Not signed and not used by the product.
    `eval/probe/v14/PREREGISTERED.md` fixes the criteria before any call (no new trap shown as
    supports, no worse than v1.1 on the signed bars, recall within one item, at least 15% less
    time per stance call on a timed case01 audit); `bash eval/probe/mac_v14.sh` runs it on the
    Mac (about 3 to 4 hours) and `eval/probe/v14/score.py` decides.
- Where: branch claude/project-thread-lt1vdp
- Verified: tests/test_run_profile.py and tests/test_stance_v14_order.py (synthetic rows and a
  stand-in model). The profiler on the case04 database from Arsh's Mac go/no-go run (main
  67dabdb, MacBook Air M4 24 GB, Qwen3-14B Q4_K_M, flash runtime, 2026-10-29, reported): about
  4.9 h of model time on the first pass, 3.9 h on the repeat pass. First pass: stance 283 calls,
  3.62 h, mean 46.0 s (median 43.1 s); testability 66 calls, 0.72 h; assumptions 48 calls,
  0.56 h. 168 of 283 stance answers (59%) were "irrelevant"; 170 of 283 were on an assumption
  whose code checks all passed, 30 of them on a record the check cited. Stance prompts average
  6,557 characters: 13% shared with the previous call, 40% fixed text after the case data.
  The v1.4 Mac run has not happened: whether v1.4 is faster or labels the same is unverified.
- Open: times are wall gaps, not per-call seconds; per-call seconds and token counts would need
  new `model_calls` columns (schema, Arsh's to sign), not proposed here. Character shares stand
  in for tokens. One run on one machine; not measured on Windows or NVIDIA. If v1.4 passes, it
  still needs Arsh's signature and a new 14B repeat check before the product uses it.
- Affects: performance (measurement only)
- Status doc: pending: in section 7's "Local 14B speed" list, add "Measured 2026-10-29 (reported,
  case04 go/no-go Mac run at 67dabdb, MacBook Air M4 24 GB, flash): about 4.9 h of model time
  for a 48-claim synthetic case, 74% of it stance labelling (283 calls, mean 46 s); 59% of
  stance answers were irrelevant. From `python -m eval.run_profile`." Under the signed prompts
  line, note "stance v1.4 draft (eval/probe/stance_v1_4_draft.md): v1.1 reordered for speed,
  not signed, Mac test not run."
