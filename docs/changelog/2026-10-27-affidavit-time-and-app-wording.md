## 2026-10-27: Assumption filler reads real affidavit times, written zones and export app names (#150)
- Changed: run 1 of the real-export validation tested 0 of 106 claims, and its refusals showed
  wording the filler's code could not read. This change is code only. No model, prompt, rule,
  contract, schema, gold, scorer or `eval/validation/` file changes.
  - Date first. `stated_windows` now reads a date followed by its time: "On April 30, 2023, at
    approximately 11:11 a.m. EDT", "On May 2, 2026, between 9 and 11 p.m.". Before, it read
    only the time-first order ("At 11:11 a.m. on April 30, 2023"). The ±8 minute rule for
    "about" is unchanged, and so is the rule that leaves "between approximately X and Y" to
    the model.
  - Never wider than the words. Before, a time code could not tie to its date was widened to
    the whole day. That covered "On April 26, 2023, between approximately 11:42 a.m. and
    12:18 p.m.", "after 10:00 a.m.", "beginning at" and a zone between the time and the date.
    Now any time of day the claim writes outside quoted words that no range was read from
    leaves the claim's ranges to the model and `check_window`.
  - Open ranges. A word right before a date or time that opens or extends its range ("after",
    "since", "by", "from", "between", "starting", "beginning", "as of") or right after it
    ("onward", "or later", "and thereafter") leaves the claim's ranges to the model. Before,
    main read "After 9 p.m. on January 9, 2026" as the 9 p.m. minute, so an absence would have
    searched one minute. A weekday between that word and the date counts the same way:
    "Starting on Friday, January 9, 2026, at 9 p.m." is not read.
  - Written zones. A zone written right after a time ("EDT", "(EST)", "ET", "Eastern Time",
    "UTC"), or right after a date ("March 3, 2026 (UTC)"), is read by code, never taken from
    the model. After a date, a two-letter zone counts only in brackets, since "PT" there may
    be a person's initials. UTC or GMT is read as UTC; before, a model that said "phone" put
    a written "UTC" time in the phone's zone. A zone inside quoted words is the message's,
    never the range's. Any other zone must
    have the offset the phone's zone has at both ends of the range. Otherwise the range is
    refused with both offsets named, for example "EST (UTC-05:00), but the phone's zone
    America/New_York is at UTC-04:00 then". A zone right after a time that code does not read
    refuses the range (review fix), so it is never read in the phone's zone instead: an
    abbreviation not in capitals ("pdt"), an offset ("UTC+3", or "+0300" with no name), a zone
    outside the US and UTC
    ("BST", "AST", "bst") or another zone's name ("Central European Time", "central european
    time"). After a date, an offset ("January 9, 2026 UTC+3") or a zone in brackets that code
    does not read ("(BST)") refuses the range too (review fix). The claim's words right after
    the model's are checked even when the model's words give a zone, so "On January 9, 2026
    UTC" taken from a claim that writes "UTC+3" is refused (review fix). A title-case word ("Sgt."), a
    lowercase English word ("west") and "local time" are not taken for a zone.
  - Export app names. `APP_ALIASES` covers the names real exports use: "Wickr Pro" and "Wickr
    Me" for "Wickr", "Kik Messenger" for "Kik", "Microsoft Teams" for "Teams", and iOS "Native
    Messages" for "iMessage" and the SMS words.
    - A word names such an app only when no other app in the case goes by it. In a case with
      both "Wickr Pro" and "Wickr Me", "Wickr" is refused as ambiguous.
    - A capitalized word names the app only as written or in capitals: "Teams" or "TEAMS",
      never "the teams met".
    - No message count and no absence is read from "Native Messages" by an alias, because it
      holds iMessage and SMS together. A count could include messages the claim does not name,
      and an SMS could fail a claim of no iMessages.
- Where: PR #150 (branch `claude/project-thread-6i2msb-coverage`)
- Verified: new `tests/test_affidavit_wording.py`, 91 tests on synthetic case01 with made-up
  wording:
    - the date-first forms and written zones, each also passing `check_window`;
    - 11 phrasings that must not be read, including a second time, "beginning at", "after",
      a spelled-out range across two dates, 24-hour and bare hours, and midnight;
    - a count after a date is not read as a time;
    - 19 open ranges are not read, 6 of them with a weekday before the date, and words beside
      a range that do not open it still read;
    - 11 zones code does not read after a time, and 5 after a date, refuse the range, in the
      claim's words and after the model's (an offset with no name, "+0300" or "(-05:00)",
      among them), while one in quoted words or after no time does not; 7 words after a time
      or date that are not a zone still read, and a range's other end ("9 p.m.-10:00 p.m.",
      "10:00-10:30 a.m.") or a year ("2026-2027") is not taken for an offset;
    - the claim's zone wins over the model's;
    - a "UTC" inside the quoted message does not make the range UTC;
    - a written UTC is read as UTC, a whole day too;
    - a zone right after a date is read, and initials after a date are not;
    - a zone the phone is not in then is refused (EST in July, CST and CT in January);
    - the zone the claim writes after the model's words is checked, also when the model's words
      stop inside it ("UTC" of "UTC+3", "(GMT" of "(GMT-5)", after a date and after a time),
      and a zone the model's words give still reads when the claim adds nothing to it;
    - every alias works, ambiguity is refused, "the teams met" names no app, and no count or
      absence is read on Native Messages.
  - One existing expectation changed on purpose (`tests/test_assumption_filler.py`). "On March
    12, 2026 at noon" now reads the noon minute; before, it returned no range.
  - `make check` passes; its eval numbers are in the PR.
  - Read-only comparison on run 1's 106 claim texts, from its stored database. The
    review fixes (open ranges, quoted zones, capitalized words, absences on Native Messages,
    a weekday before an open range, zones code does not read) came after it; rerun, they
    change none of the 106 claims' ranges, and replaying run 1's 106 recorded proposals gives
    the same output before and after the last one.
    - 41 claims the old reader gave no range now get the exact stated time.
    - 1 claim the old reader widened to the whole day now gets its stated time.
    - 15 claims the old reader widened to the whole day now go to the model.
    - 35 plain-date claims are unchanged.
    - No run 1 result used a widened range, because run 1 tested no claim.
- Open: unmeasured. Whether these claims now get tested needs a new run under a new signed plan
    (PREREGISTERED_v2, low-coverage rule 4).
  - The fixes were designed after reading run 1's refusals on the same affidavit. A run 3 on
    those 106 claims would therefore not be a held-out test of them. A held-out affidavit, or
    another public phone, measures them cleanly.
  - Not covered here:
    - "between approximately X and Y";
    - times about midnight;
    - 24-hour times;
    - zones other than US and UTC, which are refused, not read.
  - Account lookups (#152) and call lengths (#153) are the next PRs. The planned retry on
    invalid output is dropped: run 1's 2 invalid outputs were the same bytes on all 3 runs.
  - When "texted" or "iMessage" names Native Messages, the report does not yet say that the
    export holds SMS and iMessage together. That is a report and screen change, planned as its
    own PR.
- Affects: capabilities. More claims can be set up from real affidavit wording. A claim whose
  written zone the phone was not in is now refused, where before it was read in the phone's
  zone.
- Status doc: pending: two edits.
  - Section 7, "Real-export validation", run 1 bullet: after "run 1's 43 model-side refusals
    are not fixed" add "; the date-first time wording, written time zones and export app names
    behind many of them are read by code since #150 (unmeasured until a run under a new signed
    plan)".
  - Section 9 item 8 ("Other gaps"): add "a time zone written beside a claim's time must match
    the phone's zone at that time, or the claim's range is refused; 'between approximately X
    and Y', 24-hour times and zones other than US and UTC are left to the model (#150)".
