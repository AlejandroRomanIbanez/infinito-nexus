from __future__ import annotations

from pathlib import PurePosixPath

STATE_SUBDIR = "infinito-state"

NFS_SERVER_SERVICES_YML = "roles/svc-storage-nfs-server/meta/services.yml"
NFS_CLIENT_SERVICES_YML = "roles/svc-storage-nfs-client/meta/services.yml"


def get_export_base() -> str:
    """NFS export base from the provider's services.yml SPOT."""
    from utils.cache.yaml import load_yaml_any

    return load_yaml_any(NFS_SERVER_SERVICES_YML)["nfs-server"]["export_base"]


def get_client_version() -> int:
    """NFS mount protocol version from the client's services.yml SPOT."""
    from utils.cache.yaml import load_yaml_any

    return int(load_yaml_any(NFS_CLIENT_SERVICES_YML)["nfs-client"]["version"])


def state_path(export_base, subdir):
    return str(PurePosixPath(str(export_base)) / str(subdir))


def fstype(version):
    return "nfs4" if int(version) >= 4 else "nfs"


def mount_opts(version, runtime):
    reliability = (
        "soft,timeo=50,retrans=3" if runtime in ("dev", "act") else "hard,timeo=600"
    )
    locking = "local_lock=flock" if int(version) >= 4 else "nolock"
    return f"vers={version},rw,{reliability},{locking}"


def client_src(server, version, flavor, state_path_value):
    use_root = flavor == "kernel" and int(version) >= 4
    return f"{server}:{'/' if use_root else state_path_value}"
