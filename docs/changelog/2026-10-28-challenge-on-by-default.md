## 2026-10-28: The challenge step runs by default, is marked in the report, and shows in the demo (#162)
- Changed: Arsh asked on 2026-10-28 (07:44Z) for the agents to be on by default and part of the
  demos and pilots, and (07:50Z) for their work to be featured in the demo. This is PR 1 of
  `plans/agents-on-by-default.md`: the challenge step (#154). The testability agent stays off and
  eval only (#159, and the CLAUDE.md line Arsh signed).
  - On by default: `Components.challenge` defaults to True, so the review screen's audit, `mabillon
    audit` and the eval run the step. One run can skip it: "Skip the challenge step" on the
    screen's audit form, `mabillon audit --no-challenge`, or `eval/run_pipeline.py
    --no-challenge` (output in `<out>/no_challenge/`). A run that skips it has no `challenge` key
    in its configuration, as before.
  - The step is unchanged. It has no model of its own, stores only contradicts and complicates
    labels (the invariant still fails the run otherwise), logs every search, and verify-bundle
    re-runs them. Under rules 0.3.0 an open item it stores blocks SUPPORTED until the expert
    decides it, and a model "contradicts" still needs the expert's confirm. It can add doubt and
    model calls, never support.
  - Marked: an item the step stored says "Found by the challenge step" in the report (report
    0.22.0, after #149's 0.20.0 and #159's 0.21.0) and carries a "found by the challenge step"
    badge on its review-screen card. Both are read from the step's own audit entries
    (`challenge.found_items`). The report's versions table says "Challenge step: ran (1.0.0)" or
    "skipped for this run", read from the audit whose evidence the run shows, so a verdict re-run
    says it too.
  - Demo: the step runs in the scripted demo as in the product. Its search for someone else
    using the account finds C16's "its ilya btw, dan's at work. he left his login on my ipad".
    The demo's scripted labels mark C16's two counter-records in the signed key complicates on
    its authorship assumption (`CHALLENGE_DOUBT`), and the scripted expert leaves both for the
    person giving the demo. C16 waits under "Also waiting on you", the step's find carries its
    mark, and C16 stays unproven whatever the presenter decides. `docs/demo.md` gains the live
    step.
- Where: PR #162 (branch `claude/project-thread-6i2msb-challenge-default`)
- Verified: `make check` passes; its eval numbers are in the PR. New and changed tests:
  - `tests/test_challenge.py`: the step is on by default and a run can skip it, with the report
    saying "skipped for this run"; the CLI runs it unless `--no-challenge`; the review screen's
    audit runs it unless skipped; a stored doubt is marked in its own report row and only the
    step's finds are marked; the report says the audit ran the step; the eval runs it by default
    under the rubber-stamp expert.
  - `tests/test_demo.py`: the demo's audit ran the step; C16's two counter-records are open
    complicating items and the step's find is among them; the claim page marks each find; the
    report marks it and says the step ran; accepting both leaves C16 unproven. The overview tests
    now expect C16 under "Also waiting on you" (19 of 21 done, not 20).
  - case03 model-free with the step (cloud container, 2026-10-28, information only): 72 searches
    on 15 claims, 58 records labelled, 0 stored, verdicts unchanged. The model-free stand-in
    labels every record the way the gold verdict points, so it cannot tell a counter-record from
    support: what the step catches with a real labeler is unmeasured.
- Open: the step's effect on the 14B is unmeasured; case03, which Arsh signed today, is the case
  built to measure it, on the Mac. Time per case with the step on is unmeasured. The per-search
  cap (6 records) and a per-claim cap are Arsh's to set. On case01 model-free the rubber-stamp
  expert still lets 6 of 20 claims through with or without the step (#154): it adds doubt for
  the expert, it does not replace the expert. On a case that opted into cloud AI, the step's
  records go to the cloud labeler like any retrieved record, so such a case sends more records;
  what is sent per record is unchanged. Pilot and privacy docs that list what an audit does are
  Arsh's to update. Validation run 3 should pin the step on or off in PREREGISTERED_v3.
- Affects: capabilities (the challenge step runs by default), performance (more stance calls on
  claims close to supported), customer-facing demo
- Status doc: pending: section 8 item 2 ("Audit"): in place of #154's pending line, add "A
  challenge step runs by default (`mabillon audit --no-challenge`, or "Skip the challenge step"
  on the screen, turns it off for one run): code's counter-searches on claims close to
  supported, storing only contradicts and complicates labels, each search logged and re-run by
  verify-bundle; its finds are marked "found by the challenge step" on screen and in the report;
  its effect with a real labeler is unmeasured (#154, #162)". Keep #154's section 7 or 10
  line on the simulated experts as written.
