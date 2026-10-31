## 2026-10-30: Run 3 plan filled at the tag commit e5ce04b (validation, #176)
- Changed: `eval/validation/PREREGISTERED_v3.md` (draft since #165) now names e5ce04b, where #172
  merged, as the commit for the tag `validation-v1-run3`.
  - It completes the change table with #166 to #175. It says which signed files changed (rules
    0.4.0, contracts 0.5.0) and why neither moves a run 3 verdict: the testability agent is
    off, so 0.4.0 decides as 0.3.0.
  - It fills the prediction from the replay at e5ce04b: 52 of 106 tested, 34 code-checked, 15
    unsettled, 3 expert only (31, 18 and 3 without the R4 links).
  - It counts how the sender and time checks' results moved since sender 1.0.1, weekday 1.0.1
    and time 1.0.2: 21 of 68 core results changed, 17 inconclusive to pass and 4 inconclusive
    to fail, none between pass and fail, and no core weekday result.
  - Arsh approved the plan on 2026-10-30 at 23:10 UTC ("approve", validation thread), recorded
    in its Status line, so it binds. Run 3 is still a coverage check on development claims:
    no accuracy figure from it is quoted outside the validation write-up.
  Why: the plan needs the replay at the tag before it binds, and the Grok audit on #165 asked
  for the check changes by direction.
- Where: PR #176 (branch claude/project-thread-ds0ify)
- Verified: on this container, 2026-10-30. Replay of run 2's recorded 14B answers through
  e5ce04b's code (no model), with the checks on a copy of run 2's case database, made both with
  and without the run driver's R4 links. The check comparison runs each core check with the
  current text match and with the match before #165; that match is the only difference between
  the versions (`git diff e99c0a8..e5ce04b -- core/audit/checks`). Development data, in the
  project files (`run-v2/replay/REPLAY.md`), not in the repo.
- Open: run 3 itself (AWS A10G, Arsh's call). Its result equals this replay only if the A10G
  repeats run 2's answers byte for byte, which is unmeasured on AWS. The 11 failed core checks
  are scored by measure 7 only after the run.
- Affects: none (plan text only; no code change)
- Status doc: pending: in section "Real-export validation", add a bullet "Run 3 plan
  (`eval/validation/PREREGISTERED_v3.md`): a coverage check on the same 106 claims, now
  development data, at tag `validation-v1-run3` on e5ce04b; the replay there predicts 34
  code-checked of 106 against a minimum of 30; no accuracy claim from it. Approved by Arsh
  2026-10-30, binding."
