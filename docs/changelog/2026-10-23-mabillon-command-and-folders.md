## 2026-10-23: The `mabillon` command and folders, with the Baker names still read (#PR)
- Changed: step 2 of the rename to Mabillon (/mnt/project-files/baker/plans/rename-mabillon.md).
  The command is `mabillon`; `baker` still runs it for a release and prints a one-line note.
  Windows installs get `mabillon.cmd` beside `baker.cmd`. New defaults: cases in
  ~/Mabillon/cases, the demo in ~/Mabillon/demo, settings in ~/.mabillon/ (model.json,
  cloud.json, speed.json, model-check.json), variables MABILLON_* (CASES, DEMO, MODEL_CONFIG,
  CLOUD_CONFIG, ANTHROPIC_API_KEY). A computer set up as Baker keeps working with nothing moved
  (core/paths.py): a MABILLON_* variable wins over the same BAKER_* one, and ~/Baker/<folder> or
  ~/.baker/<file> is used while the new one does not exist. Messages, the bundle's METHOD.md
  (bundle format 1.2.0) and the docs name `mabillon` commands. The pip package name stays
  `baker` until the installers change (step 3), so a reinstall does not leave two packages.
- Where: branch claude/project-thread-2bmti8
- Verified: `make check`; tests/test_paths.py (variable precedence, old folders and files kept,
  new ones winning once they exist, the command's name, the alias and its note).
- Open: step 3 (installers: ~/Mabillon/app and models, launchers "Mabillon" and "Mabillon
  demo", the Start-menu shortcut, the pip package name). Until then a new Mac install keeps the
  app and model under ~/Baker and its config in ~/.baker, and puts new cases under ~/Mabillon.
- Affects: capabilities (command name, default folders; old ones still read). No privacy or
  network change: the cloud key is read from the same places plus the new variable name.
- Status doc: pending: wherever the command is named, `mabillon` (with `baker` as an alias for a
  release); default cases folder ~/Mabillon/cases and settings in ~/.mabillon, with ~/Baker and
  ~/.baker read when only they exist; MABILLON_* variables, BAKER_* still read; bundle format
  1.2.0.
