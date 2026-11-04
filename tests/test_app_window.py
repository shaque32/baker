"""Mabillon in its own window (ui/window.py, `serve --window`) and the downloads the screen saves
itself there (ui/downloads.py). No window is drawn here: a stand-in pywebview records the calls."""

from __future__ import annotations

import argparse
import http.client
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli import main as cli
from ui import downloads, screen_key, window
from ui.app import Response
from ui.server import make_server


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    return h


@pytest.fixture(autouse=True)
def webview2(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stand-in web view is WebView2 on Windows too (the real check needs pywebview)."""
    monkeypatch.setattr(window, "windows_renderer", lambda: window.GUI["win32"])


class FakeWindow:
    def __init__(self) -> None:
        self.confirm_close = False
        self.events = SimpleNamespace(closing=Handlers())


class Handlers(list):
    def __iadd__(self, fn):  # noqa: ANN001, ANN204
        self.append(fn)
        return self


class FakeWebview:
    """Records create_window and start; start "closes" the window by running the closing
    handlers, as pywebview does, then returns."""

    def __init__(self, fail: bool = False, during: object = None) -> None:
        self.fail = fail
        self.during = during
        self.created: list[tuple[tuple, dict]] = []
        self.started: dict = {}
        self.window = FakeWindow()
        self.confirm_on_close: bool | None = None

    def create_window(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.created.append((args, kwargs))
        return self.window

    def start(self, **kwargs) -> None:  # noqa: ANN003
        if self.fail:
            raise RuntimeError("no WebView2 runtime")
        self.started = kwargs
        if callable(self.during):
            self.during()
        for fn in self.window.events.closing:
            assert fn(self.window) is True  # never cancels; it only decides whether to ask
        self.confirm_on_close = self.window.confirm_close


# ---------------------------------------------------------------- the window


def test_the_window_opens_the_launch_link_privately_and_asks_only_while_auditing():
    for running in (False, True):
        wv = FakeWebview()
        assert window.show("http://127.0.0.1:1/open?key=k", lambda r=running: r, webview=wv)
        ((args, kwargs),) = wv.created
        assert args == ("Mabillon", "http://127.0.0.1:1/open?key=k")
        assert kwargs["localization"] == {"global.quitConfirmation": window.QUIT_WHILE_AUDITING}
        assert wv.started["private_mode"] is True  # no cookies or site data kept between launches
        assert wv.confirm_on_close is running


def test_no_window_means_the_browser(monkeypatch: pytest.MonkeyPatch):
    assert not window.show("x", lambda: False, webview=FakeWebview(fail=True))
    monkeypatch.setattr(window, "load_webview", lambda: None)
    assert not window.show("x", lambda: False)


def test_windows_never_falls_back_to_internet_explorer(monkeypatch: pytest.MonkeyPatch):
    assert window.GUI["win32"] == "edgechromium"
    # pywebview falls back to Internet Explorer's engine without WebView2, even when asked for
    # edgechromium: so without WebView2 there is no window, and the browser opens instead.
    monkeypatch.setattr(window.sys, "platform", "win32")
    for engine, shown in (("mshtml", False), (None, False), ("edgechromium", True)):
        monkeypatch.setattr(window, "windows_renderer", lambda e=engine: e)
        wv = FakeWebview()
        assert window.show("x", lambda: False, webview=wv) is shown
        assert bool(wv.created) is shown


def test_with_no_console_the_output_goes_to_a_log_file(tmp_path, monkeypatch):
    # pythonw (the Windows shortcuts) leaves sys.stdout and sys.stderr as None; the screen's
    # request log writes to sys.stderr, so the first request would fail without a stream.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(cli.sys, "stdout", None)
    monkeypatch.setattr(cli.sys, "stderr", None)
    cli._log_when_no_console()
    log = cli.sys.stderr
    try:
        assert log is cli.sys.stdout and log is not None
        log.write("mabillon serve: GET /open\n")
        assert (
            (tmp_path / "Mabillon" / "Mabillon.log")
            .read_text(encoding="utf-8")
            .endswith("GET /open\n")
        )
    finally:
        log.close()


def args(tmp_path: Path, port: int = 0, window_: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        db=None, cases=tmp_path / "cases", port=port, expert=None, open=False, window=window_
    )


def test_serve_in_window_serves_the_key_and_stops_when_it_closes(home, tmp_path, monkeypatch):
    seen: dict = {}

    def show(link: str, audit_running) -> bool:  # noqa: ANN001
        port = int(link.split(":")[2].split("/")[0])
        seen["key_file"] = screen_key.read_key(port)
        seen["audit"] = audit_running()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)  # the server thread answers
        c.request("GET", link.split(str(port), 1)[1])
        seen["status"] = c.getresponse().status
        seen["link"], seen["port"] = link, port
        return True

    monkeypatch.setattr(window, "show", show)
    monkeypatch.setattr(cli, "_open_in_browser", lambda link: pytest.fail("no browser"))
    assert cli.cmd_serve(args(tmp_path)) == 0
    assert seen["status"] == 303 and seen["audit"] is False
    assert seen["link"].endswith(seen["key_file"].value)
    assert screen_key.read_key(seen["port"]) is None  # removed when the window closed
    with pytest.raises(OSError):  # and the server is closed
        http.client.HTTPConnection("127.0.0.1", seen["port"], timeout=2).request("GET", "/")


def test_with_no_window_serve_opens_the_browser(home, tmp_path, monkeypatch):
    opened: list[str] = []
    served: list[object] = []
    monkeypatch.setattr(window, "show", lambda link, audit_running: False)
    monkeypatch.setattr(cli, "_open_in_browser", opened.append)

    def until_stopped(server, key) -> None:  # noqa: ANN001
        served.append(server.RequestHandlerClass.download_folder)
        server.server_close()
        screen_key.remove_key(key)

    monkeypatch.setattr(cli, "_serve_until_stopped", until_stopped)
    assert cli.cmd_serve(args(tmp_path)) == 0
    assert len(opened) == 1 and "/open?key=" in opened[0]
    assert served == [None]  # in a browser, the browser saves downloads


def test_demo_passes_window_through(monkeypatch: pytest.MonkeyPatch):
    p = cli.parser()
    assert p.parse_args(["demo", "--window"]).window is True
    assert p.parse_args(["serve", "--window"]).window is True
    assert p.parse_args(["serve"]).window is False


# ---------------------------------------------------------------- downloads


def attachment(name: str = "mabillon-report.html", body: bytes = b"<p>report</p>") -> Response:
    return Response(
        200,
        body,
        [("Content-Type", "text/html"), ("Content-Disposition", f'attachment; filename="{name}"')],
    )


def test_attachment_names_are_safe_file_names():
    assert downloads.attachment_name(attachment()) == "mabillon-report.html"
    assert downloads.attachment_name(attachment("../../evil.sh")) == "evil.sh"
    # / and \ both end a folder name on every system, as they would on Windows
    assert downloads.attachment_name(attachment("a/b\\c:d.txt")) == "c_d.txt"
    assert downloads.attachment_name(attachment("..\\..\\evil.bat")) == "evil.bat"
    assert downloads.attachment_name(Response(200, b"", [("Content-Type", "text/html")])) is None
    assert (
        downloads.attachment_name(Response(500, b"", [("Content-Disposition", "attachment")]))
        is None
    )


def test_a_saved_download_never_overwrites(tmp_path: Path):
    first = downloads.save(attachment(), "r.html", tmp_path)
    second = downloads.save(attachment(body=b"two"), "r.html", tmp_path)
    assert (first.name, second.name) == ("r.html", "r (2).html")
    assert first.read_bytes() == b"<p>report</p>" and second.read_bytes() == b"two"


def test_back_to_only_this_screens_own_pages():
    hosts = {"127.0.0.1:8765"}
    assert downloads.back_to("http://127.0.0.1:8765/report?x=1", hosts) == "/report?x=1"
    assert downloads.back_to("http://evil.example/report", hosts) == "/"
    assert downloads.back_to(None, hosts) == "/"


def ask(server, path: str, headers: dict):  # noqa: ANN001, ANN201
    port = server.server_address[1]
    t = threading.Thread(target=server.handle_request)
    t.start()
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{port}", **headers})
    r = c.getresponse()
    out = (r.status, dict(r.getheaders()), r.read())
    t.join(10)
    return out


@pytest.mark.parametrize("in_window", [True, False])
def test_in_the_window_the_screen_saves_downloads_itself(tmp_path, monkeypatch, in_window):
    folder = tmp_path / "Downloads"
    server = make_server(
        home=tmp_path / "cases", port=0, download_folder=folder if in_window else None
    )
    try:
        monkeypatch.setattr(server.app, "handle", lambda req: attachment())
        port, key = server.server_address[1], server.key
        headers = {
            "Cookie": f"{key.cookie_name}={key.value}",
            "Referer": f"http://127.0.0.1:{port}/report",
        }
        status, got, body = ask(server, "/report?download=1", headers)
    finally:
        server.server_close()
    if in_window:
        assert status == 303 and got["Location"] == "/report"
        assert (folder / "mabillon-report.html").read_bytes() == b"<p>report</p>"
        assert server.app.flash == (f"Saved mabillon-report.html in {folder}.", False)
    else:
        assert status == 200 and body == b"<p>report</p>" and not folder.exists()
