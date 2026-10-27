## 2026-10-27: Website scroll build, hero ledger, IBM Plex Sans (#156)
- Changed: Arsh asked for a walkthrough that builds as you scroll, a more interesting hero and a
  font other than Inter. The walkthrough panel now builds one claim piece by piece from scroll
  progress (claim typed out, assumptions one by one, each check landing, your review, the status),
  with a step rail; on narrow screens the panel repeats the current step's text. The hero shows a
  made-up case's four claims taking their statuses. Sections play once when a third is on screen,
  with one easing curve; a small diagram shows a pulse stopping at the "off unless you opt in" gate;
  the header is frosted. Body font is IBM Plex Sans (OFL, Fontsource 5.3.0); Inter and JetBrains
  Mono files removed from site/. Reduced motion turns all motion off.
- Where: PR #156
- Verified: Chromium at 1280x800, 1280x720, 1920x1080, 1280x900 and 390x844, light and dark, no
  console errors; walkthrough steps advance in order. Safari iOS unverified.
- Open: hero statuses are illustrative and must keep matching the rules (Supported only after the
  expert accepts; absence stays Unproven; identity links stay proposed).
- Affects: customer-facing claims (website wording only, no new claims)
- Status doc: no change
