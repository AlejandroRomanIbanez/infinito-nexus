import importlib.util
import unittest

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar


def _run(name, variables):
    """Lookups must read resolved values from `variables`; templar.template('{{..}}')
    no-ops on untrusted strings in ansible 2.19+ and emits literal Jinja into exports."""
    spec = importlib.util.spec_from_file_location(name, f"plugins/lookup/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    lm = m.LookupModule()
    lm._templar = Templar(loader=DataLoader(), variables=variables)
    return lm.run([], variables=variables)[0]


BASE = {
    "storage": {
        "nfs": {"export_base": "/srv/nfs", "version": 4, "server": "192.168.244.2"}
    },
    "STORAGE_NFS_STATE_SUBDIR": "infinito-state",
    "RUNTIME": "github",
}


class TestNfsLookups(unittest.TestCase):
    def test_state_path_renders(self):
        self.assertEqual(_run("nfs_state_path", BASE), "/srv/nfs/infinito-state")

    def test_fstype_renders(self):
        self.assertEqual(_run("nfs_fstype", BASE), "nfs4")

    def test_mount_opts_github_hard(self):
        self.assertEqual(_run("nfs_mount_opts", BASE), "vers=4,rw,hard,timeo=600,nolock")

    def test_mount_opts_act_soft(self):
        self.assertEqual(
            _run("nfs_mount_opts", {**BASE, "RUNTIME": "act"}),
            "vers=4,rw,soft,timeo=50,retrans=3,nolock",
        )


if __name__ == "__main__":
    unittest.main()
