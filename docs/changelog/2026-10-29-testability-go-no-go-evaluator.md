## 2026-10-29: The testability step's go/no-go, read by code from one eval run
- Changed: the agent plan (plans/agentic.md, approved by Arsh 2026-10-27) fixes the testability
  step's go/no-go before the run, but the eval only printed its measures and "none given". Now
  `eval/run_pipeline.py` reads the decision itself after a `--testability CAP` run
  (`testability_go_no_go`) and writes it to `<out>/go_no_go.json`.
  - GO only if every bar holds: conversion of the refusals the sheet makes testable at least X%
    (with its Wilson 95% interval), no try naming a different person, phone or window than the
    sheet, 0 false supported under the rubber-stamp expert, every output valid, a byte-identical
    repeat, and calls and seconds per claim within Y. Any bar missed is NO-GO, naming it.
  - The repeat compares the predictions and every filler and testability model call (prompt and
    raw output), byte for byte, between the run and its `--repeat`.
  - Fewer sheet-testable refusals than a least denominator gives "insufficient", not a decision.
  - None is given until Arsh sets X (`TESTABILITY_X_PERCENT`), Y (`TESTABILITY_Y_BUDGET`, calls
    and seconds per claim), the cap (`TESTABILITY_CAP`) and the least denominator
    (`TESTABILITY_MIN_TESTABLE`), all still placeholders, and until the run has the signed
    prompt, a held-out case, `--expert rubber-stamp`, `--repeat` and Arsh's signed key (false
    supported is never scored against a builder's draft). The reasons are printed.
  - The record names the hardware, the Python version and the wall-clock date of the run.
  - The run's measures print as before; the old "none given" line moved into the go/no-go.
- Where: branch `claude/project-thread-6i2msb-go-no-go` (stacked on the rules 0.4.0 branch)
- Verified: `tests/test_testability_go_no_go.py` (17 tests): every bar held is a GO; each bar
  missed alone is a NO-GO naming it; conversion exactly at X passes; a repeat whose filler and
  step answers differ by one byte is a NO-GO that says the model calls differ; too few testable
  refusals is insufficient; with nothing set, a draft prompt, a development case, the simulated
  expert and no repeat, none is given with every reason; a run's cap other than Arsh's gives
  none; a draft gold key gives none; the Wilson interval; and two eval runs of synthetic case01 with the scripted model, the
  signed prompt and the rubber-stamp expert give a GO with the hardware recorded.
  `make check` results are in the PR.
- Open: X, Y, the cap and the least denominator are Arsh's to set, and no held-out case is
  listed yet (case04 is being written for it, by a writer who never saw the step's prompt). No
  go/no-go has been run with the local model. Tokens per second and peak GPU memory are not
  recorded.
- Affects: performance (how the testability step's go/no-go is measured before pilots). No
  capability, privacy, network, model or verdict change.
- Status doc: pending: section 8 item 2 ("Audit"), after #159's pending line on the testability
  step: "Its go/no-go before pilots (plans/agentic.md) is read by code from one eval run with
  the rubber-stamp expert and a repeat, against X, Y, a per-claim cap and a least denominator
  that Arsh sets; none has been run yet".
