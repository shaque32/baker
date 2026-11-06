## 2026-11-06: Sign-in client, built and switched off (license check, browser hand-back)
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
  audit starts as before and nothing connects. The license server (`workers/license/`) is not
  written yet. Plan and privacy wording: plans/desktop-sign-in.md.
- Where: local only (branch claude/project-thread-jvh1pc after #219 merges)
- Verified: `tests/test_account.py` (signatures, edited or foreign licenses refused, status
  through a license's life, file permissions, license files, the RFC 7636 example challenge,
  one-use state within 10 minutes, the client against a fake server: exactly the fields sent,
  logged before sending, nothing sent when the log cannot be written; only `account/client.py`
  imports a network client, `core/` never imports `account`, `ui/` never imports the client);
  `tests/test_account_screen.py` (off: no page, no sign-in built, audits start; on: sign in and
  out, hand-back over real HTTP without the key, wrong or reused state refused before any
  exchange, wrong Host refused, audits held back signed out, renewal at most hourly, offline sign
  out); `make check` on Linux. Not run against a real license server (none exists).
- Open: turning it on needs Arsh's signed wording (docs/SECURITY_PRIVACY.md row and section,
  site privacy page, the CLAUDE.md line in PROPOSED_CHANGES.md), the license server and its
  signing key, and a real sign-in on a Mac and a Windows PC. The "Offline" pill's tooltip
  ("Nothing leaves this computer") must say "nothing from this case" once it is on. A clock set
  back can stretch the 30-day grace; not handled. A license file is imported from the command
  line only, not yet from the screen.
- Affects: none while off (no capability, privacy, network or customer-facing change ships).
  Once on: privacy and network use (one license host).
- Status doc: no change
