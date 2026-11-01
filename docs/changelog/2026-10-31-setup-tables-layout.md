## 2026-10-31: Set up and run's tables keep words whole and controls on one row
- Changed: on Set up and run, the Files, Claims and Devices tables broke words mid-word
  ("identi ty", "acce pted", "paragrap hs") and made rows tall, because the app-wide
  `td { overflow-wrap: anywhere }` let the browser shrink columns to one letter. These tables now
  carry a `tidy` class that wraps only between words. Claims: Accept, Up, Down and Remove sit on
  one row (Remove set apart by a gap, keeping the 10-30 critique's separation from the reorder
  buttons) with "Edit the wording" under them. Devices: the model line is left out when it
  repeats the device name, "by expert:<name>" now reads "Stipulated by <name>", and with a
  stipulation in place only Withdraw shows, with "Name someone else" folded under it. Files: the
  hash stays on one line and the import time drops
  its microseconds (full value on hover). Layout only (ui/pages.py, ui/theme.py); no route, form
  field, stored value or decision changed.
- Where: branch claude/project-thread-wuaqui (PR to follow)
- Verified: checked in the scripted demo case with headless Chromium at 1512, 1280 and 1100 px
  wide; a test in tests/test_start_case.py checks the claims table's class and action row.
  Not checked in the Mac app window or on Windows.
- Open: the wider Set up and run rework (less on screen, controls restyled, full hash shown)
  comes in a second PR.
- Affects: none
- Status doc: no change
