# GPU test and probe

Checks whether a local model can run Baker's reviewer and stance steps well enough, on the
machine that will run Baker. Everything here is synthetic.

## Files
- `smoke_reviewer.jsonl`, `smoke_stance.jsonl`: provisional items written by Claude so the test
  can run before the signed probe set exists. Rebuild with `python -m eval.probe.build_smoke`.
  Results on them are provisional; the signed probe set (thread 3, signed by Arsh) replaces them.
- `stance_draft.md`: the old probe-only stance prompt, kept for comparison. The probe now scores
  the signed product prompt `core/audit/prompts/stance.md` by default (`--stance-prompt` picks
  another).
- The reviewer prompt is read from `core/audit/prompts/reviewer.md` unchanged.

## Signed probe set (thread 3)
`run_probe --probe-set <eval/probe_draft/probe_draft.jsonl>` scores the signed set directly.
Only signed, undisputed items count toward a pass bar; disputed items and drafts are scored
and reported under `not_gated` (Arsh's rule, 2026-10-07). Accuracy alone misleads: a reviewer
that dismisses everything scores about 65% on the gated set, so read the false-accept rate and
the clear-accept rate (support recall) next to it.

## Run on a Mac (Apple silicon)
1. `python3 -m venv .venv && source .venv/bin/activate`, then `pip install -e ".[dev,local]"`.
   On Apple silicon llama-cpp-python builds with Metal by default, so the model runs on the GPU.
   Xcode command line tools are needed for the build (`xcode-select --install`).
2. Pick models that fit in memory: 16 GB fits 8B models at Q4/Q5; 24 GB or more fits 14B at Q4_K_M.
3. Steps 3 to 5 below are the same. Accuracy results carry over to Windows; speed does not.

## Run on the GPU PC (Windows)
1. `python -m venv .venv` and `.venv\Scripts\activate`, then `pip install -e ".[dev]"`.
2. llama-cpp-python with CUDA. Prebuilt wheel first:
   `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124`
   (pick the cuXXX that matches `nvidia-smi`). Otherwise build it: install VS Build Tools and the
   CUDA toolkit, `set CMAKE_ARGS=-DGGML_CUDA=on`, `pip install llama-cpp-python --no-binary :all:`.
3. Download GGUF files to a folder outside the repo. Check each model's license on its original
   model card. Only permissive licenses (Apache-2.0, MIT).
4. Copy `models.example.json` to `models.local.json` (git-ignored) and list each file.
5. `python -m eval.probe.run_probe --models eval/probe/models.local.json --repeat 2`

Output goes to `eval/out/probe/`: `summary.md`, `summary.json`, and one `<model>.calls.jsonl` per
model with every raw output, including the ones that failed to parse.

## Pass bars (wave2-consensus.md section 4)
valid output 100%, quote check >= 95%, "supports" precision >= 95% and recall >= 90%,
zero reviewer false accepts on overreach items, identical output on a repeat run.
An invalid reviewer output counts as a dismissal, and a stance whose quote is not verbatim is
dropped, so neither can turn into a false "supported".

## Cloud upper bound (eval only)
`pip install -e ".[bench]"`, then `python -m eval.bench.claude_bench`. Sends only these synthetic
items to the Claude API. Agreeing with Claude does not count as being right.

## Wave 3: which model the alpha ships with (expert confirms)
Under rules 0.2.0 the expert accepts the key evidence of every SUPPORTED claim and the AI
reviewer decides nothing (the product leaves it off unless `baker audit --ai-review`). So the
model is chosen on how well its stance labels put the right evidence in front of the expert,
not on reviewer precision. `run_probe --stance-only` prints an "Expert confirms" table:

| criterion | bar | why |
|---|---|---|
| supports recall (quote verified) | >= 90% | a missed or misquoted support never reaches the expert |
| contradicts precision | >= 90% | a "contradicts" on an observed record makes the claim contradicted with no expert step (rule 1b) |
| contradicts shown as supports | 0 | the expert would see contradicting evidence offered as support |
| valid output | 100% | |

Decision rule, fixed before the 8B and 14B were re-run (2026-10-08): ship the fastest model
that meets all four on the signed, undisputed items; among those, the higher supports recall.
If none meets them, ship the one with the fewest contradictions shown as support, then the
higher supports recall, and say plainly which bar it misses. Supports precision is expert
load (items to dismiss), reported, not gated.

Speed: `time_case` audits case01 on each model (cold run, then the rerun an expert triggers
after accepting evidence, which reuses stored outputs and costs no model calls), counts model
calls per claim, projects a full-case time from the measured seconds per call, and reports
how much gold key evidence was surfaced next to how much retrieval reached at all.
`time_case --dry-run` counts the calls with no model. `claim_recall` scores
`baker claims propose` against the 20 case01 gold claims (target 90%, not gating).

One command runs all three on a Mac and prints a file to paste back:

    bash eval/probe/mac_wave3.sh

On 16 GB it uses n_ctx 4096 and three claims (C02, C05, C12), projected to the whole case; on
more memory it runs the whole case at n_ctx 8192. `CLAIMS=`, `NCTX=`, `MODELS=` and
`PROBE_SET=` override; the probe set defaults to the signed `eval/gold/probe/probe.jsonl`.
