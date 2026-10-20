## 2026-10-19: Stance prompt v1.2 for a cloud model only, and the Mac check that chose it (#93)
- Changed: a cloud model (Opus 5.5) now reads its own signed stance prompt,
  `core/audit/prompts/stance_cloud.md`: v1.2, which is v1.1 plus two told-frame sentences in
  "contradicts" (signed by Arsh 2026-10-15, "Audit our model scoring"). They teach stance guide
  v0.3 rules 12 and 23: a reply in which X says the opposite does not rule out "X told the owner
  that ...", since another message could still have said it, so it is "complicates"; a denial
  that names no time rules out only an act dated before it. The local model keeps
  `core/audit/prompts/stance.md`, v1.1, unchanged (prompt version `sha256:4c35f1cf01b0b227`), so
  local cases label exactly as before. Why: with v1.1, Opus called those "contradicts" on the
  signed probe set (contradicts precision 73%, bar 90%), and an unreviewed "contradicts" on an
  event assumption can make a claim CONTRADICTED with no expert step; v1.2 fixed that for Opus
  but took the local 14B's contradicts precision from 58% to 50% on Arsh's Mac, so Arsh chose
  "Opus only" on 2026-10-19. Code: `core/audit/stance.py` gives a cloud model the cloud prompt
  (`CLOUD_PROMPT_FILE`, `prompt_file`), on the case's cloud labeler and when a benchmark passes
  a cloud model in; `core/casework/cloud.py` checks `PROBE_PASSED` against the cloud prompt's
  version (`sha256:2863d8dbf66960f6`), the one a cloud case would send. Eval only:
  `eval/bench/claude_bench.py` scores the cloud prompt by default; `eval/probe/mac_v12.sh` runs
  the 14B's probe on v1.2 and on v1.1 and its half of the 14B-vs-Opus test Arsh chose on
  2026-10-15 ("Test after fixes"); `eval/bench/fair_steps.py` runs that test for either model at
  one commit: claim proposal (the committed matcher, a split-aware one, since the claims prompt
  asks for splitting, and a strict split-aware one), the case01 audit without the assumption
  sheet, the same fills replayed with no model call under a lenient labeler, and the fills
  against the signed sheet's core templates and stated values. Its Opus arm retries a failed
  send as the product does; a cloud call still failing after that marks the run invalid. Each
  result records its commit, model hash and effort; `--rescore` scores a finished arm again from
  its stored databases with no model call, and `--compare` applies the written rule, deciding
  nothing when the arms are not comparable (an invalid arm, Opus not at medium effort, a dirty
  tree, different commits, or arms scored at different commits).
- Where: PR #93 (branch `claude/project-thread-01fybj`), not merged.
- Verified: the cloud prompt's body is byte for byte the text the preregistered Opus runs sent,
  and `stance.md` is byte for byte main's v1.1 (tests pin both, check that v1.2 is v1.1 plus the
  two sentences only, and that a cloud model gets the cloud prompt's version while the local
  model keeps v1.1's). Opus 5.5 with v1.2 on the signed set, high and medium: contradicts
  precision 10/10, supports recall 33/33, 0 contradicting shown as supports, contradicts recall
  10/11 (misses P065). New items: wrong contradicts 2 to 0 (24 items, high) and 1 to 0 (26
  items, medium), controls kept. $8.59 of API spend, synthetic data only
  (`/mnt/project-files/baker/cloud-bench/2026-10-15/told-frame-line/`). The local 14B on Arsh's
  24 GB MacBook Air (`bash eval/probe/mac_v12.sh` at eee8d15, 2026-10-19, first answers, the
  signed set): v1.1 supports recall 100%, contradicts precision 58% (11 of 19), 6 moved traps
  shown as supports; v1.2 100%, 50% (11 of 22), 6 (counts inferred from the percentages; all 11
  real contradicts found in both). The test's 14B half ran in the same run (its audit labeled
  with v1.2, then in `stance.md`; the decision measures read no stance prompt); with the Opus
  arm rescored at eee8d15, claim proposal and assumption filling both stay local under the
  written rule (`/mnt/project-files/baker/cloud-bench/2026-10-16/fair-14b-vs-opus/DECISION.md`).
  `make check` in the PR description.
- Open: cloud stays off: #68's `PROBE_PASSED` needs an entry for (claude-opus-5-5, medium,
  `sha256:2863d8dbf66960f6`), signed by Arsh, before cloud labels can run. Opus with v1.2 misses
  P065. The local 14B still misses the signed bars with v1.1 (58% contradicts precision, 6 moved
  traps shown as supports); which 3 items it newly called "contradicts" with v1.2 is not known
  here (the call logs are on the Mac). No case has Opus labels (cloud was never on), so nothing
  stored is labeled again.
- Affects: capabilities (once Arsh signs its entry, Opus labels with v1.2: fewer wrong
  "contradicts", so fewer wrong CONTRADICTED verdicts; a claim it changes goes UNPROVEN, never
  SUPPORTED). No change for local cases. No privacy change. No new customer-facing claim.
- Status doc: pending: header, "Signed prompts on main": replace "stance v1.1" with "stance v1.1
  (local model) and v1.2 for a cloud model only (`stance_cloud.md`: v1.1 plus the told-frame
  sentences, signed 2026-10-15, #93)". Section 4, "When Opus is used": replace "with the current
  stance prompt" with "with the cloud stance prompt (`core/audit/prompts/stance_cloud.md`, v1.2,
  which only a cloud model reads)", and replace "That list is **empty**: Opus 5.5 fails the
  signed set's contradicts bar (below), so every case still labels locally until a signed prompt
  fix passes a recorded re-run (the signed set plus new held-out items not used to write the
  prompt) and Arsh signs the entry." with "That list is **empty**. With v1.2, Opus 5.5 met the
  bars on the signed set and on new held-out items (section 7); every case labels locally until
  Arsh signs an entry for it." Section 4, "Known risk": replace "until a signed prompt line
  fixes it (section 7)." with "with stance v1.1. The cloud prompt, v1.2 (#93), removed every such
  answer in the Opus tests (section 7)." Section 4, "Claim proposal and assumption filling stay
  local": add "The same-test comparison Arsh chose (2026-10-15, `eval/bench/fair_steps.py`) ran
  in two halves: Opus (2026-10-16, medium, $5.23) claim splitting 95%, audit without the sheet
  70%, lenient fills 75%, sheet values 3 of 20; the 14B (2026-10-19, Mac, eee8d15) 90%, 55%, 60%,
  4 of 20; 0 false supported in both. Both steps stay local under the written rule
  (`/mnt/project-files/baker/cloud-bench/2026-10-16/fair-14b-vs-opus/DECISION.md`); one run per
  arm." Section 7: replace "The planned fix is a stance prompt line for guide rules 12 and 23,
  signed by Arsh and tested on new items." with "The fix is stance v1.2 (#93), signed by Arsh
  2026-10-15: with it Opus scored contradicts precision 10/10, supports recall 33/33, 0
  contradicting shown as supports and contradicts recall 10/11 (misses P065), at high and at
  medium, and its wrong contradicts on new items went from 2 to 0 (24 items) and 1 to 0 (26
  items) (`/mnt/project-files/baker/cloud-bench/2026-10-15/told-frame-line/`). It is the cloud
  model's prompt only (Arsh, \"Opus only\", 2026-10-19)." and after the 14B's v1.1 sentence add
  "With v1.2 (same run) the 14B's contradicts precision fell to 50% (11 of 22) with the same 6
  moved traps, which is why the local model keeps v1.1." Section 9, limitation 2: replace "until
  a signed prompt fix lands." with "with stance v1.1. The cloud prompt, v1.2 (#93), removed every
  such answer in the Opus tests; with it Opus misses one real contradiction (P065), which leaves
  a claim UNPROVEN." Section 11, "Before a first real case" item 3: replace "until a signed
  told-frame prompt fix passes on new items (line signed 13:45Z) and Arsh signs a gate entry."
  with "until Arsh signs a `PROBE_PASSED` entry for Opus 5.5 with the cloud prompt, stance v1.2
  (#93)."
