"""`mabillon serve`: the expert review screen on this computer only.

The standard library's HTTP server, bound to 127.0.0.1 and nothing else, handling one request
at a time (one SQLite connection per request). Every request must carry this launch's screen key
(ui/screen_key.py) before ui/app.py sees it. A background audit or claim proposal runs in its
own thread with its own connection (core/casework/jobs.py). It never opens an outbound
connection; ui/app.py does all the work. File uploads (multipart/form-data) are streamed to the
case folder, never held in memory (ui/upload.py).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from core.support import errors as support_errors
from ui.app import MAX_BODY, App, Request, Response
from ui.screen_key import OPEN_PATH, REFUSED, ScreenKey

HOST = "127.0.0.1"  # never anything else: the screen is for this computer only
DEFAULT_PORT = 8765
_SECURITY = App._security_headers()
_PLAIN = ("Content-Type", "text/plain; charset=utf-8")
WRONG_HOST = "This screen only answers requests from this computer."
UNEXPECTED = (
    "Mabillon hit an unexpected error and did not finish this request. Open /help to save a bug "
    "report (it holds no case data) and send it to support."
)
_UNEXPECTED_PAGE = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Unexpected error"
    "</title></head><body style='font-family:system-ui,sans-serif;max-width:40rem;margin:3rem "
    "auto;padding:0 1rem;line-height:1.5'><h1>Something went wrong</h1><p>"
    + UNEXPECTED
    + "</p><p>Nothing in the case changed because of this error.</p><p><a href='/help'>Save a"
    " bug report</a> &middot; <a href='/'>Back to Mabillon</a> (or use your browser's Back"
    " button)</p></body></html>"
)


class _Handler(BaseHTTPRequestHandler):
    app: App
    key: ScreenKey
    server_version = "Mabillon"
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
        self._guarded(self._get, "screen")

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        multipart = (self.headers.get("Content-Type") or "").lower().startswith("multipart/")
        self._guarded(self._post, "upload" if multipart else "screen")

    def _guarded(self, answer: Callable[[], None], where: str) -> None:
        """Answer; an unexpected error is kept for the bug report (type and Mabillon's file and
        line, never its message) and the browser gets a plain 500 that says where to go."""
        try:
            answer()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # The browser went away mid-answer: not a Mabillon failure, kept out of the report.
            return
        except Exception as err:  # noqa: BLE001 - one bad request never stops the screen
            event = support_errors.note(where, err)
            # One line in the Terminal window: the error's type, never its message (which can
            # hold case data), so whoever runs Mabillon sees that something failed.
            print(  # noqa: T201
                f"Mabillon: unexpected error ({'/'.join(event.types) or 'unknown'}) while "
                "answering the screen. Open /help to save a bug report.",
                file=sys.stderr,
            )
            try:
                headers = [("Content-Type", "text/html; charset=utf-8")]
                body = _UNEXPECTED_PAGE.encode("utf-8")
                self._send(Response(500, body, headers + _SECURITY))
            except OSError:
                pass  # the browser went away

    def _gate(self) -> Response | None:
        """The per-launch key: GET /open?key=<key> sets it as a cookie and goes to the screen;
        any other request without it is refused here. A request must name this server in exactly
        one Host header: the app reads the headers as a dictionary (the last value wins), so a
        second Host header must never let a request past this gate on the first one's value."""
        hosts = self.headers.get_all("Host") or []
        if len(hosts) != 1 or hosts[0] not in self.app.allowed_hosts():
            return Response(400, WRONG_HOST.encode("utf-8"), [_PLAIN, *_SECURITY])
        parts = urlsplit(self.path)
        if parts.path == OPEN_PATH:
            given = dict(parse_qsl(parts.query)).get("key")
            if self.command == "GET" and self.key.matches(given):
                cookie = ("Set-Cookie", self.key.set_cookie())
                return Response(303, b"", [("Location", "/"), cookie, *_SECURITY])
        elif self.key.admits(self.headers.get("Cookie")):
            return None
        return Response(403, REFUSED.encode("utf-8"), [_PLAIN, *_SECURITY])

    def _refuse(self, resp: Response) -> None:
        """Answer a refused request; a small body is read first, so the browser sees the answer
        rather than a reset connection."""
        raw = self.headers.get("Content-Length") or ""
        if self.command == "POST" and raw.isdigit() and int(raw) <= MAX_BODY:
            self.rfile.read(int(raw))
        self._send(resp)

    def _get(self) -> None:
        refused = self._gate()
        if refused is not None:
            self._refuse(refused)
            return
        req = self._request("GET")
        if req is not None:
            self._send(self.app.handle(req))

    def _post(self) -> None:
        refused = self._gate()
        if refused is not None:
            self._refuse(refused)
            return
        ctype = self.headers.get("Content-Type") or ""
        if ctype.lower().startswith("multipart/form-data"):
            parts = urlsplit(self.path)
            raw = self.headers.get("Content-Length")
            length = int(raw) if raw and raw.isdigit() else None
            req = Request(
                method="POST",
                path=parts.path,
                headers={k.lower(): v for k, v in self.headers.items()},
            )
            self._send(self.app.handle_upload(req, self.rfile, length))
            return
        req = self._request("POST")
        if req is not None:
            self._send(self.app.handle(req))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        sys.stderr.write(f"mabillon serve: {self.command} {urlsplit(self.path).path}\n")


class _Server(HTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind a port another one holds, so a second
    # Mabillon would bind without an error; there, the port is not reused and the bind fails.
    allow_reuse_address = sys.platform != "win32"


def make_server(
    db: Path | None = None,
    port: int = DEFAULT_PORT,
    expert: str | None = None,
    home: Path | None = None,
    name_file: Path | None = None,
) -> HTTPServer:
    """Bind 127.0.0.1:port (0 picks a free port). Nothing else is ever bound. On one case
    database (db) or on a cases folder (home). The server's screen key is new on every call;
    only launch_url(server) opens the screen. name_file remembers the examiner's name between
    launches (the command passes ~/.mabillon/reviewer.json)."""
    app = App(db, expert=expert, home=home, name_file=name_file)
    handler = type("Handler", (_Handler,), {"app": app})
    server = _Server((HOST, port), handler)
    app.port = server.server_address[1]
    handler.key = ScreenKey(app.port)
    server.app = app  # type: ignore[attr-defined]
    server.key = handler.key  # type: ignore[attr-defined]
    return server


def url(server: HTTPServer) -> str:
    return f"http://{HOST}:{server.server_address[1]}/"


def launch_url(server: HTTPServer) -> str:
    """The one link that opens this launch's screen: it sets the screen key in the browser."""
    return server.key.launch_url()  # type: ignore[attr-defined]
