"""The role contract is written from the declarations, not alongside them.

Stating the mesh names in the contract by hand is the same fact in two files,
and the drift is found at the rotation gate, after a pass has already run.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cli.administration.inventory.mesh.contract import (
    contract_of,
    write_contract,
)
from cli.administration.inventory.mesh.model import MeshSpec
from utils.cache.yaml import load_yaml_any

SHAPE_KEYS = {
    "host",
    "address",
    "subnet",
    "listen_port",
    "is_hub",
    "primary",
    "public_key",
    "peers",
}


def spec(name: str, third: int) -> MeshSpec:
    return MeshSpec(
        name=name,
        hub_group="hub-group",
        spoke_groups=(),
        subnet=f"10.100.{third}.0/24",
        listen_port=51820 + third,
    )


class TestContractOf(unittest.TestCase):
    def test_a_mesh_nobody_named_here_still_gets_a_block(self):
        """The point: a deployment declares meshes this repository never saw."""
        contract = contract_of([spec("wireguard-IV", 9), spec("tenant-b", 10)])
        self.assertEqual({"tenant-b", "wireguard-IV"}, set(contract))

    def test_every_block_carries_the_whole_shape(self):
        for name, block in contract_of([spec("a", 1), spec("b", 2)]).items():
            with self.subTest(mesh=name):
                self.assertEqual(SHAPE_KEYS, set(block))

    def test_the_values_stay_empty_because_the_writer_supplies_them(self):
        block = contract_of([spec("a", 1)])["a"]
        self.assertEqual("", block["host"])
        self.assertEqual(0, block["listen_port"])
        self.assertIs(False, block["is_hub"])
        self.assertEqual([], block["peers"])

    def test_no_two_blocks_share_one_peers_list(self):
        """A shared list is one object under two keys, dumped as a YAML alias."""
        contract = contract_of([spec("a", 1), spec("b", 2)])
        self.assertIsNot(contract["a"]["peers"], contract["b"]["peers"])

    def test_the_order_does_not_follow_the_declaration_order(self):
        """Sorted, so re-ordering a declaration is not a contract change."""
        self.assertEqual(
            list(contract_of([spec("b", 2), spec("a", 1)])),
            list(contract_of([spec("a", 1), spec("b", 2)])),
        )


class TestWriteContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "meta" / "meshes.yml"

    def test_the_first_write_creates_the_file_and_its_parent(self):
        self.assertTrue(write_contract([spec("a", 1)], self.path))
        self.assertEqual(contract_of([spec("a", 1)]), load_yaml_any(str(self.path)))

    def test_writing_the_same_declarations_twice_changes_nothing(self):
        write_contract([spec("a", 1)], self.path)
        self.assertFalse(write_contract([spec("a", 1)], self.path))

    def test_a_new_mesh_rewrites_the_contract(self):
        write_contract([spec("a", 1)], self.path)
        self.assertTrue(write_contract([spec("a", 1), spec("b", 2)], self.path))
        self.assertEqual({"a", "b"}, set(load_yaml_any(str(self.path))))

    def test_a_dropped_mesh_leaves_no_block_behind(self):
        write_contract([spec("a", 1), spec("b", 2)], self.path)
        self.assertTrue(write_contract([spec("a", 1)], self.path))
        self.assertEqual({"a"}, set(load_yaml_any(str(self.path))))
