## 2026-11-05: Hosted screen of open-weight models on the probe set and case01 (eval only) (#225)
- Changed: `eval/bench/open_bench.py` scores hosted open-weight models on the signed probe set,
  stance only, through OpenRouter, with the same stage-1 bars as `eval/probe/candidates.py`
  (Expert-confirms bars and 0 moved traps), and with `--case` runs synthetic case01 through the
  real pipeline with the hosted model as stance labeler on the cloud prompt (v1.2). Arsh asked
  to try models too big for a Mac, then which one could serve a self-hosted endpoint (plan C).
  Eleven models: MiniMax M3.1 Flash, DeepSeek V4.1 Flash 1017, Reflection Beam 1.0 501B (not
  screened: 4-bit providers only), Kimi K3.1 Pro, Qwen3.6 35B-A3B, NVIDIA Nemotron 3.5
  Lightning, Qwen3.8 27B, gpt-oss-120b, Nemotron 3 Ultra, Mistral Large 4, Llama 4 Maverick.
  Each model's weights are pinned by Hugging Face commit, so one that passes can be self-hosted
  and repeat-checked (`eval/probe/aws_repeat.sh`). A model with no thinking mode is not asked to
  reason; a model no 8-bit provider serves may widen only its own precision list, recorded in
  the model list. `candidates.verdict` takes the model names.
- Where: PR #225
- Verified: unit tests with a stand-in API (no network). Run 2026-11-07 from a cloud container
  (results: `eval/probe/results/2026-11-07-hosted-open-bench.md`): only DeepSeek V4.1 Flash
  (contradicts precision 92% of 12, Wilson 65%-98%) and Kimi K3.1 Pro (100% of 10, 72%-100%)
  pass stage 1, both with prompt v1.2 only; every other model misses the 90% contradicts
  precision bar (42% to 86%) and several show moved traps as supports. On synthetic case01
  both score 95% with 0 false supported (Opus 5.5 on 2026-10-20: 95%, 0). About $15 of
  OpenRouter spend in total.
- Open: hosted answers are not reproducible (many providers per model, unknown kernels and
  quantization), so a pass is only a reason to self-host the pinned weights and re-run every
  bar there, plus fresh held-out items; the passes were picked from 19 model and prompt runs on
  about 10 to 12 contradicts answers each. Licenses for MiniMax, Kimi, Nemotron, Mistral and
  Llama are custom and unread. Names, sizes and prices read from huggingface.co and
  openrouter.ai on 2026-11-05 and 2026-11-07.
- Affects: none for the product (the local model stays Qwen3-14B, the only cloud option stays
  Opus 5.5). Eval network use: synthetic probe items, synthetic case01 prompts and the signed
  stance prompts go to OpenRouter and the providers it routes to (data collection denied);
  nothing from a real case, and `core/` makes no new network call.
- Status doc: pending: in section 7 (Benchmarks and hardware), after the paragraph on newer
  local models screened on 2026-10-22, add: "Hosted open-weight models were screened on the same
  signed set through OpenRouter (cloud container, 2026-11-07, both signed prompts, one run each;
  eval only, #225; hosted answers are not reproducible): of eleven models, only DeepSeek V4.1
  Flash (contradicts precision 92% of 12) and Kimi K3.1 Pro (100% of 10) passed stage 1, both
  with prompt v1.2; both scored 95% with 0 false supported on synthetic case01. Neither has been
  self-hosted or repeat-checked. Source: `eval/probe/results/2026-11-07-hosted-open-bench.md`."
