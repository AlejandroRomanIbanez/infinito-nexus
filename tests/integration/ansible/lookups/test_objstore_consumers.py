"""Integration test: objstore_consumers against the real merged config.

The unit tests stub the ``objstore`` lookup, so they only pin this lookup's
own predicate. This one runs it through the real Ansible plugin loader over
the real role tree, which is what the seaweedfs role does at render time, and
requires that a multi-domain consumer reaches the volume budget.
"""

from __future__ import annotations

import unittest

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

from plugins.filter.seaweedfs import VOLUME_GROW_BATCH, volume_slots
from plugins.lookup.applications import (
    LookupModule as ApplicationsLookup,
)
from plugins.lookup.applications import (
    _reset_cache_for_tests,
)
from plugins.lookup.objstore_consumers import LookupModule as ObjstoreConsumersLookup

from . import PROJECT_ROOT

ROLES_DIR = PROJECT_ROOT / "roles"
PROVIDER = "web-app-seaweedfs"
CONSUMER = "web-app-matrix"
NON_CONSUMER = "svc-db-postgres"
GROUP_NAMES = [CONSUMER, PROVIDER, NON_CONSUMER, "svc-swarm-manager"]


def _variables(applications: dict, group_names: list[str]) -> dict:
    return {
        "applications": applications,
        "users": {},
        "DOMAIN_PRIMARY": "infinito.example",
        "SYSTEM_EMAIL_DOMAIN": "infinito.example",
        "DIR_COMPOSITIONS": "/opt/compose/",
        "group_names": list(group_names),
    }


class TestObjstoreConsumersIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _reset_cache_for_tests()
        variables = _variables({}, GROUP_NAMES)
        applications = ApplicationsLookup()
        applications._templar = Templar(loader=DataLoader())
        merged = applications.run([], variables=variables, roles_dir=str(ROLES_DIR))[0]
        variables["applications"] = merged
        cls.variables = variables

        lookup = ObjstoreConsumersLookup()
        lookup._loader = DataLoader()
        lookup._templar = Templar(loader=lookup._loader)
        cls.consumers = lookup.run(["seaweedfs"], variables=variables)[0]

    @classmethod
    def tearDownClass(cls) -> None:
        _reset_cache_for_tests()

    def test_multi_domain_consumer_is_counted(self) -> None:
        self.assertIn(
            CONSUMER,
            self.consumers,
            f"{CONSUMER} binds seaweedfs as a shared object store, so it must "
            f"appear among the consumers. Resolved: {self.consumers}",
        )

    def test_provider_is_not_its_own_consumer(self) -> None:
        self.assertNotIn(PROVIDER, self.consumers)

    def test_group_without_a_binding_is_absent(self) -> None:
        self.assertNotIn(NON_CONSUMER, self.consumers)

    def test_volume_budget_exceeds_the_default_collection_batch(self) -> None:
        slots = volume_slots(len(self.consumers))
        self.assertGreater(
            slots,
            VOLUME_GROW_BATCH,
            "The first grow batch goes to the unnamed default collection, so a "
            "budget of one batch leaves no volume for any named collection and "
            f"every S3 PUT fails. Consumers: {self.consumers}",
        )


class TestInventoryOverrideConsumer(unittest.TestCase):
    OVERRIDDEN = "web-app-hugo"

    @classmethod
    def setUpClass(cls) -> None:
        _reset_cache_for_tests()
        variables = _variables({}, [cls.OVERRIDDEN, PROVIDER])
        variables["applications"] = {
            cls.OVERRIDDEN: {
                "services": {"seaweedfs": {"enabled": True, "shared": True}}
            }
        }
        applications = ApplicationsLookup()
        applications._templar = Templar(loader=DataLoader())
        variables["applications"] = applications.run(
            [], variables=variables, roles_dir=str(ROLES_DIR)
        )[0]

        lookup = ObjstoreConsumersLookup()
        lookup._loader = DataLoader()
        lookup._templar = Templar(loader=lookup._loader)
        cls.consumers = lookup.run(["seaweedfs"], variables=variables)[0]

    @classmethod
    def tearDownClass(cls) -> None:
        _reset_cache_for_tests()

    def test_the_role_declares_nothing_on_disk(self) -> None:
        declared = (ROLES_DIR / self.OVERRIDDEN / "meta" / "services.yml").read_text()
        self.assertNotIn(
            "seaweedfs",
            declared,
            f"{self.OVERRIDDEN} was picked because it declares no object store; "
            "pick another role for this test now that it does.",
        )

    def test_override_only_consumer_is_counted(self) -> None:
        self.assertIn(
            self.OVERRIDDEN,
            self.consumers,
            "A store bound through the inventory alone still grants S3 write "
            "access, so it must reach the volume budget too. Resolved: "
            f"{self.consumers}",
        )


if __name__ == "__main__":
    unittest.main()
