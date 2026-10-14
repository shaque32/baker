# Timeline check and Gaps

Two views for the expert, derived by code from the case database each time they are shown.
Nothing is stored, no model is involved, and neither view sets or changes a verdict. Both appear
on the review screen (Timeline and Gaps tabs) and in the report.

## Timeline check (`core/timeline/stated.py`, `core/timeline/check.py`)

1. **Read every stated time.** Each government-document paragraph is searched for dates, ranges,
   open ranges ("before", "since") and a time of day tied to a date. What code cannot read
   plainly is listed under "Not compared" with the reason:
   - a numeric date that reads either way (3/5/2026 could be March 5 or May 3). Baker never picks
     a month/day order; 3/25/2026 and 25/3/2026 read as March 25 because only one order exists;
   - a date with no year, when the paragraph and the document do not state exactly one year;
   - a two-digit year, an impossible date, or a time of day with no date beside it.
   "about 7:58 p.m." is read as 8 minutes either side, as the signed case01 sheet reads it.
   A weekday the document gives ("Monday, March 9") is checked against the calendar.
2. **Tie records to the statement, only through the sentence's own words.** Quoted words (two or
   more, not a contact, account, thread or person name) are found verbatim and word-aligned in
   message bodies; a phone number in a sentence about a call is matched to calls with that number.
   Each goes with the nearest stated time in the same sentence.
3. **Compare.** A stated time without a zone is read in the record's phone's own zone
   (`devices.timezone`), never in the offset a report printed. Inside the stated time, or within
   the case's tolerance (default 5 minutes), is a match; otherwise the difference is shown. When
   the report printed a different offset, the row also says whether the stated time agrees with
   the printed clock, which is how a display setting turns into a wrong time in an affidavit.
   When the sentence orders events ("after that call PETROV sent ..."), the order is tested
   instead of closeness. A statement with nothing to tie shows the records around it (a time of
   day) or what the phones hold on those days, and never says a record is the one meant.

## Quiet stretches (`core/timeline/gaps.py`)

For each phone, each app on it (the call log counts as one) and each thread: consecutive records
at least the shortest-stretch setting apart (default 72 h), where the series' own pace (records
between its first and last, over that time) would put at least 8 records in the gap. A stretch
its whole app already shows is listed once, at the app. Each stretch states what was searched
and the source's coverage (a curated report holds only what the examiner chose), records with no
usable time, what other phones hold in the same span, and the times the document states inside
it. Baker states a quiet stretch; it never explains one. Not found does not mean it did not
happen. The Selection tab names a listed stretch that falls in the pause just before or just
after an exchange holding a message the government picked
([selection-audit.md](selection-audit.md)).

## Settings

`timeline_tolerance_min` and `gap_min_hours` live in the case's settings file beside `case.db`.
A change is made on either page, and the audit log records it as `timeline.settings` with the
expert's name and the old and new values. The report prints the tolerance it used.

On synthetic case01: paragraph 8 differs by 5 hours (the report printed UTC+0 for a New York
phone), paragraph 9 puts "move it tonight" 14 minutes before the call the document says it
followed, and both phones show the WhatsApp silence from the evening of March 19 to March 24,
which paragraph 11 states a range inside.
