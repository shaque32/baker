## 2026-10-28: Validation run 3 plan (draft) and scorer 1.3.0 (PR pending)
- Changed: `eval/validation/PREREGISTERED_v3.md` is the run 3 plan, which v2's low-coverage rule
  item 4 requires. It is a draft for Arsh to approve. Run 3 reruns the 106 iOS 15 claims as a
  coverage check only: these claims are now development data, so no accuracy figure from run 3
  is quoted outside the validation write-up. It lists every change since run 2 and states the
  prediction (35 of 106 tested, 31 code-checked, from the replay of run 2's recorded answers).
  Its minimum is 30 code-checked claims. It adds a fidelity audit before scoring and a
  determinism repeat on the A10G. `eval/validation/aws_run.sh` now clones the tag
  `validation-v1-run3`. The scorer (`eval/validation/score_hickman.py`, 1.3.0) adds two
  things, beside the existing measures and without changing any of them:
  - each tested claim's tier: code-checked (a core assumption went to a deterministic check,
    whatever the outcome) or expert only, with the minimum counted on the code-checked tier;
  - measure 5, the claims that a failed check contradicted although gold does not.
- Where: branch claude/project-thread-ds0ify (PR to follow)
- Verified: on this container, 2026-10-28. New tests in tests/test_validation_score.py cover
  the tiers on the synthetic scored run (all 3 code-checked), the run 3 minimum on the
  code-checked tier only, a row from before 1.3.0 counting as expert only, and measure 5.
  `make check`: see the PR.
- Open: Arsh has not approved the plan yet. The tag does not exist yet. The prediction is a
  replay, not a run, and determinism on the A10G is unmeasured.
- Affects: performance (what validation reports); no capability, privacy or customer-facing
  claim change
- Status doc: pending: in the validation section, after the "Scorer 1.2.0" bullet, add "Scorer
  1.3.0 (#N): run 3's tiers (code-checked or expert only, minimum 30 code-checked) and measure 5
  (contradicted by a failed check, gold not contradicted), beside the 1.2.0 measures. Run 3 plan
  `eval/validation/PREREGISTERED_v3.md` (#N): coverage check only on development data; [approval
  as the file records]"; in the build line, change "validation scorer 1.2.0
  (`eval/validation/score_hickman.py`, #143)" to "validation scorer 1.3.0
  (`eval/validation/score_hickman.py`, #N)"
