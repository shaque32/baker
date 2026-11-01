## 2026-11-01: Site walkthrough on phones: even step tabs, no random pauses (#203)

- Changed: On getmabillon.com's "One claim, start to finish" stepper (`site/index.html`,
  `site/styles.css`, `site/main.js`), two phone bugs Arsh reported from an iPhone. (1) Uneven
  tabs: each tab sized to its own label, so one-line tabs ("Claim", "Checks") sat shorter than
  two-line ones ("Assump-tions", "Failed check") and their underlines did not line up. Every tab
  now fills its cell, so all five share one height and one underline. Below 460px, where
  "Assumptions" cannot fit on one line, the tabs show only their numbers (the caption below names
  the step; the label stays for screen readers); the soft hyphen is gone. (2) Random pauses: a
  finger landing on the panel to scroll counted as a mouse hover and froze autoplay, and a tap
  could leave it held. Hover now pauses only for a mouse; keyboard focus holds the walk only after
  keyboard input, tracked by the page instead of `:focus-visible` (which differs by browser);
  a tab tap still holds for 10 seconds as before. The panel also keeps one height through the walk
  (a hidden copy is laid out at every step to find the tallest caption and body), so the page
  below no longer jumps each step and the panel can no longer jump out of view, which stopped the
  walk. A long frame gap (phone asleep, tab hidden) no longer skips the walk ahead, and the last
  step's underline fills fully before the loop instead of stopping at 95%. `?v=` hashes updated.
- Where: PR #203
- Verified: Headless Chromium (Playwright, Linux, 2026-11-01) with touch emulation at 320, 360,
  390, 430, 460, 540, 620 and 900px: all five tabs the same height with one underline line at
  every width, and panel and page height constant over a full 26-second cycle. A held finger on
  the panel and a tap on its body no longer pause it (before the fix both froze it in the same
  test); a tab tap holds about 10 seconds, then resumes. Real iOS Safari was not checked.
- Open: Under 460px the tabs no longer show step names; the caption carries them. The 3-second
  hold on the last step before the loop is kept on purpose.
- Affects: none (site behavior and layout only; no wording or claims changed)
- Status doc: no change
