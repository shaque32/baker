## 2026-11-03: `mabillon demo` and `serve` move off a port already in use (#212)
- Changed: when the port was taken, `mabillon demo` said "cannot open port 8766 ... try
  --port 8766", naming the port that had just failed (seen on Arsh's Mac with an earlier demo
  still running). Now `cli/main.py` `_bind` opens the screen on the next free port of the ten
  after the asked one and prints which, and who holds the asked port: "another Mabillon (stop it
  with Ctrl+C in its window)" when one HEAD request on 127.0.0.1 finds Mabillon's Server header,
  else "another program". A Mabillon already on the port is never reused, because it may hold
  another case, cases folder or examiner, or a demo case the reset has just replaced. Any other
  bind error is shown without a port suggestion. The HEAD request is answered before any page
  runs, so nothing is logged in a case's audit log. On Windows the server no longer sets
  SO_REUSEADDR (`ui/server.py`), which there let a second server bind a port another one held
  instead of failing.
- Where: PR #212
- Verified: tests/test_serve_port.py (7 tests: free port, next free port, another Mabillon on
  the port named and not reused, all ports taken, other bind errors, a real Mabillon server
  recognised, another program not taken for Mabillon); by hand on Linux: a second `serve` on a
  running Mabillon's port and one on a port held by `python -m http.server` each moved to the
  next port. `make check` (numbers in the PR).
- Open: the Windows change is reasoned from how Windows treats SO_REUSEADDR, not tried on a
  Windows machine. Not tried by hand on macOS. An old demo left running keeps serving until it
  is stopped.
- Affects: none (command-line message and port choice; the only new connection is to
  127.0.0.1)
- Status doc: no change
