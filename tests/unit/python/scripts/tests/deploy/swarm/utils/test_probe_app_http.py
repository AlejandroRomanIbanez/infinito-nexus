"""The kill-primary probe's app checks, run against stubbed containers.

The failover app check used to pass on an HTTP 500 and on a bare open port.
``probe_app_http`` judges the status code instead, and the save hook of the
representative app (``web-app-wordpress``) proves a write through the app. The stub ``docker`` drops every ``exec [flags] <target>``
and runs the rest locally, so the in-container shell runs against stubbed
``curl``, ``wget`` and ``wp``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

CONTEXT = (
    PROJECT_ROOT / "scripts" / "tests" / "deploy" / "swarm" / "utils" / "_context.sh"
)
SAVE_HOOK = (
    PROJECT_ROOT
    / "roles"
    / "web-app-wordpress"
    / "files"
    / "shell"
    / "failover_save.sh"
)

DOCKER = """#!/bin/sh
while [ "$1" = exec ]; do
	shift
	while [ "${1#-}" != "$1" ]; do
		case "$1" in
		-u | -e | -w) shift 2 ;;
		*) shift ;;
		esac
	done
	shift
	if [ "$1" = docker ]; then
		shift
	fi
done
exec "$@"
"""
CURL = """#!/bin/sh
printf '%s' "${STUB_CODE}"
exit "${STUB_RC}"
"""
WGET = """#!/bin/sh
printf '  HTTP/1.1 301 Moved Permanently\\n  HTTP/1.1 %s Stub\\n' "${STUB_CODE}" >&2
exit "${STUB_RC}"
"""
WP = """#!/bin/sh
case "$2" in
create)
	for arg in "$@"; do
		case "$arg" in --post_title=*) printf '%s' "${arg#--post_title=}" >"${STUB_STORE}" ;; esac
	done
	echo 42
	;;
get) cat "${STUB_STORE}${STUB_SUFFIX}" ;;
esac
"""
TOOLS = ("sh", "sed", "tail", "cat")


class _Stubs:
    def __init__(self, tmp: str, programs: dict[str, str]):
        self.bin = Path(tmp) / "bin"
        self.bin.mkdir()
        for name in TOOLS:
            (self.bin / name).symlink_to(shutil.which(name))
        for name, body in {"docker": DOCKER, **programs}.items():
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)


def _probe(
    programs: dict[str, str], *, code: str, rc: int
) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        stubs = _Stubs(tmp, programs)
        env = dict(os.environ)
        env.update(
            APP_ID="web-app-wordpress", BASH_ENV="", STUB_CODE=code, STUB_RC=str(rc)
        )
        return subprocess.run(
            [
                "bash",
                "-c",
                f'source "{CONTEXT}"; PATH="{stubs.bin}"; probe_app_http node ctr 80',
            ],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )


class TestProbeAppHttp(unittest.TestCase):
    def test_an_ok_answer_passes_and_names_the_status(self) -> None:
        proc = _probe({"curl": CURL}, code="200", rc=0)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "HTTP 200")

    def test_a_redirect_to_the_login_counts_as_an_answer(self) -> None:
        self.assertEqual(_probe({"curl": CURL}, code="302", rc=0).returncode, 0)

    def test_a_server_error_fails_although_curl_exits_zero(self) -> None:
        proc = _probe({"curl": CURL}, code="500", rc=0)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.strip(), "HTTP 500")

    def test_a_refused_connection_fails(self) -> None:
        self.assertEqual(_probe({"curl": CURL}, code="000", rc=7).returncode, 1)

    def test_wget_is_judged_by_its_last_status_line(self) -> None:
        self.assertEqual(_probe({"wget": WGET}, code="200", rc=0).returncode, 0)
        self.assertEqual(_probe({"wget": WGET}, code="503", rc=8).returncode, 1)

    def test_a_container_without_an_http_client_exits_two(self) -> None:
        self.assertEqual(_probe({}, code="200", rc=0).returncode, 2)


def _save(suffix: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        stubs = _Stubs(tmp, {"wp": WP})
        env = dict(os.environ)
        env.update(
            PATH=f"{stubs.bin}:{env['PATH']}",
            STUB_STORE=str(Path(tmp) / "title"),
            STUB_SUFFIX=suffix,
        )
        if suffix:
            (Path(tmp) / f"title{suffix}").write_text("someone else's post")
        return subprocess.run(
            ["bash", str(SAVE_HOOK), "node", "ctr", "1234"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )


class TestWordpressSaveHook(unittest.TestCase):
    def test_a_post_that_reads_back_passes(self) -> None:
        proc = _save("")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("post 42 saved and read back", proc.stdout)

    def test_a_post_that_reads_back_wrong_fails(self) -> None:
        proc = _save(".other")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("expected 'failover-save-1234'", proc.stderr)


class TestSaveHookDiscovery(unittest.TestCase):
    def _hook(self, app_id: str) -> str:
        env = dict(os.environ)
        env.update(APP_ID=app_id, BASH_ENV="")
        return subprocess.run(
            ["bash", "-c", f'source "{CONTEXT}"; printf "%s" "${{FAILOVER_SAVE}}"'],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def test_the_representative_app_declares_its_save_hook(self) -> None:
        self.assertEqual(self._hook("web-app-wordpress"), str(SAVE_HOOK))

    def test_an_app_without_a_hook_declares_none(self) -> None:
        self.assertEqual(self._hook("web-svc-html"), "")


if __name__ == "__main__":
    unittest.main()
