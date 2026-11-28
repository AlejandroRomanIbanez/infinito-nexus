"""Ensure the Mattermost OAuth app of Nextcloud's integration_mattermost exists, then print its credentials.

Runs on the Mattermost node's host against the local REST API.

Env:
    MM_LOCAL_URL: internal base URL, e.g. http://localhost:8065.
    MM_TOKEN: admin API token; when set, MM_ADMIN_LOGIN and MM_ADMIN_PASS are ignored.
    MM_ADMIN_LOGIN, MM_ADMIN_PASS: password-login fallback.
    MM_APP_NAME: OAuth app display name, the stable identity key.
    NC_BASE_URL: Nextcloud base URL.
    NC_REDIRECT_PATH: integration_mattermost OAuth redirect path, with a leading slash.
    MM_HOMEPAGE: Nextcloud base URL.

Prints ``CLIENT_ID=<id>`` and ``CLIENT_SECRET=<secret>`` on success.
"""

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ["MM_LOCAL_URL"].rstrip("/") + "/api/v4"


def call(method, path, headers, body):
    """Args: the HTTP method, the API path, request headers, the JSON body or None.

    Returns the response headers and body, also for an HTTP error status.
    """
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(  # noqa: S310 - MM_LOCAL_URL is the role's own http base URL
        API + path, data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - see above
            return response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.headers, error.read()


def token():
    if os.environ.get("MM_TOKEN"):
        return os.environ["MM_TOKEN"]
    headers, _ = call(
        "POST",
        "/users/login",
        {"Content-Type": "application/json"},
        {
            "login_id": os.environ["MM_ADMIN_LOGIN"],
            "password": os.environ["MM_ADMIN_PASS"],
        },
    )
    return headers.get("Token", "")


def existing_app(auth, name):
    _, body = call("GET", "/oauth/apps?page=0&per_page=200", auth, None)
    try:
        apps = json.loads(body)
    except ValueError:
        apps = []
    for app in apps if isinstance(apps, list) else []:
        if app.get("name") == name:
            return app.get("id", ""), app.get("client_secret", "")
    return None


def created_app(auth):
    base = os.environ["NC_BASE_URL"].rstrip("/")
    path = os.environ["NC_REDIRECT_PATH"]
    _, body = call(
        "POST",
        "/oauth/apps",
        {**auth, "Content-Type": "application/json"},
        {
            "name": os.environ["MM_APP_NAME"],
            "description": "Nextcloud integration_mattermost connector",
            "homepage": os.environ["MM_HOMEPAGE"],
            "callback_urls": [base + path, base + "/index.php" + path],
            "is_trusted": True,
        },
    )
    app = json.loads(body)
    return app.get("id", ""), app.get("client_secret", "")


bearer = token()
if not bearer:
    print("mattermost authentication failed: no token available", file=sys.stderr)
    sys.exit(1)
authorization = {"Authorization": f"Bearer {bearer}"}
client_id, client_secret = existing_app(
    authorization, os.environ["MM_APP_NAME"]
) or created_app(authorization)
if not client_id or not client_secret:
    print("failed to obtain mattermost oauth app credentials", file=sys.stderr)
    sys.exit(1)
print(f"CLIENT_ID={client_id}")
print(f"CLIENT_SECRET={client_secret}")
