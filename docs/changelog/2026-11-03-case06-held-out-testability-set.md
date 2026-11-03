## 2026-11-03: Synthetic case06 draft, the held-out set for the next testability go/no-go
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
  `PROPOSED_CHANGES.md` holds Arsh's signing entry with the commands that copy the drafts into
  `eval/gold/case06/`.
- Where: branch `claude/project-thread-6i2msb-case06` (PR, merge after #210)
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
  then report as signed. make check: see the PR.
- Open: no go/no-go has run on case06. It needs #201, #209 and #210 merged, prompt v1.1 signed,
  Arsh's signature on this key and sheet, and an overnight run on Arsh's Mac (about 10 to 12
  hours, unmeasured for case06); the first complete run is the result of record. Whether the
  conversion bar should count only claims that end on the key's verdict is Arsh's decision,
  asked before the run. The model-free result shows only that the right sheet gives the drafted
  verdicts, not that the hazards trap a model.
- Affects: none (eval data draft)
- Status doc: no change
