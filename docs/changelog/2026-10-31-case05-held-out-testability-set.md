## 2026-10-31: Synthetic case05 draft, the new held-out set for the testability step's go/no-go
- Changed: a new synthetic case05 replaces case04 as the held-out set for the testability step's
  go/no-go, because case04's go/no-go run (2026-10-30) spent it. A fresh builder wrote it from a
  brief (project files, `plans/case05-brief.md`) without reading the step's prompt, code, tests
  or demo claims, the other prompts, the eval runner, or case04's results. It keeps case04's
  design so the two runs are comparable:
  - 48 claims in a mock affidavit, six of each claim type, and per type three in plain wording
    and three in affidavit wording;
  - verdicts set before the story was written;
  - a planted wrong reading on 46 claims: near_window 11, similar_quote 9, second_number 8,
    second_phone 7, same_name 6, contact_name 5;
  - a sheet for every claim, 86 rows, 70 of them tested by a check;
  - only C39 and C42 (role) have a role row alone.

  The world is new. Three Cellebrite-style reports are all set to America/Denver, and the case
  crosses the end of daylight saving on 2025-11-02, so 1 to 2 a.m. happens twice. Item 1 prints
  local time with each row's offset, Item 2 prints UTC+0, and Item 3 prints a fixed UTC-7. It
  shares no name, number or handle with case01, case03 or case04, and every handle and id is
  invented.

  The affidavit's definitions are recorded as the phone owners' aliases in `case.json`:
  - MERROW: SUBJECT-1 and TOBY;
  - VARGA: SUBJECT-2;
  - ODUM: SUBJECT-3, CAL and the COURIER.

  The first draft was 24 supported, 12 contradicted and 12 unproven. A second blind read (13
  findings, each answered in `SIGNING_SHEET.md`) moved C04 to unproven, because its only tie is
  the number's own self-identification. It also set `each_way` on four "exchanged" rows, added a
  core `person_identity` row to C10, reworded C10, C22, C35, C36 and C48 so each window and
  meaning follows from the claim's own words, and renamed two businesses and four handles that
  could be real. So the draft is 23 supported, 12 contradicted and 13 unproven. The signing sheet
  also lists each alias that matches inside a quoted name (C07, C08, C09, C12, C24) and which
  person it points to, right or wrong. That is real product behaviour, so it is left for the
  measurement to see.

  `TESTABILITY_GO_NO_GO_CASES` now names case05 alone, and case04 leaves it. `eval/run_pipeline.py`
  gains case05 entries in DRAFT_GOLD and DRAFT_SHEETS, and case05 branches for the reports and
  the affidavit PDF.

  Building it turned up an eval harness bug: the sheet filler mapped the sheet's person ids in
  `person_ids` to the case's stipulated owners but left `sent_by` as written. A `sent_by` count
  row then named a party its own row no longer held, and the row was refused, so the claim was
  never tested. `spec_filler` now maps `sent_by` too. No earlier sheet uses `sent_by`, so no
  earlier result changes.
- Where: branch `claude/project-thread-6i2msb-case05`
- Verified: `tests/test_synthetic_case05.py` (synthetic only, 32 tests):
  - the generator gives the same bytes twice, and the committed drafts match a fresh build;
  - the real importer reads all three reports, and every key and wrong-reading record exists and
    imports at its story time with the right offset, both passes of the repeated hour included;
  - the design counts hold;
  - every sheet row fits its template, and each checked row gives the sheet's expected outcome;
  - the second read is answered;
  - every alias match inside a quote is recorded;
  - a model-free run on the draft sheet gives the drafted verdict for all 48 claims;
  - case05 is the go/no-go's one held-out case, and the step refuses its draft sheet.

  `tests/test_simulated_expert.py` adds `test_spec_filler_maps_sent_by_with_the_people_it_names`,
  which fails without the fix.

  The model-free run on the draft key and sheet (cloud container, 2026-10-31, information only)
  gave accuracy 1.00 and 0 false supported against the draft key. That is partly by construction,
  since the simulated expert reads that key. The unreviewed run gives 0 supported by design.
  Key-evidence recall is 66% retrieved and 65% surfaced, over 136 records. Arsh's signing
  commands in `PROPOSED_CHANGES.md` were run on a scratch copy, and both files then report as
  signed. `make check` passed.
- Open: Arsh signs the key and sheet; until then no go/no-go is given.
  - The closest calls are C04, which goes back to supported if paragraph 3's premise is accepted;
    C24, whose meaning the conversation doesn't fix; C39, where recruitment is interpretation;
    and C08, which is unproven because a missing contact entry never fails.
  - C10's same_account pass depends on the importer keeping the first display name seen.
  - The model-free result shows only that the right sheet gives the drafted verdicts, not that
    the hazards trap a model.
  - The go/no-go run itself waits for the validation thread's window and quote work and for Arsh's
    Mac (about 10 hours).
- Affects: none (eval data draft and an eval harness fix)
- Status doc: no change
