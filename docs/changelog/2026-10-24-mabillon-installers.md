## 2026-10-24: The Mac and Windows installers say Mabillon (#132)
- Changed: step 3, the last step of the rename to Mabillon
  (/mnt/project-files/baker/plans/rename-mabillon.md).
  - Mac: `packaging/mac/Install Mabillon.command` (was `Install Baker.command`). It installs into
    ~/Mabillon/app and ~/Mabillon/models, writes ~/.mabillon/model.json and puts **Mabillon**
    and **Mabillon demo** on the Desktop. The test-only variables are now MABILLON_PINS and
    MABILLON_MIN_MEMORY_GB; the BAKER_* names are still read.
  - Windows: Setup is `Mabillon-Setup-<version>.exe`. It installs into
    %LOCALAPPDATA%\Programs\Mabillon with the model in %LOCALAPPDATA%\Mabillon\models and the
    setting in %USERPROFILE%\.mabillon\model.json. The Start menu gets **Mabillon command
    prompt** (running `mabillon`), PATH gets the `mabillon` command, and Settings > Apps shows
    Mabillon. The CI artifact is `mabillon-installer`.
  - A computer installed under the name Baker is updated, not duplicated, and keeps what it
    has.
    - Mac: a verified model in ~/Baker/models and a setting in ~/.baker/model.json are used
      where they are; while that setting is kept, a model still to download goes to
      ~/Baker/models too. The Desktop launchers the Baker installer made are replaced (only those:
      a file of the person's own with the same name stays). The installer says when ~/Baker/app
      can be deleted.
    - Windows: Setup keeps the AppId, so it updates the install in place in Programs\Baker. It
      uses a model in %LOCALAPPDATA%\Baker\models where it is (a replacement for one that fails
      its check goes to the same folder), leaves a ~/.baker/model.json of
      the person's own, and moves the shortcuts out of the old "Baker" Start-menu group.
  - The docs name the new folders, launchers, shortcut and file names. Code comments that #117
    added after #127 now say Mabillon too.
  - Kept: the pip package and the installed source folder keep the name `baker`, like the
    file-format ids (CLAUDE.md). So a reinstall never leaves two packages, and `pip install -e .`
    on a development checkout needs no uninstall. The Azure signing resource names are kept as
    well.
- Where: PR #132
- Verified: `make check` (lint, tests, eval; numbers in the PR).
  - `tests/test_packaging.py`: the AppId is unchanged, Setup keeps a Baker-era model and the
    person's own setting, the old shortcut is removed, and the Mac installer never writes over a
    Baker-era setting.
  - The clean-install workflow runs a third install, over a Mac laid out as the Baker installer
    left it. It checks that the model and setting are kept where they are, that model-check
    reads ~/.baker/model.json, that the Baker launcher is replaced and that a same-named file
    of the person's own is left alone. A fourth run, after a Baker install made with `--no-model`,
    checks that the model downloads to ~/Baker/models, where that kept setting points.
  - The Windows smoke test installs on a fresh runner and runs `mabillon.cmd`, `baker.cmd` and
    the Start-menu shortcut check.
- Open: three items.
  - The Windows update over a real Baker-era install is unverified. CI has no 9 GB model and no
    earlier install to update. The code paths are short: the model folder choice, the setting
    check and three InstallDelete lines.
  - The Windows publisher in the signature stays "Shayan Haque" until an organization
    validation.
  - The repository is still named baker.
- Affects: customer-facing names (installer, launchers, Start menu, Settings > Apps, default
  folders). No change to capabilities, verdicts, privacy or network use: the installers download
  the same pinned files from the same places.
- Status doc: pending: wherever installation is described, the Mac installer is "Install
  Mabillon.command", installing to ~/Mabillon/app and ~/Mabillon/models with Desktop launchers
  "Mabillon" and "Mabillon demo"; the Windows installer is Mabillon-Setup-<version>.exe,
  installing to %LOCALAPPDATA%\Programs\Mabillon with the "Mabillon command prompt" Start-menu
  shortcut; an install made under the name Baker is updated in place and keeps its model and
  model setting.
