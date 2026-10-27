## 2026-10-27: Quieter website with a scroll walkthrough of one claim (#PR)
- Changed: getmabillon.com redesigned to look restrained for defense lawyers and examiners (Arsh
  found it too busy and AI-template-like). Removed the "Alpha" pill, fake window chrome, scan line,
  auto-rotating demo, endless message scroll, bento cards, dark bands, mono uppercase labels and
  italics. One text face (Inter); Instrument Serif only for the wordmark and headlines; JetBrains
  Mono no longer loaded. The hero demo is now a scroll walkthrough: claim, assumptions, checks,
  your call, and a failed check. Copy shortened about by half, keeping the safe wording in
  PRODUCT_STATUS section 12 (status line, formats line and caveats unchanged). Demo form fields,
  action and privacy page text unchanged.
- Where: branch claude/project-thread-ix2p8e
- Verified: pages rendered in Chromium (desktop 1280 px, phone 390 px), no console errors; the
  walkthrough steps through all five states on scroll; without the script the finished first claim
  shows. Demo form not re-submitted (markup and action unchanged).
- Open: live check on getmabillon.com after merge; real-browser check on Safari iOS unverified.
- Affects: customer-facing claims (website wording, shorter, no new claims)
- Status doc: no change
