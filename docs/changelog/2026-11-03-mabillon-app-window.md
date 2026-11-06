## 2026-11-03: Mabillon opens in its own window: a Mac app and Windows shortcuts (#219)
- Changed: Arsh asked for a real desktop app (like Loom) instead of a browser tab and a Terminal
  window. `mabillon serve --window` and `mabillon demo --window` (`ui/window.py`) start the screen
  as before, on 127.0.0.1 with the per-launch screen key (#215), and show it in a native window
  drawn by pywebview 6 (BSD) on the system's web view: WebKit on a Mac, Edge WebView2 on Windows.
  The window keeps no cookies or site data between launches. Closing it stops Mabillon, asking
  first while an audit runs. In the window, downloads (report, activity CSV, request draft, bug
  report, flag summary) are saved into the Downloads folder by the screen itself
  (`ui/downloads.py`), because WebKit's download path re-fetches without the key. Without
  pywebview or a web view (on Windows, without Edge WebView2: pywebview would otherwise use
  Internet Explorer's engine) it opens the browser. The report on screen (which already links back to the case and
  saves itself) now also says where a save went, or why it failed, since the window has no
  download bar. The Mac installer builds "Mabillon" and "Mabillon
  Demo" apps in ~/Applications (icon from the app's mark; logs in ~/Library/Logs/Mabillon.log);
  the Desktop browser launchers stay. The Windows installer adds "Mabillon" and "Mabillon demo"
  to the Start menu and an optional desktop icon, run with pythonw (no console; output goes to
  %LOCALAPPDATA%\Mabillon\Mabillon.log). New optional
  dependency group `app` (pywebview, pythonnet on Windows); the installers include it. Second PR
  of the desktop-app plan (plans/desktop-app-sign-in.md). No sign-in, no new network use.
- Where: PR #219
- Verified: `tests/test_app_window.py` (stand-in pywebview: launch link, private mode, close
  prompt only while auditing, fallback to the browser, second launch, downloads saved without
  overwriting, back to the page asked from); `make check` on Linux. Windows staging resolved
  pywebview, pythonnet and a built proxy_tools wheel for win_amd64 on Linux. A real window was
  not drawn here: the clean-install CI job opens the Mabillon Demo app on a macOS runner (report
  only). On a real Mac (Arsh's MacBook Air M4, macOS 15.6.1, 2026-11-06): `mabillon demo --window`
  opened the window with Mabillon's Dock icon, and the installed Mabillon Demo app shows
  "Mabillon" in the menu bar. Windows window unverified until seen on a real PC.
- Open: run from Terminal (`mabillon demo --window`), the menu bar says "Python", because macOS
  names it after the program that started; the installed apps say "Mabillon". Edge WebView2 may
  run Microsoft's SmartScreen check on navigations, as the Edge browser does (unverified for
  127.0.0.1). Printing from the window is not wired; the downloaded report prints from a
  browser.
- Affects: capabilities (desktop app); customer-facing claims (Mabillon can be described as a
  desktop app on Mac and Windows once seen working); privacy: none (same local server and key;
  pywebview and the web view load only 127.0.0.1).
- Status doc: pending: in the section that says experts work in the browser on their own
  computer (`mabillon serve`, http://127.0.0.1:8765), add "Mabillon also opens in its own window
  (`mabillon serve --window`; the Mac apps in ~/Applications and the Windows Start-menu
  shortcuts), WebKit on a Mac and Edge WebView2 on Windows; seen working on a Mac 2026-11-06, unverified on
  a Windows PC."
