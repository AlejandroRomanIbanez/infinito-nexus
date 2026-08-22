"""Unit tests for :mod:`utils.install.node`."""

from __future__ import annotations

import unittest
import unittest.mock as mock

from utils.install import node as node_mod


class TestEnsureNodePresent(unittest.TestCase):
    def test_present_noop(self) -> None:
        with (
            mock.patch.object(node_mod.shutil, "which", return_value="/usr/bin/node"),
            mock.patch.object(node_mod, "install_command_via_pkg") as install_pkg,
        ):
            node_mod.ensure_node_present()
        install_pkg.assert_not_called()

    def test_installs_via_system_pkg(self) -> None:
        whiches = iter([None, "/usr/bin/node"])
        with (
            mock.patch.object(
                node_mod.shutil, "which", side_effect=lambda _x: next(whiches)
            ),
            mock.patch.object(node_mod, "install_command_via_pkg") as install_pkg,
        ):
            node_mod.ensure_node_present()
        install_pkg.assert_called_once_with("node")

    def test_raises_when_still_missing(self) -> None:
        with (
            mock.patch.object(node_mod.shutil, "which", return_value=None),
            mock.patch.object(node_mod, "install_command_via_pkg"),
            self.assertRaises(RuntimeError),
        ):
            node_mod.ensure_node_present()


if __name__ == "__main__":
    unittest.main()
