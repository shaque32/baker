## 2026-11-05: Hosted screen of big open-weight models on the probe set (eval only)
- Changed: `eval/bench/open_bench.py` scores four large open-weight models (MiniMax M3.1 Flash,
  DeepSeek V4.1 Flash 1017, Reflection Beam 1.0 501B, Kimi K3.1 Pro) on the signed probe set,
  stance only, through OpenRouter, with the same stage-1 bars as `eval/probe/candidates.py`
  (Expert-confirms bars and 0 moved traps). Arsh asked to try models too big for a Mac. Each
  model's weights are pinned by Hugging Face commit, so one that passes can be self-hosted and
  repeat-checked (`eval/probe/aws_repeat.sh`). `candidates.verdict` takes the model names.
- Where: branch claude/project-thread-fujfti
- Verified: dry run and unit tests with a stand-in API (no network); a request with a wrong
  key reaches openrouter.ai and comes back as a failed answer. No model has been scored yet.
- Open: needs `OPENROUTER_API_KEY` in the cloud environment. Hosted answers are not
  reproducible (the provider batches requests and picks kernels), so a pass is only a reason
  to self-host. Licenses for MiniMax and Kimi are custom and unread. Names, sizes and prices
  were read from huggingface.co and openrouter.ai on 2026-11-05.
- Affects: none for the product. Eval network use: synthetic probe items and the signed stance
  prompts go to OpenRouter and the providers it routes to (data collection denied); nothing
  from a case, and `core/` makes no new network call.
- Status doc: no change
