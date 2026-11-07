## 2026-11-05: Hosted screen of big open-weight models on the probe set (eval only) (#225)
- Changed: `eval/bench/open_bench.py` scores four large open-weight models (MiniMax M3.1 Flash,
  DeepSeek V4.1 Flash 1017, Reflection Beam 1.0 501B, Kimi K3.1 Pro) on the signed probe set,
  stance only, through OpenRouter, with the same stage-1 bars as `eval/probe/candidates.py`
  (Expert-confirms bars and 0 moved traps). Arsh asked to try models too big for a Mac. Each
  model's weights are pinned by Hugging Face commit, so one that passes can be self-hosted and
  repeat-checked (`eval/probe/aws_repeat.sh`). `candidates.verdict` takes the model names.
  Added 2026-11-07: three models that fit one 48 GB GPU at 8-bit (Qwen3.6 35B-A3B, NVIDIA
  Nemotron 3.5 Lightning 30B-A3B, Qwen3.8 27B), the realistic sizes for a hosted endpoint
  we run ourselves on one machine.
- Where: PR #225
- Verified: dry run and unit tests with a stand-in API (no network); a request with a wrong
  key reaches openrouter.ai and comes back as a failed answer. No model has been scored yet.
- Open: needs `OPENROUTER_API_KEY` in the cloud environment. Hosted answers are not
  reproducible (the provider batches requests and picks kernels), so a pass is only a reason
  to self-host. Licenses for MiniMax and Kimi are custom and unread. Names, sizes and prices
  were read from huggingface.co and openrouter.ai on 2026-11-05 and 2026-11-07. Nemotron's
  license (openmdw-1.1) is unread.
- Affects: none for the product. Eval network use: synthetic probe items and the signed stance
  prompts go to OpenRouter and the providers it routes to (data collection denied); nothing
  from a case, and `core/` makes no new network call.
- Status doc: no change
