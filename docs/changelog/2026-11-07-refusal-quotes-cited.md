## 2026-11-07: A not-tested claim that says "deleted" no longer stops the report
- Changed: On the 14B baseline run of synthetic case01 on the Mac (2026-11-06), the audit
  finished and then the report refused to write. A claim the filler could not set up
  ("PETROV deleted the WhatsApp messages he exchanged with REYES ...") got the refusal
  "'PETROV deleted ...' is not inside quotation marks in the claim". The filler prints the words
  it was given in single quotes, the cited mark only covered double quotes, and the report printed
  the not-tested line without the names helper at all. So the forbidden-word check read the
  claim's own sentence as the tool's words and stopped the whole report, after the run's model
  work was done.
  `core/report/names.Names` now also cites words in single quotes when they stand, as whole
  words, in the claim the line belongs to. A single quote counts only where no letter or digit
  touches it on the outside, so an apostrophe never opens or closes one. Double and single quotes
  are matched separately and only cited spans are kept, since a rule's reason nests one in the
  other ('The words "..." mean ...'). The words are compared with the claim as printed first (a template
  prints a quote raw, so a path such as C:\temp stays as it is), then with Python's escapes read
  back (a refusal prints a line break as \n and a quote mark as \'). The report's not-tested line goes through `Names.cite`,
  and the claim page's "Why code could not set it up" through `Names.for_claim(...).html`.
  Quoted words no claim holds stay the tool's own and are still checked. Report 0.39.0 (#228 took 0.38.0).
- Where: branch claude/project-thread-ds0ify
- Verified: new test in `tests/test_cited_quotes_page.py` builds synthetic case01 with one claim
  refused the same way (one line, a line break, both quote marks), renders the report, runs the
  forbidden-word check and opens the claim page; it fails without the fix, and the line-break
  and quote-mark cases fail without the read-back. A unit test in `tests/test_report_names.py`
  keeps a quoted Windows path cited (both found by Greptile on the PR). The Mac run's own case01 database (synthetic) fails the check
  without the fix and passes with it, and all 20 of its claim pages open. make check (see the PR).
- Open: The Mac run stopped before its expert pass, so case01's 14B baseline still has to run
  again on the fixed code. Its audit took about 2 h 36 min on the MacBook Air M4 (2026-11-06,
  from the case files' times; not a timed measurement).
- Affects: customer-facing behavior (a report that could not be written now is)
- Status doc: no change
