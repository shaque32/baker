"""Sign-in: the license check on this computer, the browser hand-back's one-use values, and the
one network client (account/client.py), against a fake license server. Nothing here connects."""

from __future__ import annotations

import ast
import base64
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import account
from account import client as acc_client
from account import flow
from account import license as lic

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
PRIVATE = Ed25519PrivateKey.generate()
KEYS = {
    "test1": PRIVATE.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
}


def make(
    issued: datetime = NOW,
    expires: datetime | None = None,
    offline: bool = False,
    key: Ed25519PrivateKey = PRIVATE,
    **over: object,
) -> lic.Signed:
    body = {
        "v": 1,
        "aud": "mabillon",
        "kid": "test1",
        "id": "lic_abcdefgh1234",
        "email": "expert@example.com",
        "plan": "pilot",
        "issued_at": issued.isoformat(),
        "expires": (expires or issued + timedelta(days=365)).isoformat(),
        "offline": offline,
        **over,
    }
    text = json.dumps(body)
    sig = base64.urlsafe_b64encode(key.sign(text.encode())).rstrip(b"=").decode()
    return lic.Signed(text, sig)


# -- off by default


def test_sign_in_is_off_and_no_key_is_trusted_yet():
    """Pilots get no login: sign-in stays off until it is turned on in its own PR, and no
    license verifies until the license server's key is made."""
    assert account.SIGNIN_ON is False
    assert lic.SIGNING_KEYS == {}
    with pytest.raises(lic.BadLicense):
        lic.verify(make())


# -- the license


def test_a_signed_license_verifies():
    got = lic.verify(make(), KEYS)
    assert got.email == "expert@example.com" and got.id == "lic_abcdefgh1234"
    assert got.renew_by == NOW + lic.GRACE


def test_an_edited_license_or_another_key_is_refused():
    good = make()
    edited = lic.Signed(good.text.replace("pilot", "firm"), good.signature)
    with pytest.raises(lic.BadLicense, match="signature"):
        lic.verify(edited, KEYS)
    with pytest.raises(lic.BadLicense, match="signature"):
        lic.verify(make(key=Ed25519PrivateKey.generate()), KEYS)
    with pytest.raises(lic.BadLicense, match="key this Mabillon knows"):
        lic.verify(make(kid="other"), KEYS)
    with pytest.raises(lic.BadLicense):
        lic.verify(lic.Signed(good.text, "!!!"), KEYS)
    with pytest.raises(lic.BadLicense):
        lic.verify(lic.Signed("not json", good.signature), KEYS)


@pytest.mark.parametrize(
    "over",
    [
        {"aud": "other"},
        {"v": 2},
        {"id": "x"},
        {"email": "nobody"},
        {"extra": "field"},
        {"issued_at": "2026-11-06T12:00:00"},  # no offset
    ],
)
def test_a_signed_license_with_a_wrong_field_is_refused(over):
    with pytest.raises(lic.BadLicense):
        lic.verify(make(**over), KEYS)


def test_a_license_that_ends_before_it_starts_is_refused():
    with pytest.raises(lic.BadLicense, match="ends before"):
        lic.verify(make(expires=NOW - timedelta(days=1)), KEYS)


def stored(signed: lic.Signed | None = None, token: str | None = "t" * 32) -> lic.Stored:
    return lic.Stored(signed or make(), token)


def test_status_through_the_life_of_a_license():
    s = stored()
    assert lic.status(None, NOW, KEYS).state == "signed_out"
    assert lic.status(s, NOW, KEYS).state == "active"
    assert lic.status(s, NOW, KEYS).may_start_audit
    day2 = lic.status(s, NOW + timedelta(days=2), KEYS)
    assert day2.state == "renew_due" and day2.may_start_audit and day2.wants_renewal
    lapsed = lic.status(s, NOW + lic.GRACE, KEYS)
    assert lapsed.state == "lapsed" and not lapsed.may_start_audit and lapsed.wants_renewal
    assert "still work" in lapsed.message
    short = stored(make(expires=NOW + timedelta(days=5)))
    ended = lic.status(short, NOW + timedelta(days=5), KEYS)
    assert ended.state == "expired" and not ended.may_start_audit
    assert "ended on 11 November 2026" in ended.message and "still work" in ended.message
    bad = lic.status(stored(lic.Signed("", "")), NOW, KEYS)
    assert bad.state == "invalid" and not bad.may_start_audit


def test_a_license_file_needs_no_renewal_until_it_expires():
    s = lic.Stored(make(offline=True, expires=NOW + timedelta(days=200)))
    later = lic.status(s, NOW + timedelta(days=100), KEYS)
    assert later.state == "active" and "license file" in later.message
    assert lic.status(s, NOW + timedelta(days=200), KEYS).state == "expired"


def test_license_saved_for_this_account_only_and_loaded_back(tmp_path):
    s = stored()
    path = lic.save(s, tmp_path)
    assert lic.load(tmp_path) == s
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    lic.save(lic.Stored(s.signed), tmp_path)  # replaced in one step
    assert lic.load(tmp_path) == lic.Stored(s.signed)
    assert not path.with_suffix(".tmp").exists()
    lic.clear(tmp_path)
    assert lic.load(tmp_path) is None
    lic.clear(tmp_path)  # twice is fine


def test_a_damaged_license_file_reads_as_invalid_not_signed_out(tmp_path):
    lic.license_file(tmp_path).parent.mkdir(parents=True)
    lic.license_file(tmp_path).write_text("{oops", encoding="utf-8")
    assert lic.status(lic.load(tmp_path), NOW, KEYS).state == "invalid"
    lic.license_file(tmp_path).write_text('{"license": 3}', encoding="utf-8")
    assert lic.status(lic.load(tmp_path), NOW, KEYS).state == "invalid"


def test_license_file_import_takes_only_an_offline_license():
    data = json.dumps(make(offline=True).to_json()).encode()
    assert lic.read_license_file(data, KEYS).token is None
    with pytest.raises(lic.BadLicense, match="for sign-in"):
        lic.read_license_file(json.dumps(make().to_json()).encode(), KEYS)
    for junk in (b"\xff\xfe", b"[]", b"x" * 20000, b'{"license": "a"}'):
        with pytest.raises(lic.BadLicense):
            lic.read_license_file(junk, KEYS)


# -- the browser hand-back


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_sign_in_address_carries_only_the_one_use_values():
    f = flow.SignInFlow(8765, Clock())
    url = f.start("0.0.1")
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == ("https", account.ACCOUNT_HOST, "/signin")
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert set(q) == {"state", "challenge", "challenge_method", "return", "v"}
    assert q["return"] == "http://127.0.0.1:8765/signin/done"
    assert q["challenge_method"] == "S256"
    pending = f.take(q["state"])
    assert pending is not None and flow.challenge_for(pending.verifier) == q["challenge"]
    assert pending.verifier not in url


def test_rfc7636_challenge_example():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert flow.challenge_for(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_a_hand_back_is_taken_once_for_its_own_state_within_ten_minutes():
    clock = Clock()
    f = flow.SignInFlow(8765, clock)
    state = parse_qs(urlsplit(f.start("v")).query)["state"][0]
    assert not f.waiting_for(None) and not f.waiting_for("guess")
    assert f.take("guess") is None and f.waiting_for(state)  # a wrong state uses nothing up
    assert f.take(state) is not None
    assert f.take(state) is None  # once
    state = parse_qs(urlsplit(f.start("v")).query)["state"][0]
    clock.t += flow.WAIT_SECONDS + 1
    assert f.take(state) is None  # too late
    first = parse_qs(urlsplit(f.start("v")).query)["state"][0]
    second = parse_qs(urlsplit(f.start("v")).query)["state"][0]
    assert f.take(first) is None and f.take(second) is not None  # starting again replaces
    state = parse_qs(urlsplit(f.start("v")).query)["state"][0]
    f.cancel()
    assert f.take(state) is None


# -- the client, against a fake server


class Answer:
    def __init__(self, status: int, body: object) -> None:
        self.status = status
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self, n: int = -1) -> bytes:
        return self._raw[:n] if n >= 0 else self._raw

    def __enter__(self) -> Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeServer:
    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.sent: list[tuple[str, dict, dict]] = []

    def __call__(self, req: urllib.request.Request, timeout: float) -> Answer:
        assert timeout == acc_client.TIMEOUT
        self.sent.append((req.full_url, json.loads(req.data), dict(req.header_items())))
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a  # type: ignore[return-value]


def issued(token: str | None = "tok_" + "x" * 30, **kw: object) -> dict:
    body: dict = make(**kw).to_json()
    if token is not None:
        body["token"] = token
    return body


def client(tmp_path: Path, server: FakeServer) -> acc_client.Client:
    return acc_client.Client("0.0.1", home=tmp_path, keys=KEYS, send=server)


def log_lines(tmp_path: Path) -> list[dict]:
    text = acc_client.log_file(tmp_path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_exchange_sends_only_the_code_verifier_and_version_and_logs_first(tmp_path):
    server = FakeServer(Answer(200, issued()))
    got = client(tmp_path, server).exchange("code_123456789", "verifier_abcdefgh")
    assert got.token == "tok_" + "x" * 30
    url, body, headers = server.sent[0]
    assert url == "https://account.getmabillon.com/api/token"
    assert body == {"code": "code_123456789", "verifier": "verifier_abcdefgh", "v": "0.0.1"}
    assert headers["User-agent"] == "Mabillon/0.0.1"
    lines = log_lines(tmp_path)
    assert lines[0]["send"] == url
    assert lines[0]["fields"] == {"code": "code_1…", "verifier": "verifi…", "v": "0.0.1"}
    assert lines[1] == {"at": lines[1]["at"], "answer": url, "status": 200}
    assert "verifier_abcdefgh" not in acc_client.log_file(tmp_path).read_text(encoding="utf-8")


def test_the_request_is_not_sent_when_it_cannot_be_logged(tmp_path, monkeypatch):
    server = FakeServer(Answer(200, issued()))
    c = client(tmp_path, server)

    def no_log(entry: dict) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(c, "_log", no_log)
    with pytest.raises(OSError):
        c.exchange("code_123456789", "verifier")
    assert server.sent == []


def test_exchange_refuses_an_answer_that_does_not_check(tmp_path):
    bad = issued(key=Ed25519PrivateKey.generate())
    with pytest.raises(acc_client.AccountError, match="does not check"):
        client(tmp_path, FakeServer(Answer(200, bad))).exchange("c", "v")
    with pytest.raises(acc_client.AccountError, match="no sign-in token"):
        client(tmp_path, FakeServer(Answer(200, issued(token=None)))).exchange("c", "v")
    with pytest.raises(acc_client.AccountError):
        client(tmp_path, FakeServer(Answer(200, b"[1]"))).exchange("c", "v")


def test_a_refusal_carries_the_servers_message(tmp_path):
    refused = Answer(400, {"error": "used", "message": "This sign-in link was already used."})
    server = FakeServer(urllib.error.HTTPError("u", 400, "x", {}, io.BytesIO(refused.read())))
    with pytest.raises(acc_client.AccountError, match="already used") as err:
        client(tmp_path, server).exchange("c", "v")
    assert err.value.code == "used" and err.value.reachable


def test_offline_is_reported_as_unreachable(tmp_path):
    server = FakeServer(urllib.error.URLError("no route"))
    with pytest.raises(acc_client.AccountError, match="Could not reach") as err:
        client(tmp_path, server).exchange("c", "v")
    assert not err.value.reachable
    assert log_lines(tmp_path)[-1]["failed"] == "URLError"


def test_renew_sends_the_license_id_token_and_version_only(tmp_path):
    old = lic.Stored(make(), "tok_" + "y" * 30)
    newer = issued(token=None, issued=NOW + timedelta(days=3))
    server = FakeServer(Answer(200, newer))
    got = client(tmp_path, server).renew(old)
    assert got.token == old.token
    assert lic.verify(got.signed, KEYS).issued_at == NOW + timedelta(days=3)
    url, body, _ = server.sent[0]
    assert url.endswith("/api/renew")
    assert body == {"license_id": "lic_abcdefgh1234", "token": old.token, "v": "0.0.1"}


def test_renew_refuses_a_different_license(tmp_path):
    other = issued(token=None, id="lic_zzzzzzzz9999")
    with pytest.raises(acc_client.AccountError, match="different license"):
        client(tmp_path, FakeServer(Answer(200, other))).renew(lic.Stored(make(), "t" * 30))


def test_sign_out_sends_the_id_and_token_and_skips_a_license_file(tmp_path):
    server = FakeServer(Answer(204, b""))
    client(tmp_path, server).sign_out(lic.Stored(make(), "t" * 30))
    assert server.sent[0][1] == {"license_id": "lic_abcdefgh1234", "token": "t" * 30}
    quiet = FakeServer()
    client(tmp_path, quiet).sign_out(lic.Stored(make(offline=True)))
    assert quiet.sent == []


# -- where the network is


NETWORK_MODULES = {"socket", "ssl", "urllib.request", "urllib.error", "http.client", "requests",
                   "httpx", "aiohttp", "ftplib", "smtplib", "webbrowser"}  # fmt: skip


def _imports(py: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_only_the_account_client_connects():
    """account/client.py is the only file in account/ with a network client, and no file in
    core/ or ui/ imports it: the screen gets the client handed to it by cli/main.py."""
    for py in (ROOT / "account").rglob("*.py"):
        found = _imports(py) & NETWORK_MODULES
        if py.name == "client.py":
            assert found <= {"urllib.request", "urllib.error"}, found
        else:
            assert not found, f"{py}: {found}"
    for py in (ROOT / "ui").rglob("*.py"):
        assert "account.client" not in _imports(py), py
    for py in (ROOT / "core").rglob("*.py"):
        assert not {n for n in _imports(py) if n.split(".")[0] == "account"}, py


# -- the license server (workers/license/), when Node is here


def _node() -> str | None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        return None
    out = subprocess.run([node, "--version"], capture_output=True, text=True, check=False)  # noqa: S603
    major = out.stdout.strip().lstrip("v").split(".")[0]
    return node if major.isdigit() and int(major) >= 22 else None


NODE = _node()
needs_node = pytest.mark.skipif(NODE is None, reason="Node 22 or later is not installed")


@needs_node
def test_license_server_tests_pass():
    import subprocess

    out = subprocess.run(  # noqa: S603
        [NODE, "--no-warnings", str(ROOT / "workers/license/test.mjs")],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr + out.stdout
    assert "all tests passed" in out.stdout


@needs_node
def test_a_license_the_server_signs_verifies_in_the_app():
    """The Worker's signLicense and the app's verify agree on the bytes, the key format and the
    date format."""
    import subprocess

    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes_raw()
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    jwk = {"kty": "OKP", "crv": "Ed25519", "d": b64(raw), "x": b64(pub)}
    script = (
        "import { signLicense } from "
        + json.dumps((ROOT / "workers/license/src/index.js").as_uri())
        + ";\nconst env = { KEY_ID: 'k9', SIGNING_KEY_JWK: process.env.JWK };\n"
        "const lic = { id: 'lic_abcdefgh1234', email: 'expert@lab.example', plan: 'pilot', "
        "paid_through: '2027-11-06T00:00:00.000Z' };\n"
        "const now = new Date('2026-11-06T12:00:00Z');\n"
        "console.log(JSON.stringify(await signLicense(env, lic, now)));"
    )
    out = subprocess.run(  # noqa: S603
        [NODE, "--no-warnings", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={**__import__("os").environ, "JWK": json.dumps(jwk)},
    )
    assert out.returncode == 0, out.stderr
    signed = lic.Signed.from_json(json.loads(out.stdout))
    got = lic.verify(signed, {"k9": pub.hex()})
    assert got.email == "expert@lab.example" and got.issued_at == NOW
    assert got.expires == datetime(2027, 11, 6, tzinfo=UTC)
    assert lic.status(lic.Stored(signed, "t" * 30), NOW, {"k9": pub.hex()}).state == "active"
