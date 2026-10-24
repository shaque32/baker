## 2026-10-21: A Mac re-probe for the local 14B's told-frame and denial contradictions (stance v1.3 candidates) (#120)
- Changed: eval only. Two candidate wordings for the local model's stance prompt teach stance
  guide v0.3 rules 12 (told frames) and 23 (undated denials): `eval/probe/stance_v1_3a_draft.md`
  (two checks before answering "contradicts") and `eval/probe/stance_v1_3b_draft.md` (the checks
  plus four worked examples). Why: the 14B's contradicts precision on the signed probe set is
  11 of 19 (58%, bar 90%; Mac run 2026-10-19 at `eee8d15`), all 8 misses told frames or an
  undated denial, and the cloud prompt's v1.2 sentence fixed none of them for the 14B. The plan
  and its criteria were committed before any held-out item or call
  (`eval/probe/v13/PREREGISTERED.md`). New: a fresh 32-item synthetic set
  (`eval/probe/v13/heldout.jsonl`, written by a separate agent from the guide alone, labeled by
  three blind readers), copies of the two 2026-10-15 sets the 14B never answered, the Mac
  script `eval/probe/mac_v13.sh`, the scorer `eval/probe/v13/score.py` (decision, every item's
  answer, model SHA-256, Wilson intervals, time per call) and the v1.1 baseline's per-item file
  `eval/probe/results/2026-10-19-qwen3-14b-stance-v1-1.jsonl`. The product prompt
  (`core/audit/prompts/stance.md`, v1.1) is unchanged.
- Where: PR #120 (branch `claude/expert-confirms-contradicts-y6ti2f`), not merged.
- Verified: `tests/test_probe_v13.py` (each candidate is v1.1 word for word plus its blocks; the
  copied sets keep their 2026-10-15 SHA-256; the fresh set is well formed and fictional; the
  baseline file reproduces the 2026-10-19 numbers; the scorer applies the written criteria on
  stand-in answers). Arsh's Mac run, 2026-10-22 at `162716a` (MacBook Air M4 24 GB, macOS
  15.6.1, llama-cpp-python 0.3.36, model SHA-256 500a8806..., the same file as 2026-10-19;
  `eval/probe/v13/RESULTS-2026-10-22-mac.md`): both candidates FAIL the preregistered criteria,
  so no prompt change. Signed set contradicts precision: v1.1 11/19 (58%), v1.3a 11/24 (46%),
  v1.3b 10/18 (56%); bar 90%. On the three new sets every prompt called 41 of the 42
  told-frame and undated-denial items "contradicts" (fresh 16/16, told-frame 24 12/12,
  rules 12 and 23 26 13/14). v1.3a added 5 new wrong contradicts on the signed set (P039,
  P072, P073, P075, P076); v1.3b lost one true one. Mean seconds per call: v1.1 34.0, v1.3a
  31.8, v1.3b 27.0. $0 API.
- Open: the 14B does not follow either wording; a prompt change is not the route for it. Next
  approach is Arsh's call (thread "Expert confirms contradicts"). `mac_v13.sh` with
  `MODEL_NAME` re-runs the same test on another local model.
- Affects: performance (a measured benchmark: the local 14B's contradicts precision stays 58%).
  No capability, privacy, network or verdict change.
- Status doc: no change
