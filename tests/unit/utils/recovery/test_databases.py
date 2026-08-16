#!/usr/bin/env python3
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock

from utils.recovery import databases

APPLICATIONS = {
    "web-app-zammad": {"services": {"postgres": {"enabled": True}}},
    "web-app-nextcloud": {"services": {"mariadb": {"enabled": True}}},
    "web-app-static": {"services": {"redis": {"enabled": True}}},
}


def generation(root: Path) -> Path:
    path = root / "Backups" / "abc123" / "backup-docker-to-local" / "20260816190906"
    path.mkdir(parents=True)
    return path


class TestEngineResolution(TestCase):
    def setUp(self):
        self.engines = databases.engine_by_key(APPLICATIONS)

    def test_central_instances_are_their_own_engine(self):
        self.assertEqual(self.engines["postgres"], "postgres")
        self.assertEqual(self.engines["mariadb"], "mariadb")

    def test_both_volume_spellings_resolve(self):
        self.assertEqual(self.engines["zammad"], "postgres")
        self.assertEqual(self.engines["zammad_database"], "postgres")
        self.assertEqual(self.engines["nextcloud_database"], "mariadb")

    def test_an_app_without_a_database_contributes_nothing(self):
        self.assertNotIn("static", self.engines)

    def test_engine_of_prefers_the_volume_then_the_database(self):
        dump = databases.Dump("nextcloud_database", "nextcloud", Path("/x"))
        self.assertEqual(databases.engine_of(dump, self.engines), "mariadb")
        by_name = databases.Dump("unknown_volume", "zammad", Path("/x"))
        self.assertEqual(databases.engine_of(by_name, self.engines), "postgres")

    def test_an_unknown_dump_aborts_instead_of_guessing(self):
        dump = databases.Dump("mystery_data", "mystery", Path("/x"))
        with self.assertRaises(databases.RecoveryError):
            databases.engine_of(dump, self.engines)

    def test_the_real_repository_resolves_its_own_apps(self):
        engines = databases.engine_by_key()
        self.assertEqual(engines["postgres"], "postgres")
        self.assertEqual(engines["zammad"], "postgres")


class TestGenerationLayout(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.generation = generation(self.root)
        (self.generation / "postgres/sql").mkdir(parents=True)
        (self.generation / "postgres/sql/zammad.backup.sql").write_text("")
        (self.generation / "postgres/sql/all.cluster.backup.sql").write_text("")
        (self.generation / "openldap_data/files").mkdir(parents=True)

    def test_parts_come_from_the_path(self):
        parts = databases.generation_of(self.generation)
        self.assertEqual(parts.backups_dir, str(self.root / "Backups"))
        self.assertEqual(parts.machine_hash, "abc123")
        self.assertEqual(parts.repo_name, "backup-docker-to-local")
        self.assertEqual(parts.name, "20260816190906")

    def test_cluster_dumps_stay_out_of_the_replay(self):
        dumps, clusters = databases.dumps_of(self.generation)
        self.assertEqual(
            [(d.volume, d.database) for d in dumps], [("postgres", "zammad")]
        )
        self.assertEqual([path.name for path in clusters], ["all.cluster.backup.sql"])

    def test_restore_argv_matches_the_baudolo_contract(self):
        dump = databases.Dump("postgres", "zammad", Path("/x"))
        argv = databases.restore_argv(
            dump,
            databases.generation_of(self.generation),
            "postgres",
            "postgres-1",
            "zammad",
            "s3cret",
        )
        self.assertEqual(
            argv[:5],
            [
                "baudolo-restore",
                "postgres",
                "postgres",
                "abc123",
                "20260816190906",
            ],
        )
        self.assertIn("--empty", argv)
        self.assertEqual(argv[argv.index("--container") + 1], "postgres-1")
        self.assertEqual(argv[argv.index("--db-name") + 1], "zammad")


POSTGRES_HEADER = """--
-- PostgreSQL database dump
--

\\restrict BbyzwODc1rWKL3rDyLhEjgCF0Kf2TU5ma7gcTs8eQI7copLtydXkc61zdULsPav

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
"""

MARIADB_HEADER = """/*M!999999\\- enable the sandbox mode */
-- MariaDB dump 10.19-11.8.8-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: 127.0.0.1    Database: mysql
-- ------------------------------------------------------
-- Server version\t11.8.8-MariaDB-ubu2404

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
"""


class TestDumpVersion(TestCase):
    """Headers captured from postgres:17-alpine and mariadb:11 themselves."""

    def dump(self, header):
        path = Path(tempfile.mkdtemp()) / "app.backup.sql"
        path.write_text(header, encoding="utf-8")
        return databases.Dump("vol", "app", path)

    def test_postgres_states_the_source_server_not_the_tool(self):
        dump = self.dump(POSTGRES_HEADER)
        self.assertEqual(databases.dump_version(dump, "postgres"), "17.11")

    def test_mariadb_ignores_the_tool_version_on_the_first_line(self):
        dump = self.dump(MARIADB_HEADER)
        self.assertEqual(
            databases.dump_version(dump, "mariadb"), "11.8.8-MariaDB-ubu2404"
        )

    def test_a_dump_without_a_version_header_aborts(self):
        dump = self.dump("-- no version here\nSET statement_timeout = 0;\n")
        with self.assertRaises(databases.RecoveryError):
            databases.dump_version(dump, "postgres")

    def test_major_of_both_spellings(self):
        self.assertEqual(databases.major_of("17.11"), 17)
        self.assertEqual(databases.major_of("11.8.8-MariaDB-ubu2404"), 11)
        with self.assertRaises(databases.RecoveryError):
            databases.major_of("unknown")

    def test_a_newer_dump_refuses_an_older_engine(self):
        dump = databases.Dump("vol", "app", Path("/x"))
        with self.assertRaises(databases.RecoveryError) as raised:
            databases.assert_replayable(dump, "postgres", "17.11", "15.6")
        self.assertIn("does not replay into an older engine", str(raised.exception))

    def test_forward_and_equal_are_allowed(self):
        dump = databases.Dump("vol", "app", Path("/x"))
        databases.assert_replayable(dump, "postgres", "15.6", "17.11")
        databases.assert_replayable(dump, "mariadb", "11.8.8-MariaDB", "11.4.2-MariaDB")


class TestCredentials(TestCase):
    def write(self, text):
        path = Path(tempfile.mkdtemp()) / "databases.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_first_row_per_database_wins(self):
        path = self.write(
            "instance;database;username;password\n"
            "postgres;zammad;zammad;secret\n"
            "postgres;zammad;other;later\n"
            "\n"
        )
        self.assertEqual(
            databases.credentials_of(path), {"zammad": ("zammad", "secret")}
        )

    def test_short_row_aborts(self):
        path = self.write("instance;database;username;password\npostgres;zammad\n")
        with self.assertRaises(databases.RecoveryError):
            databases.credentials_of(path)

    def test_missing_file_aborts(self):
        with self.assertRaises(databases.RecoveryError):
            databases.credentials_of(Path("/nonexistent/databases.csv"))


class TestReplay(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.generation = generation(self.root)
        (self.generation / "postgres/sql").mkdir(parents=True)
        (self.generation / "postgres/sql/zammad.backup.sql").write_text(POSTGRES_HEADER)
        self.csv = self.root / "databases.csv"
        self.csv.write_text(
            "instance;database;username;password\npostgres;zammad;zammad;s3cret\n",
            encoding="utf-8",
        )
        self.engines = {"postgres": "postgres"}

    def replay(self, running):
        calls = []

        def fake_run(argv, secret=""):
            calls.append(argv)
            return "17.11\n" if "exec" in argv else ""

        with (
            mock.patch.object(databases, "_run", fake_run),
            mock.patch.object(databases, "consumers_running", lambda *a, **k: running),
            mock.patch.object(
                databases, "container_of_volume", lambda *a, **k: "postgres-1"
            ),
        ):
            replayed = databases.replay(self.generation, self.csv, engines=self.engines)
        return replayed, calls

    def test_a_running_consumer_aborts_before_anything_is_restored(self):
        with self.assertRaises(databases.RecoveryError) as raised:
            self.replay(["zammad-railsserver"])
        self.assertIn("zammad-railsserver", str(raised.exception))

    def test_a_quiesced_host_replays_the_dump(self):
        replayed, calls = self.replay([])
        self.assertEqual(replayed, 1)
        restores = [argv for argv in calls if argv[0] == "baudolo-restore"]
        self.assertEqual(len(restores), 1)
        self.assertEqual(restores[0][:2], ["baudolo-restore", "postgres"])

    def test_the_version_is_checked_before_anything_is_replayed(self):
        _, calls = self.replay([])
        asked = next(i for i, argv in enumerate(calls) if "exec" in argv)
        replayed = next(
            i for i, argv in enumerate(calls) if argv[0] == "baudolo-restore"
        )
        self.assertLess(asked, replayed)

    def test_a_generation_without_dumps_is_not_an_error(self):
        empty = generation(Path(tempfile.mkdtemp()))
        self.assertEqual(databases.replay(empty, self.csv, engines=self.engines), 0)

    def test_a_missing_generation_aborts(self):
        with self.assertRaises(databases.RecoveryError):
            databases.replay(self.generation / "nope", self.csv, engines=self.engines)

    def test_a_stopped_database_container_says_to_start_it(self):
        with mock.patch.object(databases, "_run", lambda argv, secret="": "postgres\n"):
            self.assertEqual(databases.container_of_volume("postgres"), "postgres")

        def only_ps_all(argv, secret=""):
            return "postgres\n" if "-a" in argv else ""

        with (
            mock.patch.object(databases, "_run", only_ps_all),
            self.assertRaises(databases.RecoveryError) as raised,
        ):
            databases.container_of_volume("postgres")
        self.assertIn("is not running", str(raised.exception))

    def test_no_container_at_all_says_to_deploy_first(self):
        with (
            mock.patch.object(databases, "_run", lambda argv, secret="": ""),
            self.assertRaises(databases.RecoveryError) as raised,
        ):
            databases.container_of_volume("postgres")
        self.assertIn("deploy the stack first", str(raised.exception))

    def test_the_password_is_redacted_from_a_failure(self):
        with self.assertRaises(databases.RecoveryError) as raised:
            databases._run(["false", "--db-password", "s3cret"], secret="s3cret")
        self.assertNotIn("s3cret", str(raised.exception))
        self.assertIn("***", str(raised.exception))


if __name__ == "__main__":
    main()
