## 2026-10-21: Help tab, support contact and a bug report with no case data (#92)
- Changed: a Help tab on the review screen with the support contact, a short "what Baker does
  and doesn't do", and a bug-report export (`/help/bug-report.json` and `baker bug-report`),
  shown in full before it is saved. It holds versions, system and model setup, the last job,
  recent error types with Baker file and line (never messages), and the open case's counts and
  states; it leaves out case and file names, paths, any case text and every hash. Built from an
  allowlist and re-checked before display (`core/support/`). The screen server answers an
  unexpected error with a plain 500 that points to Help, and keeps the error's type and frames in
  memory only. New docs: `docs/ONE_PAGER.md` (one-page explainer, no speed or accuracy
  claims) and `docs/SUPPORT.md`. Why: pilot gate 17 in `docs/PILOT_GATES.md`.
- Where: main (#92, merged 2026-10-21)
- Verified: `tests/test_bug_report.py` on a synthetic case01 with marked values in case name,
  expert name, file names, a claim, a job message and an error message: none appears in the
  report, the Help page or the CLI output, nor any input SHA-256 prefix or 32+ hex run.
  Headless-Chromium check of the Help tab and download.
- Support address: support@getmabillon.com (set by Arsh 2026-10-21; Mabillon is the company,
  Baker the product). It forwards to the team's inbox, so replies come from a different address.
- Open: row counts and source kinds are case metadata and are
  included; the docs say how to leave them out.
- Affects: capabilities (Help tab, bug report); privacy (a new export that holds no case data;
  Baker still sends nothing); customer-facing claims (the explainer; no new speed or accuracy
  claim).
- Status doc: applied 2026-10-27
