## 2026-10-16: Stance prompt v1.2, the told-frame sentences, and its Mac check (#93)
- Changed: `core/audit/prompts/stance.md` is v1.2, signed by Arsh on 2026-10-15 ("approved" in
  "Audit our model scoring"). Two sentences in the "contradicts" entry teach stance guide v0.3
  rules 12 and 23: a reply in which X says the opposite does not rule out "X told the owner that
  ...", since another message could still have said it, so it is "complicates"; a denial that
  names no time rules out only an act dated before it. Why: with v1.1, Opus 5.5 called those
  "contradicts" on the signed probe set (contradicts precision 73%, bar 90%), and an unreviewed
  "contradicts" on an event assumption can make a claim CONTRADICTED with no expert step. No code
  changes; the recorded prompt version becomes `sha256:2863d8dbf66960f6` (was
  `sha256:4c35f1cf01b0b227`). Also eval only: `eval/probe/mac_v12.sh`, one Mac run for the 14B's
  probe on v1.2, the same probe on v1.1 as its baseline, and its half of the 14B-vs-Opus test
  Arsh chose on 2026-10-15 ("Test after fixes"); and `eval/bench/fair_steps.py`, which runs that
  test for either model at one commit: claim proposal (scored by the committed matcher, a
  split-aware one, since the claims prompt asks for splitting, and a strict split-aware one), the
  case01 audit without the assumption sheet, the same fills replayed with no model call under a
  lenient labeler, and the fills against the signed sheet's core templates and stated values.
  Its Opus arm retries a failed send as the product does; a cloud call still failing after that
  marks the run invalid. Each result records its commit, model hash and effort; `--rescore`
  scores a finished arm again from its stored databases with no model call, and `--compare`
  applies the written rule to two results, deciding nothing when they are not comparable (an
  invalid arm, Opus not at medium effort, a dirty tree, different commits, or arms scored at
  different commits).
- Where: PR #93 (branch `claude/project-thread-01fybj`), held, not merged.
- Verified: the v1.2 body is byte for byte the text the preregistered Opus runs sent (tests pin
  its SHA-256 and check it is v1.1 plus the two sentences only). Opus 5.5 on the signed set,
  high and medium: contradicts precision 10/10, supports recall 33/33, 0 contradicting shown as
  supports, contradicts recall 10/11 (misses P065). New items: wrong contradicts 2 to 0 (24
  items, high) and 1 to 0 (26 items, medium), controls kept. $8.59 of API spend, synthetic data
  only (`/mnt/project-files/baker/cloud-bench/2026-10-15/told-frame-line/`). The local 14B on
  Arsh's 24 GB MacBook Air (`bash eval/probe/mac_v12.sh` at eee8d15, 2026-10-19, first answers,
  the signed set): v1.1 supports recall 100%, contradicts precision 58% (11 of 19), 6 moved
  traps shown as supports; v1.2 100%, 50% (11 of 22), 6 (counts inferred from the percentages;
  all 11 real contradicts found in both). The test's 14B half ran in the same run; with the
  Opus arm rescored at eee8d15, claim proposal and assumption filling both stay local under the
  written rule (`/mnt/project-files/baker/cloud-bench/2026-10-16/fair-14b-vs-opus/DECISION.md`).
  `make check` in the PR description.
- Open: v1.2 misses the hold Grok Product set for this PR (the 14B at or above v1.1 on supports
  recall and contradicts precision, 0 moved traps shown as supports), so the PR is held and Arsh
  chooses the next step; if that changes the PR, this entry is rewritten with it. Which 3 items
  the 14B newly calls "contradicts" is not known (the call logs stayed on the Mac). #68's
  `PROBE_PASSED` list needs an entry for Opus with v1.2, signed by Arsh, before cloud labels can
  run. Opus with v1.2 misses P065. Stored v1.1 answers are not reused, so a re-run of an
  existing case labels again.
- Affects: capabilities (stance labels for every model that reads the signed prompt: for Opus,
  fewer wrong "contradicts" and so fewer wrong CONTRADICTED verdicts; for the local 14B, 3 more
  wrong "contradicts" on the signed set, the reason for the hold; a claim it changes goes
  UNPROVEN or CONTRADICTED, never SUPPORTED); performance (one full re-label per existing case).
  No privacy change. No new customer-facing claim.
- Status doc: pending: written for this PR merged as it stands. Header, "Signed prompts on
  main": "stance v1.1" becomes "stance v1.2 (v1.1 plus the told-frame sentences, signed by Arsh
  2026-10-15, #93)". Section 4, the Opus "Known risk" bullet: end it with "Stance v1.2 (#93)
  removed every such answer in the Opus tests; #68 uses Opus only for a (model, effort, prompt
  version) on its `PROBE_PASSED` list, which is empty, so Opus with v1.2 needs an entry signed
  by Arsh." Section 4, "Claim proposal and assumption filling stay local": add "The same-test
  comparison Arsh chose (2026-10-15, `eval/bench/fair_steps.py`) ran in two halves: Opus
  (2026-10-16, medium, $5.23) claim splitting 95%, audit without the sheet 70%, lenient fills 75%, sheet
  values 3 of 20; the 14B (2026-10-19, Mac, eee8d15) 90%, 55%, 60%, 4 of 20; 0 false supported in both. Both
  steps stay local under the written rule (`/mnt/project-files/baker/cloud-bench/2026-10-16/
  fair-14b-vs-opus/DECISION.md`); one run per arm." Section 7, replace "The local 14B has not
  been run on the signed set." with the two tables of this entry's Verified line (Opus 5.5 high
  and medium on v1.2; the 14B on v1.1 and v1.2) and their sources. Section 9, limitation 2: replace "until
  a signed prompt fix lands." with "Stance v1.2 (#93) removed every such answer in the Opus
  tests; with it Opus misses one real contradiction (P065), which leaves a claim UNPROVEN."
  Section 9, limitation 4: replace the sentence on the 14B's probe result with "The local 14B's stance
  labels miss the signed bars: on the signed set (Mac, 2026-10-19) its contradicts precision is
  58% with v1.1 and 50% with v1.2 (bar 90%), with 6 moved traps shown as supports under both.
  Under rule 1b a model's "contradicts" on an assumption that is not a meaning and has no passed
  check can make a claim CONTRADICTED with no expert step, until the expert dismisses it."
  Section 11, "Before a first real case" item 3: replace "until a signed
  told-frame prompt fix passes on new items (line signed 13:45Z) and Arsh signs a gate entry" with "until Arsh signs a `PROBE_PASSED` entry for
  Opus with stance v1.2 (#93)".
