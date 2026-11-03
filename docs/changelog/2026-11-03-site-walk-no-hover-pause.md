## 2026-11-03: Site walkthrough keeps playing under the mouse (#PR)
- Changed: getmabillon.com's one-claim walkthrough no longer pauses while the mouse rests on
  it. Arsh found the hover pause made the animation feel broken. The pause button, keyboard
  focus, tab clicks and arrow keys still take over, and reduced motion still shows a still
  panel with no autoplay. Only site/main.js and its ?v= link in site/index.html changed.
- Where: PR #PR
- Verified: headless Chromium against the local site with the mouse held over the panel: the
  walk advanced from step 1 to step 3 in 9 s (on main it stayed on step 1); with reduced
  motion it stayed on step 1. make check (lint, tests, eval) passed.
- Open: open draft PR #203 edits the same hover line (mouse-only pause); whichever merges
  second drops that line when it syncs with main.
- Affects: none (website behavior only)
- Status doc: no change
