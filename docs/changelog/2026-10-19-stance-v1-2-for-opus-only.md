## 2026-10-19: Stance prompt v1.2 for a cloud model only, and the Mac check that chose it (#93)
- Changed: a cloud model (Opus 5.5) now reads its own signed stance prompt,
  `core/audit/prompts/stance_cloud.md`: v1.2, which is v1.1 plus two told-frame sentences in
  "contradicts" (signed by Arsh 2026-10-15, "Audit our model scoring"). They teach stance guide
  v0.3 rules 12 and 23: a reply in which X says the opposite does not rule out "X told the owner
  that ...", since another message could still have said it, so it is "complicates"; a denial
  that names no time rules out only an act dated before it. The local model keeps
  `core/audit/prompts/stance.md`, v1.1, unchanged (prompt version `sha256:4c35f1cf01b0b227`), so
  local cases label exactly as before. Why: with v1.1, Opus called those "contradicts" on the
  signed probe set (contradicts precision 73%, bar 90%), and under rules 0.2.x an unreviewed
  "contradicts" on an event assumption made a claim CONTRADICTED with no expert step (since
  rules 0.3.0, #98, the expert confirms each one, so a wrong one now costs the expert a look,
  not a verdict); v1.2 fixed that for Opus but took the local 14B's contradicts precision from
  58% to 50% on Arsh's Mac, so Arsh chose "Opus only" on 2026-10-19. Code: `core/audit/stance.py` gives a cloud model the cloud prompt
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
- Where: main (PR #93, merge 79fc398, 2026-10-20).
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
  shown as supports; v1.2 100%, 50% (11 of 22), 6 (all 11 real contradicts found in both; a
  replay of the Mac call logs gives the same scores, `.../local-arm/PER_ITEM.md`). The test's 14B half ran in the same run (its audit labeled
  with v1.2, then in `stance.md`; the decision measures read no stance prompt); with the Opus
  arm rescored at eee8d15, claim proposal and assumption filling both stay local under the
  written rule (`/mnt/project-files/baker/cloud-bench/2026-10-16/fair-14b-vs-opus/DECISION.md`).
  `make check` in the PR description.
- Open: cloud stays off: #68's `PROBE_PASSED` needs an entry for (claude-opus-5-5, medium,
  `sha256:2863d8dbf66960f6`), signed by Arsh, before cloud labels can run. Opus with v1.2 misses
  P065. The local 14B still misses the signed bars with v1.1 (58% contradicts precision, 6 moved
  traps shown as supports); with v1.2 it newly called P039, P073 and P076 "contradicts"
  (`/mnt/project-files/baker/cloud-bench/2026-10-16/fair-14b-vs-opus/local-arm/PER_ITEM.md`). No case has Opus labels (cloud was never on), so nothing
  stored is labeled again.
- Affects: capabilities (once Arsh signs its entry, Opus labels with v1.2: fewer wrong
  "contradicts" for the expert to dismiss; under rules 0.3.0 none becomes CONTRADICTED without
  the expert, and a claim it changes goes UNPROVEN, never SUPPORTED). No change for local cases. No privacy change. No new customer-facing claim.
- Status doc: applied 2026-10-20
