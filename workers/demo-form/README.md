# Book a demo form handler

A Cloudflare Worker at `https://forms.getmabillon.com/demo`. The form on `site/demo.html` posts
here; the Worker checks the fields, drops bots that fill the hidden `website` field, and emails
the request to the team through the Email Routing `send_email` binding. It stores nothing and
sets no cookies. It is not part of the Mabillon app and makes no call from `core/`.

- From: `demo-form@getmabillon.com` (`FROM` in `wrangler.toml`). Reply-To is the visitor.
- To: the secret `NOTIFY_TO`, a destination address already verified in Email Routing. It is
  a secret so the inbox address stays out of this public repo.
- Origin: a post naming another site is refused. "null" or no Origin is accepted, because
  browsers send that under some referrer and privacy settings.
- Rate limit: 5 submits a minute per IP address (the `LIMITER` binding in `wrangler.toml`);
  more are sent back to the form with a "please wait a minute" message.
- Tests: `node workers/demo-form/test.mjs` (no dependencies).

## Setup (Cloudflare dashboard, about 10 minutes)

1. Workers & Pages > Create application > Import a repository > `shaque32/baker`.
   Project name `mabillon-demo-form`. Root directory `workers/demo-form`. Leave the build
   command empty; the deploy command stays `npx wrangler deploy`. Deploy.
2. The Worker > Settings > Variables and secrets > Add > type Secret, name `NOTIFY_TO`, value
   the inbox that support@getmabillon.com forwards to. Deploy.
3. The Worker > Settings > Domains & Routes should list `forms.getmabillon.com` (from
   `wrangler.toml`). If it does not, add it as a custom domain there.
4. Test: submit the form on getmabillon.com/demo.html. The email arrives from
   demo-form@getmabillon.com.

Every problem a visitor can fix or retry (a missing or invalid field, the rate limit, an
unreadable post, a send that failed or a missing `NOTIFY_TO`) redirects 303 to
`demo.html?error=<code>`, where `site/demo.js` shows the message in the site's style and refills
the fields. Until step 2 is done every valid post comes back as "unavailable", which points to
the support address, and the Worker logs "NOTIFY_TO is not set".
