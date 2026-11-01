## 2026-11-01: Cases, Help, Audit log and Activity pages decluttered (#PR)
- Changed: after an Impeccable audit of each page (findings and before/after screenshots in
  /mnt/project-files/baker/declutter/), these pages show less at once. Cases: ledger-style case
  rows (name, slug, one muted state line, Open at the right), the cases-folder line under the
  list, one card for a new case with "Make the case" as the only primary button; the passphrase
  fields show only while "Encrypt" is ticked (CSS only). Name form: one card. Error page: the
  message first, one button back. Help: the bug report's full JSON folds under "Exactly what
  the file holds" (every byte kept); the page is about a quarter as tall. Audit log: the chain
  status as one line ("Hash chain FAILED VERIFICATION" now reads "failed verification", in bold,
  under the no-uppercase rule), filters as two-part toggles, the flags tool as one panel, no
  wrapping in the number, time and action columns, monospace only for payloads and hashes.
  Activity: narrower intro, the CSV link as a quiet button beside the summary, the
  activity-in-report switch on one row, tidy numeric columns. No form action, field, entry or
  caveat removed.
- Where: PR #PR
- Verified: per-page pytest selections (cases/help 379, log/activity 229 passed), ruff, a
  replay of packaging/smoke_ui.py's cases-screen steps in Node Playwright, and `make check` on
  the combined branch (numbers in the PR). Impeccable detect, before to after: /help 3 to 1,
  /activity 2 to 1; the finding left on each page is the warm paper palette Arsh chose.
- Open: the sidebar still says "Enter your name on the case page" though the form is on the
  cases page (ui/pages.py Page.wrap, not changed here); Windows not looked at.
- Affects: none (look of the local screen only)
- Status doc: no change
