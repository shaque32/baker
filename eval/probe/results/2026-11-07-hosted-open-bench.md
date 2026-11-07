# Hosted open-weight screen on the signed probe set and synthetic case01 (2026-11-07)

Eval only, synthetic data only. Code: `eval/bench/open_bench.py` (#225, branch
claude/project-thread-fujfti at 7c7ee91). Ran 2026-11-07 06:22Z-10:30Z from a cloud container
through OpenRouter (temperature 0, seed 1234, strict JSON schema, reasoning effort medium with
the reasoning left out, 8,000-token cap, data collection denied, 8-bit or wider weights unless
noted). Bars fixed before the run (eval/probe/candidates.py stage 1). Hosted answers are not
reproducible: each model was served by many providers, so a pass is only a reason to self-host
the pinned weights and test them there. Total OpenRouter spend for the screen, case01 runs and
the agents bench: about $15.

## Stage 1: signed probe set, stance only, layout product_members, 105 items asked twice

| model | prompt | supports recall | contradicts precision [Wilson 95%] | contradicts as supports | moved traps as supports | valid | stage 1 | median s/call | cost |
|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash-1017 | v1.1 | 100% | 52% of 21 [32%-72%] | 0 | 0 | 100% | fail | 3.3 | $0.11 |
| deepseek-v4.1-flash-1017 | v1.2 | 100% | 92% of 12 [65%-98%] | 0 | 0 | 100% | pass | 3.2 | $0.11 |
| gpt-oss-120b | v1.1 | 100% | 42% of 26 [26%-61%] | 0 | 0 | 100% | fail | 1.7 | $0.03 |
| gpt-oss-120b | v1.2 | 100% | 46% of 24 [28%-65%] | 0 | 1 | 100% | fail | 1.7 | $0.03 |
| kimi-k3.1-pro | v1.1 | 100% | 55% of 20 [34%-74%] | 0 | 0 | 100% | fail | 3.6 | $1.27 |
| kimi-k3.1-pro | v1.2 | 100% | 100% of 10 [72%-100%] | 0 | 0 | 100% | pass | 2.9 | $1.21 |
| llama-4-maverick | v1.1 | 100% | 55% of 20 [34%-74%] | 0 | 5 | 100% | fail | 1.3 | $0.07 |
| llama-4-maverick | v1.2 | 100% | 55% of 20 [34%-74%] | 0 | 4 | 100% | fail | 1.2 | $0.08 |
| minimax-m3.1-flash | v1.1 | 100% | 50% of 22 [31%-69%] | 0 | 2 | 100% | fail | 0.6 | $0.03 |
| minimax-m3.1-flash | v1.2 | 100% | 55% of 20 [34%-74%] | 0 | 2 | 100% | fail | 0.6 | $0.02 |
| mistral-large-4 | v1.1 | 100% | 46% of 24 [28%-65%] | 0 | 0 | 100% | fail | 27.3 | $1.50 |
| mistral-large-4 | v1.2 | 97% | 85% of 13 [58%-96%] | 0 | 0 | 98% | fail | 30.9 | $1.67 |
| nemotron-3-ultra | v1.1 | 100% | 53% of 19 [32%-73%] | 0 | 1 | 100% | fail | 1.4 | $0.12 |
| nemotron-3-ultra | v1.2 | 100% | 52% of 21 [32%-72%] | 0 | 1 | 100% | fail | 1.2 | $0.12 |
| nemotron-3.5-lightning | v1.1 | 79% | 50% of 14 [27%-73%] | 0 | 0 | 85% | fail | 15.3 | $0.22 |
| nemotron-3.5-lightning | v1.2 | 91% | 86% of 7 [49%-97%] | 0 | 0 | 91% | fail | 14.4 | $0.20 |
| qwen3.6-35b-a3b | v1.1 | 100% | 42% of 26 [26%-61%] | 0 | 1 | 100% | fail | 17.6 | $0.41 |
| qwen3.6-35b-a3b | v1.2 | 100% | 48% of 23 [29%-67%] | 0 | 1 | 100% | fail | 13.5 | $0.42 |
| qwen3.8-27b | v1.1 | 100% | 46% of 24 [28%-65%] | 0 | 0 | 100% | fail | 8.7 | $0.36 |
| qwen3.8-27b | v1.2 | 100% | 79% of 14 [52%-92%] | 0 | 0 | 100% | fail | 11.2 | $0.38 |

Not screened: Reflection Beam 1.0 501B (only 4-bit providers). Nemotron 3 Ultra ran at 4-bit (the
only providers that honor seed and schema) and Mistral Large 4 on Mistral's own API (precision
not stated); both are recorded in the model list. Qwen3.6 v1.2 was restarted once after the run
was stopped by a time limit; the stopped partial run is not scored.

## Stage 2: synthetic case01, real pipeline, simulated expert, cloud prompt v1.2

| model | verdict accuracy (bar 80%) | false supported (bar 0) | stance calls | wall time | cost |
|---|---|---|---|---|---|
| DeepSeek V4.1 Flash 1017 | 95% | 0 | 493 | 30 min | $0.36 |
| Kimi K3.1 Pro | 95% | 0 | 493 | 34 min | $3.71 |

Both miss only C19, as Opus 5.5 did on 2026-10-20 (95%, 0 false supported). DeepSeek had 2 of
493 calls cut off at the token cap (dropped, never a label).

## What this does not show
- Nothing about the self-hosted model: weights, quantization and engine differ by provider.
- Contradicts precision rests on 10 to 12 answers per passing model; the passes were picked
  from 19 model and prompt runs on the same set, so fresh held-out items must confirm them.
- No change to the product: the local model is still Qwen3-14B and the only cloud option is
  Opus 5.5. Model choice for plan C (self-hosted endpoint) is recorded in the project's plan.
