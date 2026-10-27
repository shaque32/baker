## 2026-10-21: Public website for getmabillon.com (#113)
- Changed: Adds `site/`, a static landing page, privacy page and 404 page for the company
  website at getmabillon.com, under the new name Mabillon, in the review screen's look. Plain
  HTML and CSS plus one small self-hosted script that plays the home page's example of three
  claims (respects reduced motion; nothing is sent anywhere). No third-party requests, self-hosted OFL fonts, strict Content-Security-Policy in `site/_headers`.
  Contact is a mailto link to support@getmabillon.com; there is no sign-in, form backend or public
  download. No app code changes.
- Where: main (#113, merged 2026-10-21)
- Verified: every product statement copied from `docs/ONE_PAGER.md` (on main since #92) and PRODUCT_STATUS
  section 12 safe wording; the hero's contradicted example uses a message matched by its exact words
  with its only copy outside the stated day, the one case where the time check (1.0.1) can fail; rendered in headless Chromium at 1280 px and 390 px wide. Dark mode,
  other browsers and the live Cloudflare headers are unverified until deploy.
- Open: Arsh's sign-off on the copy; deploy and custom domain; the app itself still says Baker
  until the rename lands.
- Affects: customer-facing claims (public website; no speed or accuracy claims, UFDR and AXIOM
  stated as unverified on real exports, no logos or testimonials). Privacy: the site sets no
  cookies and loads nothing from other hosts.
- Status doc: applied 2026-10-27
