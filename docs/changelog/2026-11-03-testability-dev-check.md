## 2026-11-03: Testability dev check: case setup names, a no-stance run, prompt v1.1 draft
- Changed: Steps 2 to 4 of plans/testability-pass.md, after the case05 go/no-go (NO-GO,
  conversion 5 of 33).
  - **Case setup.** The eval's case setup (eval/run_pipeline.build_case) now enters the
    document's names for each phone (`devices[].names`) and for a number (`numbers`, each an
    identifier and its names) from case.json, with the expert actions name_device and
    name_account, as it already did for aliases. case04 gains the TARGET PHONE (Item 2) and the
    PREPAID (+1 (312) 555-0199); case05 gains the SAMSUNG, the iPHONE, the ONEPLUS and the BURNER
    (+1 (720) 555-0186). Names the affidavits give people who used a number (CW-1, the BUYER,
    the FENCE) stay out: they are not the number. Both generators write the new fields; the
    reports, affidavits, keys and sheets are byte for byte the same (the generator version
    stays 0.1.0, because the reports print it).
  - **Spent cases.** case05's go/no-go of record is done, so TESTABILITY_GO_NO_GO_CASES is now
    empty: no run on case04 or case05 gives a go/no-go again. The next held-out case joins it
    once Arsh signs it.
  - **`--no-stance`.** With `--testability CAP`, a dev check of the filler and the step only: a
    stand-in labels every candidate irrelevant with no model call, the run's measures are
    recorded as usual, and the go/no-go says none given ("stance was skipped"). Output in
    `<out>/no_stance/`.
  - **Prompt v1.1 draft** (`docs/prompts/agent_testability.md`), for Arsh to sign: a retry
    changes what the reasons name; a name the lookups list as an account goes in "accounts",
    never "people"; "quoted_text" only holds words inside the claim's quotation marks; a
    sender names only the sender; a message count names its two sides. Its header lists each
    change. PROPOSED_CHANGES.md has the exact edit to the signed copy, which stays v1.0.
- Where: PR #210 (merge after #209)
- Verified: tests/test_case_setup_names.py (case.json matches the generators; case04 and
  case05 setup enter the names under the eval's expert actor; the names resolve in the filler
  to the affidavit's phones and number; "COURIER" reads as the alias "the COURIER"; the FENCE
  is no account). tests/test_testability_go_no_go.py (a no-stance run records the step's
  measures, sends no stance prompt and gives no go/no-go even on a held-out case with every
  other condition met; no spent case is a go/no-go case; --no-stance needs --testability).
  tests/test_synthetic_case05.py now checks case05 is spent. tests/test_testability.py passes
  with the v1.1 draft. make check: see the PR. No model run.
- Open: The dev check itself runs on Arsh's Mac (unmeasured: about 1 to 1.5 hours a case). A
  replay of case05's recorded answers through the filler 5 code (no model) converts 6 of 33,
  up from 5: most remaining misses need the model to answer differently (a number's name
  written as a person, the wrong number, a sender with two parties), which is what v1.1 and
  the new lookups aim at. Dev numbers on case04 and case05 can flatter; only case06 counts.
- Affects: performance (eval only: what the testability dev check measures); no capability,
  privacy or customer-facing claim. The signed prompt is unchanged until Arsh signs v1.1.
- Status doc: pending: section 8, in the item that describes the testability step's go/no-go
  (the one #208's entry edits), add after its results: "case04 and case05 are spent and give
  no go/no-go again; the eval's case setup enters the affidavits' phone and number names, and
  `--no-stance` runs a dev check of the filler and the step without the stance model."
