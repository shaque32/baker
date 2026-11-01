## 2026-11-01: The app takes the site's warm paper palette (#PR)
- Changed: Arsh chose (2026-10-31 decision card, "Yes, match the site fully") to give the local
  review screen the getmabillon.com colors. ui/theme.py tokens now use site/styles.css values:
  page and sidebar #f7f5f0, cards #fdfcfa, panel #efece5, warm gray lines and muted text,
  text #141414; navy accent unchanged. The last hard-coded cool grays now use tokens. Unproven
  stays a neutral (warm) gray as chosen on 2026-10-29, not the site's amber. Colors only: no
  markup, wording, verdict or behavior change. The exported report keeps its own palette.
- Where: PR #PR (stacked on the shared-controls PR)
- Verified: ruff; UI tests and `make check` (numbers in the PR); demo screenshots of the case,
  claims and one-claim pages at 1440 px.
- Open: contrast of muted text measured by eye only (#5f5a51 on #f7f5f0 is the site's own
  pair); Windows not looked at.
- Affects: none (look of the local screen only)
- Status doc: no change
