"""Contract between the DR drill and the in-node unit trigger.

``trigger_units.sh`` runs inside a lab node, so it cannot read the paths SPOT
itself; the drill resolves it once and hands it over. Pinned here: the script
demands both arguments, every call site supplies them, the rescue path is never
copied into the script, and the environment key the drill guards on is the one
the env handler derives from ``group_vars/all/05_paths.yml``.
"""

from __future__ import annotations

import re
import unittest

from utils.cache.files import PROJECT_ROOT, read_text

TRIGGER = (
    PROJECT_ROOT
    / "scripts"
    / "tests"
    / "deploy"
    / "swarm"
    / "utils"
    / "trigger_units.sh"
)
DRILL = (
    PROJECT_ROOT
    / "scripts"
    / "tests"
    / "deploy"
    / "swarm"
    / "routine"
    / "backup"
    / "base.sh"
)
HANDLER = (
    PROJECT_ROOT
    / "utils"
    / "env"
    / "handlers"
    / "infinito"
    / "rescue_diagnostics_dir.py"
)
SPOT_FILE = PROJECT_ROOT / "group_vars" / "all" / "05_paths.yml"
ENV_KEY = "INFINITO_RESCUE_DIAGNOSTICS_DIR"
CALL = re.compile(r'bash "\$\{TRIGGER_UNITS\}"')
FULL_CALL = re.compile(
    r"""bash "\$\{TRIGGER_UNITS\}"\s+'[^']+'\s+"\$\{UNIT_DUMPS\}\"""",
)


class TestTriggerUnitsContract(unittest.TestCase):
    def setUp(self) -> None:
        self.trigger = read_text(str(TRIGGER))
        self.drill = read_text(str(DRILL))

    def test_the_script_demands_both_arguments(self) -> None:
        self.assertIn('PATTERN="${1:?', self.trigger)
        self.assertIn('DUMPS="${2:?', self.trigger)

    def test_every_call_site_supplies_both(self) -> None:
        self.assertEqual(
            len(CALL.findall(self.drill)), len(FULL_CALL.findall(self.drill))
        )

    def test_the_drill_has_at_least_one_call_site(self) -> None:
        self.assertGreater(len(CALL.findall(self.drill)), 0)

    def test_the_drill_guards_the_env_key(self) -> None:
        self.assertIn(f'UNIT_DUMPS="${{{ENV_KEY}:?', self.drill)

    def test_the_env_key_is_derived_from_the_paths_spot(self) -> None:
        handler = read_text(str(HANDLER))
        self.assertIn(f'KEY = "{ENV_KEY}"', handler)
        self.assertIn('read_group_path("DIR_RESCUE_DIAGNOSTICS")', handler)
        self.assertIn("DIR_RESCUE_DIAGNOSTICS:", read_text(str(SPOT_FILE)))

    def test_the_rescue_path_is_not_copied_into_the_script(self) -> None:
        self.assertNotIn("/tmp/infinito-rescue-diagnostics", self.trigger)
        self.assertNotIn("/tmp/infinito-rescue-diagnostics", self.drill)


if __name__ == "__main__":
    unittest.main()
