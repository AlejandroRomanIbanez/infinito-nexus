"""``swarm_deploy`` and ``swarm_deploy_replicas`` decide the swarm ``deploy:`` block of one service."""

from __future__ import annotations

import unittest

from plugins.filter.swarm.deploy import swarm_deploy, swarm_deploy_replicas


def ctx(**overrides):
    base = {
        "db_instance": None,
        "seeded_after_converge": None,
        "replicas_forced": None,
        "replicas_declared": "",
        "max_replicas_per_node": None,
        "db_endpoint": False,
        "placement": "",
        "manager_placed": False,
        "managers": ["mgr-01", "mgr-02", "mgr-03"],
        "arch": "",
        "kata_group": False,
        "kata_enabled": False,
        "update_parallelism": 1,
        "update_delay": "10s",
        "update_order": None,
        "restart_condition": "any",
        "runtime": "host",
        "seed_wait_label": "infinito.seed_wait",
        "db_endpoint_label": "infinito.db_endpoint",
        "host_id_label": "infinito.host_id",
        "stack_host_label": "infinito.stack_host",
        "sandbox_label": "kata-capable",
        "resources": {
            "cpus": "2.0",
            "mem_limit": "1g",
            "pids_limit": 512,
            "mem_reservation": "256m",
        },
    }
    return {**base, **overrides}


class TestReplicas(unittest.TestCase):
    def test_a_db_instance_always_runs_one_task(self):
        self.assertEqual(
            swarm_deploy_replicas(
                ctx(db_instance={"host": "mgr-02"}, replicas_forced=5)
            ),
            1,
        )

    def test_a_forced_count_beats_the_declared_one(self):
        self.assertEqual(
            swarm_deploy_replicas(ctx(replicas_forced=3, replicas_declared=2)), 3
        )

    def test_the_declared_count_or_the_topology_default(self):
        self.assertEqual(swarm_deploy_replicas(ctx(replicas_declared=2)), 2)
        self.assertEqual(swarm_deploy_replicas(ctx()), "")


class TestBlock(unittest.TestCase):
    def test_a_plain_service_renders_resources_and_rolling_update(self):
        self.assertEqual(
            swarm_deploy(ctx(), "replicas: 2"),
            (
                "    deploy:\n"
                "      replicas: 2\n"
                "      update_config:\n"
                "        parallelism: 1\n"
                "        delay: 10s\n"
                "        failure_action: continue\n"
                "      restart_policy:\n"
                "        condition: any\n"
                "      resources:\n"
                "        limits:\n"
                '          cpus: "2.0"\n'
                "          memory: 1g\n"
                "          pids: 512\n"
                "        reservations:\n"
                "          memory: 256m"
            ),
        )

    def test_a_single_replica_updates_without_delay(self):
        self.assertIn("        delay: 0s", swarm_deploy(ctx(), "replicas: 1"))

    def test_a_db_instance_is_pinned_to_its_host_and_waits_for_its_seed(self):
        block = swarm_deploy(
            ctx(db_instance={"host": "mgr-02"}, seeded_after_converge=True),
            "replicas: 1",
        )
        self.assertIn('        infinito.seed_wait: "true"', block)
        self.assertIn("          - node.labels.infinito.host_id == mgr-02", block)

    def test_a_seed_flag_without_a_db_instance_adds_no_label(self):
        self.assertNotIn(
            "labels:", swarm_deploy(ctx(seeded_after_converge=True), "replicas: 2")
        )

    def test_the_write_endpoint_spreads_without_a_role_constraint(self):
        block = swarm_deploy(
            ctx(
                db_endpoint=True,
                max_replicas_per_node=1,
                placement="manager",
                manager_placed=True,
            ),
            "replicas: 3",
        )
        self.assertIn('        infinito.db_endpoint: "true"', block)
        self.assertIn("        max_replicas_per_node: 1", block)
        self.assertNotIn("constraints:", block)

    def test_a_placed_service_gets_its_role_stack_host_and_arch(self):
        block = swarm_deploy(ctx(placement="manager", arch="amd64"), "replicas: 2")
        for constraint in (
            "node.role == manager",
            "node.labels.infinito.stack_host == true",
            "node.platform.arch == amd64",
        ):
            self.assertIn(f"          - {constraint}", block)

    def test_a_manager_placed_role_without_a_service_placement_is_pinned(self):
        self.assertIn(
            "          - node.role == manager",
            swarm_deploy(ctx(manager_placed=True), "replicas: 2"),
        )

    def test_a_kata_lab_keeps_plain_services_off_the_sandbox_node(self):
        self.assertIn(
            "          - node.labels.kata-capable != true",
            swarm_deploy(ctx(kata_group=True), "replicas: 2"),
        )
        self.assertIn(
            "          - node.labels.kata-capable == true",
            swarm_deploy(ctx(kata_group=True, kata_enabled=True), "replicas: 2"),
        )

    def test_github_runners_reserve_no_memory_and_the_order_is_kept(self):
        block = swarm_deploy(
            ctx(runtime="github", restart_condition="none", update_order="stop-first"),
            "replicas: 2",
        )
        self.assertNotIn("reservations:", block)
        self.assertIn("        condition: none", block)
        self.assertIn("        order: stop-first", block)


if __name__ == "__main__":
    unittest.main()
