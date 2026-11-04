## 2026-11-03: Per-launch screen key: only the browser Mabillon opened can use the screen (#215)
- Changed: `127.0.0.1` answers every account on the computer, so another account on a shared lab
  machine could read an open, unlocked case and the form token on its pages (security checklist
  gap A, 2026-11-03). Each launch now makes a random key (`ui/screen_key.py`). `mabillon serve`
  and `mabillon demo` open the browser at `/open?key=<key>` and print that link; that request sets
  the key as an HttpOnly, SameSite=Strict cookie named for the port, and `ui/server.py` refuses
  every other request without it (403) before `ui/app.py` sees it. The key is kept in
  `~/.mabillon/screen/<port>.key` (0600 in a 0700 folder) while the screen runs, for this
  account's tools, and is removed on
  Ctrl+C, SIGTERM or the Terminal window closing (SIGHUP). The install smoke tests
  (`packaging/smoke_ui.py`, `packaging/safari_scroll.py`) read that file and go through the
  launch link. First PR of the desktop-app plan (plans/desktop-app-sign-in.md).
- Where: PR #215
- Verified: `tests/test_screen_key.py` (11 tests: refused without the key, launch link sets the
  cookie, wrong keys and other ports refused, app token check still behind the key, key file
  mode and cleanup, a second launch on a busy port gets its own port and key); a demo run on Linux driven by
  headless Chromium through the launch link (403 without the key; case opened and claims queue
  shown with it; no failed requests); SIGINT, SIGTERM and SIGHUP each removed the key file. The
  Mac and Windows install smoke tests run in CI on this PR; Safari on a real Mac unverified.
- Open: guards against other accounts, not against programs running as the expert. A browser that
  was quit loses the session cookie; the expert double-clicks the launcher again (the server keeps
  running). A key file left by a killed process is replaced at the next launch.
- Affects: privacy (stronger: an open case is no longer readable by other accounts on the
  computer); customer-facing claims (docs/SECURITY_PRIVACY.md could add this protection; wording
  left for Arsh).
- Status doc: pending: in the privacy and network section, after "The UI serves only 127.0.0.1.",
  add "Each launch makes a random screen key held in an HttpOnly cookie; requests without it are
  refused, so other accounts on the computer cannot read an open case (ui/screen_key.py)."
