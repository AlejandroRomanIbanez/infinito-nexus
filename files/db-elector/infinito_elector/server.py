"""``GET /writer``: the health check HAProxy routes writes by."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def make_handler(is_writer: Callable[[], bool]) -> type[BaseHTTPRequestHandler]:
    """A request handler answering 200 on ``/writer`` while *is_writer*
    holds, 503 otherwise, and 404 on any other path."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] != "/writer":
                self._reply(404, b"not found\n")
            elif is_writer():
                self._reply(200, b"writer\n")
            else:
                self._reply(503, b"read-only\n")

        def _reply(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    return Handler


def serve(is_writer: Callable[[], bool], host: str, port: int) -> ThreadingHTTPServer:
    """Start the status server on a daemon thread and return it."""
    server = ThreadingHTTPServer((host, port), make_handler(is_writer))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
