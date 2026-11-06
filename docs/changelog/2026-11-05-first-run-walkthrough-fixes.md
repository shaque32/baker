## 2026-11-05: fixes from the first-run walkthrough of the real app (PR pending)
- Changed: five synthetic-data walkthroughs of the real app (empty start, imports, setup, run,
  encryption, errors; 2026-11-04) found 10 bugs and 10 confusing spots. This change fixes them,
  one commit per group.
  - A. Every form names its case (`for_case`): a post from a tab drawn for another case is
    refused and nothing is saved. A form from before a restart gets a plain page with a link
    back, not a bare refusal.
  - B. Re-run verdicts (`core/review/redecide.py`) keeps an expert's confirmation or override on
    a claim whose verdict and basis come out the same. It logs `verdict.carry` for each. A
    changed verdict drops the old decision, and the message lists the claims that need
    confirming again. `core/bundle/verify.py` and `core/review/flags.py` read `verdict.carry`.
    Rules are unchanged (no `core/audit/rules.py` edit).
  - C. Recovery key:
    - Lock waits until the shown key is written down.
    - A key never confirmed is flagged (`recovery_unconfirmed`).
    - "Make a new recovery key" on Set up and `mabillon recovery-key` replace it and log
      `case.recovery_key`.
    - Unfinished encryption shows as such in the case list, not as "Encrypted, locked".
    - The cloud key line says where the key comes from (environment, this case, or this
      computer), and the key can be removed there.
  - D. Imports:
    - A file in the phone slot that holds no report tables is refused.
    - Each file gets its own source id (item1.xlsx and item1.ufdr no longer collide).
    - A wrong file can be removed only before the first audit. The removal is logged as
      `case.remove_file` with the file's name, SHA-256 and the expert's reason. It is refused
      while a confirmed stipulation or link, document names, an accepted claim, an event or an
      exhibit still points at the file. Withdrawn stipulations, links not confirmed and
      proposed claims go with it; the entry lists their ids and `verify-bundle` replays them.
  - E. No model:
    - Every model-check failure says what to do on this computer: run the Mac installer again,
      or Mabillon Setup with Download the AI model ticked.
    - Starting the audit says "Checking the model first", not "started".
    - Set up shows the model's state in words and lists it under Run. The local model now
      comes before Cloud in step 4.
    - A finished propose or model check reports once and replaces "This page updates itself".
  - G. Small bugs:
    - `audit_log.append` takes the write lock before it reads the last entry. Two connections
      could take the same seq ("UNIQUE constraint failed: audit_log.seq").
    - The redacted flag summary downloads before the first audit (it returned a 500). An
      unexpected error is now a page with Help and Back links plus one Terminal line.
    - Add a claim refuses a used id plainly and keeps the typed text. Its picker shows each
      paragraph in full, and Set up marks claims added by the expert.
    - A change of examiner name is logged (`reviewer.rename`). The name is remembered on this
      computer (`~/.mabillon/reviewer.json`).
    - Claims sort by number. Toasts name claims as on screen (¶6.2).
    - Outgoing messages in context show the recipient on screen. The stance prompt text is
      unchanged, which a test checks.
    - The Run page shows one message on a failed start, never "No audit has run" under a
      running audit, and no link to itself.
    - `verify-bundle` reads the screen's `case.import` and `case.remove_file` entries, so it
      no longer says a matched government document's import is missing.
    - `export-bundle --by` takes a plain name and warns when verdicts are out of date.
  - F. Orientation and handoff:
    - An audited case opens on its Case page.
    - The Cases list gives each case's stage, what waits and the next step, and the sidebar
      has All cases.
    - Claims says when proposed claims wait. Set up offers "Accept all N proposed claims",
      which accepts only the claims that page listed, each one logged.
    - Changes made before any audit say they apply when it runs. A finished case's button reads
      "Run the full audit again", and a resume says how many claims it reuses.
    - The claim page and report print "Verdict confirmed by <name>, <time> UTC", separate from
      "expert-confirmed" evidence.
    - A report made on the screen opens with the case, examiner and time, and has Save and
      Back links. Its file is named after the case. Report 0.35.0; a bundle's report has no
      header, so bundles re-render unchanged.
    - Evidence cards show the file, sheet and spreadsheet row unfolded.
    - Files explains why Records differs from rows imported.
    - Set up notes two phones listing the same own number, and a document whose numbers match
      none of the phones. Nothing is merged.
- Where: branch claude/project-thread-ngqisv (draft PR).
- Verified: the full test suite passes. New tests cover each group: tests/test_stale_tab.py,
  test_redecide_carry.py, test_recovery_key.py, test_import_dead_ends.py,
  test_audit_log_lock.py (it fails without the fix), test_small_fixes.py, and new tests in
  test_start_case.py. The PR states the `make eval` numbers; no eval metric was tuned.
- Open: the report's "#" column is not stored, so cards show the spreadsheet row and say it is
  not the "#". The document-versus-phone check compares numbers only, not makes and models.
  The remembered examiner name is per computer, not per case. Look and wording on Set up's
  files table and the selection page belong to the de-slop thread's PR (#222); a rebase may be
  needed after it merges.
- Affects: capabilities (remove a file before the first audit, new recovery key, carried
  verdict decisions, accept all proposed claims); customer-facing claims none.
- Status doc: pending: in section 8 (Implemented features) add "Re-run verdicts keeps an
  expert's confirmation or override when the verdict is unchanged (logged as verdict.carry)",
  "A wrong file can be removed before the first audit, logged with its SHA-256 and reason",
  "Make a new recovery key (screen and mabillon recovery-key)" and "Forms are bound to their
  case"; in the header set the report version to 0.35.0; in section 9 (Known limitations) add
  "The report's # column is not stored; cards cite the spreadsheet row".
