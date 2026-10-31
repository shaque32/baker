## 2026-10-30: Case page leads with what waits on the expert; flags tool moves to the Audit log page (#177)
- Changed: The case page (`ui/pages.py` `overview()`) was a run log, a stipulation form, a flags
  tool and the status all at one weight. It now opens on one action ("N claims need you") with the
  verdict counts grouped as the Claims screen groups them, each linking to its section. The format
  notices and the demo or stand-in banner fold to their first sentence; every word stays one click
  away. The always-on "Re-run verdicts" box is gone: the out-of-date banner already offers the
  re-run when a decision made the verdicts stale, and now returns to `/#audit`. Because it is
  now the only re-run, the banner also counts a testability decision the verdicts have not seen
  (a confirmed failed check, or a rejection that undoes one), as the claim page already did
  (Codex on #177). The case name heads the page as cited text, so a name with a word Mabillon
  never says itself still renders (Codex on #177). Devices and
  stipulations show read-only under "Case setup", with a link to Set up and run, which keeps the
  only form. Run id, versions, audit log, flags count and custody hashes sit in a quiet "Record"
  list. A hash chain that fails verification now shows as an error at the top of the case page.
  The flags tool (pilot name and "Download the redacted summary") moved to the Audit log page.
- Where: PR #177
- Verified: make check (see the PR description for the run); tests changed only where content
  moved: tests/test_flags.py (summary download now on /log), tests/test_demo.py (case status
  counts follow the Claims screen grouping instead of one pill per label). Two new tests in
  tests/test_agent_fail_confirm.py cover the Codex fixes. Screenshots at 1440
  and 390 px of the synthetic demo case01.
- Open: the old per-label pills ("Support found: do you agree?", "Unproven, not tested") no longer
  appear on the case page; they stay on the Claims screen and claim pages. Not checked with a
  screen reader.
- Affects: capabilities (where the flags summary download lives; stipulations are edited only on
  Set up and run)
- Status doc: pending: wherever docs/PRODUCT_STATUS.md says the case page offers the redacted
  flags summary download or edits stipulations, say the download is on the Audit log page and
  stipulations are edited on Set up and run; the case page shows both read-only.
