# Support and bug reports

## Contact

**support@getmabillon.com**, run by Mabillon, the company behind Baker. The Help tab and the bug
report show it from `SUPPORT_EMAIL` in `core/support/contact.py`. If the address changes, update
it there, in this file and in `docs/ONE_PAGER.md` in the same change, since these are static text.

When you write, say what you did, what you saw and what you expected. **Never send case
content**: no case files, case database, screenshots of evidence, or claim or message text.

## The bug report

A small JSON file that describes your Baker install, and the case open at the time in counts and
states only. Baker never sends it: you save it, read it, and attach it to an email yourself.

- **In the app:** the **Help** tab (any page, with or without a case open) shows the whole report,
  then **Save the bug report** downloads the same text.
- **On the command line:** `baker bug-report --out report.json`, or add `--db <case>/case.db` to
  include that case's counts and states.

**What it holds:** Baker's package, commit, pipeline, contracts, rules, quote-check and report
versions and the shipped prompt versions; the operating system, Python and memory; whether the
model is set up, its file size and the last model check's result (not its lines); whether a cloud
key is set up (yes or no) and how many cloud models passed the stance test; which `BAKER_*`
settings are set (names, not values); the last background job's kind, state and progress; recent
unexpected errors in this session as the error's type and the file and line in Baker's own code;
and for the open case: encryption state, whether the audit log verifies, row counts per table,
each source's kind, fidelity, importer and importer version, claims per status, the latest run's
verdict counts, recent runs' status and versions, model runs per purpose and whether each used
the shipped prompt, model-call outcomes, and the timeline settings.

**What it leaves out:** the case name, your name, file names and folder paths; any claim,
record, document or quote text; every error message (a message can quote any of those); hashes
of inputs, records, the model file and the audit log; API keys.

**How that is enforced** (`core/support/bug_report.py`): the report is built from an allowlist of
fields, never by copying and cleaning case data. Errors are kept in memory only
(`core/support/errors.py`), as type names and Baker file and line, never the message; Baker writes
no log file. Before the report is shown or saved, it is checked again: if it holds a run of 32 or
more hex characters (a hash or a key) or any of the open case's name, folder, file names or input
hashes, it is withheld, not cleaned, and the Help tab says so. `tests/test_bug_report.py` builds a
synthetic case with marked values in every one of those places and checks that none comes out.

Row counts and source kinds are case metadata, not content. If even that may not leave your
office, use the report made with no case open, or delete the `open_case` section before sending.
