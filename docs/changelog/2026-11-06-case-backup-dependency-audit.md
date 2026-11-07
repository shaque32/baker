## 2026-11-06: case backups, a dependency vulnerability scan, hidden input names (#230)
- Changed: fixes three gaps from the pre-launch security checklist (2026-11-03).
  - Backups: "Back up this case" on Set up and run, and `mabillon backup --db <case>/case.db
    --by expert:<name> [--to <folder>]` (`core/casework/backup.py`). A new folder, by default
    `~/Mabillon/backups/<case folder>-backup-<UTC time>`, gets the anchor file first, then a
    SQLite backup-API snapshot of the database under the case's own key, then every other file,
    each hashed against its original. The copy is opened and its audit log checked against its
    own anchors before it is kept; one that fails is deleted. Refused for a locked case, a case
    whose log does not verify, a target inside the case folder, a `--db` database outside a case
    folder, and on the screen while background work runs. Logged in the case as `case.backup`.
    Restoring is copying the backup folder whole into the cases folder.
  - Dependencies: `.github/workflows/dependency-audit.yml` runs pip-audit on what a fresh
    `pip install ".[cloud]"` resolves, on dependency changes, pushes to main and weekly.
    `.github/dependabot.yml` opens one grouped pip and one grouped Actions update PR a month.
  - Input names: in an encrypted case, a file imported from the screen is renamed
    `input-<24 hex>` in `inputs/` once its import is stored; the real name stays in the encrypted
    database and the import's audit-log entry records the new name (`copied_to`). Removing a file
    and bundle export already find copies by that entry or by hash.
  - Claim order: each move that changes the order is logged as `claim.move` (claim id, old and
    new place) before `case.json` is saved. A move past the top or bottom changes nothing and
    logs nothing.
- Where: PR #230
- Verified: `make check` on Linux (see the PR). New `tests/test_backup.py` restores plain and
  encrypted backups (rows, files, audit chain and anchors match; the same passphrase opens it),
  and checks the refusals and that a backup failing verification is deleted. After Greptile's
  review: a backup never deletes a folder another backup made in the same second; the check
  also requires every file copy the snapshot names (by plain hash); removing a file finds an
  encrypted copy by hash when its log entry names a path that is not there. Updated tests in
  `tests/test_encryption.py`, `tests/test_axiom.py`, `tests/test_ufdr.py` (hidden names) and
  `tests/test_start_case.py` (claim moves logged). pip-audit on 2026-11-06 (Linux, Python 3.12):
  no known vulnerabilities in the 29 packages resolved.
- Open: a case encrypted after files were imported keeps those files' names (the rename runs at
  import only). Backups land on the same disk by default; the expert must copy them off. The
  installers still resolve Python packages by version range with no lock file or hashes, and
  pip-audit does not cover llama-cpp-python (built from source, version pinned). Not run on a
  Mac or Windows by hand; Windows CI runs the tests.
- Affects: capabilities (backup), privacy (input names hidden in encrypted cases, more actions
  logged), customer-facing claims (docs/SECURITY_PRIVACY.md and docs/PILOT_ONBOARDING.md
  updated to match).
- Status doc: pending: section 2 (Pipeline), Import row: add "In an encrypted case each copy is
  renamed input-<random> once its import is stored; the real name is in the encrypted database
  (#230)". Section 8 (Implemented features): add "Case backup: `mabillon backup` and 'Back up this
  case' make a verified copy of a case folder (`core/casework/backup.py`, #230), logged as
  case.backup" and "Claim moves are logged as claim.move (#230)". Section 9 (Known limitations):
  drop "input file names not encrypted" and "claim order not logged" where listed; add "a case
  encrypted after import keeps those files' names". Section 10 (Tests and results): add "CI also
  runs pip-audit (dependency-audit workflow) and Dependabot opens monthly update PRs (#230)".
