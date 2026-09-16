import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.install.collections import unsatisfied

REQUIREMENTS = """---
collections:
  - name: community.general
    version: 13.4.0
  - name: hetzner.hcloud
    version: 7.0.1
"""


def _write_requirements(root: Path, body: str = REQUIREMENTS) -> Path:
    path = root / "requirements.galaxy.yml"
    path.write_text(body, encoding="utf-8")
    return path


def _install(collections_dir: Path, fqcn: str, version: str) -> None:
    namespace, _, name = fqcn.partition(".")
    target = collections_dir / "ansible_collections" / namespace / name
    target.mkdir(parents=True)
    (target / "MANIFEST.json").write_text(
        json.dumps({"collection_info": {"version": version}}), encoding="utf-8"
    )


class TestUnsatisfied(unittest.TestCase):
    def test_every_pin_installed_at_its_version_is_satisfied(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirements = _write_requirements(root)
            _install(root, "community.general", "13.4.0")
            _install(root, "hetzner.hcloud", "7.0.1")

            self.assertEqual(unsatisfied(requirements, root), [])

    def test_absent_collection_is_reported(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirements = _write_requirements(root)
            _install(root, "community.general", "13.4.0")

            self.assertEqual(unsatisfied(requirements, root), ["hetzner.hcloud:7.0.1"])

    def test_wrong_version_is_reported_although_the_directory_exists(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirements = _write_requirements(root)
            _install(root, "community.general", "13.4.0")
            _install(root, "hetzner.hcloud", "6.9.0")

            self.assertEqual(unsatisfied(requirements, root), ["hetzner.hcloud:7.0.1"])

    def test_unpinned_entry_can_never_be_confirmed(self):
        body = "---\ncollections:\n  - name: community.general\n"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirements = _write_requirements(root, body)
            _install(root, "community.general", "13.4.0")

            self.assertEqual(unsatisfied(requirements, root), ["community.general"])

    def test_unreadable_manifest_is_reported(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirements = _write_requirements(root)
            _install(root, "community.general", "13.4.0")
            _install(root, "hetzner.hcloud", "7.0.1")
            manifest = (
                root / "ansible_collections" / "hetzner" / "hcloud" / "MANIFEST.json"
            )
            manifest.write_text("{not json", encoding="utf-8")

            self.assertEqual(unsatisfied(requirements, root), ["hetzner.hcloud:7.0.1"])


if __name__ == "__main__":
    unittest.main()
