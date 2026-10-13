"""Reading declarations, wherever an inventory keeps them.

An inventory declares its own meshes, so the declarations are not necessarily
a neighbour of the platform's ``group_vars/all``. When the pool reference
cannot be followed, ``routed_range`` narrows from the pool to the mesh's own
subnet without saying so, and a spoke stops routing to the planes it is not a
member of -- the hub being in both is the whole point.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cli.administration.inventory.mesh.inventory import groups_of, specs_of
from utils.cache.yaml import dump_yaml

from . import PROJECT_ROOT

DECLARATIONS = {
    "WIREGUARD_MESHES": [
        {
            "name": "alpha",
            "hub_group": "svc-swarm-manager",
            "spoke_groups": ["svc-swarm-node"],
            "subnet": "10.100.10.0/24",
            "listen_port": 51830,
        }
    ],
}


class TestPoolResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.path = self.directory / "meshes.yml"

    def test_declarations_silent_about_the_pool_route_the_platform_one(self):
        """Restating the pool per deployment is the duplication to avoid."""
        dump_yaml(str(self.path), dict(DECLARATIONS))
        self.assertEqual("10.100.0.0/16", specs_of(self.path)[0].routed_range)

    def test_a_neighbour_wins_over_the_platform(self):
        dump_yaml(str(self.path), dict(DECLARATIONS))
        dump_yaml(
            str(self.directory / "00_own.yml"), {"NETWORK_MESH_POOL": "10.100.0.0/17"}
        )
        self.assertEqual("10.100.0.0/17", specs_of(self.path)[0].routed_range)

    def test_a_deployment_may_declare_its_own_pool(self):
        dump_yaml(
            str(self.path),
            {**DECLARATIONS, "WIREGUARD_SUBNET_POOL": "10.100.0.0/18"},
        )
        self.assertEqual("10.100.0.0/18", specs_of(self.path)[0].routed_range)

    def test_a_reference_nothing_defines_is_refused(self):
        dump_yaml(
            str(self.path),
            {**DECLARATIONS, "WIREGUARD_SUBNET_POOL": "{{ NOT_DECLARED_ANYWHERE }}"},
        )
        with self.assertRaises(ValueError) as raised:
            specs_of(self.path)
        self.assertIn("NOT_DECLARED_ANYWHERE", str(raised.exception))


class TestTheShippedExample(unittest.TestCase):
    """The example inventory is the claim that a deployment declares its own."""

    EXAMPLE = PROJECT_ROOT / "inventories" / "examples" / "wireguard-three-meshes"

    def setUp(self):
        if not self.EXAMPLE.is_dir():
            self.skipTest(f"{self.EXAMPLE} is absent")
        self.specs = specs_of(self.EXAMPLE / "meshes.yml")
        self.groups = groups_of([self.EXAMPLE / "inventory.yml"])

    def test_it_declares_more_than_the_two_the_platform_used_to_ship(self):
        self.assertGreater(len(self.specs), 2)

    def test_every_mesh_routes_the_whole_pool_so_the_planes_can_reach_each_other(self):
        for spec in self.specs:
            with self.subTest(mesh=spec.name):
                self.assertEqual("10.100.0.0/16", spec.routed_range)

    def test_one_host_hubs_every_mesh(self):
        hubs = {spec.hub_group for spec in self.specs}
        self.assertEqual(1, len(hubs))
        self.assertEqual(1, len(self.groups[hubs.pop()]))

    def test_every_group_it_names_is_a_group_the_inventory_declares(self):
        """A group nobody declares resolves to no spokes, silently."""
        for spec in self.specs:
            for group in spec.spoke_groups:
                with self.subTest(mesh=spec.name, group=group):
                    self.assertIn(group, self.groups)
