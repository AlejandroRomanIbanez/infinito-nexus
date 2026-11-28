import unittest
from pathlib import Path

from jinja2 import Environment

from utils import PROJECT_ROOT
from utils.cache.yaml import load_yaml_any
from utils.roles.db.backup import BACKUP_ROLE

HA_DIR = (
    Path(PROJECT_ROOT) / "roles" / "sys-svc-compose" / "tasks" / "utils" / "db" / "ha"
)
PREPARE = HA_DIR / "prepare.yml"
PREPARE_HA = HA_DIR / "prepare_ha.yml"
REFUSAL = "🛡️ db_ha_prepare | no HA migration of '{{ application_id }}' without a backup"
BACKUP = "💾 db_ha_prepare | back up before migrating to the HA form"
APP = "svc-db-postgres"


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _env() -> Environment:
    env = Environment(autoescape=True)
    env.filters["bool"] = _as_bool
    return env


def _task(path: Path, name: str) -> dict:
    for task in load_yaml_any(str(path)):
        if task.get("name") == name:
            return task
    raise AssertionError(f"{name!r} not found in {path}")


def _backup_facts(*, backup_kind: str | None, backup_hosts: list[str]) -> dict:
    facts = _task(
        PREPARE, "🔧 db_ha_prepare | load the instance model of '{{ application_id }}'"
    )["ansible.builtin.set_fact"]
    context = {
        "_db_ha_prepare_model": {"ha": {"backup": backup_kind}},
        "groups": {BACKUP_ROLE: backup_hosts} if backup_hosts else {},
        "lookup": lambda *terms: BACKUP_ROLE if terms == ("db_backup", "role") else "",
    }
    env = _env()
    return {
        key: _as_bool(env.from_string(facts[key]).render(**context))
        for key in ("_db_ha_prepare_backup_declared", "_db_ha_prepare_backup")
    }


def _context(
    *, migrating: bool, backup_kind: str | None, backup_hosts: list[str]
) -> dict:
    return {
        "application_id": APP,
        "DB_HA_MIGRATING": {APP: migrating},
        **_backup_facts(backup_kind=backup_kind, backup_hosts=backup_hosts),
    }


def _refusal_holds(**kwargs) -> bool:
    that = _task(PREPARE_HA, REFUSAL)["ansible.builtin.assert"]["that"]
    context = _context(**kwargs)
    env = _env()
    return all(bool(env.compile_expression(check)(**context)) for check in that)


def _backup_runs(**kwargs) -> bool:
    guards = _task(PREPARE_HA, BACKUP)["when"]
    context = _context(**kwargs)
    env = _env()
    return all(bool(env.compile_expression(guard)(**context)) for guard in guards)


class TestHaMigrationBackupGate(unittest.TestCase):
    def test_a_migration_without_a_backup_host_is_refused(self) -> None:
        self.assertFalse(
            _refusal_holds(migrating=True, backup_kind="sql", backup_hosts=[]),
            "the migration takes a backup before converting a standalone "
            "engine; with no backup host the deploy must stop, not skip it",
        )

    def test_a_migration_with_a_backup_host_passes_and_backs_up(self) -> None:
        kwargs = {"migrating": True, "backup_kind": "sql", "backup_hosts": ["mgr-01"]}
        self.assertTrue(_refusal_holds(**kwargs))
        self.assertTrue(_backup_runs(**kwargs))

    def test_an_engine_without_a_backup_kind_migrates_without_one(self) -> None:
        kwargs = {"migrating": True, "backup_kind": None, "backup_hosts": []}
        self.assertTrue(
            _refusal_holds(**kwargs),
            "Redis declares no ha.backup: it is not backed up in either form",
        )
        self.assertFalse(_backup_runs(**kwargs))

    def test_a_deploy_that_does_not_migrate_needs_no_backup_host(self) -> None:
        self.assertTrue(
            _refusal_holds(migrating=False, backup_kind="sql", backup_hosts=[])
        )


if __name__ == "__main__":
    unittest.main()
