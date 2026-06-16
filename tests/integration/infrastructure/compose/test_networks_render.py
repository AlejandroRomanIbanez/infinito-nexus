"""Render-snapshot tests for the registry-driven networks templates.

Both `sys-svc-compose/networks.yml.j2` (top-level networks block) and
`sys-svc-container/networks.yml.j2` (service-level networks attachment)
iterate the service_registry and emit overlay attachments based on each
entry's `server.networks.overlay` metadata. These tests pin the exact
rendered YAML for four representative scenarios so future template edits
have to update the expected snapshots — guarding against silent regressions
between `make test green` and `actual deploy works`.
"""

from __future__ import annotations

import unittest

import jinja2

from utils import PROJECT_ROOT
from utils.roles.entity_name import get_entity_name


def _registry():
    return {
        "ollama": {
            "role": "svc-ai-ollama",
            "entity_name": "ollama",
            "shared": True,
            "enabled": True,
            "overlay": {
                "modes": ["compose", "swarm"],
                "topology": "shared_net",
            },
        },
        "mariadb": {
            "role": "svc-db-mariadb",
            "entity_name": "mariadb",
            "shared": True,
            "enabled": True,
            "overlay": {
                "modes": ["compose", "swarm"],
                "topology": "shared_net",
                "consumer": {"kind": "database"},
            },
        },
        "ldap": {
            "role": "svc-db-openldap",
            "entity_name": "openldap",
            "shared": True,
            "enabled": True,
            "provides": "ldap",
            "overlay": {
                "modes": ["compose", "swarm"],
                "topology": "shared_net",
            },
        },
        "postgres": {
            "role": "svc-db-postgres",
            "entity_name": "postgres",
            "shared": True,
            "enabled": True,
            "overlay": {
                "modes": ["compose", "swarm"],
                "topology": "shared_net",
                "consumer": {"kind": "database"},
            },
        },
        "openresty": {
            "role": "svc-prx-openresty",
            "entity_name": "openresty",
            "shared": True,
            "enabled": True,
            "overlay": {
                "modes": ["swarm"],
                "topology": "default_net",
                "consumer": {
                    "kind": "services_flags",
                    "key": "sso",
                    "flags": ["enabled"],
                },
            },
        },
        "sso": {
            "role": "web-app-keycloak",
            "entity_name": "keycloak",
            "shared": True,
            "enabled": True,
            "provides": "sso",
            "overlay": {
                "modes": ["swarm"],
                "proxy_resolvable": True,
                "aliases": ["auth.example.com"],
            },
        },
    }


def _make_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(PROJECT_ROOT)),
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,  # noqa: S701
    )
    env.filters["get_entity_name"] = get_entity_name
    env.filters["bool"] = lambda v: (
        bool(v) if not isinstance(v, str) else v.lower() in ("true", "1", "yes")
    )
    return env


def _make_lookup(database_data, config_data, domain_data):
    def lookup(plugin, *args):
        if plugin == "database":
            app, key = args
            return database_data.get(app, {}).get(key, "")
        if plugin == "config":
            app, path = args[0], args[1]
            default = args[2] if len(args) > 2 else None
            cur = config_data.get(app, {})
            for part in path.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return default
            return cur
        if plugin == "domain":
            (app,) = args
            return domain_data.get(app, "")
        raise NotImplementedError(plugin)

    return lookup


def _make_query(registry):
    def query(plugin):
        if plugin == "service_registry":
            return [registry]
        raise NotImplementedError(plugin)

    return query


def _render(
    template_rel_path: str,
    *,
    application_id: str,
    deployment_mode: str,
    database: dict | None = None,
    services: dict | None = None,
    subnet: str = "",
) -> str:
    env = _make_env()
    template = env.get_template(template_rel_path)
    registry = _registry()
    database_data = {application_id: database} if database else {}
    config_data = {
        application_id: {
            "services": services or {},
            "server": {"networks": {"local": {"subnet": subnet} if subnet else {}}},
        }
    }
    domain_data = {"web-app-keycloak": "auth.example.com"}
    out = template.render(
        application_id=application_id,
        DEPLOYMENT_MODE=deployment_mode,
        swarm={"network": {"encryption": True}},
        lookup=_make_lookup(database_data, config_data, domain_data),
        query=_make_query(registry),
    )
    return _normalize(out)


def _normalize(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    collapsed: list[str] = []
    blank_run = False
    for line in lines:
        if not line:
            if blank_run:
                continue
            blank_run = True
        else:
            blank_run = False
        collapsed.append(line)
    while collapsed and not collapsed[0]:
        collapsed.pop(0)
    while collapsed and not collapsed[-1]:
        collapsed.pop()
    return "\n".join(collapsed) + "\n"


COMPOSE_TMPL = "roles/sys-svc-compose/templates/networks.yml.j2"
CONTAINER_TMPL = "roles/sys-svc-container/templates/networks.yml.j2"


class TestNetworksRender(unittest.TestCase):
    def test_openresty_swarm_top_level(self):
        rendered = _render(
            COMPOSE_TMPL,
            application_id="svc-prx-openresty",
            deployment_mode="swarm",
        )
        expected = (
            "networks:\n"
            "  default:\n"
            "    name: openresty\n"
            "    driver: overlay\n"
            "    attachable: true\n"
            "    driver_opts:\n"
            '      encrypted: "true"\n'
        )
        self.assertEqual(rendered, expected)

    def test_openresty_swarm_service_level_collects_keycloak_alias(self):
        rendered = _render(
            CONTAINER_TMPL,
            application_id="svc-prx-openresty",
            deployment_mode="swarm",
        )
        expected = (
            "    networks:\n"
            "      default:\n"
            "        aliases:\n"
            "          - auth.example.com\n"
        )
        self.assertEqual(rendered, expected)

    def test_openresty_compose_skips_overlay(self):
        rendered = _render(
            COMPOSE_TMPL,
            application_id="svc-prx-openresty",
            deployment_mode="compose",
            subnet="192.168.105.32/28",
        )
        expected = (
            "networks:\n"
            "  default:\n"
            "    name: openresty\n"
            "    driver: bridge\n"
            "    ipam:\n"
            "      driver: default\n"
            "      config:\n"
            "        - subnet: 192.168.105.32/28\n"
        )
        self.assertEqual(rendered, expected)

    def test_consumer_swarm_attaches_to_postgres_and_openresty(self):
        rendered = _render(
            COMPOSE_TMPL,
            application_id="web-app-baserow",
            deployment_mode="swarm",
            database={"enabled": True, "shared": True, "id": "svc-db-postgres"},
            services={"sso": {"enabled": True}},
        )
        expected = (
            "networks:\n"
            "  postgres:\n"
            "    external: true\n"
            "  openresty:\n"
            "    external: true\n"
            "  default:\n"
            "    name: baserow\n"
            "    driver: overlay\n"
            "    attachable: true\n"
            "    driver_opts:\n"
            '      encrypted: "true"\n'
        )
        self.assertEqual(rendered, expected)

    def test_consumer_swarm_service_attaches_without_keycloak(self):
        rendered = _render(
            CONTAINER_TMPL,
            application_id="web-app-baserow",
            deployment_mode="swarm",
            database={"enabled": True, "shared": True, "id": "svc-db-postgres"},
            services={"sso": {"enabled": True}},
        )
        expected = (
            "    networks:\n"
            "      postgres:\n"
            "        {}\n"
            "      openresty:\n"
            "        {}\n"
            "      default:\n"
        )
        self.assertEqual(rendered, expected)

    def test_mariadb_provider_swarm_suppresses_default(self):
        rendered = _render(
            COMPOSE_TMPL,
            application_id="svc-db-mariadb",
            deployment_mode="swarm",
        )
        expected = "networks:\n  mariadb:\n    external: true\n"
        self.assertEqual(rendered, expected)

    def test_ldap_consumer_swarm_uses_default_consumer_derivation(self):
        rendered = _render(
            COMPOSE_TMPL,
            application_id="web-app-bookwyrm",
            deployment_mode="swarm",
            services={"ldap": {"enabled": True, "shared": True}},
        )
        expected = (
            "networks:\n"
            "  openldap:\n"
            "    external: true\n"
            "  default:\n"
            "    name: bookwyrm\n"
            "    driver: overlay\n"
            "    attachable: true\n"
            "    driver_opts:\n"
            '      encrypted: "true"\n'
        )
        self.assertEqual(rendered, expected)

    def test_ollama_consumer_swarm_uses_default_consumer_derivation(self):
        rendered = _render(
            CONTAINER_TMPL,
            application_id="web-app-openwebui",
            deployment_mode="swarm",
            services={"ollama": {"enabled": True, "shared": True}},
        )
        expected = "    networks:\n      ollama:\n        {}\n      default:\n"
        self.assertEqual(rendered, expected)

    def test_mariadb_provider_swarm_service_attaches_with_alias(self):
        rendered = _render(
            CONTAINER_TMPL,
            application_id="svc-db-mariadb",
            deployment_mode="swarm",
        )
        expected = (
            "    networks:\n      mariadb:\n        aliases:\n          - mariadb\n"
        )
        self.assertEqual(rendered, expected)


if __name__ == "__main__":
    unittest.main()
