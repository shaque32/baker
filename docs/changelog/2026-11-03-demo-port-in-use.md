## 2026-11-03: `mabillon demo` and `serve` handle a port already in use (#212)
- Changed: when the port was taken, `mabillon demo` said "cannot open port 8766 ... try
  --port 8766", naming the port that had just failed (seen on Arsh's Mac with an earlier demo
  still running). Now `cli/main.py` `_bind` asks the port's server with one HEAD request on
  127.0.0.1 whether it is Mabillon (its Server header). If it is, the command says Mabillon is
  already running there and opens that one (the demo case is still reset first, so the running
  demo shows the clean case). If another program holds the port, the screen opens on the next
  free port of the ten after it and the line printed names it. Any other bind error is shown
  without a port suggestion. The HEAD request is answered before any page runs, so nothing is
  logged in a case's audit log.
- Where: PR #212
- Verified: tests/test_serve_port.py (7 tests: free port, next free port, Mabillon already
  running, all ports taken, other bind errors, a real Mabillon server recognised, another
  program not taken for Mabillon); by hand on Linux: a second `serve` on a running Mabillon's
  port printed "already running" and exited 0, and one on a port held by `python -m http.server`
  moved to the next port. Not tried on macOS or Windows by hand.
  On Windows the server no longer sets SO_REUSEADDR (`ui/server.py`), which there let a
  second server bind a port another one held instead of failing.
- Open: the Windows change is reasoned from how Windows treats SO_REUSEADDR, not tried on a
  Windows machine. A real `serve` someone started on 8766 would be opened by `mabillon demo` as
  "already running".
- Affects: none (command-line message and port choice; the only new connection is to
  127.0.0.1)
- Status doc: no change
