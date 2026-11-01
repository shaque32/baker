## 2026-11-01: case events, the dated events the document defines (schema 0.7.0) (#201)
- Changed: the expert can enter the events a government document defines and later claims are
  dated by (`the "SEARCH"`). Each event holds its name, its first and last wall-clock day, and
  the paragraph and words that define it. Code checks the words verbatim against the paragraph,
  and refuses days that disagree with dates the words state plainly. It also refuses a name
  that a person, an alias or another event is already matched by, comparing names with Unicode
  case folding (`core/audit/case_events.py`, `core/review/actions.add_event` and
  `remove_event`, logged as `case.event.add` and `case.event.remove`). The assumption filler
  then reads an allow list of whole-day ties to a one-day event: "the day of", "the same day
  as", "the day before or after" and "N days before or after". The day is read in the phone's
  zone like a date the claim writes, so a clock-change day is 23 or 25 hours long. It refuses
  everything else: "in the days before", "shortly before", "the night of", "after" with no
  count, any time of day, part of a day or weekday, two ties, a multi-day event, a quoted name,
  and a name that runs on ("the SEARCH warrant").
  - The Set up page lists events and adds or removes them.
  - The report's Limitations list each event as an expert statement (report 0.31.0).
  - An event change after a run marks verdicts "Not current".
  - The bundle check holds each event to the logged actions.
  - The eval's case setup reads `events` from a case.json that has them. None does yet.
  - Schema and contracts 0.7.0, signed by Arsh 2026-11-01 18:47Z.
  - Why: in the case04 alias replay, 8 of the 11 remaining window or quote refusals were dated
    only by an event or by the sentence before.
- Where: PR #201 (branch claude/project-thread-ds0ify)
- Verified: 42 new tests in `tests/test_case_events.py`. They fail on main, which has no table, actions
    or reader. The near-miss tests are guards that pass both before and after.
  - Replay of Arsh's recorded case04 filler answers (development data, filler only, no model)
    with the three events an expert would enter from its affidavit: claims with a core
    assumption are 15 before and 15 after. The window refusal on C47 ("Two days after the KEDZIE
    YARD theft") is gone, but C47 still converts nothing, because the model's answer holds no
    event or role template. C17 and C35 need forms this version does not read, and the rest are
    refused as before. No new assumption was made, so no new false supported.
  - Outputs are in project files under `baker/agentic/case04-run-2026-10-30/case-events-replay/`.
  - `make check` passes; eval numbers are in the PR.
- Open: conversion gain is measured as zero on case04's recorded answers, and on no other case.
  - The testability step and the model are not told about events, so their effect on an agent
    run is unmeasured.
  - The later forms ("from Monday through Wednesday" in the days before X, a time on the day
    before X) and the sentence-before relation ("The next day") are not read.
- Affects: capabilities (a new expert input; more claims can get a code-set window); customer-facing
  claims (the report lists events as expert statements). No privacy or network change.
- Status doc: pending: section 2 "Pipeline (main)", row "5. Assumptions": add "reads a whole day
  tied to an event the expert entered (the day of, the day before or after, N days before or
  after; one-day events only; schema 0.7.0)". Section 8 item 5 ("Case safety and delivery"),
  after the person-aliases sentence: add "The expert can also enter the events the document
  defines (the SEARCH) with their days and defining words, checked verbatim against the
  paragraph, on the Set up page; every report lists them as the expert's statement (schema
  0.7.0)."
