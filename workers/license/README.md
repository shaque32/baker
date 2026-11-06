# License server (account.getmabillon.com)

A Cloudflare Worker with one D1 database. It signs people in from the Mabillon app through the
browser and hands the app a license signed with our Ed25519 key. It is not part of the app and
holds no case data. The app's side is `account/` (off until `account.SIGNIN_ON` is turned on).
Plan and privacy wording: `/mnt/project-files/baker/plans/desktop-sign-in.md`.

## The sign-in, step by step

1. The app opens `GET /signin?state&challenge&challenge_method=S256&return&v` in the system
   browser. `return` must be exactly `http://127.0.0.1:<port>/signin/done` (port 1024 to 65535);
   anything else is refused.
2. The expert types a work email (`POST /signin`). If that address holds a current license, we
   email a one-time link through Resend, good for 15 minutes. The page says the same thing
   either way, so it never tells anyone which addresses hold a license. 5 tries a minute per
   address and email.
3. The link (`GET /signin/link?t=`) shows a "Continue to Mabillon" button; only pressing it
   (`POST /signin/link`) uses the link up, so mail scanners that open links first cannot spend it.
   It sends the browser to the app's `return` address with a one-time `code` (5 minutes) and the
   app's own `state`.
4. The app sends `POST /api/token {code, verifier, v}`. The verifier's SHA-256 must match the
   challenge from step 1, so a code caught on the way is no use to anyone else; a wrong one
   spends the code. The answer is `{license, signature, token}`.
5. `POST /api/renew {license_id, token, v}` gives a freshly signed license, at most daily.
   `POST /api/signout {license_id, token}` drops the token.

We keep only SHA-256 hashes of links, codes and tokens (`schema.sql`), and for each signed-in
computer only when it last renewed and its Mabillon version.

## Tests

`node workers/license/test.mjs` (Node 22 or later, no dependencies): the whole sign-in on a real
SQLite database standing in for D1. `make test` runs it too when Node 22 is installed
(`tests/test_account.py`), and checks that a license this Worker signs verifies in the app.

## Setup (Arsh; about 20 minutes, once)

1. **Signing key.** On your own computer: `node workers/license/make-key.mjs k1`. Keep the
   private JWK it prints for step 4 only; put the `SIGNING_KEYS` line it prints into
   `account/license.py` in a PR.
2. **Database.** `npx wrangler d1 create mabillon-license`, put the id it prints in
   `wrangler.toml`, then `npx wrangler d1 execute mabillon-license --remote --file
   workers/license/schema.sql`.
3. **Email.** A Resend account with getmabillon.com as a verified sending domain (it adds DNS
   records in Cloudflare). Sender: `signin@getmabillon.com`.
4. **Worker.** Workers & Pages > Create > Import a repository > `shaque32/mabillon`, project
   `mabillon-license`, root directory `workers/license`, deploy command `npx wrangler deploy`.
   Then Settings > Variables and secrets: secret `SIGNING_KEY_JWK` (step 1) and secret
   `RESEND_KEY`. Check that Domains & Routes lists `account.getmabillon.com`.
5. **A license.** For each person:
   `npx wrangler d1 execute mabillon-license --remote --command "INSERT INTO licenses (id, email, plan, paid_through, created_at) VALUES ('lic_<12 letters or digits>', '<email in lower case>', 'pilot', '2027-06-30T00:00:00.000Z', '<today>T00:00:00.000Z')"`.
   To end one: `UPDATE licenses SET status = 'revoked' WHERE email = '...'`.

## Not done yet

- License files for labs with no internet (signed with `offline: true`): the app reads them;
  making one needs a small admin step, not written yet.
- No admin page: licenses are added with the command above.
- Untested on Cloudflare itself (no deploy yet); the tests run the same code on Node 22.
