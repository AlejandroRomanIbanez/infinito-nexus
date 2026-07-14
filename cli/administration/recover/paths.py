"""Standard filesystem layout the recover console restores into.

Mirrors the deploy-side SPOTs (group_vars/all/05_paths.yml DIR_VAR_LIB /
DIR_BACKUPS / DIR_SECRETS, roles/svc-storage-nfs-server/meta/services.yml
export_base + utils.storage.nfs STATE_SUBDIR). This uniform layout is what
lets a recovery target a host by name alone: every host restores into
these same fixed paths.
"""

from __future__ import annotations

from pathlib import Path

DIR_VAR_LIB = "/var/lib/infinito"
BACKUP_ROOT = f"{DIR_VAR_LIB}/backup"
SECRETS_DIR = f"{DIR_VAR_LIB}/secrets"
NFS_EXPORT_STATE = "/srv/nfs/infinito-state"
RECOVER_MOUNT = "/mnt/infinito-recover"


def volume_from_source(source: str) -> str:
    """Docker volume name embedded in a snapshot path ``<generation>/<volume>/files``."""
    path = Path(source.rstrip("/"))
    return path.parent.name if path.name == "files" else path.name
