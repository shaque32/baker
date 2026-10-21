## 2026-10-21: Public website for getmabillon.com (#113)
- Changed: Adds `site/`, a static landing page, privacy page and 404 page for the company
  website at getmabillon.com, under the new name Mabillon, in the review screen's look. Plain
  HTML and CSS plus one small self-hosted script that plays the home page's example of three
  claims (respects reduced motion; nothing is sent anywhere). No third-party requests, self-hosted OFL fonts, strict Content-Security-Policy in `site/_headers`.
  Contact is a mailto link to support@getmabillon.com; there is no sign-in, form backend or public
  download. No app code changes.
- Where: PR #113 (branch claude/project-thread-866ya3). Not deployed: Arsh connects Cloudflare
  Pages after merge (`site/README.md`).
- Verified: every product statement copied from `docs/ONE_PAGER.md` (#92) and PRODUCT_STATUS
  section 12 safe wording; rendered in headless Chromium at 1280 px and 390 px wide. Dark mode,
  other browsers and the live Cloudflare headers are unverified until deploy.
- Open: Arsh's sign-off on the copy; deploy and custom domain; the app itself still says Baker
  until the rename lands.
- Affects: customer-facing claims (public website; no speed or accuracy claims, UFDR and AXIOM
  stated as unverified on real exports, no logos or testimonials). Privacy: the site sets no
  cookies and loads nothing from other hosts.
- Status doc: pending: section 12, add after the table "The public website (`site/`,
  getmabillon.com) uses only the safe wording above and the one-pager; update it when these
  claims change."
