## 2026-10-31: Speed work, step 2: replay a recorded audit's stance calls
- Changed: `eval/probe/replay.py` 1.0.0, eval only, no product behavior change. It rebuilds a
  recorded audit's stance prompts with today's code (the product's retrieval, context, names
  and claim) and asks a local model again under a variant: the signed prompt or the v1.4
  order (`eval/probe/stance_v1_4_draft.md`), with 20, 8 or 5 messages either side of the
  record. Calls keep the recorded order, so prefix reuse works as in the audit, and only calls
  whose signed 20-message prompt rebuilds byte for byte are replayed. Labels are compared the
  way the product stores them (invalid, quote dropped, forwarded words). `check` needs no
  model; `run` resumes a stopped replay only as the same replay (`identity.json`: the model
  file, its settings, the prompt, the context size, the recorded calls and the exact prompt
  text) and refuses anything else; `report` prints label changes by direction, gold key
  records, each safety count with its 95% Wilson upper bound, every call behind the repeat
  criterion and every label change by ids, the per-call time spread and a run record. Why: the probe sets carry 2 to 6 context
  lines while real audit prompts carry about 23, so only real prompts can test a shorter
  context. `eval/probe/REPLAY_PREREGISTERED.md` fixes the criteria for showing 8 messages
  instead of 20 before any replay (both replays on the same calls, audit, model file and
  settings; the 20-message replay repeating the recorded answer on at least 99% of calls; no
  call newly labelled supports, none leaving complicates or contradicts, no key record changing
  its label; at least 10% faster per call with no failed call in either replay; supports lost
  on at most 5% of the baseline's supports calls, and no assumption losing all of them);
  `bash eval/probe/mac_replay.sh` runs it on the Mac (about 4 hours, estimated).
- Where: PR #185
- Verified: tests/test_probe_replay.py (a case01 audit labelled by a stand-in model through the
  product's wiring; synthetic folders for the decision). `replay check` on the case04 database
  of Arsh's go/no-go Mac run (main 67dabdb, 2026-10-29), no model, re-run on main 085c48e:
  279 of 283 stance prompts rebuild byte for byte; mean prompt 6,569 characters at 20 messages, 5,401 at 8 (about 18%
  shorter), 4,993 at 5 (about 24% shorter). With the v1.4 order, the text a call must newly
  read falls from 5,702 to 3,310 characters at 20 messages and to 2,161 at 8. No model has run
  a replay: whether a shorter context keeps the labels, and how much time it saves, is
  unverified.
- Open: character counts stand in for tokens. case04 was already spent as a held-out case, so
  a result there is not a held-out result. The sample is small: zero new supports on its 116
  calls that were not supports still allows a rate up to about 3.2% (95% Wilson upper bound),
  so a pass is not evidence of no effect, and the PR that adopts one is a labeling change that
  needs the eval gate on a fresh synthetic case. Only the local 14B is tested; the cloud labeler and
  retrieval would keep 20 messages. One machine.
- Affects: performance (measurement only)
- Status doc: no change
