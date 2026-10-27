## 2026-10-27: Assumption filler reads call lengths with halves, two parts and bounds
- Changed: in run 1 of the real-export validation, 2 claims were refused only because code
  could not read the call length: "about one and a half minutes" and "more than a minute and a
  half". `duration_range` in `core/audit/assumption_filler.py` now reads more of the ways a
  document states a call's length. The change is code only: no model, prompt, rule, contract,
  schema, gold, scorer or `eval/validation/` file changes.
  - Halves: "a minute and a half" and "one and a half minutes" are 90 to 119 seconds, to the
    half minute the words state. "half an hour" is 1,800 to 3,599.
  - Two parts: "two minutes and 30 seconds" is 150 seconds, to the second.
  - Compound number words: "forty-five", "twenty two".
  - Bounds, which were refused before, are open ranges. "more than a minute and a half" is 91
    seconds to one day, "at least two minutes" 120 to one day, "under two minutes" 1 to 119,
    and "no more than two minutes" 1 to 120. The lower end is 1 second, because a call that
    lasted 0 seconds never connected.
  - A bound or "about" the claim writes right before the model's words counts. In "a call
    lasting more than two minutes", the model's "two minutes" is read as "more than two
    minutes". Before, it was read as 120 to 179 seconds. If the claim writes the same words
    twice with different words before them, the duration is refused.
  - The rules for "about" (25% either side) and for a plain length ("two minutes" is 120 to
    179) are unchanged.
  - A call length only narrows which calls the time check counts. That check never fails on
    calls (`core/audit/checks/timing.py`), so a call length cannot contradict a claim.
- Where: branch `claude/project-thread-6i2msb-parsers`, stacked on #152
- Verified: `tests/test_assumption_filler.py`, all on made-up wording:
  - `test_duration_range` grows from 5 to 17 cases: halves, two parts, compound number words
    and the four bounds;
  - a new test reads a bound the claim writes before the model's words, and refuses the same
    words written twice with different leads;
  - `test_duration_range_refuses` covers "a while", "2m", "a few minutes", "just two
    minutes", "under a second", "zero seconds", "between one and two minutes" and "two minutes
    and three minutes".
  - One existing expectation changed on purpose. "under two minutes" and "more than a
    minute" were refused before and are now read as open ranges.
  - Read-only replay of run 1's 2 recorded duration proposals on run 1's own case data, with
    #150 and #152, done after the code was written. Both now give a record_time assumption
    with no coverage gap: "more than a minute and a half" is 91 seconds to one day, and "about
    one and a half minutes" is 68 to 112 seconds.
  - `make check` passes; its eval numbers are in the PR.
- Open: unmeasured on a run, and not held out, because the parser was written after reading
  run 1's refusals.
  - The planned "one retry on invalid output" is dropped. Run 1's 2 invalid outputs were
    deterministic model failures, the same bytes on all 3 runs (temperature 0, seed 1234):
    - one is a channel list that repeats "WhatsApp" until the output limit;
    - the other lists every app in the case, which is more than the 4 channels allowed.
    A retry with the same prompt would get the same answer, so these 2 claims stay refused
    with their reasons, for the testability agent.
  - "between one and two minutes" and decimal lengths ("1.5 minutes") are still refused.
  - The time check's own text shows an open bound as "lasting 91 to 86400 s".
- Affects: capabilities. More claims can be set up from real affidavit wording.
- Status doc: pending: section 9 item 8 ("Other gaps"): add "a call length with a half, two
  parts or a bound ('more than a minute and a half') is read by code as a range of seconds
  (#N)".
