"""The Mattermost OAuth app provisioning of Nextcloud's integration_mattermost,
run against a fake Mattermost API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.cache.files import PROJECT_ROOT

SCRIPT = (
    PROJECT_ROOT
    / "roles/web-app-nextcloud/files/python/addons/mattermost/provision_oauth_app.py"
)


class _Mattermost(BaseHTTPRequestHandler):
    def _reply(self, status, body, headers):
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v4/users/login":
            ok = body.get("password") == "pw"
            self._reply(200 if ok else 401, {}, {"Token": "login-token"} if ok else {})
            return
        self.server.created.append((self.headers.get("Authorization"), body))
        self._reply(201, {"id": "new-id", "client_secret": "new-secret"}, {})

    def do_GET(self):
        self.server.seen_auth.append(self.headers.get("Authorization"))
        self._reply(200, self.server.apps, {})

    def log_message(self, *args):
        return


class TestProvisionOauthApp(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Mattermost)
        self.server.apps = []
        self.server.created = []
        self.server.seen_auth = []
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _run(self, **extra):
        env = {
            key: value
            for key, value in os.environ.items()
            if key.lower() not in ("http_proxy", "https_proxy", "all_proxy")
        }
        env.update(
            MM_LOCAL_URL=f"http://127.0.0.1:{self.server.server_address[1]}/",
            MM_APP_NAME="Nextcloud",
            NC_BASE_URL="https://cloud.example/",
            NC_REDIRECT_PATH="/apps/integration_mattermost/oauth-redirect",
            MM_HOMEPAGE="https://cloud.example",
            **extra,
        )
        return subprocess.run(
            [sys.executable, "-"],
            input=SCRIPT.read_text(
                encoding="utf-8"
            ),  # nocheck: cache-read  fed once as stdin
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def test_an_existing_app_is_reused(self):
        self.server.apps = [
            {"name": "Other", "id": "x", "client_secret": "y"},
            {"name": "Nextcloud", "id": "old-id", "client_secret": "old-secret"},
        ]
        proc = self._run(MM_TOKEN="pat")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines(), ["CLIENT_ID=old-id", "CLIENT_SECRET=old-secret"]
        )
        self.assertEqual(self.server.seen_auth, ["Bearer pat"])
        self.assertEqual(self.server.created, [])

    def test_a_missing_app_is_created_with_both_redirects(self):
        proc = self._run(MM_TOKEN="pat")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines(), ["CLIENT_ID=new-id", "CLIENT_SECRET=new-secret"]
        )
        auth, body = self.server.created[0]
        self.assertEqual(auth, "Bearer pat")
        self.assertEqual(
            body["callback_urls"],
            [
                "https://cloud.example/apps/integration_mattermost/oauth-redirect",
                "https://cloud.example/index.php/apps/integration_mattermost/oauth-redirect",
            ],
        )
        self.assertTrue(body["is_trusted"])

    def test_the_password_login_supplies_the_token(self):
        proc = self._run(MM_TOKEN="", MM_ADMIN_LOGIN="admin", MM_ADMIN_PASS="pw")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.server.seen_auth, ["Bearer login-token"])

    def test_a_failed_login_stops_with_a_message(self):
        proc = self._run(MM_TOKEN="", MM_ADMIN_LOGIN="admin", MM_ADMIN_PASS="wrong")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no token available", proc.stderr)


if __name__ == "__main__":
    unittest.main()
