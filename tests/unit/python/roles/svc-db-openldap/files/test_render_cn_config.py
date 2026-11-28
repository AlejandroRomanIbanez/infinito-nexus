import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "roles/svc-db-openldap/files/python/render_cn_config.py"


class TestRenderCnConfig(unittest.TestCase):
    def test_every_token_is_filled_and_the_file_is_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cn-config.ldif"
            target = Path(tmp) / "rendered.ldif"
            source.write_text(
                "olcRootPW: @ROOT_PW_HASH@\nuid @OPENLDAP_UID@ gid @OPENLDAP_GID@\n"
                "credentials=@ROOT_PW@\n",
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "ROOT_PW_HASH": "{SSHA}hash",
                "OPENLDAP_UID": "101",
                "OPENLDAP_GID": "102",
                "LDAP_ROOT_PW": "secret",
            }
            subprocess.run(
                [sys.executable, str(SCRIPT), str(source), str(target)],
                env=env,
                check=True,
            )
            self.assertEqual(
                target.read_text(encoding="utf-8"),  # nocheck: cache-read  temp file
                "olcRootPW: {SSHA}hash\nuid 101 gid 102\ncredentials=secret\n",
            )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
