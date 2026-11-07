"""The plan C model server's gateway and first-boot checks (deploy/model_server/), with no
engine and no network: a stand-in answers every forwarded request. Synthetic data only."""

from __future__ import annotations

import http.client
import importlib.util
import io
import json
import shutil
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path
from types import ModuleType

import pytest

HERE = Path(__file__).resolve().parents[1] / "deploy" / "model_server"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"model_server_{name}", HERE / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gw = _load("gateway")
fb = _load("firstboot")
PINS = json.loads((HERE / "pins.json").read_text(encoding="utf-8"))
TOKEN = "t0ken-for-tests"


def _ready_state(tmp_path: Path) -> Path:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "revision": PINS["model"]["revision"],
        "manifest_sha256": "ab" * 32,
        "engine_version": PINS["engine"]["version"],
        "smoke_identical": True,
    }))  # fmt: skip
    return state


def _body(**over: object) -> bytes:
    body = {
        "model": PINS["model"]["served_name"],
        "messages": [{"role": "user", "content": "synthetic"}],
        "temperature": 0,
        "seed": PINS["serve"]["seed"],
        "max_tokens": 1000,
    }
    body.update(over)
    return json.dumps(body).encode()


def _gateway(tmp_path: Path, forward=None) -> object:  # noqa: ANN001
    tokens = tmp_path / "tokens"
    tokens.write_text(f"# one per customer\n{TOKEN}\n")
    return gw.Gateway(
        PINS,
        _ready_state(tmp_path),
        gw.load_tokens(tokens),
        "http://127.0.0.1:1",
        forward=forward or (lambda body: (200, json.dumps({"echo": body}).encode())),
    )


def test_every_model_pin_is_exact():
    assert len(PINS["model"]["revision"]) == 40
    assert PINS["model"]["repo"] == "deepseek-ai/DeepSeek-V4.1-Flash-1017"
    assert PINS["engine"]["version"].count(".") == 2
    assert PINS["serve"]["max_num_seqs"] == 1


def test_no_token_or_a_wrong_token_gets_nothing(tmp_path):
    g = _gateway(tmp_path)
    for auth in (None, "Bearer wrong", TOKEN, f"Basic {TOKEN}"):
        with pytest.raises(gw.Refused) as e:
            g.complete(auth, _body())
        assert e.value.status == 401


def test_only_the_validated_settings_are_forwarded(tmp_path):
    g = _gateway(tmp_path)
    status, raw = g.complete(f"Bearer {TOKEN}", _body())
    sent = json.loads(raw)["echo"]
    assert status == 200 and sent["n"] == 1 and sent["stream"] is False
    assert sent["model"] == PINS["model"]["served_name"]
    bad = [
        {"temperature": 0.7}, {"seed": 1}, {"n": 2}, {"stream": True}, {"top_p": 0.9},
        {"max_tokens": PINS["serve"]["max_tokens"] + 1}, {"model": "other/model"},
        {"logprobs": True}, {"messages": []},
    ]  # fmt: skip
    for over in bad:
        with pytest.raises(gw.Refused) as e:
            g.complete(f"Bearer {TOKEN}", _body(**over))
        assert e.value.status == 400, over


def test_nothing_is_served_until_the_first_boot_checks_pass(tmp_path):
    g = _gateway(tmp_path)
    for broken in (
        {"manifest_sha256": None},
        {"engine_version": "0.0.1"},
        {"smoke_identical": False},
        {"revision": "0" * 40},
    ):
        st = json.loads(g.state_path.read_text())
        st.update(broken)
        g.state_path.write_text(json.dumps(st))
        assert g.health()["ready"] is False
        with pytest.raises(gw.Refused) as e:
            g.complete(f"Bearer {TOKEN}", _body())
        assert e.value.status == 503
        _ready_state(tmp_path)
    assert g.health()["ready"] is True and g.health()["keeps_bodies"] is False


def test_requests_reach_the_engine_one_at_a_time(tmp_path):
    inside, most = [0], [0]
    lock = threading.Lock()

    def slow(body):  # noqa: ANN001, ANN202
        with lock:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        with lock:
            inside[0] -= 1
        return 200, b"{}"

    g = _gateway(tmp_path, forward=slow)
    threads = [
        threading.Thread(target=g.complete, args=(f"Bearer {TOKEN}", _body())) for _ in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert most[0] == 1


def _post(g, raw: bytes, auth: str | None, rfile=None, log=None):  # noqa: ANN001, ANN202
    handler = gw.make_handler(g, log=log if log is not None else io.StringIO())

    class Fake(handler):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            self.command, self.path = "POST", gw.COMPLETIONS
            self.headers = {"Content-Length": str(len(raw))}
            if auth:
                self.headers["Authorization"] = auth
            self.rfile, self.wfile = rfile or io.BytesIO(raw), io.BytesIO()
            self.request_version, self.requestline = "HTTP/1.1", "POST"
            self.close_connection = True

        def send_response(self, code, message=None):  # noqa: ANN001, ANN202
            self.code = code

        def send_header(self, k, v):  # noqa: ANN001, ANN202
            pass

        def end_headers(self):  # noqa: ANN202
            pass

    f = Fake()
    f.do_POST()
    return f


def test_the_log_never_holds_a_prompt_or_an_answer(tmp_path):
    secret = "SYNTHETIC-PROMPT-TEXT-123"
    g = _gateway(tmp_path, forward=lambda body: (200, b'{"answer": "SYNTHETIC-ANSWER-456"}'))
    log = io.StringIO()
    raw = _body(messages=[{"role": "user", "content": secret}])
    f = _post(g, raw, f"Bearer {TOKEN}", log=log)
    assert f.code == 200 and b"SYNTHETIC-ANSWER-456" in f.wfile.getvalue()
    assert secret not in log.getvalue() and "SYNTHETIC-ANSWER" not in log.getvalue()
    assert log.getvalue().startswith("POST /v1/chat/completions 200")


def test_without_a_token_the_body_is_never_read(tmp_path):
    class NeverRead(io.BytesIO):
        def read(self, *a):  # noqa: ANN002, ANN202
            raise AssertionError("the body was read before the token check")

    g = _gateway(tmp_path)
    for auth in (None, "Bearer wrong"):
        assert _post(g, _body(), auth, rfile=NeverRead()).code == 401


def test_a_body_shorter_than_its_length_is_refused(tmp_path):
    g = _gateway(tmp_path)
    raw = _body()
    assert _post(g, raw, f"Bearer {TOKEN}", rfile=io.BytesIO(raw[:-5])).code == 400


def test_a_pinned_manifest_must_match_the_recorded_one(tmp_path):
    g = _gateway(tmp_path)  # state.json records "ab" * 32
    g.pins = {**PINS, "model": {**PINS["model"], "manifest_sha256": "cd" * 32}}
    assert g.health()["ready"] is False
    with pytest.raises(gw.Refused) as e:
        g.complete(f"Bearer {TOKEN}", _body())
    assert e.value.status == 503
    g.pins = {**PINS, "model": {**PINS["model"], "manifest_sha256": "ab" * 32}}
    assert g.health()["ready"] is True


def _tls_server(tmp_path: Path, max_connections: int):  # noqa: ANN202
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl not installed")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(  # noqa: S603
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert)],
        check=True, capture_output=True,
    )  # fmt: skip
    server = gw.TLSServer(
        ("127.0.0.1", 0), gw.make_handler(_gateway(tmp_path)), gw.tls_context(cert, key),
        max_connections=max_connections, io_timeout=5.0,
    )  # fmt: skip
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _health(port: int) -> int:
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE  # self-signed test certificate
    conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=3, context=ctx)
    try:
        conn.request("GET", "/health")
        return conn.getresponse().status
    finally:
        conn.close()


def test_a_silent_client_does_not_block_the_next_one(tmp_path):
    server = _tls_server(tmp_path, max_connections=4)
    port = server.server_address[1]
    try:
        with socket.create_connection(("127.0.0.1", port)):  # opens TCP, never says hello
            assert _health(port) == 200
    finally:
        server.shutdown()
        server.server_close()


def test_connections_over_the_cap_are_closed(tmp_path):
    server = _tls_server(tmp_path, max_connections=1)
    port = server.server_address[1]
    try:
        with socket.create_connection(("127.0.0.1", port)):  # holds the only slot
            time.sleep(0.2)
            with pytest.raises((ssl.SSLError, OSError, http.client.HTTPException)):
                _health(port)
        for _ in range(30):  # the slot comes back once the silent client leaves
            time.sleep(0.1)
            try:
                assert _health(port) == 200
                break
            except (ssl.SSLError, OSError, http.client.HTTPException):
                continue
        else:
            pytest.fail("the slot never came back")
    finally:
        server.shutdown()
        server.server_close()


def test_the_manifest_hashes_every_weights_file(tmp_path):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "a.safetensors").write_bytes(b"one")
    (tmp_path / "w" / "config.json").write_text("{}")
    (tmp_path / "w" / ".cache").mkdir()
    (tmp_path / "w" / ".cache" / "x").write_text("ignored")
    files = fb.manifest(tmp_path / "w")
    assert sorted(files) == ["a.safetensors", "config.json"]
    before = fb.manifest_sha256(files)
    (tmp_path / "w" / "a.safetensors").write_bytes(b"two")
    assert fb.manifest_sha256(fb.manifest(tmp_path / "w")) != before


def _answer(text: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": text}}]}).encode()


def test_first_boot_passes_only_on_identical_repeats_and_the_pinned_manifest(tmp_path):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "a.safetensors").write_bytes(b"one")
    pinned = lambda name: PINS["engine"]["version"]  # noqa: E731
    same = fb.run(PINS, tmp_path / "w", lambda body: _answer("x"), pinned, lambda: "8 x H200")
    assert same["smoke_identical"] and same["manifest_sha256"] and same["gpu"] == "8 x H200"
    turns = iter(["x", "y"])
    differ = fb.run(PINS, tmp_path / "w", lambda body: _answer(next(turns)), pinned, lambda: None)
    assert differ["smoke_identical"] is False
    other = {**PINS, "model": {**PINS["model"], "manifest_sha256": "0" * 64}}
    wrong = fb.run(other, tmp_path / "w", lambda body: _answer("x"), pinned, lambda: None)
    assert wrong["manifest_sha256"] is None and "not the pinned" in wrong["problem"]


def test_the_smoke_prompt_is_synthetic_and_uses_the_pinned_settings():
    body = fb.smoke_body(PINS)
    assert body["temperature"] == 0 and body["seed"] == PINS["serve"]["seed"]
    assert "Boston" in body["messages"][0]["content"]
    gw.check_request(body, PINS)  # the gateway would accept exactly this shape


def test_the_launch_script_parses():
    bash = shutil.which("bash")
    assert bash
    subprocess.run([bash, "-n", str(HERE / "launch.sh")], check=True)  # noqa: S603


def test_the_engine_must_be_on_this_machine(tmp_path):
    with pytest.raises(SystemExit):
        gw.local_upstream("http://10.0.0.5:8001")
    assert gw.local_upstream("http://127.0.0.1:8001/") == "http://127.0.0.1:8001"
