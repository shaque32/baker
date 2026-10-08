"""`baker serve`: the expert review screen on this computer only.

The standard library's HTTP server, bound to 127.0.0.1 and nothing else, handling one request
at a time (one SQLite connection per request, no threads). It never opens an outbound
connection; ui/app.py does all the work.
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from ui.app import MAX_BODY, App, Request, Response

HOST = "127.0.0.1"  # never anything else: the screen is for this computer only
DEFAULT_PORT = 8765


class _Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "Baker"
    sys_version = ""

    def _request(self, method: str) -> Request | None:
        parts = urlsplit(self.path)
        form: dict[str, str] = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(Response(413, b"too large"))
                return None
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            form = dict(parse_qsl(raw, keep_blank_values=True))
        return Request(
            method=method,
            path=parts.path,
            query=dict(parse_qsl(parts.query, keep_blank_values=True)),
            headers={k.lower(): v for k, v in self.headers.items()},
            form=form,
        )

    def _send(self, resp: Response) -> None:
        self.send_response(resp.status)
        for k, v in resp.headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp.body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(resp.body)

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        req = self._request("GET")
        if req is not None:
            self._send(self.app.handle(req))

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        req = self._request("POST")
        if req is not None:
            self._send(self.app.handle(req))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        sys.stderr.write(f"baker serve: {self.command} {urlsplit(self.path).path}\n")


def make_server(db: Path, port: int = DEFAULT_PORT, expert: str | None = None) -> HTTPServer:
    """Bind 127.0.0.1:port (0 picks a free port). Nothing else is ever bound."""
    app = App(db, expert=expert)
    handler = type("Handler", (_Handler,), {"app": app})
    server = HTTPServer((HOST, port), handler)
    app.port = server.server_address[1]
    server.app = app  # type: ignore[attr-defined]
    return server


def url(server: HTTPServer) -> str:
    return f"http://{HOST}:{server.server_address[1]}/"
