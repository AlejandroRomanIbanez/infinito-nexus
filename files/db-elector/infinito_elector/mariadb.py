"""MariaDB role backend: ``read_only`` toggle and GTID-based promotion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .roles import Role, RoleError, run_command

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


@dataclass(frozen=True, order=True)
class GtidPosition:
    """A GTID position ordered by its total sequence number."""

    total: int
    text: str = field(compare=False, default="")

    @classmethod
    def parse(cls, text: str) -> GtidPosition:
        total = 0
        for gtid in filter(None, (part.strip() for part in text.split(","))):
            pieces = gtid.split("-")
            if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
                raise RoleError(f"unparsable GTID {gtid!r}")
            total += int(pieces[2])
        return cls(total, text.strip())


def _quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


class MariaDBRole(Role):
    """One MariaDB instance driven through the ``mariadb`` client.

    Args:
        host_id: this instance's host id.
        peers: the other instances' host ids.
        defaults_file: client option file holding the elector's SQL user.
        socket: the local server socket.
        local_user: SQL user authenticated by ``unix_socket`` for the local
            server, so a rotated password never locks the elector out of its
            own instance; ``None`` uses the option file locally too.
        peer_address: maps a host id to the address its instance listens on.
        replication_user: user replicas connect as.
        replication_password: that user's password.
        run: command runner, ``(argv, stdin) -> stdout``.
        relay_wait_seconds: how long one promotion attempt waits for the
            relay log; kept under the runner's 5 s timeout and the renew
            deadline, a lagging relay log is retried on the next tick.
    """

    QUERY_POSITION = "SELECT @@GLOBAL.gtid_current_pos"

    def __init__(
        self,
        *,
        host_id: str,
        peers: Sequence[str],
        defaults_file: str,
        socket: str,
        peer_address: Callable[[str], str],
        local_user: str | None = None,
        replication_user: str,
        replication_password: str,
        run: Callable[[Sequence[str], str | None], str] = run_command,
        relay_wait_seconds: int = 3,
    ) -> None:
        self.host_id = host_id
        self.peers = [peer for peer in peers if peer != host_id]
        self._defaults = defaults_file
        self._socket = socket
        self._local_user = local_user
        self._address = peer_address
        self._repl_user = replication_user
        self._repl_password = replication_password
        self._run = run
        self._relay_wait = relay_wait_seconds
        self._following: str | None = None

    def _sql(self, query: str, host: str | None = None) -> str:
        """Run *query*, fed on stdin so the replication password never shows
        up in the process list."""
        target = self._remote(host) if host else self._local()
        return self._run(["mariadb", *target, "-N", "-B"], query).strip()

    def _remote(self, host: str) -> list[str]:
        return [
            f"--defaults-extra-file={self._defaults}",
            "-h",
            host,
            "--connect-timeout=1",
        ]

    def _local(self) -> list[str]:
        if self._local_user:
            return [
                "--no-defaults",
                "--user",
                self._local_user,
                "--socket",
                self._socket,
            ]
        return [f"--defaults-extra-file={self._defaults}", "--socket", self._socket]

    def _slave_status(self) -> dict[str, str]:
        out = self._run(["mariadb", *self._local(), "-E"], "SHOW SLAVE STATUS")
        status: dict[str, str] = {}
        for line in out.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                status[key.strip()] = value.strip()
        return status

    def is_ready_to_compete(self) -> bool:
        try:
            self._sql("SELECT 1")
        except RoleError:
            return False
        return True

    def rank(self) -> GtidPosition:
        return GtidPosition.parse(self._sql(self.QUERY_POSITION))

    def peer_ranks(self) -> dict[str, GtidPosition]:
        ranks: dict[str, GtidPosition] = {}
        for peer in self.peers:
            try:
                ranks[peer] = GtidPosition.parse(
                    self._sql(self.QUERY_POSITION, self._address(peer))
                )
            except RoleError:
                continue
        return ranks

    def is_writable(self) -> bool:
        """Report whether the server accepts writes.

        Returns:
            True when ``read_only`` is off: ``OFF`` from MariaDB 11.7 on, where
            it became an ENUM, and ``0`` on older servers.
        """
        return self._sql("SELECT @@GLOBAL.read_only") in ("0", "OFF")

    def become_read_only(self) -> None:
        self._sql("SET GLOBAL read_only = 1")

    def _wait_relay_log(self) -> None:
        status = self._slave_status()
        if not status:
            return
        self._sql("STOP SLAVE IO_THREAD")
        status = self._slave_status()
        io_pos = status.get("Gtid_IO_Pos", "")
        if not io_pos:
            return
        result = self._sql(
            f"SELECT MASTER_GTID_WAIT({_quote(io_pos)}, {self._relay_wait})"
        )
        if result != "0":
            raise RoleError(f"relay log not applied within {self._relay_wait}s")

    def become_writer(self) -> None:
        self._wait_relay_log()
        self._sql("STOP SLAVE")
        self._sql("RESET SLAVE ALL")
        self._following = None
        self._sql("SET GLOBAL rpl_semi_sync_master_enabled = 1")
        self._sql("SET GLOBAL read_only = 0")

    def follow(self, writer: str | None) -> None:
        if writer is None or writer in (self.host_id, self._following):
            return
        self._sql("SET GLOBAL rpl_semi_sync_master_enabled = 0")
        self._sql("STOP SLAVE")
        if not self._slave_status():
            # A former writer's gtid_slave_pos predates its own writes; asking
            # the new writer for them again breaks gtid_strict_mode.
            self._sql("SET GLOBAL gtid_slave_pos = @@GLOBAL.gtid_current_pos")
        self._sql(
            "CHANGE MASTER TO "
            f"MASTER_HOST={_quote(self._address(writer))}, "
            f"MASTER_USER={_quote(self._repl_user)}, "
            f"MASTER_PASSWORD={_quote(self._repl_password)}, "
            "MASTER_USE_GTID=slave_pos"
        )
        self._sql("START SLAVE")
        self._following = writer
