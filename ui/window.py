"""Mabillon in its own window: the same screen, without a browser tab or a Terminal.

`mabillon serve --window` and `mabillon demo --window` (what the Mac app and the Windows Start
menu shortcut run) start the screen exactly as `serve` does, on 127.0.0.1 with this launch's
screen key (ui/screen_key.py), and show it in a native window drawn by pywebview (BSD). The page
engine is the operating system's own: WebKit on a Mac (Safari's engine), Edge WebView2 on
Windows. Nothing about the screen changes.

- The window opens the launch link, so it holds the screen key, and keeps no cookies or site
  data between launches (pywebview's private mode).
- Closing the window stops Mabillon, as closing the Terminal window did. While an audit runs it
  asks first; the audit's finished claims are kept and it resumes later, as before.
- A download is saved into the Downloads folder by the screen itself (ui/downloads.py).
- With no pywebview or no web view (Linux, or a Windows PC without WebView2), Mabillon says so and
  opens the browser instead, as `serve --open`.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

TITLE = "Mabillon"
SIZE = (1280, 860)
MIN_SIZE = (900, 600)
# The page engine to ask for. On Windows only WebView2: pywebview would otherwise fall back to
# Internet Explorer's engine, which the screen does not support; show() checks before it opens.
GUI = {"win32": "edgechromium", "darwin": "cocoa"}
QUIT_WHILE_AUDITING = (
    "An audit is running. Closing Mabillon stops it; the claims it finished are kept, and you can "
    "resume it to label the rest. Close Mabillon?"
)
# The Dock icon on a Mac (the Mac install keeps the whole source folder; Windows takes the
# shortcut's icon instead).
ICON = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "art" / "mabillon.ico"


def load_webview() -> Any | None:
    """pywebview, or None when it is not installed (the `app` extra)."""
    try:
        return importlib.import_module("webview")
    except ImportError:
        return None


def windows_renderer() -> str | None:
    """The page engine pywebview will use on Windows: "edgechromium" when WebView2 is installed.
    pywebview picks it when its Windows backend is first imported and, without WebView2, falls
    back to Internet Explorer's engine (MSHTML) even when asked for edgechromium."""
    try:
        winforms = importlib.import_module("webview.platforms.winforms")
    except Exception:  # noqa: BLE001 - no backend at all: no window
        return None
    return getattr(winforms, "renderer", None)


def _name_the_mac_app() -> None:
    """On a Mac the process is Python; give the menu bar and the About box Mabillon's name.
    pywebview reads this same dictionary when it builds the menu."""
    if sys.platform != "darwin":
        return
    try:
        foundation = importlib.import_module("Foundation")
        bundle = foundation.NSBundle.mainBundle()
        # The installed app (packaging/mac/install.sh) shows "Mabillon" in the menu bar (seen on
        # a Mac, 2026-11-06). Run from Terminal, macOS names the menu after Python at start, and
        # this cannot change it; it still names pywebview's own menus.
        for info in (bundle.infoDictionary(), bundle.localizedInfoDictionary()):
            if info is not None:
                info["CFBundleName"] = TITLE
                info["CFBundleDisplayName"] = TITLE
    except Exception as err:  # noqa: BLE001 - a name is cosmetic; never stop the window over it
        print(f"(menu bar name not set: {type(err).__name__})")


def show(
    link: str,
    audit_running: Callable[[], bool],
    webview: Any | None = None,
    title: str = TITLE,
) -> bool:
    """Show the screen at link in a window until the expert closes it. False when no window
    could be shown (no pywebview, or the system has no web view): the caller opens the browser.
    """
    webview = webview or load_webview()
    if webview is None:
        print("Mabillon's own window needs pywebview, which is not installed here.")
        return False
    if sys.platform == "win32" and (engine := windows_renderer()) != GUI["win32"]:
        print(f"Mabillon's own window needs Microsoft Edge WebView2 (this PC has {engine}).")
        return False
    _name_the_mac_app()

    def closing(window: Any) -> bool:
        # pywebview asks to confirm (with the message below) only when confirm_close is set, and
        # reads it after this handler: so ask only while an audit runs.
        window.confirm_close = audit_running()
        return True

    try:
        window = webview.create_window(
            title,
            link,
            width=SIZE[0],
            height=SIZE[1],
            min_size=MIN_SIZE,
            text_select=True,
            localization={"global.quitConfirmation": QUIT_WHILE_AUDITING},
        )
        window.events.closing += closing
        webview.start(
            gui=GUI.get(sys.platform),
            private_mode=True,
            icon=str(ICON) if ICON.exists() else None,
        )
    except Exception as err:  # noqa: BLE001 - any failure to draw a window falls back to the browser
        print(f"Mabillon could not open its own window ({type(err).__name__}: {err}).")
        return False
    return True
