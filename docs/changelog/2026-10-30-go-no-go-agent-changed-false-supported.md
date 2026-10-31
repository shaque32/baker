## 2026-10-30: The testability go/no-go's false-supported bar counts only the claims the agent changed (#183)
- Changed: the go/no-go's third bar (`eval/run_pipeline.py`, `testability_go_no_go` and
  `report_go_no_go`) now reads "0 false supported on the claims the agent changed, under the
  rubber-stamp expert". Arsh chose this on 2026-10-30 at 23:08Z, on a decision card in the
  project thread. Why: on case04's go/no-go (his Mac run, 2026-10-30) the one false supported
  was C39, a role claim the step never touched. The 14B labelled two messages as supporting it,
  and the rubber-stamp expert accepted both. With the agent off, C39 fails the same way, so the
  bar as built (#168, every claim in the run) measured the base pipeline under a careless
  expert, not the agent.
  - "The claims the agent changed" are the claims whose scored verdicts used a proposal the step
    made and the examiner accepted: `agent_changed`, through `testability.accepted_in`. These are
    the assumptions `rules.decide_verdict` got as `agent_proposed`. The step reaches a verdict
    only through an accepted proposal: a refused or rejected try is a log entry. The expert's
    own inputs (persons, aliases, stipulations) apply with the step off, so they count in the
    whole run's figure.
  - A run in which the agent changed no claim fails the bar, since an empty set is no evidence
    (Baker Eval on #183).
  - The whole run's false-supported count is still computed, printed beside the bar "for
    information" and written to `go_no_go.json`. As before, the file holds counts only, so a
    hidden case names no claim.
  - Every other bar, value and setting is unchanged. No rule, prompt, pin, contract, schema or
    gold change.
- Where: PR #183 (branch `claude/project-thread-6i2msb-bar3`)
- Verified: the go/no-go's tests and a re-score of Arsh's case04 run.
  - `tests/test_testability_go_no_go.py`, 20 tests. Two are new. In the first, a false
    supported on a claim the step did not change leaves a GO, with "1 in the whole run, for
    information", and the same claim counted as changed gives a NO-GO. In the second, a run
    with no changed claim fails the bar.
  - Arsh's case04 run re-scored with this code from his uploaded `rubber_stamp.zip`, with no new
    model run (cloud container, 2026-10-30). Still **NO-GO**, on two bars: conversion, 2 of 34,
    and 4 tries naming a different person, phone or window. The third bar now passes: 0 false
    supported on the 2 claims the agent changed (C10 and C26, both supported in the signed key),
    and 1 in the whole run.
  - `make check` passes; its eval numbers are in the PR and unchanged from main.
- Open: the bar was narrowed after this NO-GO was seen, on the run that produced it, so the
  re-score is no evidence that the narrower bar works. The first go/no-go that counts is the
  next one, on case05, scored with this bar from the start. C39 itself is a base-pipeline
  finding for the validation thread. Under an expert who
  accepts everything, a role claim goes supported on two stance labels when the record that
  keeps it unproven was never retrieved. This change does not fix that, and does not hide it.
- Affects: none (eval scorer only; the agent stays off by default)
- Status doc: no change
