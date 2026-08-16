"""Replay the sql dumps of one backup generation into their databases.

The file counterpart of a backup is a tree; the database counterpart is a
dump, and the two cannot be restored the same way. ``baudolo-restore
<engine> --empty`` pre-cleans the schema in one psql session and replays the
dump in the next, so a consumer that boots in between recreates the schema
and the replay dies on its own ``CREATE TABLE``. The replay therefore refuses
to run while a consumer of that database is up.

The engine is read from the repository, not guessed from a container image:
the service key under a role's ``meta/services.yml`` is the engine, the same
value ``lookup('database', id, 'type')`` feeds into the backup seed.

The engine *version* is read from the dump's own header, because that is the
only place stating what the dump came out of. Mind which line: postgres says
``-- Dumped from database version 17.11`` on line 7, while mariadb's line 2
(``-- MariaDB dump 10.19-11.8.8-MariaDB``) opens with mariadb-dump's own
version and only the tab-separated ``-- Server version`` line further down
names the server. Matching the first number in the header reads the tool on
one engine and the server on the other.
"""

from __future__ import annotations

import csv
import re
import subprocess
from typing import TYPE_CHECKING, NamedTuple

from utils.cache.applications import get_application_defaults
from utils.roles.applications.services.database import (
    RDBMS_SERVICE_KEYS,
    resolve_database_service_key,
)
from utils.roles.entity.name import get_entity_name

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

RESTORE_BIN = "baudolo-restore"
DOCKER_BIN = "docker"
DUMP_SUFFIX = ".backup.sql"
CLUSTER_SUFFIX = ".cluster.backup.sql"
DEDICATED_VOLUME_SUFFIX = "_database"
HEADER_LINES = 20
VERSION_IN_DUMP = {
    "postgres": re.compile(r"^-- Dumped from database version (\S+)"),
    "mariadb": re.compile(r"^-- Server version\s+(\S+)"),
}
SERVER_VERSION_QUERY = {
    "postgres": (
        "psql",
        "-U",
        "{user}",
        "-d",
        "{database}",
        "-tAc",
        "SHOW server_version",
    ),
    "mariadb": (
        "mariadb",
        "-u{user}",
        "-p{password}",
        "-N",
        "-B",
        "-e",
        "SELECT VERSION()",
    ),
}


class RecoveryError(Exception):
    """A condition that makes the replay unprovable."""


class Dump(NamedTuple):
    """One single-database dump inside a generation."""

    volume: str
    database: str
    path: Path


class Generation(NamedTuple):
    """A generation directory, decomposed into baudolo-restore's arguments."""

    backups_dir: str
    machine_hash: str
    repo_name: str
    name: str


def engine_by_key(applications: Mapping[str, object] | None = None) -> dict[str, str]:
    """Map every name a dump can be addressed by to its database engine.

    Args:
        applications: the materialised application payload; loaded from the
            repository when omitted.

    Returns:
        A mapping of docker volume names and database names to ``postgres``
        or ``mariadb``. Both volume spellings are emitted per application,
        because which one a host used depends on ``shared``, which is
        inventory-dependent and therefore unknowable from a checkout - and
        both spellings resolve to the same engine anyway.
    """
    payload = get_application_defaults() if applications is None else applications
    mapping = {key: key for key in RDBMS_SERVICE_KEYS}
    for application_id in payload:
        engine = resolve_database_service_key(payload, application_id)
        if not engine:
            continue
        entity = get_entity_name(application_id)
        mapping[f"{entity}{DEDICATED_VOLUME_SUFFIX}"] = engine
        mapping[entity] = engine
    return mapping


def generation_of(generation_dir: Path) -> Generation:
    """Decompose <backups>/<machine-hash>/<repo>/<generation> into its parts."""
    repo_dir = generation_dir.parent
    machine_dir = repo_dir.parent
    return Generation(
        str(machine_dir.parent),
        machine_dir.name,
        repo_dir.name,
        generation_dir.name,
    )


def dumps_of(generation_dir: Path) -> tuple[list[Dump], list[Path]]:
    """Split a generation's dumps into replayable ones and cluster dumps.

    Returns:
        The single-database dumps, and the cluster dumps (seeded with an
        empty database name) that ``baudolo-restore`` has no subcommand for.
    """
    dumps: list[Dump] = []
    clusters: list[Path] = []
    for path in sorted(generation_dir.glob("*/sql/*" + DUMP_SUFFIX)):
        if path.name.endswith(CLUSTER_SUFFIX):
            clusters.append(path)
            continue
        volume_dir = path.parent.parent
        dumps.append(Dump(volume_dir.name, path.name[: -len(DUMP_SUFFIX)], path))
    return dumps, clusters


def credentials_of(csv_path: Path) -> dict[str, tuple[str, str]]:
    """Read database credentials from the host's databases.csv.

    Args:
        csv_path: semicolon-separated, header row first, written by
            ``baudolo-seed`` as instance;database;username;password.

    Returns:
        Database name to (user, password); the first row of a name wins,
        matching the upsert order of the seed.

    Raises:
        RecoveryError: the file is missing, or a row is short of columns.
    """
    if not csv_path.is_file():
        raise RecoveryError(f"{csv_path} does not exist")
    credentials: dict[str, tuple[str, str]] = {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = csv.reader(handle, delimiter=";")
        next(rows, None)
        for row in rows:
            if not any(field.strip() for field in row):
                continue
            if len(row) < 4:
                raise RecoveryError(f"{csv_path} has a row with {len(row)} column(s)")
            credentials.setdefault(row[1], (row[2], row[3]))
    return credentials


def engine_of(dump: Dump, engines: Mapping[str, str]) -> str:
    """Name the engine a dump has to be replayed with.

    Args:
        dump: the dump to place.
        engines: the map from :func:`engine_by_key`.

    Raises:
        RecoveryError: neither the volume nor the database name is known to
            the repository, so the engine would have to be guessed.
    """
    for key in (dump.volume, dump.database):
        engine = engines.get(key)
        if engine:
            return engine
    raise RecoveryError(
        f"no database service in the repository claims volume '{dump.volume}' "
        f"or database '{dump.database}', so its engine is unknown"
    )


def major_of(version: str) -> int:
    """The major number of an engine version string.

    Args:
        version: as the engine spells it, e.g. ``17.11`` or
            ``11.8.8-MariaDB-ubu2404``.

    Raises:
        RecoveryError: the string does not start with a number, so comparing
            it would be a guess.
    """
    leading = re.match(r"(\d+)", version)
    if not leading:
        raise RecoveryError(f"cannot read a major version from '{version}'")
    return int(leading.group(1))


def dump_version(dump: Dump, engine: str) -> str:
    """Read the engine version a dump was taken from, out of its own header.

    The dump is the only place that knows this: databases.csv is written at
    seed time and would state the version deployed back then, not the one the
    dump came out of, and a generation copied to another host keeps its header
    while a csv row stays behind.

    Raises:
        RecoveryError: the header carries no version line, so the dump cannot
            be matched against the engine it would be replayed into.
    """
    pattern = VERSION_IN_DUMP[engine]
    with dump.path.open(encoding="utf-8", errors="replace") as handle:
        for _ in range(HEADER_LINES):
            line = handle.readline()
            if not line:
                break
            found = pattern.search(line)
            if found:
                return found.group(1)
    raise RecoveryError(
        f"{dump.path} carries no {engine} version header in its first "
        f"{HEADER_LINES} lines; refusing to replay a dump of unknown origin"
    )


def server_version(
    container: str,
    engine: str,
    user: str,
    password: str,
    database: str,
    docker_host: str | None = None,
) -> str:
    """Ask the running engine which version it is."""
    query = [
        part.format(user=user, password=password, database=database)
        for part in SERVER_VERSION_QUERY[engine]
    ]
    return _run(
        _docker(["exec", container, *query], docker_host), secret=password
    ).strip()


def assert_replayable(dump: Dump, engine: str, dumped: str, serving: str) -> None:
    """Refuse a dump the target engine is too old to read.

    A dump restores forward across major versions - that is the upgrade path -
    but not backward: a newer dump uses syntax an older server rejects, and it
    would fail halfway through an already pre-cleaned schema.

    Raises:
        RecoveryError: the dump is from a newer major version than the server.
    """
    if major_of(dumped) > major_of(serving):
        raise RecoveryError(
            f"dump '{dump.database}' came from {engine} {dumped} but "
            f"{serving} is running; a newer dump does not replay into an older "
            "engine, and the pre-clean would already have dropped the schema"
        )


def restore_argv(
    dump: Dump,
    generation: Generation,
    engine: str,
    container: str,
    user: str,
    password: str,
) -> list[str]:
    """Build the baudolo-restore call that replays one dump."""
    return [
        RESTORE_BIN,
        engine,
        dump.volume,
        generation.machine_hash,
        generation.name,
        "--backups-dir",
        generation.backups_dir,
        "--repo-name",
        generation.repo_name,
        "--container",
        container,
        "--db-name",
        dump.database,
        "--db-user",
        user,
        "--db-password",
        password,
        "--empty",
    ]


def _docker(argv: list[str], docker_host: str | None) -> list[str]:
    return [DOCKER_BIN, *(["-H", docker_host] if docker_host else []), *argv]


def _run(argv: list[str], secret: str = "") -> str:
    """Run a command, aborting the replay when it fails.

    Args:
        argv: the command.
        secret: a value to redact from the error message.
    """
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError as missing:
        raise RecoveryError(f"{argv[0]} is not on PATH") from missing
    if result.returncode != 0:
        shown = " ".join(argv)
        if secret:
            shown = shown.replace(secret, "***")
        raise RecoveryError(
            f"command failed ({result.returncode}): {shown}\n{result.stderr.strip()}"
        )
    return result.stdout


def container_of_volume(volume: str, docker_host: str | None = None) -> str:
    """Name the running container that mounts a volume.

    Raises:
        RecoveryError: nothing is running to replay into. A dump reaches its
            database through ``docker exec``, so unlike a file tree it cannot
            be restored onto a bare host - the engine has to be up. The two
            ways to get there differ, so they are reported apart.
    """
    listed = _docker(
        ["ps", "--filter", f"volume={volume}", "--format", "{{.Names}}"], docker_host
    )
    running = _run(listed).split()
    if running:
        return running[0]
    known = _run(
        _docker(
            ["ps", "-a", "--filter", f"volume={volume}", "--format", "{{.Names}}"],
            docker_host,
        )
    ).split()
    if known:
        raise RecoveryError(
            f"{known[0]} mounts volume {volume} but is not running; the dump is "
            "replayed through docker exec, so start that container first"
        )
    raise RecoveryError(
        f"no container mounts volume {volume} on this host; a dump can only be "
        "replayed into a running database service, so deploy the stack first "
        "and recover with the consumers stopped"
    )


def consumers_running(project: str, docker_host: str | None = None) -> list[str]:
    """List the running containers of one compose project."""
    return _run(
        _docker(
            [
                "ps",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--format",
                "{{.Names}}",
            ],
            docker_host,
        )
    ).split()


def replay(
    generation_dir: Path,
    csv_path: Path,
    *,
    docker_host: str | None = None,
    engines: Mapping[str, str] | None = None,
) -> int:
    """Replay every single-database dump of a generation.

    Args:
        generation_dir: <backups>/<machine-hash>/<repo>/<generation>.
        csv_path: the host's databases.csv.
        docker_host: remote docker endpoint, or None for this host.
        engines: engine map override; read from the repository when omitted.

    Returns:
        The number of dumps replayed.

    Raises:
        RecoveryError: a consumer of a database is still running, a dump has
            no credentials row, or its engine is unknown to the repository.
    """
    if not generation_dir.is_dir():
        raise RecoveryError(f"{generation_dir} is not a directory")
    generation = generation_of(generation_dir)
    dumps, clusters = dumps_of(generation_dir)
    for cluster in clusters:
        print(f"SKIP: cluster dump {cluster.name} has no single-database replay path")
    if not dumps:
        print(f"OK: generation {generation.name} carries no single-database dumps")
        return 0

    engine_map = engine_by_key() if engines is None else engines
    credentials = credentials_of(csv_path)
    for dump in dumps:
        if dump.database not in credentials:
            raise RecoveryError(f"{csv_path} has no row for database '{dump.database}'")
        still_up = consumers_running(dump.database, docker_host)
        if still_up:
            raise RecoveryError(
                f"project '{dump.database}' still runs {', '.join(still_up)}; a booting "
                "consumer recreates the pre-cleaned schema under the replay, so stop it first"
            )

    for dump in dumps:
        engine = engine_of(dump, engine_map)
        container = container_of_volume(dump.volume, docker_host)
        user, password = credentials[dump.database]
        dumped = dump_version(dump, engine)
        serving = server_version(
            container, engine, user, password, dump.database, docker_host
        )
        assert_replayable(dump, engine, dumped, serving)
        print(
            f"OK: {dump.database} dumped from {engine} {dumped}, {serving} is serving"
        )
        _run(
            restore_argv(dump, generation, engine, container, user, password),
            secret=password,
        )
        print(f"OK: replayed {engine} dump '{dump.database}' into {container}")
    return len(dumps)
