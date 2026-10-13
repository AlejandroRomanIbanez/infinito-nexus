"""Lint: a declared mesh sits inside the declared mesh pool, and the role
contract names exactly the declared meshes.

``NETWORK_MESH_POOL`` in ``group_vars/all/08_networks.yml`` names the block
every WireGuard mesh subnet is carved from. The planner already refuses an
overlap, but it refuses it during a deploy: a declaration that escapes the
pool is a firewall or export list that silently excludes the hosts on it, and
nothing says so until traffic is attempted.

``roles/svc-net-wireguard/meta/meshes.yml`` is generated from the same
declarations, because the validator refuses any ``applications.<app>.<key>``
the role's meta tree does not declare. Written by hand it is the same fact
stated twice, and the copy that drifts is found at the rotation gate, after a
pass has already run.
"""

from __future__ import annotations

import ipaddress
import unittest

import jinja2

from cli.administration.inventory.mesh.contract import contract_of
from cli.administration.inventory.mesh.inventory import specs_of
from utils.cache.yaml import load_yaml_any

from . import PROJECT_ROOT

NETWORKS_FILE = PROJECT_ROOT / "group_vars" / "all" / "08_networks.yml"
DEVELOPMENT_FILE = PROJECT_ROOT / "inventories" / "development" / "meshes.yml"
CONTRACT_FILE = PROJECT_ROOT / "roles" / "svc-net-wireguard" / "meta" / "meshes.yml"
EXAMPLES_DIR = PROJECT_ROOT / "inventories" / "examples"


def declaration_files() -> list:
    """Every declarations file the repository ships."""
    found = [DEVELOPMENT_FILE] if DEVELOPMENT_FILE.is_file() else []
    found += sorted(EXAMPLES_DIR.glob("*/meshes.yml"))
    return found


def _pool() -> ipaddress.IPv4Network:
    data = load_yaml_any(str(NETWORKS_FILE), default_if_missing={}) or {}
    pool = data.get("NETWORK_MESH_POOL")
    if isinstance(pool, str) and "{{" in pool:
        pool = jinja2.Template(
            pool, autoescape=jinja2.select_autoescape(default_for_string=False)
        ).render(**data)
    if not isinstance(pool, str):
        raise TypeError(f"{NETWORKS_FILE} must declare NETWORK_MESH_POOL as a string")
    return ipaddress.ip_network(pool, strict=True)


class TestMeshSubnetPool(unittest.TestCase):
    def setUp(self) -> None:
        self.files = declaration_files()
        if not self.files:
            self.skipTest("the repository ships no mesh declarations")

    def test_every_declared_mesh_sits_inside_the_pool(self) -> None:
        pool = _pool()
        for path in self.files:
            for spec in specs_of(path):
                with self.subTest(declarations=path.name, mesh=spec.name):
                    self.assertTrue(
                        ipaddress.ip_network(spec.subnet, strict=True).subnet_of(pool),
                        f"{path}: mesh '{spec.name}' subnet {spec.subnet} sits "
                        f"outside NETWORK_MESH_POOL ({pool})",
                    )

    def test_no_two_meshes_of_one_deployment_share_a_listen_port(self) -> None:
        for path in self.files:
            ports = [spec.listen_port for spec in specs_of(path)]
            duplicated = sorted({port for port in ports if ports.count(port) > 1})
            with self.subTest(declarations=path.name):
                self.assertEqual([], duplicated, f"{path}: shared listen port(s)")

    def test_the_committed_contract_matches_the_development_declarations(self) -> None:
        """A deployment rewrites it from its own; the committed one is ours."""
        if not DEVELOPMENT_FILE.is_file():
            self.skipTest(f"{DEVELOPMENT_FILE} is absent")
        self.assertEqual(
            contract_of(specs_of(DEVELOPMENT_FILE)),
            load_yaml_any(str(CONTRACT_FILE), default_if_missing=None),
            f"{CONTRACT_FILE} is out of step with {DEVELOPMENT_FILE}. It is "
            "generated: run the mesh CLI rather than editing it.",
        )

    def test_the_platform_itself_declares_no_meshes(self) -> None:
        """Shipping a default mesh is the hardcoding the review asked to end."""
        shipped = load_yaml_any(
            str(PROJECT_ROOT / "group_vars" / "all" / "21_wireguard.yml"),
            default_if_missing={},
        )
        self.assertNotIn("WIREGUARD_MESHES", shipped or {})
