# getmabillon.com

The public website: plain static HTML and CSS plus one small script (`main.js`: the home page walkthrough that builds an example claim as you scroll, and sections that play once when they come into view), no build step, no third-party
requests. Fonts are OFL files: Instrument Serif (as in `ui/static/fonts`) and IBM Plex Sans (licenses in `fonts/LICENSES.txt`).

- `index.html` home page, `demo.html` Book a demo form, `demo-thanks.html` its confirmation,
  `privacy.html` privacy page, `404.html` not-found page.
- `_headers` sets a strict Content-Security-Policy and security headers on Cloudflare Pages.

Every statement must match the safe wording in `docs/PRODUCT_STATUS.md` section 12 and the
one-pager, `docs/ONE_PAGER.md`: no speed
or accuracy figures, UFDR and AXIOM unverified on real exports, no logos, testimonials or
"court-ready". Change the copy when those docs change.

Preview locally: `python -m http.server -d site 8000`, then open http://127.0.0.1:8000.

## Deploy (Cloudflare Pages, Git integration)

1. Cloudflare dashboard > Workers & Pages > Create > Pages > Connect to Git, pick `shaque32/baker`.
2. Production branch `main`. Framework preset None. Build command empty. Build output directory
   `site`. Leave build watch paths at `*`: on 2026-10-21 a `site/*` filter made Pages skip every
   build. Under branch control, set preview branches to None.
3. After the first deploy: the project > Custom domains > add `getmabillon.com`, then
   `www.getmabillon.com`. Cloudflare adds the DNS records because the domain is on the same account.
4. Leave Web Analytics off: the privacy page says it is off.

The live project is `baker-axe.pages.dev`. The Book a demo form posts to a separate Worker,
`workers/demo-form` (its README has the setup).
