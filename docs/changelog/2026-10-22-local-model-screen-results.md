## 2026-10-22: Newer local stance models screened; none beats the 14B (#123)
- Changed: no code change. This records the result of the screen added in #105 (Arsh asked
  whether Qwen3-14B is the best local model). Gemma 4 26B-A4B, Gemma 4 12B and Qwen3.8-27B ran
  the signed probe set, stance only, with both signed stance prompts (v1.1 and v1.2), against
  the stage 1 rule fixed before the run (four Expert-confirms bars plus 0 moved traps shown as
  supports). No candidate passed, so none goes to stage 2 and Qwen3-14B stays the local model.
- Where: PR #123
- Verified: one run per model and prompt on Arsh's Mac (macOS 15.6.1 arm64, 24 GB, commit
  f9461b9, llama-cpp-python 0.3.36, GPU memory limit raised to 19456 MB), finished
  2026-10-22 12:55Z; RESULTS.md in /mnt/project-files/baker/local-model/. Every run failed the
  contradicts precision bar (90%): Gemma 4 26B-A4B 43% (9 of 21) with both prompts, Gemma 4 12B
  48% (v1.1) and 52% (v1.2), Qwen3.8-27B 42% (v1.1) and 41% (v1.2). Each showed 1 (Gemmas) or
  2 (Qwen) moved traps as supports. Gemma 4 12B also failed supports recall (73% and 48%).
  Most wrong contradicts are the same told-frame and undated-denial items the 14B gets wrong.
  Mean seconds per stance call: Gemma 4 26B-A4B about 10, Gemma 4 12B 28 to 32, Qwen3.8-27B
  58 to 76.
- Open: one run each, no repeat. GPU memory use was not recorded (n/a in RESULTS.md). Gemma 4
  12B's slow speed relative to the 26B MoE is not explained.
- Affects: none (no capability, model, privacy or verdict change; a measured benchmark only).
- Status doc: pending: in the stance labelers section, after the paragraph ending "which is why
  the local model keeps v1.1. Source: ...", add: "Newer local models were screened on the same
  signed set (Arsh's Mac, macOS 15.6.1 arm64, 24 GB, commit f9461b9, 2026-10-22, both signed
  prompts, one run each): Gemma 4 26B-A4B, Gemma 4 12B and Qwen3.8-27B all failed the
  contradicts precision bar (41% to 52%, bar 90%) and showed 1 or 2 moved traps as supports.
  None passed, so Qwen3-14B stays the local model. Source:
  `/mnt/project-files/baker/local-model/2026-10-22-mac-screen-RESULTS.md`."
