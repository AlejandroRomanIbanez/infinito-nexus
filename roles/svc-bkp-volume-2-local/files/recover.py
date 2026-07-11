#!/usr/bin/env python3
"""Restore a docker volume's files from a backup-docker-to-local
generation.

Runs the role's deployed backup unit first (the usual baudolo run,
storing a fresh differential generation of every volume and database),
resolves the volume's mountpoint and mirrors the snapshot into it
(``rsync -a --delete``). Stop the consuming project first. Database
restores stay with ``baudolo-restore postgres|mariadb``.

Usage:
    recover.py SOURCE_DIR VOLUME [--no-service-backup]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # nocheck: project-root-import
sys.path.insert(0, str(_REPO_ROOT))

from utils.recovery.base import DirectoryRecovery  # noqa: E402


class VolumeRecovery(DirectoryRecovery):
    unit_pattern = "svc-bkp-volume-2-local*.service"

    def __init__(
        self, source_dir: str, volume: str, *, service_backup: bool = True
    ) -> None:
        mountpoint = subprocess.run(
            ["docker", "volume", "inspect", "--format", "{{.Mountpoint}}", volume],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        super().__init__(source_dir, mountpoint, service_backup=service_backup)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_dir",
        help="snapshot to restore from (e.g. <backups>/<machine-hash>/backup-docker-to-local/<generation>/<volume>/files)",
    )
    parser.add_argument("volume", help="docker volume name to restore into")
    parser.add_argument(
        "--no-service-backup",
        action="store_true",
        help="skip the pre-recover backup unit run (only when the target holds nothing worth saving)",
    )
    args = parser.parse_args()
    return VolumeRecovery(
        args.source_dir, args.volume, service_backup=not args.no_service_backup
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
