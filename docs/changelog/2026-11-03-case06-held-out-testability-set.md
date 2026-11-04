## 2026-11-03: Synthetic case06, signed, the held-out set for the next testability go/no-go; testability prompt v1.1 signed
- Changed: a new synthetic case06 is the held-out set for the testability step's next go/no-go,
  because the case05 go/no-go (2026-11-03, NO-GO on conversion, 5 of 33) spent case05. A fresh
  builder wrote it from a brief (project files, `plans/case06-brief.md`) without reading the
  step's prompt, code, tests or demo, the filler, name or event code, the eval runner, or any
  case04 or case05 result or diagnosis. The brief is case05's, with two additions that say only
  what the product reads: the names the affidavit defines go in `case.json` (person aliases,
  phone names, number names and events), and the sheet's windows follow code's conventions
  ("at about H:MM" is 8 minutes either side, end exclusive; "at H:MM" is that minute; "between
  H1 and H2" runs through the whole H2 minute; a date or a day set by an event is midnight to
  midnight). Six windows follow no convention; each carries its reasoning and is listed in
  `SIGNING_SHEET.md` under its own heading. case05's design is kept so the runs can be compared:
  - 48 claims in a mock affidavit, six of each claim type, three plain and three in affidavit
    wording per type;
  - verdicts set before the story: 24 supported, 12 contradicted, 12 unproven;
  - a planted wrong reading on 47 claims: near_window 12, similar_quote 8, second_number 8,
    second_phone 8, same_name 6, contact_name 5;
  - a sheet for every claim, 89 rows, 71 tested by a check (50 pass, 12 fail, 9 inconclusive);
    only C39 (role) has a role row alone.

  The world is new: three Cellebrite-style reports in America/Los_Angeles, across the start of
  daylight saving on 2025-03-09 (2 to 3 a.m. never happens). Item 1 prints UTC, Item 2 local time
  with its offset, Item 3 a fixed UTC-8. `case.json` holds what the affidavit defines:
  - aliases: VARLOW CC-1 and SKIP; COYLE CC-2; PELLOQUIN CC-3, DUKE and the HAULER;
  - phone names: the GALAXY (Item 1), the KYOCERA (Item 3);
  - number names: the SPARE LINE (+1 (360) 555-0163), the WORK NUMBER (+1 (360) 555-0192), the
    KELPWISE ACCOUNT (a Telegram id);
  - events: HARBOR THEFT, TRANSFER, KITTIWAKE THEFT, SURVEILLANCE, RECOVERY.

  SKIP and DUKE equal the first names of two people in the reports who own no phone, on
  purpose (the same-name hazard, as case05's TOBY and CAL). That departs from the brief's naming
  rule, and the signing sheet says so for Arsh to accept. The builder first wrote the
  designations as "SUBJECT A/B/C"; the eval's case setup refused them, because the Identities
  page's name words drop single letters, so "SUBJECT A" and "SUBJECT B" both read as "subject".
  It used CC-1 to CC-3 instead. That refusal is a product gap (affidavits use letter
  designations), noted in plans/testability-pass.md for a separate fix.

  A second blind reader, under the same limits, read the draft claim by claim: 10 findings
  (2 likely, 8 questions). The builder fixed 9 by changing the data or the key, with no verdict
  moving: C40's trailer keys now rest on records that name the trailer; Item 2's decoy 'Duke'
  number is now plainly a mechanic, so C12's contradicted is not arguable; C39's decoy now gives
  the wrong reading the key says it does. It kept C34's wording ("the hour before the clocks went
  forward"), since the affidavit defines that night and a clock-time wording would end on a
  minute that never existed. The reader rechecked the fixes, found every finding settled, and
  raised four small items, all fixed. Every answer is in `SIGNING_SHEET.md` and the key.

  `eval/run_pipeline.py` registers case06's draft key, sheet, reports and affidavit PDF, and
  `TESTABILITY_GO_NO_GO_CASES` names case06 alone (registered before the build started).

  Signed: Arsh approved on 2026-11-03 at 21:03Z, in the project thread, both the case06 key and
  sheet (as they stood after the second read and its recheck, the SKIP and DUKE naming
  departure included) and the testability prompt v1.1 (the draft in #210). On his choice the
  same minute, the conversion bar stays as it is; how many claims the agent changed end on the
  key's verdict is reported beside it, not a bar (#210). Both are applied here from their
  `PROPOSED_CHANGES.md` entries: `eval/gold/case06/gold.jsonl` and `assumptions.jsonl` are the
  drafts with only `labeled_by` and `labeled_at` changed, and
  `core/audit/prompts/agent_testability.md` is v1.1, its body the draft's word for word.

  Codex's review of the synced head (4168585) found two things that would have biased the
  case06 run, both fixed here before any run:
  - Prompt draft v1.2, waiting for Arsh's signature (`PROPOSED_CHANGES.md`). v1.1 had narrowed
    "handles" to "handles exactly as written" and sent saved names to "quoted_text", but the
    same-account check resolves a handle from account names, thread titles, printed sender text
    and saved contacts, and `same_account` takes only handles. A claim that names accounts by
    display names had no field for them. Draft v1.2 restores v1.0's "handles or display names";
    a contact entry's saved name stays in "quoted_text". That is the only change to the body.
  - The eval's sheet check (`core/audit/testability.sheet_named`, with the new
    `account_copies`). For a claim that names no phone, the filler finds a number in every
    report that holds it, while a sheet row names one report's copy, and the check compared
    account ids one by one. So a right answer was rejected as naming an account the sheet does
    not name. Now, when a claim's core rows name no phone, an account they name counts in any
    report that holds it on the same app (same key, ruling R6). A claim the rows tie to a phone
    keeps exact ids. Account mismatches never counted toward the wrong person, phone or window
    bar; they cost conversion and the sheet-reject figure beside it. The signed sheet is
    unchanged.
- Where: PR #211 (branch `claude/project-thread-6i2msb-case06`; #201, #209 and #210 are merged)
- Verified: `tests/test_synthetic_case06.py` (synthetic only, 38 tests): the generator gives the
  same bytes twice and the committed drafts match a fresh build; the importer reads all three
  reports, and every key and wrong-reading record exists at its story time with the right offset
  across the clock change; the design counts; every sheet row fits its template, and each
  checked row gives the sheet's expected outcome; every window follows its convention or is
  listed; `case.json` matches the affidavit (each defining text in exactly one paragraph); the
  second read is answered and the naming departure stated; and a model-free run on the draft
  sheet gives all 48 drafted verdicts (accuracy 1.00, 0 false supported against the draft key,
  partly by construction since the simulated expert reads that key). The signing commands were
  run on a scratch copy: 48 key lines and 89 rows, `grep -c DRAFT` prints 0 for both, and both
  then report as signed. Applied the same way: `grep -c DRAFT` prints 0 for both signed files
  (48 key lines, 89 rows), each differs from its draft only in `labeled_by` and `labeled_at`,
  `key_status` and `sheet_status` say signed, and the signed prompt's body equals the draft's
  from `<!-- prompt starts -->` down. make check: see the PR.
- Open: no go/no-go has run on case06. It needs #201, #209, #210 and this PR merged, and an
  overnight run on Arsh's Mac (about 10 to 12 hours, unmeasured for case06); the first complete
  run is the result of record. Nothing is tuned on case06 before it (plans/testability-pass.md,
  "Frozen before the case06 run"). The model-free result shows only that the right sheet gives
  the signed verdicts, not that the hazards trap a model. Prompt v1.1 is unmeasured on any
  model run, and so is v1.2. The case06 run waits for Arsh to sign v1.2.
- Affects: the testability agent's prompt (v1.1, draft v1.2; eval only, the agent stays off by
  default) and how the eval compares a try's accounts with the sheet (go/no-go measurement); no
  privacy, network or verdict rule change; no customer-facing claim.
- Status doc: no change
