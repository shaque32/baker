## 2026-10-29: Synthetic case04 draft, the held-out set for the testability step's go/no-go
- Changed: new synthetic case04 to serve as the held-out set for the testability step's
  go/no-go. It was written without reading that step's code, prompt, tests or demo claims.
  Forty-eight claims in a mock affidavit, six of each claim type, three in plain wording and
  three in affidavit wording (defined terms, aliases, relative or approximate times, indirect
  speech, references back, numbers in words) per type. Draft verdicts are 24 supported,
  12 contradicted and 12 unproven, each recorded before the story was written. 46 claims carry
  a planted wrong reading (`hazard`): same_name 9, second_number 9, second_phone 6,
  near_window 11, contact_name 3, similar_quote 8 (2 have none). The data holds the wrong
  candidate and the sheet names only the right one. Every claim has a sheet in
  `draft_assumptions.jsonl` (85 rows). 46 claims have a core row a deterministic check tests;
  C39 and C42 (role) have only a role row. The case has three Cellebrite-style reports
  (1,380 messages, 47 calls), all set to America/Chicago, printing times three ways: Item 1 in
  UTC+0, Item 2 in local time, Item 3 at a fixed UTC-6. It shares no name, number or handle
  with case01 or case03. It is generated deterministically (seed 20260429) by
  `eval/synthetic/case04_generate.py` from `case04_story.py` and `case04_key.py`. The DRAFT key
  (`draft_gold.jsonl`, labeled_by "DRAFT (case04 builder, not signed by Arsh)"), the DRAFT
  sheet, `ANSWER_KEY_DRAFT.md` and `SIGNING_SHEET.md` (with count tables) are under
  `eval/synthetic/case04/`; nothing is under `eval/gold/`. `eval/run_pipeline.py` gains case04
  entries in DRAFT_GOLD and DRAFT_SHEETS and case04 branches for the reports and the affidavit
  PDF. case04 is the one case in `TESTABILITY_GO_NO_GO_CASES`, the held-out list the step's
  go/no-go reads. It is not wired into `make eval` or any merge gate. The step runs only on a
  signed sheet, so until Arsh signs case04 (the `PROPOSED_CHANGES.md` entry "sign case04's key
  and assumption sheet" copies the drafts into `eval/gold/case04/`) it refuses case04 and no
  go/no-go is given.
- Where: PR #170 (branch `claude/project-thread-6i2msb-case04`)
- Verified: `tests/test_synthetic_case04.py` (synthetic only, 26 tests):
  - the generator gives the same bytes twice, reports included, and the committed drafts match
    a fresh build, with case.json's SHA-256 pins;
  - after the real Cellebrite Excel importer reads all three reports, every key-evidence and
    wrong-reading record exists;
  - every claim records its type, verdict, wording and hazard, and the design counts hold;
  - claims are verbatim in their paragraphs, and the affidavit PDF reads back;
  - quotes are verbatim in cited records, except C06, whose quote is in no record by design;
  - every sheet row fits its template, and each of the 70 rows a check tests gives the sheet's
    expected outcome;
  - background chatter uses no reserved word and never joins two subjects;
  - a model-free run on the draft sheet gives the drafted verdict for all 48 claims;
  - case04 is the go/no-go's one held-out case, and the step refuses its draft sheet.

  Model-free run on the draft key and sheet (cloud container, 2026-10-29, information only):
  accuracy 1.00 and 0 false supported against the draft key, partly by construction since the
  simulated expert reads that key. The unreviewed run scores 0.50 (0 supported by design).
  Key-evidence recall is 66% retrieved and 65% surfaced (135 records). The 12 contradicted
  claims are decided by failed core checks. `--repeat` gave identical predictions. A spot
  check (not committed) ran the wrong reading of 17 hazard claims through the checks: 15 gave
  another outcome than the right reading. C13 and C14 did not: C13's spot-check window was not
  the wrong reading, and C14's wrong call passes too, as its hazard says. `make check` passed.
- Open: the key and sheet are drafts until Arsh signs them; the pipeline reports them as
  drafts. Closest calls: C20 and C24 (meaning not fixed by the conversation) and C39
  (recruitment as interpretation), all drafted unproven. The model-free result does not show
  that the hazards trap a model, only that the right sheet gives the drafted verdicts. The
  go/no-go measurement itself is not part of this change. case04 is in DRAFT_SHEETS (case03 is
  not), so `--mode model-free` without `--assumption-spec` uses the draft sheet.
- Affects: none (eval data draft)
- Status doc: no change
