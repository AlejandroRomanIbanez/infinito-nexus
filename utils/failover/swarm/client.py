"""Suite clients of the Swarm lab adapter: the checker and probe services on the spare."""

from __future__ import annotations

import secrets
import shlex

from utils.cache.files import read_text
from utils.failover.checker import parse_probe_output
from utils.failover.swarm import shell
from utils.failover.swarm.commands import (
    CHECKER_SCRIPT,
    PROBE_PATH,
    PROBE_SCRIPT,
    checker_service_argv,
    config_name,
    oneshot_service_argv,
    probe_service_name,
    service_name,
)


class Clients:
    """Mixin of ``SwarmLabBase``: checker and probe runs on the spare worker."""

    def _client_image(self) -> str:
        try:
            image = self._engine_image()
        except RuntimeError:
            image = self._endpoint_image()
        self._seed_spare(image)
        return image

    def _image_volumes(self, image: str) -> list[str]:
        return shell.run(
            [
                "docker",
                "exec",
                self.client_node,
                "docker",
                "image",
                "inspect",
                image,
                "--format",
                "{{range $path, $_ := .Config.Volumes}}{{$path}} {{end}}",
            ]
        ).split()

    def _seed_spare(self, image: str) -> None:
        present = shell.execute(
            ["docker", "exec", self.client_node, "docker", "image", "inspect", image]
        )
        if present.returncode == 0:
            return
        shell.run(
            [
                "sh",
                "-c",
                (
                    f"docker exec {shlex.quote(self._manager())} docker save {shlex.quote(image)}"
                    f" | docker exec -i {shlex.quote(self.client_node)} docker load"
                ),
            ],
            timeout=600,
        )

    def start_checker(self, run_id: str, duration_s: int) -> None:
        self.stop_checker(run_id)
        self._on_manager(
            "docker",
            "config",
            "create",
            config_name(run_id),
            "-",
            stdin=read_text(str(CHECKER_SCRIPT)),
        )
        image = self._client_image()
        argv = checker_service_argv(
            engine=self.engine,
            manager=self._manager(),
            spare=self.client_node,
            image=image,
            network=self.engine,
            run_id=run_id,
            duration_s=duration_s,
            scratch_dirs=self._image_volumes(image),
        )
        self._checker_id = shell.run(argv).strip()

    def checker_log(self) -> str:
        """Return the checker's log; raise once its task is gone without one."""
        log = self._spare_logs(self._checker_id)
        if not log and self._checker_task_lost():
            raise RuntimeError(
                f"the checker task on {self.client_node} ended without a container"
            )
        return log

    def _checker_task_lost(self) -> bool:
        states = self._on_manager(
            "docker",
            "service",
            "ps",
            self._checker_id,
            "--format",
            "{{.CurrentState}}",
            check=False,
        ).split("\n")
        states = [s for s in states if s.strip()]
        return bool(states) and all(
            s.startswith(("Failed", "Rejected", "Shutdown", "Orphaned", "Remove"))
            for s in states
        )

    def _spare_containers(self, service_id: str, *, exited: bool) -> list[str]:
        return shell.run(
            [
                "docker",
                "exec",
                self.client_node,
                "docker",
                "ps",
                *(["-aq"] if exited else ["-q"]),
                "--filter",
                f"label=com.docker.swarm.service.id={service_id}",
            ],
            check=False,
        ).split()

    def _spare_logs(self, service_id: str) -> str:
        cids = self._spare_containers(service_id, exited=True)
        return "".join(
            shell.run(
                ["docker", "exec", self.client_node, "docker", "logs", cid], check=False
            )
            for cid in cids
        )

    def finish_checker(self) -> None:
        for cid in self._spare_containers(self._checker_id, exited=False):
            shell.run(
                [
                    "docker",
                    "exec",
                    self.client_node,
                    "docker",
                    "kill",
                    "--signal",
                    "USR1",
                    cid,
                ],
                check=False,
            )

    def stop_checker(self, run_id: str) -> None:
        self._on_manager(
            "docker", "service", "rm", service_name(self.engine), check=False
        )
        self._on_manager("docker", "config", "rm", config_name(run_id), check=False)

    def run_probe(
        self, mode: str, arg: str = "", *, timeout_s: int = 300
    ) -> dict[str, str]:
        """Run ``probe.sh`` once through the write endpoint and return its records.

        Args:
            mode: probe mode (``ddl``, ``marker-write``, ``marker-read``,
                ``idle``, ``memberof-seed``).
            arg: the mode's argument.
            timeout_s: seconds to wait for ``probe-done``.
        """
        name = probe_service_name(self.engine)
        config = f"failover-probe-{secrets.token_hex(4)}"
        self._on_manager("docker", "service", "rm", name, check=False)
        self._on_manager(
            "docker",
            "config",
            "create",
            config,
            "-",
            stdin=read_text(str(PROBE_SCRIPT)),
        )
        try:
            image = self._client_image()
            service_id = shell.run(
                oneshot_service_argv(
                    name=name,
                    manager=self._manager(),
                    spare=self.client_node,
                    image=image,
                    network=self.engine,
                    engine=self.engine,
                    config=config,
                    script_path=PROBE_PATH,
                    env={"ENGINE": self.engine, "MODE": mode, "ARG": arg},
                    scratch_dirs=self._image_volumes(image),
                )
            ).strip()
            records: dict[str, str] = {}

            def finished() -> bool:
                done, found = parse_probe_output(self._spare_logs(service_id))
                records.update(found)
                return done

            if not shell.wait_until(finished, timeout_s=timeout_s, interval_s=5):
                raise RuntimeError(f"probe {mode} did not finish in {timeout_s}s")
            return records
        finally:
            self._on_manager("docker", "service", "rm", name, check=False)
            self._on_manager("docker", "config", "rm", config, check=False)
