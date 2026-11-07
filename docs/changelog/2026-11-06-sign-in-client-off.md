## 2026-11-06: Sign-in, built and switched off: the app's license check and the license server
- Changed: Arsh asked to start sign-in now (2026-11-06), browser-based like Claude Desktop, with
  no login for pilots. New package `account/`, outside `core/`: `account/license.py` checks an
  Ed25519-signed license on this computer (30 days of grace after the last renewal; a license
  file for a lab with no connection needs no renewal); `account/flow.py` makes the one-use state
  and PKCE verifier (RFC 8252, RFC 7636) that the browser hands back to
  http://127.0.0.1:<port>/signin/done; `account/client.py` is the only file that connects, to
  https://account.getmabillon.com only, sending the one-time code and verifier at sign-in, then
  the license id, sign-in token and Mabillon version, never anything from a case, each request
  written to ~/.mabillon/account/account.log first; `account/session.py` ties them together for
  the screen. The screen gains an Account page (`ui/account_page.py`) and lets `/signin/done` in
  without the screen key for the one waiting state only. A license only holds back starting a
  new audit; opening, review, the report and export never need one. `mabillon license status |
  import FILE | sign-out`. **Off:** `account.SIGNIN_ON = False` and `SIGNING_KEYS` is empty, so
  `serve` builds no sign-in, there is no Account page or link, `/signin/done` answers 404, every
  audit starts as before and nothing connects. The license server is `workers/license/`, a
  Cloudflare Worker for account.getmabillon.com with one D1 database (`workers/license/schema.sql`,
  the server's own tables, never case data): emailed one-time links through Resend, a "Continue"
  button so mail scanners cannot spend a link, codes bound to the app's PKCE challenge, hashed
  links, codes and tokens, and Ed25519-signed licenses. Not deployed; Arsh sets it up
  (`workers/license/README.md`). Plan and privacy wording: plans/desktop-sign-in.md.
- Where: local only (branch claude/project-thread-jvh1pc after #219 merges)
- Verified: `tests/test_account.py` (signatures, edited or foreign licenses refused, status
  through a license's life, file permissions, license files, the RFC 7636 example challenge,
  one-use state within 10 minutes, the client against a fake server: exactly the fields sent,
  logged before sending, nothing sent when the log cannot be written; only `account/client.py`
  imports a network client, `core/` never imports `account`, `ui/` never imports the client);
  `tests/test_account_screen.py` (off: no page, no sign-in built, audits start; on: sign in and
  out, hand-back over real HTTP without the key, wrong or reused state refused before any
  exchange, wrong Host refused, audits held back signed out, renewal at most hourly, offline sign
  out); `node workers/license/test.mjs` (the whole sign-in on node:sqlite standing in for D1:
  only loopback return addresses, the same answer for unlicensed addresses, links that a GET
  does not spend, one use each, timeouts, a wrong verifier spends the code, renewal, revoked and
  ended licenses, sign out), run by `tests/test_account.py` when Node 22 is installed, which also
  checks that a license the Worker signs verifies in the app; `make check` on Linux. Not run on
  Cloudflare (not deployed).
- Open: Arsh signed the privacy wording on 2026-11-06 (plans/desktop-sign-in.md A to E); it goes
  into docs/SECURITY_PRIVACY.md and the site privacy page in the PR that turns sign-in on, since
  until then "accounts, license server: None" stays true, and the CLAUDE.md line is in
  PROPOSED_CHANGES.md for a human to apply. Turning it on also needs the license server
  deployed (Cloudflare D1, Resend, the signing key), and a real sign-in on a Mac and a Windows
  PC. Making license files for offline labs needs an admin step, not written. The "Offline" pill's tooltip
  ("Nothing leaves this computer") must say "nothing from this case" once it is on. A clock set
  back can stretch the 30-day grace; not handled. A license file is imported from the command
  line only, not yet from the screen.
- Affects: none while off (no capability, privacy, network or customer-facing change ships).
  Once on: privacy and network use (one license host).
- Status doc: no change
