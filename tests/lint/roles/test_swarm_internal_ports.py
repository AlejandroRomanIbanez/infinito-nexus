"""Every role whose ``templates/compose.yml.j2`` publishes a
``services.<entity>.ports.local.<kind>`` port mapping must also declare the
matching ``ports.internal.<kind>`` for that entity in ``meta/services.yml``.

The swarm ``resolve_upstream`` (``utils/networks/proxy.py``) reads
``services.<entity>.ports.internal.<port_kind>`` and **hard-fails** (ValueError)
when it is absent, so a proxied role that exposes a port in compose but never
declares its internal (container-side) port breaks every swarm deploy that
proxies it. Compose mode reads only ``ports.local`` and is unaffected, so the
gap is invisible until a swarm deploy.

The internal value is the container-side port of the compose mapping
(``- "<host>:<...ports.local.kind...>:<container_port>"``).

Per-role opt-out: ``# nocheck: swarm-internal-port`` in the services.yml head,
only when the role is genuinely never proxied in swarm.
"""

from __future__ import annotations

import re
import unittest

import yaml

from utils.annotations.suppress import is_suppressed_in_head

from . import PROJECT_ROOT

_RULE = "swarm-internal-port"
# `services.<entity>.ports.local.<kind>` reference inside a compose mapping.
_LOCAL_REF = re.compile(r"services\.([\w-]+)\.ports\.local\.(\w+)")
# A compose publish mapping ends in `:<container_port>"`.
_PUBLISH = re.compile(r'-\s*"[^"]*:\s*\d+"\s*$')


def _entity_internal_kinds(data: object, entity: str) -> set[str]:
    if not isinstance(data, dict):
        return set()
    cfg = data.get(entity)
    if isinstance(cfg, dict) and isinstance(cfg.get("ports"), dict):
        internal = cfg["ports"].get("internal")
        if isinstance(internal, dict):
            return {str(k) for k in internal}
    return set()


class TestSwarmInternalPorts(unittest.TestCase):
    def test_published_local_ports_declare_internal(self) -> None:
        findings: list[str] = []
        for role_dir in sorted((PROJECT_ROOT / "roles").iterdir()):
            compose = role_dir / "templates" / "compose.yml.j2"
            services = role_dir / "meta" / "services.yml"
            if not compose.is_file() or not services.is_file():
                continue

            published: set[tuple[str, str]] = set()
            for line in compose.read_text().splitlines():
                if "ports.local." in line and _PUBLISH.search(line):
                    published.update(_LOCAL_REF.findall(line))
            if not published:
                continue

            services_lines = services.read_text().splitlines()
            if is_suppressed_in_head(services_lines, _RULE):
                continue

            data = yaml.safe_load("\n".join(services_lines)) or {}
            for entity, kind in sorted(published):
                if kind not in _entity_internal_kinds(data, entity):
                    findings.append(
                        f"- {role_dir.name}: services.{entity}.ports.internal.{kind}"
                    )

        if findings:
            self.fail(
                "Roles publish a `ports.local.<kind>` mapping in compose.yml.j2 but "
                "do not declare the matching `ports.internal.<kind>` in "
                "meta/services.yml. The swarm resolve_upstream "
                "(utils/networks/proxy.py) hard-fails (ValueError) at deploy for "
                "these.\n\nAdd `ports.internal.<kind>: <container_port>` (the "
                "container-side port of the compose mapping) on that entity. "
                "Suppress with `# nocheck: swarm-internal-port` in the services.yml "
                "head only when the role is genuinely never proxied in swarm.\n\n"
                "Missing declarations:\n" + "\n".join(sorted(set(findings)))
            )


if __name__ == "__main__":
    unittest.main()
