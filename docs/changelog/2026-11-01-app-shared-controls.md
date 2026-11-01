## 2026-11-01: App buttons, checkboxes and fields in the site's style; one CSS file per page (#PR)
- Changed: the review screen's shared controls (ui/theme.py) now follow getmabillon.com
  (site/styles.css): 34px buttons with 8px corners, a navy primary with a soft press, red text
  for removing actions; checkboxes and radios drawn in CSS (16px box, navy fill, white tick; the
  screen's CSP allows no images), aligned to a label's first line; fields with 7px corners and
  muted placeholders; a drawn chevron on every fold-out (details/summary). Forced-colors mode
  keeps the system checkbox. New `ui/css/` package: one CSS module per page, joined after the
  theme, so page-level work (this decluttering series and the Set up and run rework) never edits
  the same CSS lines. Look only: no markup a test or packaging/smoke_ui.py selects on changed,
  no wording, verdict, label or behavior change. The exported report is unchanged.
- Where: PR #PR
- Verified: ruff; UI tests (158 selected) and `make check` (numbers in the PR); screenshots of
  the demo's claim page and Set up checkboxes (checked and unchecked) at 1440 px.
- Open: Windows browsers not looked at; the per-page modules are empty until the page PRs fill
  them.
- Affects: none (look of the local screen only)
- Status doc: no change
