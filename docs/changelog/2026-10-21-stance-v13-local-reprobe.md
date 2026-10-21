## 2026-10-21: A Mac re-probe for the local 14B's told-frame and denial contradictions (stance v1.3 candidates)
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
- Where: branch `claude/expert-confirms-contradicts-y6ti2f` (PR2 of the "Expert confirms
  contradicts" plan), not merged.
- Verified: `tests/test_probe_v13.py` (each candidate is v1.1 word for word plus its blocks; the
  copied sets keep their 2026-10-15 SHA-256; the fresh set is well formed and fictional; the
  baseline file reproduces the 2026-10-19 numbers and every v1.1 prompt still renders byte for
  byte as that run sent it; the scorer applies the written criteria on stand-in answers). No
  model has answered the candidates yet: unverified until Arsh's Mac run.
- Open: the Mac run (about 2.5 to 4.5 hours, $0). If a candidate meets every criterion, it goes
  into `core/audit/prompts/stance.md` only after Arsh signs it, and this entry is updated with
  the numbers and the status edits. If neither does, no prompt change.
- Affects: none yet (eval tooling only). No privacy, network or verdict change.
- Status doc: no change
