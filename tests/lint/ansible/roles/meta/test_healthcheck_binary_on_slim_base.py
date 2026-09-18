"""A healthcheck that shells out to a binary must find it in the image it runs in.

A ``-slim`` tag is the upstream's stripped variant: it carries the
runtime and nothing around it. ``node:26-bookworm`` ships ``/usr/bin/curl``,
``node:26-slim`` does not, and a ``healthcheck: flavor: curl`` renders
``CMD curl -f <url>`` either way. The probe then fails from the first beat, and
the container never reports healthy.

The two deploy modes answer differently, and neither answer names the binary.
``sys-svc-compose`` waits on the database container alone in compose and on
every stack task in swarm, so a permanently unhealthy service passes unnoticed
under compose and stops the deploy under swarm: the task dies with ``non-zero
exit (137): dockerexec: unhealthy container``, is rescheduled, dies again, and
the wait fails. Every deployment holding the service in its closure fails with
it, reported against the service that was waited for.

Scope
=====
Roles whose ``meta/services.yml`` declares a healthcheck flavor on an image
whose ``version`` names a stripped variant. The binary is read from the probe
the declaration renders (:func:`utils.docker.healthcheck.compose.compose`), not
restated here, so a flavor that changes its command moves this check with it. A
flavor whose command is a shell builtin or the image's own interpreter needs no
package and is not checked.

The role's ``files/Dockerfile`` must then install that binary. An image that
already ships it is not a defence: the tag is a moving target, and the role that
depends on the binary is the one that should say so.

Per-role opt-out
================
``# nocheck: healthcheck-binary`` on the ``flavor`` line or the one above it,
with a reason naming where the binary comes from instead.
"""

from __future__ import annotations

import re
import unittest

from utils.annotations.suppress import is_suppressed_at
from utils.cache.files import read_text
from utils.cache.yaml import load_yaml_any
from utils.docker.healthcheck.compose import compose
from utils.roles.mapping import ROLE_FILE_META_SERVICES

from . import PROJECT_ROOT

RULE = "healthcheck-binary"

STRIPPED = ("slim",)
"""Tag fragments that name an upstream's stripped variant.

``alpine`` is deliberately out: measured against ``nginx:1.31.6-alpine``, the
image carries ``/usr/bin/curl`` as a real 272 KB binary and ``wget`` as a
busybox applet, so the four alpine roles that declare those flavors are served
by their base today. Widening this tuple to cover them needs that measurement
repeated per image, not an assumption from the word "alpine".
"""

SHELL_BUILTINS = frozenset({"sh", "bash", "test", "true", "exit", "CMD-SHELL"})
"""Probe commands that need no package: the image's own shell runs them."""


def _probe_binary(flavor: object) -> str | None:
    """The executable a declared flavor asks docker to run, if it is a program.

    Args:
        flavor: the ``healthcheck.flavor`` value, one name or a list.
    """
    try:
        probe = compose(flavor, port=80, path="/", hostname="localhost")
        test = probe.test()
    except Exception:
        return None
    argv = [str(part) for part in test]
    if not argv or argv[0] != "CMD" or len(argv) < 2:
        return None
    binary = argv[1]
    return None if binary in SHELL_BUILTINS else binary


def _is_stripped(version: object) -> bool:
    text = str(version)
    return any(fragment in text for fragment in STRIPPED)


def _installs(dockerfile_body: str, binary: str) -> bool:
    """Whether the Dockerfile names the binary as something it installs."""
    return (
        re.search(rf"(?<![\w-]){re.escape(binary)}(?![\w-])", dockerfile_body)
        is not None
    )


def _flavor_lines(lines: list[str]) -> dict[str, int]:
    """The 1-based ``flavor:`` line of each top-level service key.

    ``meta/services.yml`` maps one service per top-level key, so the flavor a
    key owns is the first one under it. Taking the file's first flavor line
    instead would let one service's marker silence another's.

    Args:
        lines: the file's lines, as :func:`read_text` splits them.
    """
    found: dict[str, int] = {}
    current: str | None = None
    for number, line in enumerate(lines, start=1):
        key = re.match(r"([A-Za-z0-9_.-]+):\s*(?:#.*)?$", line)
        if key:
            current = key.group(1)
            continue
        if current and current not in found and re.match(r"\s+flavor:", line):
            found[current] = number
    return found


class TestHealthcheckBinaryOnSlimBase(unittest.TestCase):
    def test_a_stripped_base_installs_the_binary_its_healthcheck_runs(self):
        offenders = []
        for services in sorted(
            (PROJECT_ROOT / "roles").glob(f"*/{ROLE_FILE_META_SERVICES}")
        ):
            role_dir = services.parent.parent
            data = load_yaml_any(str(services), default_if_missing={}) or {}
            lines = read_text(str(services)).splitlines()
            flavor_lines = _flavor_lines(lines)
            for key, entry in data.items():
                if not isinstance(entry, dict):
                    continue
                health = entry.get("healthcheck")
                if not isinstance(health, dict) or "flavor" not in health:
                    continue
                if not _is_stripped(entry.get("version", "")):
                    continue
                binary = _probe_binary(health["flavor"])
                if binary is None:
                    continue
                if is_suppressed_at(lines, flavor_lines.get(key, 0), RULE):
                    continue
                dockerfile = role_dir / "files" / "Dockerfile"
                body = read_text(str(dockerfile)) if dockerfile.is_file() else ""
                if _installs(body, binary):
                    continue
                offenders.append(
                    f"{role_dir.name}: service '{key}' declares healthcheck "
                    f"flavor {health['flavor']!r}, which runs {binary!r}, on the "
                    f"stripped image {entry.get('image')}:{entry.get('version')}; "
                    f"{'files/Dockerfile does not install it' if body else 'the role has no files/Dockerfile'}"
                )

        self.assertEqual(
            [],
            offenders,
            "A stripped base carries the runtime and nothing around it, so a "
            "healthcheck binary has to be installed by the role that depends on "
            "it. Add it to the role's files/Dockerfile, pick a flavor the image "
            f"can already run, or mark the line `# nocheck: {RULE}` with a "
            "reason naming where the binary comes from:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
