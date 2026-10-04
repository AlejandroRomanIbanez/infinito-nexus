from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "scripts" / "meta" / "wait" / "images.sh"
STUBS = {
    "docker": '#!/usr/bin/env bash\n[[ -e "${STUB_DIR}/images-ready" ]]\n',
    "gh": (
        "#!/usr/bin/env bash\n"
        'if [[ -n "${STUB_IMAGES_APPEAR:-}" ]]; then\n'
        '\ttouch "${STUB_DIR}/images-ready"\n'
        "fi\n"
        'echo "HTTP 504" >&2\n'
        "exit 1\n"
    ),
    "jq": "#!/usr/bin/env bash\ncat >/dev/null\n",
}


def wait_for_images(tmp: str, **overrides: str) -> subprocess.CompletedProcess:
    """Run the wait script against a ``gh`` that fails every lookup.

    Args:
        tmp: directory that holds the ``docker``, ``gh`` and ``jq`` stubs and their state.
        overrides: environment entries layered over the defaults.
    """
    stub_dir = Path(tmp)
    for name, body in STUBS.items():
        stub = stub_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    inherited = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
    env = {
        **inherited,
        "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
        "STUB_DIR": str(stub_dir),
        "GITHUB_REPOSITORY": "acme/widgets",
        "GH_TOKEN": "unused",
        "WORKFLOW_FILE": "entry.yml",
        "TARGET_EVENT": "pull_request_target",
        "PR_NUMBER": "1",
        "IMAGE_TAG": "ci-test",
        "INFINITO_DISTROS": "debian",
        "WAIT_ATTEMPTS": "100",
        "WAIT_SLEEP_SECONDS": "0",
        **overrides,
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class TestWaitForImages(unittest.TestCase):
    def test_failed_lookup_does_not_end_the_wait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = wait_for_images(tmp, STUB_IMAGES_APPEAR="true")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "Lookup of the privileged workflow run failed (1/30)", result.stdout
            )
            self.assertIn("All required CI images are available.", result.stdout)

    def test_lookup_that_keeps_failing_ends_the_wait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = wait_for_images(tmp)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("failed 30 times in a row", result.stderr)


if __name__ == "__main__":
    unittest.main()
