## 2026-10-29: More claims become checkable from their own words (validation rulings R1, R4, R5, R6; fills a to d, f and g)
- Changed: the assumption filler fills more from a claim's own words, and says so. Arsh ruled
  on each step in the validation thread on 2026-10-29.
  - R1, native calls: a call claim that names no app and writes the other party as a phone
    number is searched in the phone's call log (records an import gives no app, "unknown").
    A name or display name with no app is refused.
  - R6, one number written two ways: on one app, identifiers that are the same phone number
    ("+19195677484", "9195677484", "(919) 888-7386", a WhatsApp id) are one party. Before,
    such a number was refused until an expert linked the accounts. Display names, addresses
    and user ids that happen to be digits are never read as numbers.
  - R4 (run driver only, `eval/validation/hickman_run.py`): a person the affidavit defines as
    the user of a number is linked to the accounts whose identifier is that number, in any
    format. Display names never link, and bare digits link only on a phone app or the call
    log: on another app they are a user id, as the filler reads them.
  - Run driver: the challenge step, on by default since #162, is turned off for validation
    runs as the run 3 plan requires, and `run.json` records it.
  - Fill a: a dated quote with no named writer gets its time checked, with no party.
  - Fill b: "X instructed Y by App to <errand>, writing \"...\"" names X as the writer;
    "\"...\" after receiving it from Z." names Z (a person, or one account by its exact
    identifier).
  - Fill c: "after 10:00 a.m." or "before 9 a.m." on one stated day is the rest, or the
    start, of that day.
  - Fill d: an identifier in brackets right after a display name two accounts share picks
    that account.
  - A two-sided check (no contact, count) where the claim writes the phone as an account and
    names another account takes the phone's side as its owner by confirmed stipulation, only
    when that person's accounts are exactly the phone's own.
  - A time stated near midnight may start its window on the day before.
  - R5, open ranges: a no-contact claim that says "never", "before X", "after X", "since X"
    or "until X" and states no other time is checked from the extraction's first dated
    record, or to its last, on the phone's own sources; the assumption text names both
    edges. When the model gave no parties, they come from the claim: the phone's exact
    owner and the one person or number it names. Only a range open at one end takes this
    path: both ends stated, a time of day, a written time zone or an offset ("two days
    after") keep the model's range, read as before. "On or before X" takes in all of X, and a
    date with no year takes the paragraph's year. The edges leave out embedded copies of
    messages, as the absence check's coverage does. Code fills the sides only for plain
    contact wording on the case's own apps: a claim about calls only or messages only
    ("never called", "never texted", "never spoke with"), a possessive or "a friend of"
    party, or an app the case does not hold is refused, since the absence check reads every
    kind of contact on the scope. The range's words say its edges are the
    extraction's own, so contact outside its records is not seen. "Not found" still states
    what was searched and the source's coverage.
  - Fill f, call counts: with 'call' among its channels the count check (1.1.0) counts calls
    on the app named. A call count never fails, since a call log keeps calls that did not
    connect and can hold one call twice; two counted calls 60 seconds apart or less, or a
    counted call with no length or a zero length, make it inconclusive. A counted call's
    deletion flag is named, as for messages. A count of calls one side placed ("outgoing",
    "made", "missed", "called") is refused, since the check counts both directions; so is
    a count of "incoming" or "outgoing" messages, and a count of calls of a stated length or on a subject ("about narcotics"), since a call log
    keeps no subject.
    A call on a calling app the case does not hold ("a Signal call") is not read from the
    call log. The filler reads "N calls" and, when the model gave only one call's time,
    adds the count from it, with the phone's side as its exact owner.
  - Fill g: an assumption code filled, in whole or in part, ends its text with "Filled from
    the claim's wording.", which the expert reads before accepting it. `eval/run_pipeline.py`
    lists Supported claims that rest on such an assumption.
  Why: run 2 of the Hickman iOS 15 validation tested 9 of 106 claims, and run 3 needs at
  least 30 code-checked. Every step only lets code read what the claim plainly writes; the
  expert still accepts each assumption, and rules 0.3.0 are unchanged.
- Where: PR #169 (branch claude/project-thread-ds0ify)
- Verified: on this container, 2026-10-29. New tests in tests/test_assumption_filler.py,
  tests/test_account_lookups.py (two tests changed from "refused" to "one party" under R6)
  and tests/test_validation_run.py. Replaying run 2's recorded model answers through this
  code and running the checks on run 2's case database (development data, project files
  only): 33 code-checked, 14 check unsettled, 3 expert only (50 tested), up from 18, 13 and
  4 at #165. (One claim that names an app the case does not hold was check unsettled before
  the last review round and is now untested: code no longer searches every app for it.)
  One of the 33 is code-checked by its call's time while its count of calls stays
  inconclusive (calls stored twice). 11 of the 33 have a failed core check; whether those are
  right is unscored until run 3's measure 7. `make check`: see the PR.
- Open: the absence check compares stored time strings, so a window edge that falls exactly
  on a record with fractional seconds can report the source as not spanning the window
  (conservative: it leaves the claim unsettled, never supported). Direction for
  counts and "exchanged" needs a `core/contracts.py` field; the diff is in
  PROPOSED_CHANGES.md for Arsh. A failed check on rules 0.3.0 contradicts without an expert,
  so more checked claims also means more such contradictions.
- Affects: capabilities (which claims the filler can make checkable; number matching; call
  counts, count check 1.1.0; the code-made note on assumption text); no privacy change; no
  customer-facing claim change
- Status doc: pending: in the assumption filler's capabilities, add "reads native calls by
  number, one number written several ways as one party, writers from 'instructed ...,
  writing' and 'after receiving it from', part-day ranges on a stated day, open no-contact
  ranges ('never', 'before', 'since') to the extraction's first or last dated record; code-made
  assumptions say 'Filled from the claim's wording.'"
