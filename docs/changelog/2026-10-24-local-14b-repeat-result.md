## 2026-10-24: Local 14B repeat check passes on one Mac; the report says so for that file (#136)
- Changed: records the first repeat check (`eval/probe/repeat_check.py`, #126) of the local
  Qwen3-14B Q4_K_M (`500a8806…b81f0`) with its own stance prompt v1.1, run on Arsh's MacBook Air
  M4 24 GB, macOS 15.6.1, llama-cpp-python 0.3.36, 2026-10-24 (run at commit `f07aa62`; summary
  in `eval/probe/results/2026-10-24-qwen3-14b-repeat-mac.md`). On the GPU every answer was
  byte-identical: asked twice with the model loaded once 105 of 105, a fresh load 105 of 105, two
  full audits of synthetic case01 85 of 85 model calls with the same 75 evidence rows. CPU only
  (first 20 probe items) kept all 20 stances and quotes; 7 rationales were worded differently.
  Report 0.15.0 (`core/report/html.py`, `REPEAT_TESTED`): for a stance run with exactly this
  model file and this stance prompt, "What can be checked again" states that measured result and
  its limits (one Mac; GPU off changes rationale wording; other machines and runtime versions
  not tested) instead of "No claim is made that a re-run gives identical labels"; any other
  file or prompt keeps the old sentence. Why: court-defensibility plan, the 14B repeat check
  before local mode may be called reproducible (Arsh, 2026-10-20).
- Where: PR #136
- Verified: the Mac run above (one run, synthetic probe and case01 only); new tests in
  `tests/test_report_consistency.py` (the tested pair prints the statement, an untested file or
  prompt still makes no claim, the key matches the model pinned in `packaging/windows/pins.json`
  and the signed stance prompt, so a prompt or pin change drops the statement); `make check`
  (numbers in the PR).
- Open: not measured on a Windows NVIDIA PC (the pilot setup), another Mac, another
  llama-cpp-python version or real exports; the run's runtime version is not stored with each
  case run (the installers pin 0.3.36, and the build label names the build), so the report
  cannot yet show that a case ran on the tested runtime; a 2026-10-19 same-process repeat with
  prompt v1.2 changed one rationale of 105, so byte-identity is not general across prompts.
- Affects: customer-facing claims (the report states a measured, scoped re-run result for the
  default local model); performance (a measured benchmark)
- Status doc: pending: section 3, after "and identical calls reuse stored output." add "A repeat
  check (2026-10-24, MacBook Air M4, macOS 15.6.1, llama-cpp-python 0.3.36) found the 14B's
  stance answers with prompt v1.1 byte-identical on the GPU when asked again, after a fresh load
  and across two case01 audits (105/105, 105/105, 85/85); CPU only kept every stance and quote
  but reworded 7 of 20 rationales. Other machines and runtime versions are not measured."
  Section 7, after the "Local 14B speed" list add a "**Local 14B repeat check (2026-10-24)**"
  paragraph with the same numbers and source `eval/probe/results/2026-10-24-qwen3-14b-repeat-mac.md`.
  Section 12, after "and that UFDR or AXIOM imports are verified." add "Local labels may be
  described as regenerating exactly only for the 14B with stance prompt v1.1 on the tested Mac
  setup; not across machines, and never for a cloud model."
