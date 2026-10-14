from __future__ import annotations

import unittest
import urllib.error
import urllib.request

from infinito_elector_src.server import serve

from . import _NAME  # noqa: F401  side-effect import registers infinito_elector_src


class TestWriterEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {"writer": False}
        self.server = serve(lambda: self.state["writer"], "127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _status(self, path: str) -> int:
        try:
            with urllib.request.urlopen(self.base + path, timeout=2) as response:  # noqa: S310 - fixed http URL to the local test server
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def test_503_while_not_writer(self) -> None:
        self.assertEqual(self._status("/writer"), 503)

    def test_200_while_writer(self) -> None:
        self.state["writer"] = True
        self.assertEqual(self._status("/writer"), 200)

    def test_unknown_path_is_404(self) -> None:
        self.assertEqual(self._status("/"), 404)


if __name__ == "__main__":
    unittest.main()
