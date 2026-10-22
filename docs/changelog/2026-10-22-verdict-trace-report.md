## 2026-10-22: Report traces each verdict and says what can be checked again
- Changed: report 0.14.0 (`core/report/html.py`; #111 took 0.12.0 and #127 0.13.0). Each
  decided claim gets "How this verdict was reached": per core assumption, each evidence item,
  check or stipulation the verdict rules relied on, or, for an assumption not covered, what was
  found for it and not relied on; who proposed each (the named model and whether it ran local or
  in the cloud, the code for a check, the expert for a stipulation) and the expert's step
  ("Expert confirmed", "Local AI reviewer accepted; not confirmed by an expert", "Not
  reviewed"). An expert override says the expert set the verdict. A new "What can be checked
  again" section says every verdict re-derives from the recorded labels, checks and expert
  decisions under the recorded rules (checkable offline with `export-bundle` and
  `verify-bundle`), names each model run, and for a hosted model says its labels cannot be
  regenerated exactly (`HOSTED`, the wording the bundle already used, now defined in the report
  module). For a local model it says anyone with the same file can run it again and makes no
  claim that a re-run gives identical labels. Why: the court-defensibility plan (PR B) asks the
  report to show the other side, per claim, what a verdict rests on and which parts a model only
  proposed.
- Where: branch claude/project-thread-677up6
- Verified: new tests in `tests/test_report_consistency.py` (C05 traces model proposed and
  expert confirmed; claims waiting on the expert show found-not-relied-on items and never
  "Expert confirmed"; an override says so; a hosted model run prints the hosted disclosure and a
  local one makes no reproducibility claim); `make check` (numbers in the PR).
- Open: review status in the trace is as it is now, like the evidence table, not as of the
  verdict; an item decided after the verdict says so. The trace shows the identity links and
  stipulations as they stand now, not the snapshot the checks used (follow-up from #104).
  Whether the local 14B gives identical labels on a re-run is unmeasured until the repeat check
  (#126, merged) finishes its first Mac run.
- Affects: customer-facing claims (the report now states what can and cannot be regenerated)
- Status doc: pending: in section 2 (Pipeline), row "14. Report", after "model runs and rule
  version." add "Each decided claim traces its verdict per core assumption: what the rules relied
  on, who proposed it (model, code or expert) and the expert's step; a 'What can be checked
  again' section says verdicts re-derive from recorded labels and decisions, and that a hosted
  model's labels cannot be regenerated exactly (report 0.14.0)."
