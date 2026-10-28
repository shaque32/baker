## 2026-10-28: Testability agent behind a flag, eval only (step 3 of the agent plan) (#159)
- Changed: step 3 of the agent plan (approved by Arsh 2026-10-27 17:29Z, `plans/agentic.md`;
  design note `plans/testability.md`). New `core/audit/testability.py`, off by default
  (`Components.testability`) and eval only: it cannot run without a signed assumption sheet to
  check against. It loads only the signed prompt, which Arsh signed in this PR.
  - On a claim the assumption filler left untested (no core assumption), the step asks the same
    local model again, at most CAP times per claim. Each call is stateless and carries the claim,
    its paragraph, the allowed templates, the case's apps, code's reasons for refusing the last
    try, and code's lookups: the people, phones and accounts the claim's own words name in the
    case (read-only queries, fixed by code). The answer has the filler's shape and goes through
    the filler's own checks (the same functions): every value verbatim in the claim or
    paragraph, names, phones and accounts resolved by code, stated time ranges, `coverage_gap`.
  - Code then checks the try against the claim's signed sheet rows: every person, phone, time
    window, account, handle, app, template and quoted words it names must be one the sheet
    names for the claim. Anything else rejects the try. A claim the sheet gives no core row is
    never repaired, and the eval refuses to run the step on a hidden case (case02).
  - A try that passes is a proposal. Only an examiner's acceptance makes it the claim's
    assumptions; without one it is logged and never used. In v1 the examiner is the eval's
    simulated expert, which accepts every repair that passed code's checks; with `--expert none`
    nobody accepts. No UI, and no question to the expert (Arsh's change 5).
  - The repair has no field for the claim text, and the claim's stored row is hashed before and
    after; a change fails the run.
  - Each try is its own `testability.repair` audit entry (lookups, model call, reasons, sheet
    check, assumption ids). Each acceptance is a `testability.accept` entry under the examiner's
    actor. On the eval's replay pass the step reuses its answers and the logged acceptance.
  - `mabillon verify-bundle` re-runs each try's lookups and code's checks on the stored answer
    with no model. It also checks that the stored prompt carried those lookups and reasons. It
    fails a repaired assumption kept without an expert's acceptance, an acceptance by a
    non-expert actor, and repair entries for a run that did not turn the step on. A scoped
    bundle (one without the phone's records or the step's model answers), another step version
    or a change to people, phones or imports after the run is noted, not re-run. A claim removed
    after the audit is still re-run.
  - Report 0.21.0 (after #149's 0.20.0): such an assumption says "Proposed by agent, accepted by
    examiner (<name>)" in its claim's assumption table and verdict trace. A run without the step
    renders as before.
  - Eval: `eval/run_pipeline.py --mode real --testability CAP [--testability-prompt PATH]`. The
    model fills, and the sheet is used only to check and score. It reports the claims the filler
    left untested, how many of them the sheet makes testable (the denominator for X), repairs
    converted and accepted (labelled an upper bound, since the signed sheet filters every try),
    the share of tries that passed the filler's checks but failed the sheet check (the
    wrong-entity rate), calls, invalid outputs, mismatches (person, phone or window apart from
    the other kinds), repairs on claims the sheet leaves untested, and seconds. X, Y
    and the held-out go/no-go cases are placeholders (`TESTABILITY_X_PERCENT`,
    `TESTABILITY_Y_BUDGET`, `TESTABILITY_GO_NO_GO_CASES`). CAP has no default. Until all are
    set, the prompt is signed and a held-out case runs, it prints "go/no-go: none given".
  - Prompt: draft `docs/prompts/agent_testability.md` v0.1, signed by Arsh word for word as
    `core/audit/prompts/agent_testability.md` v1.0 (2026-10-28, his commit 88fe932 on this
    branch). It is written generally and not tuned to any validation claim. Its wording drew on run 2's refusal kinds (counts only: no meaning
    assumption, a call with no parties, a phone's name proposed as an account).
  - CLAUDE.md gains the line naming agents as local jobs that only propose, signed and written
    by Arsh in the same commit. Both are recorded in `PROPOSED_CHANGES.md`.
  - No rule, prompt, pin, contract, schema, gold or scorer file changes, and nothing under
    `eval/validation/` or the `validation-v1-run2` tag. Off by default, so no default run changes.
- Where: PR #159 (branch `claude/project-thread-6i2msb-testability`)
- Verified: new `tests/test_testability.py`, 34 tests on synthetic case01 with scripted models:
  - the draft prompt (and a signed copy, once there is one) carries every placeholder, and the
    answer has no field for the claim;
  - lookups find the phone and number the claim writes, whole words only;
  - the sheet check passes what the sheet names, rejects another person, phone, account, app,
    template or quoted words, and compares windows by their UTC ends;
  - a refused claim is repaired, checked and used once the examiner accepts, and its prompt
    carries code's reasons and lookups;
  - a repair nobody accepts, or that a non-expert accepts, is never used;
  - another phone is rejected and counted as a no-go, and an account the sheet does not name is
    rejected but not counted as one;
  - a claim the sheet leaves untested is never repaired;
  - the cap bounds the calls, each try is told the last one's reasons, the step stops at the
    first pass, and an unusable answer counts as invalid;
  - the first pass's refusals are left as they were, and a repair that changes the claim fails
    the run;
  - the step refuses a cap below one or an empty sheet, and the eval refuses a hidden case;
  - a claim the filler already tests never reaches the step;
  - in the audit: off by default, each try and the acceptance are logged, the model call is
    stored, a proposal without an examiner leaves the claim untested, and the report shows the
    mark;
  - verify-bundle re-runs the try and passes, notes a bundle without the step's model answers,
    re-runs a claim removed after the audit, and fails a try that no longer follows, a repair
    kept without an expert's acceptance, and entries for a run without the step;
  - with no expert, the eval logs the repair and never uses it;
  - the eval reports the measures, labels conversions an upper bound, replays without asking
    again, and gives no go/no-go.
  - The step's effect on a real model is not measured: that needs the 14B on the Mac and a
    held-out set. `make check` passes; its eval numbers are in the PR.
- Open: Arsh sets X, Y and CAP. He asked on 2026-10-28 (07:44Z) for the agents to be on by
  default in demos and pilots; that is later work (plans/agents-on-by-default.md), and this PR
  keeps the step off by default and eval only, as the signed CLAUDE.md line says.
  - The go/no-go set (held-out synthetic claims with signed sheets, written by someone other
    than the prompt's author) does not exist yet.
  - The byte-identical Mac GPU repeat and the time budget are unmeasured.
  - The step runs only on claims the filler leaves untested, so each conversion is a gain over
    the code baseline at that commit. The go/no-go should run after the planned code fills
    (validation thread), which also reach every repair, since the step calls the filler's own
    functions and does not edit them.
  - Partly refused claims that the filler still tests are not repaired in v1.
  - A real examiner's accept step (UI) is a later change. So is a `proposed_by` contract field,
    if wanted; the mark is read from the log.
- Affects: capabilities (behind a flag, off by default, eval only)
- Status doc: pending: section 8 item 2 ("Audit"): add "An eval-only testability step
  (`eval/run_pipeline.py --testability CAP`, off by default) asks the local model to retry a
  claim the assumption filler left untested; code checks each try with the filler's checks and
  against the signed sheet, only an examiner's acceptance uses it, each try is logged and
  re-run by verify-bundle, and the report marks it "Proposed by agent, accepted by examiner".
  Its prompt is signed (v1.0); its effect is unmeasured".
