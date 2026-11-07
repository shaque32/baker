"""Headless-browser smoke test of an installed Mabillon: the start screen and the demo case.

Run after a fresh install, with `baker serve` on one port and `baker demo --no-open` on another:

    python packaging/smoke_ui.py --serve http://127.0.0.1:8765 --demo http://127.0.0.1:8766

It drives a real Chromium the way a first-time expert would: the cases screen opens, the expert
types a name, opens the synthetic demo case and sees its claims with their verdicts. Any page
error, browser console error (a Content-Security-Policy block counts) or failed request fails
it. Synthetic data only: the demo case is case01. Needs `playwright` (CI installs it; Mabillon does
not). --chrome uses the machine's Google Chrome instead of Playwright's own Chromium.

Each screen opens only with its launch's screen key (ui/screen_key.py), which a running Mabillon
keeps in ~/.mabillon/screen/<port>.key for this account; the test reads it like a second click on
the launcher would, and opens /open?key=... first.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Page, sync_playwright

EXPERT = "Smoke Test (synthetic)"
# Straight to 127.0.0.1: never through a proxy from the environment or the Windows registry.
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def need(ok: bool, why: str) -> None:
    if not ok:
        raise SystemExit(f"FAIL: {why}")


def key_file(base: str) -> Path:
    """Where a running Mabillon keeps its screen key (ui/screen_key.py; this script runs on its
    own, without Mabillon installed beside it, so it names the place itself)."""
    return Path.home() / ".mabillon" / "screen" / f"{urlsplit(base).port}.key"


def wait_up(base: str, seconds: float = 90) -> str:
    """Wait until the screen answers and its key is written; return its launch link."""
    need(base.startswith("http://127.0.0.1:"), f"{base} is not a Mabillon on this computer")
    deadline = time.monotonic() + seconds
    last = "no answer"
    while True:
        try:
            with NO_PROXY.open(base + "/cases", timeout=5) as r:
                need(False, f"{base}/cases answered {r.status} without the screen key")
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 403 and key_file(base).exists():
                key = key_file(base).read_text(encoding="ascii").strip()
                return f"{base}/open?key={key}"
        except OSError as e:
            last = repr(e)
        if time.monotonic() > deadline:
            why = f"no screen with a key at {base} within {seconds:.0f} s ({last})"
            raise SystemExit(f"FAIL: {why}")
        time.sleep(1)


def watch(page: Page, problems: list[str]) -> None:
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on(
        "console",
        lambda m: problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None,
    )
    page.on("requestfailed", lambda r: problems.append(f"request failed: {r.url} {r.failure}"))
    page.on(
        "response",
        lambda r: problems.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None,
    )


def start_screen(page: Page, base: str) -> None:
    page.goto(base + "/")  # after its launch link, so the screen key is set
    need(page.url.endswith("/cases"), f"start screen went to {page.url}, not /cases")
    need("Mabillon" in page.title(), page.title())
    body = page.inner_text("body")
    for words in ("Offline", "Cases folder", "New case"):
        need(words in body, f"start screen lacks {words!r}")
    print(f"ok  start screen {page.url}: {page.title()}")


def demo_case(page: Page, base: str) -> None:
    page.goto(base + "/cases")
    name = page.locator("form[action='/expert'] input[name='name']")
    if name.count():  # asked once per running Mabillon
        name.fill(EXPERT)
        page.click("form[action='/expert'] button[type='submit']")
        page.wait_for_load_state()
    row = page.locator("tr", has_text="synthetic case01")
    need(row.count() == 1, f"{row.count()} demo case rows on the demo cases screen")
    row.locator("form[action='/case/open'] button").click()
    page.wait_for_load_state()
    need("Petrov" in page.inner_text("body"), "the demo case did not open")
    print(f"ok  demo case opened at {page.url}")
    page.click("nav a[href='/claims']")
    page.wait_for_load_state()
    folds = page.locator("details.fold > summary")
    for i in range(folds.count()):  # settled groups fold while claims wait on the expert
        folds.nth(i).click()
    body = page.inner_text("body")
    # rules 0.5.0: the demo's C05 opens as supported by its code checks (rule 3c')
    want = (
        "Supported by the records (code checks)",
        "Contradicted",
        "Supported (expert-confirmed)",
    )
    missing = [w for w in want if w not in body]
    need(not missing, f"the claims queue lacks {missing}")
    for banned in ("guilty", "innocent"):
        need(banned not in body.lower(), f"the claims queue says {banned!r}")
    print(f"ok  claims queue {page.url}: shows {', '.join(want)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serve", required=True, help="base URL of `baker serve`")
    ap.add_argument("--demo", required=True, help="base URL of `baker demo --no-open`")
    ap.add_argument("--chrome", action="store_true", help="use the installed Google Chrome")
    ap.add_argument("--screenshots", help="folder for a screenshot of each screen")
    a = ap.parse_args()
    links = [wait_up(base) for base in (a.serve, a.demo)]
    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome" if a.chrome else None)
        page = browser.new_page()
        watch(page, problems)
        try:
            for link in links:  # each sets its screen's key as a cookie, then shows the screen
                page.goto(link)
            start_screen(page, a.serve)
            if a.screenshots:
                page.screenshot(path=f"{a.screenshots}/start-screen.png", full_page=True)
            demo_case(page, a.demo)
            if a.screenshots:
                page.screenshot(path=f"{a.screenshots}/demo-case.png", full_page=True)
        finally:
            browser.close()
    if problems:
        print("FAIL: the browser reported problems:", *problems, sep="\n  ")
        return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
