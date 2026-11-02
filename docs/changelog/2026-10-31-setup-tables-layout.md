## 2026-10-31: Set up and run: a calmer page, whole words in tables, Put back for removed claims
- Changed: Arsh asked for Set up and run to be cleaner and easier to use; reworked with the
  Impeccable distill pass. Screen only; no route, form field name, stored value, verdict path or
  privacy behavior changed, and no privacy sentence was reworded (some are now folded).
  - Tables (Files, Claims, Devices) no longer break words mid-word: the app-wide
    `td { overflow-wrap: anywhere }` let columns shrink to one letter; these tables now carry a
    `tidy` class that wraps only between words.
  - A step strip under the title (Files, Claims, Who used each phone, The model, Run) links to
    each step and marks the first three Done or To do from the existing readiness checks.
  - Files: four columns (File, What it is, Records, Imported); coverage sits under the file's
    kind. The full SHA-256 of every file and the inputs folder are in a "Hashes and where the
    copies are kept" fold (the table showed 16 characters). Upload forms sit side by side under
    "Add a file", open when the case has no files yet.
  - Claims: Propose and Add a claim yourself are one row of buttons. The table merges Where and
    Type under the claim name. Row controls are quiet (move up and move down arrows, Remove set
    apart), with Edit the wording below. Removed claims are listed with a Put back button that
    accepts the claim again through the same logged claim-status action.
  - Devices: the model line is left out when it repeats the device name; "by expert:<name>"
    reads "Stipulated by <name>"; with a stipulation in place only Withdraw shows, with "Name
    someone else" folded under it.
  - Model: the cloud explanation (unchanged words) is folded under "What cloud AI sends, and
    what it never sends"; the key form is folded until the case opts in to cloud AI.
  - Run: readiness shows as a checklist; the three extra options fold under "More options";
    Start the audit stays the one primary button. Encryption: the status line shows, the
    explanation and passphrase form fold under "Encrypt this case".
- Where: PR #193
- Verified: scripted demo case in headless Chromium at 1512, 1440, 1280 and 1100 px, folds
  closed and open; Impeccable detector found nothing on ui/pages.py and ui/theme.py; tests in
  tests/test_start_case.py check the claims table's action row and the Put back buttons; make
  check results are in the PR. Not checked in the Mac app window or on Windows.
- Open: the shared button, checkbox and field styles come from the "Declutter every app page"
  work; this page's rules move to ui/css/setup.py once that lands.
- Affects: none (screen layout only)
- Status doc: no change
