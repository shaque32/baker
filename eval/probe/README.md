# GPU test and probe

Checks whether a local model can run Baker's reviewer and stance steps well enough, on the
machine that will run Baker. Everything here is synthetic.

## Files
- `smoke_reviewer.jsonl`, `smoke_stance.jsonl`: provisional items written by Claude so the test
  can run before the signed probe set exists. Rebuild with `python -m eval.probe.build_smoke`.
  Results on them are provisional; the signed probe set (thread 3, signed by Arsh) replaces them.
- `stance_draft.md`: probe-only stance prompt. The product prompt is human-owned in
  `core/audit/prompts/`.
- The reviewer prompt is read from `core/audit/prompts/reviewer.md` unchanged.

## Thread 3's probe set
`python -m eval.probe.from_draft <path to eval/probe_draft/probe_draft.jsonl>` writes
`eval/out/probe_items/reviewer.jsonl` and `stance.jsonl`; pass them to `run_probe` with
`--reviewer` and `--stance`. Results stay provisional until Arsh signs the items.

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
