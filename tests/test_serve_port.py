"""`mabillon serve` and `mabillon demo` when their port is taken (cli/main.py _bind).

A Mabillon already on the port is opened instead of a second one; another program on the port
moves the screen to the next free port, and the line printed names it."""

from __future__ import annotations

import errno
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cli import main as cli
from ui.server import make_server


def _taken(*busy: int):  # noqa: ANN202
    """A stand-in for make_server: the ports in `busy` are held by someone else."""
    opened: list[int] = []

    def make(port: int) -> str:
        if port in busy:
            raise OSError(errno.EADDRINUSE, "Address already in use")
        opened.append(port)
        return f"server on {port}"

    return make, opened


def test_a_free_port_is_used_as_asked():
    make, opened = _taken()
    assert cli._bind(8766, make) == ("server on 8766", "")
    assert opened == [8766]


def test_another_program_on_the_port_moves_to_the_next_free_one(monkeypatch):
    monkeypatch.setattr(cli, "_mabillon_on", lambda port: False)
    make, opened = _taken(8766, 8767)
    server, note = cli._bind(8766, make)
    assert server == "server on 8768" and opened == [8768]
    assert note == "Port 8766 is used by another program; using 8768."
    assert "try --port 8766" not in note


def test_a_mabillon_already_on_the_port_is_opened_not_doubled(monkeypatch):
    monkeypatch.setattr(cli, "_mabillon_on", lambda port: port == 8766)
    make, opened = _taken(8766)
    server, note = cli._bind(8766, make)
    assert server is None and opened == []
    assert "Mabillon is already running at http://127.0.0.1:8766/" in note


def test_every_port_taken_says_so(monkeypatch):
    monkeypatch.setattr(cli, "_mabillon_on", lambda port: False)
    make, _ = _taken(*range(8766, 8766 + cli.PORT_TRIES + 1))
    with pytest.raises(SystemExit, match="ports 8766 to 8776 are all in use"):
        cli._bind(8766, make)


def test_another_bind_error_is_not_retried():
    def make(port: int) -> str:
        raise OSError(errno.EACCES, "Permission denied")

    with pytest.raises(SystemExit, match="cannot open port 80 on 127.0.0.1") as err:
        cli._bind(80, make)
    assert "try --port" not in str(err.value)


def _serving(server: HTTPServer) -> int:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def test_a_running_mabillon_is_recognised(tmp_path):
    server = make_server(port=0, home=tmp_path)
    try:
        port = _serving(server)
        assert cli._mabillon_on(port)
    finally:
        server.shutdown()
        server.server_close()


def test_another_program_is_not_taken_for_mabillon():
    class Other(BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Other)
    try:
        port = _serving(server)
        assert not cli._mabillon_on(port)
    finally:
        server.shutdown()
        server.server_close()
    assert not cli._mabillon_on(port)  # nothing listening
