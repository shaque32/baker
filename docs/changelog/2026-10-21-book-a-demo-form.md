## 2026-10-21: Book a demo form on getmabillon.com (PR pending)
- Changed: Adds `site/demo.html` (first and last name, work email, role, "What brings you here?")
  and `site/demo-thanks.html`, and points the site's pilot buttons at it. Submissions post to a
  new Cloudflare Worker, `workers/demo-form`, on forms.getmabillon.com, which validates them,
  drops bots through a hidden honeypot field, and emails each request to the team through Email
  Routing's `send_email` binding. Nothing is stored. The privacy page now describes the form,
  and the site CSP allows posting only to forms.getmabillon.com. Also fixes the Pages deploy
  notes: a `site/*` build watch path skipped every build on 2026-10-21.
- Where: branch claude/project-thread-866ya3 (PR pending). The Worker is not deployed until Arsh
  imports it in Cloudflare (`workers/demo-form/README.md`).
- Verified: `node workers/demo-form/test.mjs` (validation, header-injection guard, MIME
  encoding). The pages were rendered in headless Chromium at 1280 px and 390 px. Real email
  delivery is unverified until the Worker is deployed and its secret is set.
- Open: there is no captcha. Turnstile can be added if spam gets through the honeypot. Whether
  Email Routing's `send_email` delivers to the verified Gmail destination is unverified until
  the first live test.
- Affects: privacy (the site now collects names, a work email, a role and a message, and emails
  them to the team's inbox). No app, `core/` or claims change.
- Status doc: pending: section 12, add after the website note "The site's Book a demo form
  (`workers/demo-form`) emails requests to the team and stores nothing."
