from __future__ import annotations

import unittest

from infinito_elector_src.mariadb import GtidPosition, MariaDBRole
from infinito_elector_src.roles import RoleError, choose

from . import _NAME  # noqa: F401  side-effect import registers infinito_elector_src


class FakeServers:
    """Answers the mariadb client per target (``local`` or a peer host)."""

    def __init__(self, answers: dict[str, dict[str, str]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def __call__(self, argv, stdin) -> str:
        target = argv[argv.index("-h") + 1] if "-h" in argv else "local"
        self.calls.append((target, stdin))
        server = self.answers.get(target)
        if server is None:
            raise RoleError(f"{target} unreachable")
        for prefix, answer in server.items():
            if stdin.startswith(prefix):
                return answer
        return ""


def _failing(run, message: str):
    def remote_fails(argv, stdin):
        if "-h" in argv:
            raise RoleError(message)
        return run(argv, stdin)

    return remote_fails


def _role(answers, replication_password="s'cret") -> tuple[MariaDBRole, FakeServers]:  # noqa: S107 - test fixture value
    run = FakeServers(answers)
    role = MariaDBRole(
        host_id="m1",
        peers=["m1", "m2", "m3"],
        defaults_file="/run/secrets/elector.cnf",
        socket="/run/mysqld/mysqld.sock",
        peer_address=lambda host: f"mariadb-{host}",
        replication_user="repl",
        replication_password=replication_password,
        run=run,
    )
    return role, run


class TestGtidPosition(unittest.TestCase):
    def test_orders_by_sequence(self) -> None:
        self.assertLess(GtidPosition.parse("0-1-99"), GtidPosition.parse("0-2-100"))

    def test_multi_domain_sums(self) -> None:
        self.assertEqual(GtidPosition.parse("0-1-10,1-1-5").total, 15)

    def test_empty_is_zero(self) -> None:
        self.assertEqual(GtidPosition.parse("").total, 0)

    def test_garbage_raises(self) -> None:
        with self.assertRaises(RoleError):
            GtidPosition.parse("nope")


class TestGtidChoice(unittest.TestCase):
    def test_most_advanced_reachable_peer_wins(self) -> None:
        role, _ = _role(
            {
                "local": {"SELECT @@GLOBAL.gtid_current_pos": "0-1-100"},
                "mariadb-m2": {"SELECT @@GLOBAL.gtid_current_pos": "0-1-120"},
            }
        )
        ranks = {"m1": role.rank(), **role.peer_ranks()}
        self.assertEqual(set(ranks), {"m1", "m2"})
        self.assertEqual(choose(ranks), "m2")

    def test_a_received_but_unapplied_write_counts(self) -> None:
        role, _ = _role(
            {
                "local": {"SELECT @@GLOBAL.gtid_current_pos": "0-1-934"},
                "mariadb-m2": {
                    "SELECT @@GLOBAL.gtid_current_pos": "0-1-934",
                    "SHOW SLAVE STATUS": "Gtid_IO_Pos: 0-1-935",
                },
            }
        )
        self.assertEqual(choose({"m1": role.rank(), **role.peer_ranks()}), "m2")

    def test_a_bootstrap_instance_without_peers_may_promote_alone(self) -> None:
        role, _ = _role({"local": {}})
        role._run = _failing(
            role._run, "ERROR 2005 (HY000): Unknown server host 'mariadb-m2' (-2)"
        )
        role.peer_ranks()
        self.assertEqual(role.quorum(), 1)

    def test_a_slow_peer_still_counts_toward_the_majority(self) -> None:
        role, _ = _role({"local": {}})
        role._run = _failing(role._run, "mariadb: Command timed out")
        role.peer_ranks()
        self.assertEqual(role.quorum(), 2)

    def test_ties_go_to_the_lowest_host_id(self) -> None:
        position = GtidPosition.parse("0-1-7")
        self.assertEqual(choose({"m3": position, "m1": position, "m2": position}), "m1")

    def test_self_wins_when_ahead(self) -> None:
        role, _ = _role(
            {
                "local": {"SELECT @@GLOBAL.gtid_current_pos": "0-1-130"},
                "mariadb-m2": {"SELECT @@GLOBAL.gtid_current_pos": "0-1-120"},
                "mariadb-m3": {"SELECT @@GLOBAL.gtid_current_pos": "0-1-130"},
            }
        )
        self.assertEqual(choose({"m1": role.rank(), **role.peer_ranks()}), "m1")


class TestTransitions(unittest.TestCase):
    def test_promotion_waits_for_the_relay_log_then_opens_writes(self) -> None:
        role, run = _role(
            {
                "local": {
                    "SHOW SLAVE STATUS": "Gtid_IO_Pos: 0-1-50\nSlave_SQL_Running: Yes",
                    "SELECT MASTER_GTID_WAIT": "0",
                }
            }
        )
        role.become_writer()
        statements = [stdin for _, stdin in run.calls]
        wait = next(
            i
            for i, s in enumerate(statements)
            if s.startswith("SELECT MASTER_GTID_WAIT")
        )
        self.assertIn("'0-1-50'", statements[wait])
        self.assertLess(statements.index("STOP SLAVE IO_THREAD"), wait)
        self.assertLess(wait, statements.index("STOP SLAVE"))
        self.assertEqual(statements[-1], "SET GLOBAL read_only = 0")

    def test_promotion_aborts_when_the_relay_log_lags(self) -> None:
        role, run = _role(
            {
                "local": {
                    "SHOW SLAVE STATUS": "Gtid_IO_Pos: 0-1-50",
                    "SELECT MASTER_GTID_WAIT": "-1",
                }
            }
        )
        with self.assertRaises(RoleError):
            role.become_writer()
        self.assertNotIn("SET GLOBAL read_only = 0", [s for _, s in run.calls])

    def test_follow_reads_a_rotated_replication_password(self) -> None:
        passwords = iter(["old", "new"])
        role, run = _role({"local": {}}, replication_password=lambda: next(passwords))
        role.follow("m2")
        role.follow("m3")
        changes = [s for _, s in run.calls if s.startswith("CHANGE MASTER")]
        self.assertIn("MASTER_PASSWORD='old'", changes[0])
        self.assertIn("MASTER_PASSWORD='new'", changes[1])

    SEMI_SYNC_ON = "SET GLOBAL rpl_semi_sync_master_enabled = 1"
    SEMI_SYNC_OFF = "SET GLOBAL rpl_semi_sync_master_enabled = 0"

    def test_only_the_writer_waits_for_semi_sync_acks(self) -> None:
        role, run = _role({"local": {}})
        role.follow("m2")
        statements = [s for _, s in run.calls]
        self.assertLess(
            statements.index(self.SEMI_SYNC_OFF), statements.index("START SLAVE")
        )
        self.assertNotIn(self.SEMI_SYNC_ON, statements)
        role.become_writer()
        statements = [s for _, s in run.calls]
        self.assertLess(
            statements.index(self.SEMI_SYNC_ON),
            statements.index("SET GLOBAL read_only = 0"),
        )

    def test_follow_uses_gtid_slave_pos_and_feeds_the_password_on_stdin(self) -> None:
        role, run = _role({"local": {}})
        role.follow("m2")
        change = next(s for _, s in run.calls if s.startswith("CHANGE MASTER"))
        self.assertIn("MASTER_HOST='mariadb-m2'", change)
        self.assertIn("MASTER_USE_GTID=slave_pos", change)
        self.assertIn("MASTER_CONNECT_RETRY=1", change)
        self.assertIn("'s\\'cret'", change)
        role.follow("m2")
        self.assertEqual(sum(s.startswith("CHANGE MASTER") for _, s in run.calls), 1)

    RESET_SLAVE_POS = "SET GLOBAL gtid_slave_pos = @@GLOBAL.gtid_current_pos"

    def test_a_former_writer_starts_from_its_own_position(self) -> None:
        role, run = _role({"local": {}})
        role.follow("m2")
        statements = [s for _, s in run.calls]
        reset = statements.index(self.RESET_SLAVE_POS)
        change = next(i for i, s in enumerate(statements) if s.startswith("CHANGE"))
        self.assertLess(reset, change)

    def test_a_running_replica_keeps_its_slave_position(self) -> None:
        role, run = _role({"local": {"SHOW SLAVE STATUS": "Master_Host: mariadb-m3"}})
        role.follow("m2")
        self.assertNotIn(self.RESET_SLAVE_POS, [s for _, s in run.calls])

    def test_local_calls_use_socket_auth_when_a_local_user_is_set(self) -> None:
        seen: list[list[str]] = []

        def run(argv, stdin):
            seen.append(list(argv))
            return "0"

        role = MariaDBRole(
            host_id="m1",
            peers=["m1", "m2"],
            defaults_file="/run/secrets/elector.cnf",
            socket="/run/mysqld/mysqld.sock",
            peer_address=lambda host: f"mariadb-{host}",
            replication_user="repl",
            replication_password="pw",
            local_user="mysql",
            run=run,
        )
        role.is_writable()
        role.peer_ranks()
        local, remote = seen
        self.assertEqual(local[1:4], ["--no-defaults", "--user", "mysql"])
        self.assertFalse(any(a.startswith("--defaults-extra-file") for a in local))
        self.assertIn("--defaults-extra-file=/run/secrets/elector.cnf", remote)

    def test_read_only_toggle(self) -> None:
        role, run = _role({"local": {"SELECT @@GLOBAL.read_only": "1"}})
        self.assertFalse(role.is_writable())
        role.become_read_only()
        self.assertEqual(run.calls[-1][1], "SET GLOBAL read_only = 1")

    def test_writable_reads_both_the_numeric_and_the_enum_form(self) -> None:
        for answer, writable in (
            ("0", True),
            ("OFF", True),
            ("1", False),
            ("ON", False),
            ("NO_LOCK", False),
            ("NO_LOCK_NO_ADMIN", False),
        ):
            with self.subTest(read_only=answer):
                role, _ = _role({"local": {"SELECT @@GLOBAL.read_only": answer}})
                self.assertEqual(role.is_writable(), writable)


if __name__ == "__main__":
    unittest.main()
