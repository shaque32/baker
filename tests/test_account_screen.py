"""Sign-in on the screen: hidden while off, the Account page, the browser hand-back to
/signin/done without the screen key, and the one thing a license controls (starting an audit).
Against a fake license server; nothing connects."""

from __future__ import annotations

import http.client
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import account
from account import license as lic
from account.session import SignIn
from tests.test_account import KEYS, NOW, make
from ui.app import App, Request
from ui.server import make_server

PORT = 8765
HOST = {"host": f"127.0.0.1:{PORT}"}


class FakeServer:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.exchanged: list[tuple[str, str]] = []
        self.renewed = 0
        self.signed_out = 0

    def exchange(self, code: str, verifier: str) -> lic.Stored:
        if self.fail:
            raise self.fail
        self.exchanged.append((code, verifier))
        return lic.Stored(make(), "tok_" + "x" * 30)

    def renew(self, stored: lic.Stored) -> lic.Stored:
        self.renewed += 1
        if self.fail:
            raise self.fail
        return lic.Stored(make(issued=NOW + timedelta(days=2)), stored.token)

    def sign_out(self, stored: lic.Stored) -> None:
        self.signed_out += 1
        if self.fail:
            raise self.fail


class Browser:
    def __init__(self, opens: bool = True) -> None:
        self.opens = opens
        self.urls: list[str] = []

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        return self.opens

    def state(self) -> str:
        return parse_qs(urlsplit(self.urls[-1]).query)["state"][0]


def signin(
    tmp_path: Path, server: FakeServer | None = None, browser: Browser | None = None, **kw: object
) -> SignIn:
    return SignIn(
        PORT,
        "0.0.1",
        server or FakeServer(),
        browser or Browser(),
        home=tmp_path,
        keys=KEYS,
        clock=kw.pop("clock", lambda: NOW),  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(account, "SIGNIN_ON", True)


def get(app: App, path: str, **query: str):  # noqa: ANN201
    return app.handle(Request("GET", path, dict(query), dict(HOST)))


def post(app: App, path: str, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def screen(tmp_path: Path, s: SignIn | None) -> App:
    app = App(home=tmp_path / "cases", port=PORT, model_check=None)
    app.signin = s
    return app


# -- off


def test_while_off_there_is_no_account_page_and_audits_start_as_before(tmp_path):
    s = signin(tmp_path)
    app = screen(tmp_path, s)
    assert get(app, "/account").status == 404
    assert post(app, "/signin/start").status == 404
    assert "href='/account'" not in get(app, "/cases").body.decode()
    assert s.may_start_audit() == (True, "")
    assert not lic.account_dir(tmp_path).exists()  # nothing read, nothing written


def test_serve_builds_no_sign_in_while_off(monkeypatch, tmp_path):
    import cli.main as cli

    made: list[object] = []
    real = cli._signin_for
    monkeypatch.setattr(cli, "_signin_for", lambda port: made.append(port) or real(port))
    server = make_server(None, 0, "Test Expert", home=tmp_path)
    try:
        assert server.app.signin is None  # type: ignore[attr-defined]
    finally:
        server.server_close()
    assert made == []


# -- on


def test_account_page_signs_in_through_the_browser(tmp_path, on):
    browser = Browser()
    fake = FakeServer()
    s = signin(tmp_path, fake, browser)
    app = screen(tmp_path, s)
    page = get(app, "/account").body.decode()
    assert "Not signed in." in page and "Nothing from any case is ever sent" in page
    assert "href='/account'" in page  # the header links it
    r = post(app, "/signin/start")
    assert r.status == 303 and r.header("Location") == "/account"
    assert browser.urls[0].startswith(f"https://{account.ACCOUNT_HOST}/signin?")
    assert "Your browser opened" in get(app, "/account").body.decode()
    ok, message = s.finish("code_abc", browser.state())
    assert ok and message == "Signed in as expert@example.com. Go back to Mabillon."
    assert fake.exchanged[0][0] == "code_abc"
    assert "Signed in as expert@example.com" in get(app, "/account").body.decode()
    assert s.finish("code_abc", browser.state()) == (
        False,
        "This sign-in is out of date or was already used. Start again in Mabillon.",
    )
    post(app, "/signout")
    assert fake.signed_out == 1 and lic.load(tmp_path) is None
    assert "Signed out on this computer." in get(app, "/account").body.decode()


def test_a_browser_that_does_not_open_leaves_nothing_waiting(tmp_path, on):
    browser = Browser(opens=False)
    s = signin(tmp_path, browser=browser)
    assert "could not open your browser" in s.start()
    assert s.finish("code", browser.state())[0] is False


def test_a_failed_exchange_saves_nothing(tmp_path, on):
    browser = Browser()
    s = signin(tmp_path, FakeServer(fail=RuntimeError("This sign-in link was already used.")),
               browser)  # fmt: skip
    s.start()
    ok, message = s.finish("code", browser.state())
    assert not ok and "already used" in message
    assert lic.load(tmp_path) is None


def test_a_license_holds_back_only_new_audits(tmp_path, on):
    s = signin(tmp_path)
    allowed, why = s.may_start_audit()
    assert not allowed and "Sign in on the Account page" in why and lic.ALWAYS in why
    app = screen(tmp_path, s)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Synthetic license case")
    assert app.case is not None  # making and opening a case needs no license
    post(app, "/audit/start")
    assert "Sign in on the Account page to start a new audit" in get(app, "/setup").body.decode()
    lic.save(lic.Stored(make(), "t" * 30), tmp_path)
    assert s.may_start_audit() == (True, "")


def test_renewal_when_due_once_an_hour_and_offline_is_fine(tmp_path, on):
    fake = FakeServer(fail=OSError("offline"))
    clock = [NOW + timedelta(days=2)]
    tick = [0.0]
    s = signin(tmp_path, fake, clock=lambda: clock[0], monotonic=lambda: tick[0])
    lic.save(lic.Stored(make(), "t" * 30), tmp_path)
    assert "not renewed" in (s.renew_if_due() or "")
    assert s.renew_if_due() is None and fake.renewed == 1  # not again within the hour
    assert s.may_start_audit() == (True, "")  # inside the 30 days
    tick[0] += 3601
    fake.fail = None
    assert s.renew_if_due() is None and fake.renewed == 2
    stored = lic.load(tmp_path)
    assert stored is not None
    assert lic.verify(stored.signed, KEYS).issued_at == NOW + timedelta(days=2)


def test_a_renewal_never_brings_back_a_license_signed_out_meanwhile(tmp_path, on):
    """`mabillon license sign-out` (another process) clears the license while the screen's
    renewal is on the network: the renewal is dropped, not written back."""

    class SignedOutMeanwhile(FakeServer):
        def renew(self, stored: lic.Stored) -> lic.Stored:
            lic.clear(tmp_path)
            return super().renew(stored)

    s = signin(tmp_path, SignedOutMeanwhile(), clock=lambda: NOW + timedelta(days=2))
    lic.save(lic.Stored(make(), "t" * 30), tmp_path)
    assert s.renew_if_due() is None
    assert lic.load(tmp_path) is None


def test_a_renewal_that_cannot_be_saved_keeps_the_license_here(tmp_path, on, monkeypatch):
    s = signin(tmp_path, clock=lambda: NOW + timedelta(days=2))
    lic.save(lic.Stored(make(), "t" * 30), tmp_path)

    def read_only(*a: object, **k: object) -> bool:
        raise PermissionError("read-only folder")

    monkeypatch.setattr(lic, "replace_if_unchanged", read_only)
    assert "could not be saved" in (s.renew_if_due() or "")
    assert s.may_start_audit() == (True, "")  # the saved license is still inside its grace


def test_sign_out_offline_still_signs_out_here(tmp_path, on):
    s = signin(tmp_path, FakeServer(fail=OSError("offline")))
    lic.save(lic.Stored(make(), "t" * 30), tmp_path)
    assert "not reached, but this computer is signed out" in s.sign_out()
    assert lic.load(tmp_path) is None


def test_a_license_file_is_used_without_a_connection(tmp_path, on):
    import json

    s = signin(tmp_path, FakeServer(fail=AssertionError("no connection")))
    data = json.dumps(make(offline=True).to_json()).encode()
    assert "from a license file" in s.use_license_file(data)
    assert s.may_start_audit() == (True, "")


# -- the hand-back over HTTP, without the screen key


def _http_get(port: int, path: str, headers: dict[str, str] | None = None):  # noqa: ANN202
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers=headers or {})
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read().decode()


def _serve(server, n: int) -> threading.Thread:  # noqa: ANN001
    def run() -> None:
        for _ in range(n):
            server.handle_request()

    t = threading.Thread(target=run)
    t.start()
    return t


def test_the_browser_hand_back_needs_no_screen_key_but_only_its_own_state(tmp_path, on):
    browser = Browser()
    fake = FakeServer()
    made: list[SignIn] = []

    def build(port: int) -> SignIn:
        s = SignIn(port, "0.0.1", fake, browser, home=tmp_path, keys=KEYS, clock=lambda: NOW)
        made.append(s)
        return s

    server = make_server(None, 0, "Test Expert", home=tmp_path / "cases", signin_for=build)
    port = server.server_address[1]
    try:
        made[0].start()
        assert parse_qs(urlsplit(browser.urls[0]).query)["return"] == [
            f"http://127.0.0.1:{port}/signin/done"
        ]
        t = _serve(server, 4)
        status, _, body = _http_get(port, "/signin/done?code=c1&state=guess")
        assert status == 400 and "out of date" in body and fake.exchanged == []
        status, _, _ = _http_get(port, "/account")  # every other page still needs the key
        assert status == 403
        status, headers, body = _http_get(port, f"/signin/done?code=c1&state={browser.state()}")
        assert status == 200 and "Signed in as expert@example.com" in body
        assert headers["Referrer-Policy"] == "no-referrer"
        assert "token" not in body and "Synthetic" not in body
        status, _, body = _http_get(port, f"/signin/done?code=c1&state={browser.state()}")
        assert status == 400  # once
        t.join(10)
        assert fake.exchanged == [("c1", fake.exchanged[0][1])]
    finally:
        server.server_close()


def test_the_hand_back_is_not_there_while_off(tmp_path):
    server = make_server(
        None, 0, "Test Expert", home=tmp_path / "cases", signin_for=lambda p: signin(tmp_path)
    )
    port = server.server_address[1]
    try:
        t = _serve(server, 1)
        status, _, _ = _http_get(port, "/signin/done?code=c&state=s")
        t.join(10)
        assert status == 404
    finally:
        server.server_close()


def test_the_hand_back_needs_this_screens_host(tmp_path, on):
    server = make_server(
        None, 0, "Test Expert", home=tmp_path / "cases", signin_for=lambda p: signin(tmp_path)
    )
    port = server.server_address[1]
    try:
        t = _serve(server, 1)
        status, _, _ = _http_get(port, "/signin/done?code=c&state=s", {"Host": "evil.example"})
        t.join(10)
        assert status == 400
    finally:
        server.server_close()


def test_status_dates_are_utc(tmp_path):
    late = datetime(2026, 11, 6, 23, 30, tzinfo=UTC)
    s = lic.status(lic.Stored(make(issued=late)), late, KEYS)
    assert "6 November 2027" in s.message


def test_a_command_line_audit_needs_a_license_too(tmp_path, on, monkeypatch, capsys):
    from cli import main as cli_main

    s = signin(tmp_path)
    monkeypatch.setattr(cli_main, "_signin_for", lambda port: s)
    opened: list[object] = []
    monkeypatch.setattr(cli_main, "_open", lambda db: opened.append(db))
    args = cli_main.parser().parse_args(["audit", "--db", str(tmp_path / "case.db"), "--fake"])
    assert cli_main.cmd_audit(args) == 2
    assert "Sign in" in capsys.readouterr().err
    assert opened == []  # refused before the case is even opened
    lic.save(lic.Stored(make(), "t" * 30), tmp_path)
    assert cli_main._license_allows_audit()
