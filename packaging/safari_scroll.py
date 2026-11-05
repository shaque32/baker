"""Safari on the demo case: does an action land where the examiner took it?

Mabillon's pages run no script, so after a form the server redirects to the page with an anchor
(`/claim?id=D03#agent`) and a ledger link lands on its own row (`#lg-C10`). Chrome scrolls to
both; this checks Safari, the default browser on a pilot's Mac, through safaridriver (WebDriver
over HTTP, standard library only). The demo case is synthetic.

    sudo safaridriver --enable && safaridriver -p 4444 &
    python packaging/safari_scroll.py --demo http://127.0.0.1:8766 --driver http://127.0.0.1:4444

Prints one JSON line per step and a summary. Exit 1 if a step lands at the top of the page
(or the ledger at its first claim) when it should not.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ELEMENT = "element-6066-11e4-a52e-4f735466cecc"


class Driver:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        caps = {"capabilities": {"alwaysMatch": {"browserName": "safari"}}}
        for attempt in range(4):  # a fresh runner's first session can be refused
            try:
                self.sid = self._call("POST", "/session", caps)["sessionId"]
                return
            except urllib.error.HTTPError as err:
                print(json.dumps({"session": attempt, "error": err.read().decode()[:600]}))
                time.sleep(5)
        raise SystemExit("safaridriver refused every session")

    def _call(self, method: str, path: str, body: dict | None = None):  # noqa: ANN202
        data = json.dumps(body if body is not None else {}).encode() if method == "POST" else None
        if not self.base.startswith("http://127.0.0.1:"):
            raise SystemExit("safaridriver must be on 127.0.0.1")
        req = urllib.request.Request(  # noqa: S310 - checked above: http on this machine
            self.base + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
            return json.loads(r.read() or b"{}").get("value")

    def s(self, method: str, path: str, body: dict | None = None):  # noqa: ANN202
        return self._call(method, f"/session/{self.sid}{path}", body)

    def get(self, url: str) -> None:
        self.s("POST", "/url", {"url": url})
        time.sleep(0.8)

    def js(self, script: str):  # noqa: ANN202
        return self.s("POST", "/execute/sync", {"script": script, "args": []})

    def find(self, css: str) -> str | None:
        try:
            ref = self.s("POST", "/element", {"using": "css selector", "value": css})
            return ref.get(ELEMENT) or next(iter(ref.values()))  # Safari may use "ELEMENT"
        except Exception as err:  # noqa: BLE001 - not on the page
            body = err.read().decode()[:300] if isinstance(err, urllib.error.HTTPError) else ""
            print(json.dumps({"find": css, "error": str(err), "body": body}), flush=True)
            return None

    def click(self, el: str) -> None:
        self.s("POST", f"/element/{el}/click")
        time.sleep(1.2)

    def type(self, el: str, text: str) -> None:
        self.s("POST", f"/element/{el}/value", {"text": text})

    def quit(self) -> None:
        try:
            self._call("DELETE", f"/session/{self.sid}")
        except Exception as err:  # noqa: BLE001 - the session may already be gone
            print(json.dumps({"quit": str(err)}), flush=True)


STATE = """
const h = decodeURIComponent(location.hash.slice(1));
const t = h ? document.getElementById(h) : null;
const a = document.querySelector('aside.side');
const on = a && a.querySelector('li.on');
return {
  url: location.pathname + location.search + location.hash,
  y: Math.round(scrollY),
  target: h ? (t ? Math.round(t.getBoundingClientRect().top) : 'missing') : null,
  ledger: a ? Math.round(a.scrollTop) : null,
  open_row: on ? Math.round(on.getBoundingClientRect().top - a.getBoundingClientRect().top) : null,
  ledger_h: a ? Math.round(Math.min(a.getBoundingClientRect().bottom, innerHeight)
    - a.getBoundingClientRect().top) : null,
  height: innerHeight,
};
"""


def launch_link(base: str) -> str:
    """The running demo's launch link, from the screen key it keeps for this account in
    ~/.mabillon/screen/<port>.key (ui/screen_key.py)."""
    port = urllib.parse.urlsplit(base).port
    key = (Path.home() / ".mabillon" / "screen" / f"{port}.key").read_text(encoding="ascii")
    return f"{base}/open?key={key.strip()}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", default="http://127.0.0.1:8766")
    ap.add_argument("--driver", default="http://127.0.0.1:4444")
    args = ap.parse_args()
    demo = args.demo.rstrip("/")
    d = Driver(args.driver)
    out: list[dict] = []
    bad: list[str] = []

    def note(step: str, ok: bool | None = None, **extra: object) -> dict:
        st = d.js(STATE)
        row = {"step": step, **st, **extra}
        if ok is not None:
            row["ok"] = ok(st) if callable(ok) else ok
            if not row["ok"]:
                bad.append(step)
        print(json.dumps(row), flush=True)
        out.append(row)
        return st

    try:
        d.s("POST", "/window/rect", {"width": 1440, "height": 900, "x": 0, "y": 0})
        print(json.dumps({"safari": d.js("return navigator.userAgent")}), flush=True)
        d.get(launch_link(demo))  # sets the screen key, then shows the screen
        name = d.find("form.nameform input[type=text], form.nameform input:not([type])")
        if name:
            d.type(name, "Safari Check")
            d.click(d.find("form.nameform button"))
        opener = d.find("form[action='/case/open'] button")
        if opener:
            d.click(opener)

        # 1. A link straight to an anchor, as typed into the address bar.
        d.get(demo + "/claim?id=D03#agent")
        note("open D03#agent directly", lambda s: s["y"] > 0)

        # 2. Type a reason in the testability card, then accept (POST, 303 to #agent).
        d.get(demo + "/claim?id=D03")
        box = d.find("#agent input[name=reason]")
        if box is None:
            card = d.js("const a = document.getElementById('agent'); return a && a.innerText")
            note("D03 testability card", False, error="no undecided card", card=card)
        else:
            d.click(box)
            before = note("D03 click the reason box")
            d.type(box, "Safari check: the names match")
            time.sleep(0.5)
            note("D03 typed a reason", lambda s, y=before["y"]: abs(s["y"] - y) < 40)
            d.click(d.find("#agent button[name=decision][value=accept]"))
            note("D03 accepted (redirect to #agent)", lambda s: s["y"] > 0)

        # 3. The claim page's side ledger: open C10 from it.
        d.get(demo + "/claim?id=C01")
        link = d.find("aside.side .ledger a[href^='/claim?id=C10']")
        if link:
            d.js("document.querySelector('aside.side').scrollTop = 900; return 1")
            d.click(link)
            note(
                "C10 from the side ledger",
                lambda s: s["ledger"] and s["ledger"] > 0 and s["y"] < 40,
            )

        # 4. Confirm a verdict from far down the page (POST, 303 to #verdict).
        d.get(demo + "/claim?id=C09")
        d.js("document.querySelectorAll('#verdict details').forEach(x => x.open = true); return 1")
        btn = d.find("form[action='/verdict'] button")
        if btn:
            d.click(btn)
            note("C09 confirm verdict (redirect to #verdict)", lambda s: s["y"] > 0)
            note(
                "C09's row shows in the ledger after the form",
                lambda s: 0 <= s["open_row"] and s["open_row"] + 40 <= s["ledger_h"],
            )
    finally:
        d.quit()
    print(json.dumps({"summary": {"steps": len(out), "landed_wrong": bad}}), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
