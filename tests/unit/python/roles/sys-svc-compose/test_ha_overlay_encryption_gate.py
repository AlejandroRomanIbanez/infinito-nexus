import unittest
from pathlib import Path

from jinja2 import Environment

from utils import PROJECT_ROOT
from utils.cache.yaml import load_yaml_any

PREPARE_HA = (
    Path(PROJECT_ROOT) / "roles/sys-svc-compose/tasks/utils/db/ha/prepare_ha.yml"
)
GATE = "🛡️ db_ha_prepare | refuse HA of '{{ application_id }}' on clear overlays"


def _holds(encryption) -> bool:
    task = next(t for t in load_yaml_any(str(PREPARE_HA)) if t.get("name") == GATE)
    env = Environment(autoescape=True)
    env.filters["bool"] = lambda value: (
        str(value).strip().lower() in ("true", "1", "yes")
    )
    context = {"swarm": {"network": {"encryption": encryption}}}
    return all(
        bool(env.compile_expression(check)(**context))
        for check in task["ansible.builtin.assert"]["that"]
    )


class TestHaOverlayEncryptionGate(unittest.TestCase):
    def test_encrypted_overlays_pass(self) -> None:
        self.assertTrue(_holds(True))

    def test_clear_overlays_are_refused(self) -> None:
        self.assertFalse(
            _holds(False),
            "HA replication and seed streams carry no TLS; without overlay "
            "encryption they would cross hosts in clear",
        )


if __name__ == "__main__":
    unittest.main()
