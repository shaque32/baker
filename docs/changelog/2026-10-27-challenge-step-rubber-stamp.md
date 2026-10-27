## 2026-10-27: Challenge step behind a flag, and the rubber-stamp and fallible simulated experts (#154)
- Changed: step 2 of the agent plan (approved by Arsh 2026-10-27, `plans/agentic.md`). A code
  step looks for what undercuts a claim close to SUPPORTED. It has no model of its own and is off
  by default (`Components.challenge`, `mabillon audit --challenge`).
  - A claim is close to SUPPORTED when every core assumption has a passing check or a "supports"
    label. For it, the step runs the counter-searches `core/hypotheses/explain.py` already has
    (someone else using the account, another clock, the day boundary, another app, a whole app
    gone quiet, a curated report, the same words elsewhere) as fixed queries in code.
  - The records a search finds go to the same stance labeler and the same quote check as any
    retrieved record, at most the 6 records `explain.py` shows per search (`MAX_FITS`); the rest
    are counted in the search's total and not labelled. A record retrieval already sent to the
    labeler for that assumption is not sent again.
  - Only a "contradicts" or "complicates" label is stored. A "supports" or "irrelevant" label
    from the step is discarded and counted. `invariants.check_challenge` fails the run if an item
    the step stored says otherwise. A stored item is an ordinary evidence item: under rules 0.3.0
    an open one blocks SUPPORTED until the expert dismisses it, and an unaccepted "contradicts"
    never contradicts a claim.
  - Each search is its own `challenge.query` audit-log entry: the claim, the assumptions, what
    was searched in `explain.py`'s words, the records found, the total, and what was stored,
    discarded or dropped. A search that found nothing is logged too, and a claim no search
    applies to gets one entry that says nothing was searched. `explain.alternatives` gains
    `keep_empty` for this; the report still shows only alternatives a record fits.
  - `mabillon verify-bundle` re-runs every search on the bundle's tables with no model and
    fails if one gives other records, or if a stored item is not a contradicts or complicates
    item of its claim. It notes, and does not re-run, when the bundle leaves out the phone's
    other records (a scoped bundle), when the searches' versions differ, or when the people,
    links, stipulations, phones, sources or clocks changed after the run (a phone report
    imported after the run counts). After the expert re-runs the verdicts, the bundle checks the
    searches of the audit whose evidence the re-run reused.
  - The eval gains the rubber-stamp simulated expert (`eval/simulated_expert.py`,
    `rubber_stamp_review`, `--expert rubber-stamp`): it accepts every labelled item, for the
    zero-false-supported bar. The signed-key simulated expert stays the merge gate.
    `--challenge` runs the step in the eval.
  - The eval gains the fallible simulated expert (`fallible_review`, `--expert fallible
    --error-rate RATE [--expert-seed N]`): it decides as the signed-key expert but gets each
    item wrong at RATE, drawn per item from the seed, so a run is reproducible. Its summary gives
    the wrong accepts and dismissals, the dismissal rate and the items decided per claim. The
    rate has no default: it is Arsh's to set. Time per item is not simulated.
  - No rule, prompt, pin, contract, schema, gold or scorer file changes, and nothing under
    `eval/validation/` or the `validation-v1-run2` tag. Off by default, so no default run changes.
- Where: PR #154 (branch `claude/project-thread-6i2msb-challenge`)
- Verified: new `tests/test_challenge.py`, 19 tests on synthetic case01:
  - which claims are close to SUPPORTED, and that only doubt is kept;
  - the invariant fails on a stored "supports" or "irrelevant" item, and a run whose step would
    store support fails;
  - off by default: no entries and no `challenge` key in the run's configuration;
  - every challenged claim logs every search, even ones that found nothing, every claim close
    to SUPPORTED on all its evidence is challenged, and no claim a failed check settles is
    challenged;
  - a search's complicating label is stored as one of the claim's items, and its supporting
    label is not;
  - verify-bundle re-runs every search on a full bundle and passes, notes a scoped bundle and a
    change after the run (an expert's or an importer's), checks the audit's searches after a
    verdict re-run, and fails a search that gives other records, entries for a run that did
    not run the step, and a stored item that is not doubt;
  - the rubber-stamp expert accepts every labelled item through the expert actions, and the
    eval runs the step under it.
  - new `tests/test_fallible_expert.py`, 9 tests: the draw is fixed by seed and item and near
    the rate; at rate 0 it decides exactly as the signed-key expert; each wrong decision is the
    drawn one and goes through the expert actions; the other experts' summaries are unchanged;
    a rate outside 0 to 1, a fallible expert with no rate and a rate with no fallible expert are
    refused; the eval runs it. The rates in the tests are made up to test the mechanism.
  - case01 model-free, rubber-stamp expert: 6 false supported of 20 claims, with and without the
    step (accuracy 0.70). The model-free stand-in labeller labels every record of a claim the
    way the gold verdict points, "supports" for an unproven claim, so it can never label doubt
    and the step stored nothing: it challenged 14 claims with 28 searches, which found 5
    records; retrieval had labelled 3 already and the other 2 were labelled as not doubt. The
    step's effect needs the real labeller (the 14B on the Mac) or case03's planted
    counter-evidence (#151, not yet signed). Not measured.
  - case01 model-free, signed-key simulated expert, with the step: PASS, accuracy 1.00, 0 false
    supported, the same as without it.
  - `make check` passes; its eval numbers are in the PR.
- Open: the step's effect is unmeasured, for the reason above. The fallible expert's error rate
  is Arsh's to set, and no run uses one yet. Items the step
  stores are not yet marked as found by it in the report or on screen (plan step 5); the audit
  log names them. Whether the challenge step should label more than 6 records per search, and the
  per-claim cap, are Arsh's to set. A case that uses cloud AI sends the step's records to the
  cloud labeller like any retrieved record, under the case's opt-in.
- Affects: capabilities (behind a flag, off by default)
- Status doc: pending: section 8 item 2 ("Audit"): add "An optional challenge step (`mabillon
  audit --challenge`, off by default) runs code's counter-searches on claims close to supported,
  stores only contradicts and complicates labels, logs each search, and is re-run by
  verify-bundle; its effect is unmeasured (#154)"; section 7 or 10: "The eval has a rubber-stamp
  simulated expert (`--expert rubber-stamp`); on case01 model-free it lets 6 of 20 claims through
  as false supported, with or without the challenge step; and a fallible simulated expert
  (`--expert fallible --error-rate RATE`), wrong at a set rate, whose rate is not set yet
  (#154)".
