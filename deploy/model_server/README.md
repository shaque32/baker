# Mabillon model server (plan C), not in use yet

The GPU server that plan C's app will send filled-in prompts to: our own machine running the
pinned open-weight model, one request at a time, keeping nothing. Nothing in the app calls it
yet. `core/` stays network-free except the Anthropic stance call until Arsh signs the CLAUDE.md
network change, and the server must pass the consensus conditions before any real case
(`/mnt/project-files/baker/model-pick-2026-11-07/CONSENSUS.md` in the project files).

## What is pinned (`pins.json`)
- Model: DeepSeek V4.1 Flash 1017, `deepseek-ai/DeepSeek-V4.1-Flash-1017` at commit
  `1bae0e1088993b9b82de08f59de5be5a34e42170` (MIT). Per its `config.json` (read 2026-11-07) the
  dense weights are FP8 and the experts FP4. Hugging Face lists about 763B stored values,
  roughly 765 GB on disk. That does not match one blog's 510 GB, so check it on the first boot.
- Engine: vLLM 0.32.0 (released 2026-10-18). DeepSeek V4.1 support, Hopper kernels for FP4
  experts, and the batch-invariant setting in `serve.env` are not verified for this version.
- Hardware: AWS p5en.48xlarge (8 x H200 141 GB), about $63/h on demand in us-east-1
  (secondary sources, unverified).
- Serving: temperature 0, seed 1234, one sequence at a time, token cap 32,000.

## Pieces
- `launch.sh` does the whole start on the GPU machine. It installs the pinned engine, downloads
  the pinned weights, starts the engine on 127.0.0.1, runs the first-boot checks, then starts
  the gateway on port 8443 with TLS and a bearer token. The machine shuts down on a timer
  (`STOP_AFTER_MIN`, default 240) so it never bills forgotten.
- `firstboot.py` writes `state.json`, and the gateway serves nothing until all three of its
  checks pass:
  - It takes the SHA-256 of every weights file and makes a manifest. If `pins.json` holds a
    manifest hash, the new one must match it.
  - The installed engine version must equal the pin.
  - One synthetic prompt is sent twice and must come back byte-identical.
- `gateway.py` uses only the standard library. It checks the token in constant time and lets
  one request through to the engine at a time. It accepts only the validated settings. It never
  logs or stores a request or answer body; a log line is method, path, status and seconds.
  `/health` reports the model, the revision, the weights manifest hash and the engine version,
  so the app can refuse a server that is not the pinned stack.

## What a pass here does not prove
- `/health` reports a hash, which is a claim, not proof. The proof is the audited image and the
  launch log.
- The smoke test is two answers to one prompt. Repeatability is proven by the full repeat check
  through the gateway: the probe set twice, then again after a restart, byte-identical.
- No accuracy is claimed. Every stage 1 bar must be re-run on this stack, then fresh held-out
  items, then case06 (see CONSENSUS.md).

## Order of work
1. This PR: the server pieces, tested without a GPU.
2. One audited boot (Arsh or Mir on AWS). Record `state.json` and put its `manifest_sha256` into
   `pins.json`.
3. Endpoint checks: stage 1 and the repeat check through the gateway (eval only).
4. After Arsh signs CLAUDE.md: the app client (`core/llm/remote.py`) and the per-case choice.
