"""Mabillon model server gateway (plan C): the only door to the self-hosted open-weight model.

Runs on the GPU machine in front of the inference engine, which listens on 127.0.0.1 only. It
is not part of the app: nothing in core/ imports it, and core/ makes no call to it until Arsh
signs the CLAUDE.md network change (plans/claude-md-plan-c-diff.md).

What it enforces, so every answer is repeatable and nothing about a case is kept:
- A bearer token (one per customer), compared in constant time. No token, no answer.
- One request at a time (a lock around the engine call): the engine never batches two prompts.
- Only the settings the validated stack uses: temperature 0, the pinned seed, one choice, no
  streaming, the pinned model name, and a token cap no higher than the pin.
- No request or answer body is ever logged or written to disk. The log line is method, path,
  status and seconds.
- /health reports the pinned model repository, revision, the SHA-256 of the weights manifest
  and the engine version, so the app can refuse a server that does not run the pinned stack.
  A reported hash is a claim, not proof: the audited image and the launch log are the proof.
- Until the first-boot checks pass (weights manifest recorded, engine version equal to the pin),
  /health says not ready and every completion is refused.

Standard library only. Usage (launch.sh starts it):
  python gateway.py --pins pins.json --state state.json --tokens tokens \
      --upstream http://127.0.0.1:8001 --port 8443 --cert cert.pem --key key.pem
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MAX_BODY_BYTES = 1_000_000  # a filled-in stance prompt is a few kilobytes
COMPLETIONS = "/v1/chat/completions"


class Refused(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def load_tokens(path: Path) -> list[bytes]:
    """One token per line; blank lines and lines starting with # are ignored. Only their
    SHA-256 is kept in memory, so a comparison never leaks length or prefix."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(hashlib.sha256(line.encode("utf-8")).digest())
    if not out:
        raise SystemExit(f"{path}: no tokens")
    return out


def token_ok(header: str | None, tokens: list[bytes]) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    given = hashlib.sha256(header[len("Bearer ") :].strip().encode("utf-8")).digest()
    ok = False
    for t in tokens:  # check every token, so timing says nothing about which one matched
        ok |= hmac.compare_digest(given, t)
    return ok


def local_upstream(url: str) -> str:
    """The engine must listen on this machine only; anything else is refused at start."""
    if not url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit(f"upstream {url!r}: the engine must be on 127.0.0.1")
    return url.rstrip("/")


def check_request(body: dict[str, Any], pins: dict[str, Any]) -> dict[str, Any]:
    """The request must ask for exactly the validated settings. Returns the body to forward,
    with the served model name the engine expects."""
    serve = pins["serve"]
    if body.get("model") not in (pins["model"]["served_name"], pins["model"]["repo"]):
        raise Refused(400, "model: only the pinned model is served")
    if body.get("stream"):
        raise Refused(400, "stream: not allowed")
    if body.get("n", 1) != 1:
        raise Refused(400, "n: one answer per request")
    if body.get("temperature") != 0:
        raise Refused(400, "temperature: must be 0")
    if body.get("seed") != serve["seed"]:
        raise Refused(400, f"seed: must be {serve['seed']}")
    cap = int(serve["max_tokens"])
    max_tokens = body.get("max_tokens")
    if not isinstance(max_tokens, int) or not 1 <= max_tokens <= cap:
        raise Refused(400, f"max_tokens: 1 to {cap}")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise Refused(400, "messages: required")
    allowed = {
        "model", "messages", "temperature", "seed", "max_tokens", "n", "stream",
        "response_format", "top_p", "chat_template_kwargs",
    }  # fmt: skip
    extra = sorted(set(body) - allowed)
    if extra:
        raise Refused(400, f"not allowed: {', '.join(extra)}")
    if body.get("top_p", 1) != 1:
        raise Refused(400, "top_p: must be 1")
    out = dict(body)
    out["model"] = pins["model"]["served_name"]
    out["n"] = 1
    out["stream"] = False
    return out


class Gateway:
    def __init__(
        self,
        pins: dict[str, Any],
        state_path: Path,
        tokens: list[bytes],
        upstream: str,
        forward: Any = None,
    ) -> None:
        self.pins = pins
        self.state_path = state_path
        self.tokens = tokens
        self.upstream = local_upstream(upstream)
        self.lock = threading.Lock()  # one request at a time: the engine never batches
        self.forward = forward or self._forward

    def state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def health(self) -> dict[str, Any]:
        st = self.state()
        model, engine = self.pins["model"], self.pins["engine"]
        problems = []
        if not st.get("manifest_sha256"):
            problems.append("weights manifest not recorded")
        if st.get("engine_version") != engine["version"]:
            problems.append(
                f"engine {st.get('engine_version')!r} is not the pinned {engine['version']!r}"
            )
        if st.get("revision") != model["revision"]:
            problems.append("weights revision is not the pinned one")
        if not st.get("smoke_identical"):
            problems.append("first-boot repeat check not passed")
        return {
            "ready": not problems,
            "problems": problems,
            "model_repo": model["repo"],
            "revision": model["revision"],
            "manifest_sha256": st.get("manifest_sha256"),
            "engine": engine["name"],
            "engine_version": st.get("engine_version"),
            "gpu": st.get("gpu"),
            "one_request_at_a_time": True,
            "keeps_bodies": False,
        }

    def _forward(self, body: dict[str, Any]) -> tuple[int, bytes]:
        req = urllib.request.Request(  # noqa: S310 - upstream checked to be 127.0.0.1
            self.upstream + COMPLETIONS,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        timeout = float(self.pins["serve"].get("timeout_seconds", 900))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - pinned local upstream
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def complete(self, auth: str | None, raw: bytes) -> tuple[int, bytes]:
        if not token_ok(auth, self.tokens):
            raise Refused(401, "token")
        if not self.health()["ready"]:
            raise Refused(503, "not ready: first-boot checks have not passed")
        try:
            body = json.loads(raw)
        except ValueError:
            raise Refused(400, "body: not JSON") from None
        if not isinstance(body, dict):
            raise Refused(400, "body: not an object")
        out = check_request(body, self.pins)
        with self.lock:
            return self.forward(out)


def make_handler(gw: Gateway, log: Any = sys.stderr) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "mabillon-model-server"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # the default logger prints request lines; ours is _log (no bodies, no IPs)

        def _log(self, status: int, start: float) -> None:
            print(f"{self.command} {self.path} {status} {time.perf_counter() - start:.2f}s",
                  file=log, flush=True)  # fmt: skip

        def _send(self, status: int, payload: bytes, start: float) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            self._log(status, start)

        def do_GET(self) -> None:  # noqa: N802
            start = time.perf_counter()
            if self.path != "/health":
                return self._send(404, b'{"error": "not found"}', start)
            self._send(200, json.dumps(gw.health()).encode("utf-8"), start)

        def do_POST(self) -> None:  # noqa: N802
            start = time.perf_counter()
            if self.path != COMPLETIONS:
                return self._send(404, b'{"error": "not found"}', start)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if not 0 < length <= MAX_BODY_BYTES:
                    raise Refused(413, "body size")
                status, payload = gw.complete(self.headers.get("Authorization"),
                                              self.rfile.read(length))  # fmt: skip
            except Refused as r:
                status, payload = r.status, json.dumps({"error": r.reason}).encode("utf-8")
            self._send(status, payload, start)

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pins", type=Path, required=True)
    ap.add_argument("--state", type=Path, required=True)
    ap.add_argument("--tokens", type=Path, required=True)
    ap.add_argument("--upstream", default="http://127.0.0.1:8001")
    ap.add_argument("--host", default="0.0.0.0")  # noqa: S104 - the one public port, TLS + token
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--cert", type=Path, required=True)
    ap.add_argument("--key", type=Path, required=True)
    args = ap.parse_args(argv)
    pins = json.loads(args.pins.read_text(encoding="utf-8"))
    gw = Gateway(pins, args.state, load_tokens(args.tokens), args.upstream)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(gw))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(args.cert, args.key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"gateway on {args.host}:{args.port}, upstream {args.upstream}", file=sys.stderr)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
