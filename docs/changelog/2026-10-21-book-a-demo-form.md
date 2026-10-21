## 2026-10-21: Book a demo form on getmabillon.com (PR #118)
- Changed: Adds `site/demo.html` (first and last name, work email, role, "What brings you here?")
  and `site/demo-thanks.html`, and points the site's pilot buttons at it. Submissions post to a
  new Cloudflare Worker, `workers/demo-form`, on forms.getmabillon.com, which validates them,
  drops bots through a hidden honeypot field, limits each IP address to 5 submits a minute, and emails each request to the team through Email
  Routing's `send_email` binding. Nothing is stored. The privacy page now describes the form,
  including that Cloudflare sees the visitor's IP address and user agent. The site CSP's
  form-action allows forms.getmabillon.com and the site itself (for the redirect to the thanks
  page), and the demo page sends its origin so the Worker's origin check does not see "null". Also fixes the Pages deploy
  notes: a `site/*` build watch path skipped every build on 2026-10-21.
- Where: PR #118 (branch claude/project-thread-866ya3). The Worker is not deployed until Arsh
  imports it in Cloudflare (`workers/demo-form/README.md`).
- Verified: `node workers/demo-form/test.mjs` (validation, header-injection guard, a quoted
  Reply-To name, MIME encoding, Origin null or absent accepted and another site refused, the
  honeypot redirect, the rate limit). The pages were rendered in headless Chromium at 1280 px and 390 px. A live submit from a real browser and real email
  delivery are unverified until the Worker is deployed and its secret is set.
- Open: there is no captcha. Turnstile can be added if spam gets through the honeypot. Whether
  Email Routing's `send_email` delivers to the verified Gmail destination is unverified until
  the first live test.
- Affects: privacy (the site now collects names, a work email, a role and a message, and emails
  them to the team's inbox). No app, `core/` or claims change.
- Status doc: pending: section 12, add after the website note "The site's Book a demo form
  (`workers/demo-form`) emails requests to the team and stores nothing."
