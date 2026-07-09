from __future__ import annotations


def seaweedfs_command(s3_config=""):
    """Build the SeaweedFS all-in-one ``server`` command.

    Single source for the args shared by the standalone provider stack
    (``compose.yml.j2``) and the local sidecar (``service.yml.j2``).
    ``-ip=localhost`` is deliberate: the all-in-one server otherwise
    advertises the auto-detected swarm ingress IP, which is unreachable for
    gRPC and hangs ``weed shell`` during bucket provisioning.

    Args:
        s3_config: path to the mounted s3.json; appended as ``-s3.config``
            when truthy. The local sidecar passes ``""`` since it does not
            mount that config.
    """
    command = [
        "server",
        "-dir=/data",
        "-ip=localhost",
        "-ip.bind=0.0.0.0",
        "-filer",
        "-s3",
    ]
    if s3_config:
        command.append(f"-s3.config={s3_config}")
    return command


def seaweedfs_sidecar_script(bucket, s3_port):
    """Build the ``sh -c`` bootstrap script for the embedded sidecar.

    The sidecar creates its consumer's bucket itself at startup because a
    swarm stack's converge gate blocks before any post-deploy task could
    create it, deadlocking consumers that hard-fail on a missing bucket
    (e.g. the OpenTalk controller). The stock entrypoint routes every argv
    through ``weed`` (``sh`` as a command would become ``weed sh``), so the
    template overrides it with ``sh -c``; the server itself is still
    launched via ``/entrypoint.sh`` to keep its /data chown, privilege
    drop, and default server args.

    The trap forwards TERM/INT to the server: without it ``sh`` is PID 1,
    dies on ``docker stop`` without signalling the backgrounded weed, and
    the store loses its graceful flush on every stop.

    Args:
        bucket: consumer bucket name created idempotently at startup.
        s3_port: S3 API port polled via ``/status`` before bucket creation.
    """
    server = " ".join(seaweedfs_command())
    return (
        f"/entrypoint.sh {server} & pid=$!; "
        f'trap \'kill -TERM "$pid" 2>/dev/null; wait "$pid"\' TERM INT; i=0; '
        f"until wget -q -O /dev/null http://127.0.0.1:{s3_port}/status; do "
        f'i=$((i+1)); [ "$i" -ge 150 ] && exit 1; kill -0 "$pid" || exit 1; sleep 2; done; '
        f"echo 's3.bucket.create -name {bucket}' | /usr/bin/weed shell -master=localhost:9333 || true; "
        f'wait "$pid"'
    )


class FilterModule:
    def filters(self):
        return {
            "seaweedfs_command": seaweedfs_command,
            "seaweedfs_sidecar_script": seaweedfs_sidecar_script,
        }
