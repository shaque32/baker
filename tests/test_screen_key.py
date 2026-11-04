"""The per-launch screen key (ui/screen_key.py): only the browser Mabillon opened can use the
screen, so another account on the same computer cannot read an open case."""

from __future__ import annotations

import argparse
import http.client
import http.server
import os
import threading
from pathlib import Path
from urllib.parse import urlencode

import pytest

from cli import main as cli
from ui import screen_key
from ui.screen_key import REFUSED, ScreenKey, cookie_value
from ui.server import launch_url, make_server


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home folder of the test's own, so no key file lands in the real one."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    assert Path.home() == h
    return h


@pytest.fixture
def server(tmp_path: Path):  # noqa: ANN201
    s = make_server(home=tmp_path / "cases", port=0)
    yield s
    s.server_close()


def ask(server, method: str, path: str, headers: dict | None = None, body: str = ""):  # noqa: ANN001, ANN201
    """One request to the running server: (status, headers, body)."""
    port = server.server_address[1]
    t = threading.Thread(target=server.handle_request)
    t.start()
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    if body:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    c.request(method, path, body or None, h)
    r = c.getresponse()
    out = (r.status, dict(r.getheaders()), r.read().decode())
    t.join(10)
    return out


def cookie_of(server) -> dict[str, str]:  # noqa: ANN001
    key = server.key
    return {"Cookie": f"{key.cookie_name}={key.value}"}


def test_without_the_key_every_page_and_form_is_refused(server):
    for path in ("/", "/cases", "/claims", "/help", "/fonts/x.woff2"):
        status, _, body = ask(server, "GET", path)
        assert status == 403 and body == REFUSED, path
    token = server.app.token
    status, _, body = ask(server, "POST", "/expert", body=urlencode({"token": token, "name": "X"}))
    assert status == 403 and body == REFUSED
    assert server.app.expert is None  # the form never reached the app


def test_the_launch_link_sets_a_private_cookie_and_opens_the_screen(server):
    key = server.key
    assert launch_url(server) == f"http://127.0.0.1:{key.port}/open?key={key.value}"
    status, headers, _ = ask(server, "GET", f"/open?key={key.value}")
    assert status == 303 and headers["Location"] == "/"
    cookie = headers["Set-Cookie"]
    assert cookie.startswith(f"mabillon_screen_{key.port}={key.value};")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Path=/" in cookie
    assert "Max-Age" not in cookie and "Expires" not in cookie  # ends when the browser quits
    status, _, body = ask(server, "GET", "/cases", cookie_of(server))
    assert status == 200 and "New case" in body


def test_a_wrong_or_missing_key_does_not_open_the_screen(server):
    key = server.key
    for path in ("/open", "/open?key=", f"/open?key={key.value}x", "/open?key=guess"):
        status, headers, _ = ask(server, "GET", path)
        assert status == 403 and "Set-Cookie" not in headers, path
    wrong = {"Cookie": f"{key.cookie_name}=guess"}
    assert ask(server, "GET", "/cases", wrong)[0] == 403
    other_port = {"Cookie": f"mabillon_screen_{key.port + 1}={key.value}"}
    assert ask(server, "GET", "/cases", other_port)[0] == 403
    # POST to /open never sets the cookie, even with the key
    status, headers, _ = ask(server, "POST", f"/open?key={key.value}", body="a=b")
    assert status == 403 and "Set-Cookie" not in headers


def test_with_the_key_the_app_still_checks_its_own_form_token(server):
    status, _, _ = ask(server, "POST", "/redecide", cookie_of(server), urlencode({"token": "x"}))
    assert status == 403  # the app's own token check, behind the key
    body = urlencode({"token": server.app.token, "name": "Test Expert"})
    assert ask(server, "POST", "/expert", cookie_of(server), body)[0] == 303
    assert server.app.expert == "Test Expert"


def test_another_host_is_left_to_the_app(server):
    status, _, _ = ask(server, "GET", "/cases", {"Host": "evil.example:80"})
    assert status == 400


def test_each_launch_has_its_own_key_and_cookie(tmp_path: Path):
    a = make_server(home=tmp_path / "a", port=0)
    b = make_server(home=tmp_path / "b", port=0)
    try:
        assert a.key.value != b.key.value
        assert a.key.cookie_name != b.key.cookie_name  # cookies are not kept apart by port
        assert ask(b, "GET", "/cases", cookie_of(a))[0] == 403
    finally:
        a.server_close()
        b.server_close()


def test_cookie_value_reads_one_cookie():
    header = "a=1; mabillon_screen_8765=k1; mabillon_screen_8766=k2"
    assert cookie_value(header, "mabillon_screen_8766") == "k2"
    assert cookie_value(header, "mabillon_screen_1") is None
    assert cookie_value(None, "a") is None
    assert not ScreenKey(1, "k").admits(None)


def test_the_key_file_is_this_accounts_only_and_removed_only_by_its_launch(home: Path):
    key = ScreenKey(8765)
    path = screen_key.write_key(key)
    assert path == home / ".mabillon" / "screen" / "8765.key"
    assert path.read_text(encoding="ascii") == key.value
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    assert screen_key.read_key(8765) == key
    screen_key.remove_key(ScreenKey(8765))  # another launch's key leaves the file alone
    assert path.exists()
    newer = ScreenKey(8765)
    screen_key.write_key(newer)  # a new launch on the same port replaces it
    assert screen_key.read_key(8765) == newer
    screen_key.remove_key(newer)
    assert not path.exists() and screen_key.read_key(8765) is None


def serve_args(tmp_path: Path, port: int, open_: bool = True) -> argparse.Namespace:
    return argparse.Namespace(db=None, cases=tmp_path / "cases", port=port, expert=None, open=open_)


def test_serve_opens_the_launch_link_and_cleans_up(home, tmp_path, monkeypatch, capsys):
    opened: list[str] = []
    seen: dict[str, str] = {}
    monkeypatch.setattr(cli, "_open_in_browser", opened.append)

    def stop(self) -> None:  # noqa: ANN001
        seen["file"] = screen_key.key_file(self.server_address[1]).read_text(encoding="ascii")
        raise KeyboardInterrupt

    monkeypatch.setattr(http.server.HTTPServer, "serve_forever", stop)
    assert cli.cmd_serve(serve_args(tmp_path, 0)) == 0
    out = capsys.readouterr().out
    assert len(opened) == 1 and "/open?key=" in opened[0] and opened[0] in out
    assert opened[0].endswith(seen["file"])
    assert list(screen_key.key_dir().glob("*.key")) == []  # removed on exit


def test_a_second_launch_on_a_busy_port_gets_its_own_port_and_key(
    home, tmp_path, monkeypatch, capsys
):
    running = make_server(home=tmp_path / "cases", port=0)
    seen: dict[str, object] = {}

    def stop(self) -> None:  # noqa: ANN001
        seen["port"] = self.server_address[1]
        seen["key"] = screen_key.read_key(self.server_address[1])
        raise KeyboardInterrupt

    try:
        port = running.server_address[1]
        monkeypatch.setattr(cli, "_open_in_browser", lambda link: None)
        monkeypatch.setattr(http.server.HTTPServer, "serve_forever", stop)
        assert cli.cmd_serve(serve_args(tmp_path, port)) == 0
        assert seen["port"] != port and seen["key"] is not None
        assert seen["key"] != running.key  # its own key, never the running screen's
        assert f"Port {port} is used by" in capsys.readouterr().out
    finally:
        running.server_close()
