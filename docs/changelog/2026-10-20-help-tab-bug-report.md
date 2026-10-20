## 2026-10-20: Help tab, support contact and a bug report with no case data (#92)
- Changed: a Help tab on the review screen with the support contact, a short "what Baker does
  and doesn't do", and a bug-report export (`/help/bug-report.json` and `baker bug-report`),
  shown in full before it is saved. It holds versions, system and model setup, the last job,
  recent error types with Baker file and line (never messages), and the open case's counts and
  states; it leaves out case and file names, paths, any case text and every hash. Built from an
  allowlist and re-checked before display (`core/support/`). The screen server answers an
  unexpected error with a plain 500 that points to Help, and keeps the error's type and frames in
  memory only. New docs: `docs/WHAT_BAKER_DOES.md` (one-page explainer, no speed or accuracy
  claims) and `docs/SUPPORT.md`. Why: pilot gate 17 in `docs/PILOT_GATES.md`.
- Where: PR #92
- Verified: `tests/test_bug_report.py` on a synthetic case01 with marked values in case name,
  expert name, file names, a claim, a job message and an error message: none appears in the
  report, the Help page or the CLI output, nor any input SHA-256 prefix or 32+ hex run.
  Headless-Chromium check of the Help tab and download.
- Open: the support address is a placeholder (`support@baker.example`) until Arsh sets it, so
  gate 17 stays not met until then. Row counts and source kinds are case metadata and are
  included; the docs say how to leave them out.
- Affects: capabilities (Help tab, bug report); privacy (a new export that holds no case data;
  Baker still sends nothing); customer-facing claims (the explainer; no new speed or accuracy
  claim).
- Status doc: pending: in the capabilities list add "Pilot support: a Help tab on every screen
  page with the support contact, a short what-Baker-does, and a bug report shown in full before
  it is saved (`/help/bug-report.json`, `baker bug-report`), built from an allowlist with no case
  names, paths, text or hashes (`core/support/`). Recent unexpected errors are kept in memory
  only, without messages; no log file. The support address `support@baker.example` is a
  placeholder (`core/support/contact.py`)." In the open items, add "Set the real support address
  (pilot gate 17)." In docs/PILOT_GATES.md gate 17 evidence, note the one-pager
  (`docs/WHAT_BAKER_DOES.md`) and bug report are on main and only the named contact is missing.
