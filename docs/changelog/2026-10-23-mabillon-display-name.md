## 2026-10-23: The app, report and docs say Mabillon (#127)
- Changed: Arsh renamed the product from Baker (a working name) to Mabillon on 2026-10-21. Every
  sentence the review screen, the report, CLI help and error messages, the bundle's notice and
  the docs use to name the tool now says Mabillon (step 1 of
  /mnt/project-files/baker/plans/rename-mabillon.md). Report version 0.13.0: title "Mabillon
  claims report", and the top line and Versions say "Mabillon build" and "Mabillon pipeline".
  Bundle format 1.1.0: METHOD.md and the notice say Mabillon. `verify-bundle` now says when a
  bundle was exported with another report version (check 12) or bundle version (METHOD.md) and
  names the commit to verify it with, instead of a bare mismatch that reads like tampering (any
  change to that text, this rename included, changes the bytes). The request draft's template
  is version 1.1.0. Evidence labelled before the rename keeps its stored forwarded note naming
  Baker: verify-bundle accepts it (check 8), and the screen and report show it naming Mabillon.
  Not changed here: the `baker` command, ~/Baker and
  ~/.baker paths, BAKER_* variables, Desktop launchers and installer names (steps 2 and 3);
  file-format ids and the `baker_version` field, which never change (CLAUDE.md).
- Where: PR #127
- Verified: `make check` (lint, tests, eval); new tests that a bundle from another report or
  bundle version fails naming the commit. Eval numbers unchanged (wording only).
- Open: steps 2 (`mabillon` command, `baker` alias, new paths with fallback) and 3 (installers).
  A bundle exported before this change verifies only at its own commit.
- Affects: customer-facing claims (product name only; no capability or claim changes)
- Status doc: pending: title and section 1 say Mabillon (formerly Baker) and every other
  "Baker" naming the product says Mabillon, keeping `baker` commands and ~/Baker paths as they
  are; report version 0.13.0 where the report version is named; bundle format 1.1.0; section 8
  notes `verify-bundle` names the commit for a bundle from another report or bundle version.
