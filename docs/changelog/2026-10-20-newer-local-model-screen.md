## 2026-10-20: Screen for newer local stance models, and a guard for thinking templates (#105)
- Changed: Arsh asked whether Qwen3-14B is the best local model. This PR adds a Mac screen
  (`eval/probe/candidates.py`, `eval/probe/mac_candidates.sh`) of three newer Apache-2.0 models
  that fit 24 GB: Gemma 4 26B-A4B and Gemma 4 12B (Google's QAT q4_0 GGUFs) and Qwen3.8-27B
  (unsloth UD-IQ4_XS). Each is pinned by repo revision and sha256. Each runs the signed probe
  set, stance only, with both signed stance prompts (v1.1 and v1.2). The stage 1 pass rule (four
  Expert-confirms bars plus 0 moved traps shown as supports) was fixed before any run. In
  `core/llm/runtime.py`, the "no-think" chat template now also accepts Qwen3.5-and-later
  templates, which close an empty thinking block in place of the one they open by default (and,
  for Qwen3.8, drop the effort system turn). A model whose own template ends the generation
  prompt inside an open thinking block now refuses to load on the "gguf" template, instead of
  labelling with its answer inside that block.
- Where: main (#105, merged 2026-10-20)
- Verified: unit tests for both template shapes and the guard. Checked through
  llama-cpp-python 0.3.36's own formatter against the chat templates embedded in the four GGUF
  files (Qwen3-14B Q4_K_M: loads and no-think unchanged; Qwen3.8-27B: refused on "gguf", loads
  on "no-think"; both Gemma 4 files: load on "gguf"). No model was run. The screen has not run.
- Open: all accuracy and speed figures for the candidates are unmeasured until Arsh's Mac run.
  Vendor benchmark scores were measured with thinking on, and Baker runs with it off. Stage 2
  (repeat run, then case01) is not in this PR. The 27B needs the macOS GPU memory limit raised
  (the script does it with sudo until reboot).
- Affects: capabilities (a local model with a thinking-first template is refused on the default
  template); no change to privacy, verdicts, prompts or gold.
- Status doc: no change
