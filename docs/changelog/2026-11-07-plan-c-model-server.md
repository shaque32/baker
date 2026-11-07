## 2026-11-07: Plan C model server pieces, not used by the app (#PR)
- Changed: `deploy/model_server/` adds the GPU server plan C will use: `pins.json` (DeepSeek
  V4.1 Flash 1017 at commit 1bae0e10, the 5-judge consensus pick that Arsh pre-approved; vLLM
  0.32.0; 8 x H200), `launch.sh` (pinned engine, pinned weights, engine on 127.0.0.1 with one
  sequence at a time, auto shutdown), `firstboot.py` (weights SHA-256 manifest, engine version,
  synthetic byte-identical smoke test) and `gateway.py` (bearer token, TLS, one request at a
  time, only the validated settings, no request or answer bodies logged or stored, /health
  reports model, revision, manifest hash and engine version, refuses until first boot passes).
- Where: branch claude/project-thread-fujfti-model-server
- Verified: `tests/test_model_server.py` with a stand-in engine (no GPU, no network): tokens,
  settings, one-at-a-time, no bodies in the log, readiness gate, manifest, smoke test,
  localhost-only engine, `bash -n` on launch.sh. Never booted on a GPU.
- Open: the engine version's support for DeepSeek V4.1, Hopper FP4-expert kernels and the
  batch-invariant setting are unverified; the weights' size (about 765 GB stored) disagrees with
  one blog's 510 GB; the AWS price is unverified. The app has no client for it, and `core/`
  makes no call to it, until Arsh signs the CLAUDE.md network change.
- Affects: none for the product today (not wired). Privacy and network use once wired, through
  a separate signed change.
- Status doc: no change
