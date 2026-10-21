"""``GET /writer``: the health check HAProxy routes writes by; ``POST /seed``: a peer's re-seed request."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

MAX_SEED_BODY = 4096


def make_handler(
    is_writer: Callable[[], bool], seed: Callable[[bytes], int] | None = None
) -> type[BaseHTTPRequestHandler]:
    """A request handler answering 200 on ``/writer`` while *is_writer*
    holds, 503 otherwise, *seed*'s status on ``POST /seed``, and 404 on any
    other path."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != "/writer":
                self._reply(404, b"not found\n")
            elif is_writer():
                self._reply(200, b"writer\n")
            else:
                self._reply(503, b"read-only\n")

        def do_POST(self) -> None:
            if seed is None or self.path.split("?", 1)[0] != "/seed":
                self._reply(404, b"not found\n")
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_SEED_BODY:
                self._reply(413, b"too large\n")
                return
            status = seed(self.rfile.read(length))
            self._reply(status, b"seed\n")

        def _reply(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    return Handler


def serve(
    is_writer: Callable[[], bool],
    host: str,
    port: int,
    seed: Callable[[bytes], int] | None = None,
) -> ThreadingHTTPServer:
    """Start the status server on a daemon thread and return it."""
    server = ThreadingHTTPServer((host, port), make_handler(is_writer, seed))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
