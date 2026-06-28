from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.storage.nfs import client_src


class LookupModule(LookupBase):
    """NFS client mount src (server:path): {{ lookup('nfs_client_src') }}."""

    def run(self, terms, variables=None, **kwargs):
        server = self._templar.template("{{ storage.nfs.server }}")
        version = self._templar.template("{{ storage.nfs.version | default(4) }}")
        flavor = self._templar.template("{{ STORAGE_NFS_FLAVOR }}")
        state_path_value = self._templar.template("{{ STORAGE_NFS_STATE_PATH }}")
        return [client_src(server, version, flavor, state_path_value)]
