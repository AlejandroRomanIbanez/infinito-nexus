"""Print the extra vars of a local ``playbook-sync.yml`` run as one JSON object.

Usage:
  python -m utils.tests.local.sync_extra_vars <role> <scope> <task> <base> <pw> <keep>
"""

from __future__ import annotations

import json
import shlex
import sys


def sync_extra_vars(
    role: str, scope: str, task: str, base: str, pw: str, keep: str
) -> dict:
    """Build the extra vars of one sync run.

    Args:
        role: deployed application id.
        scope: ``role`` to run the whole role, ``task`` to run one task file.
        task: task file of the role that runs alone, empty for the whole role.
        base: hex base color replacing the one of the inventory, empty to keep it.
        pw: Playwright arguments as one shell-quoted string, empty to skip the spec run.
        keep: ``true`` lets the spec run capture the design gallery.

    Returns:
        The extra vars, keyed the way playbook-sync.yml reads them.
    """
    extra = {"APPLICATIONS_WHITELIST": [role], "sync_scope": scope, "sync_task": task}
    if base:
        extra["DESIGN_BASE_COLOR"] = base
    if pw:
        extra["sync_playwright"] = True
        extra["TEST_E2E_PLAYWRIGHT_ARGUMENTS"] = shlex.split(pw)
        extra["test_e2e_playwright_keep"] = keep
    return extra


if __name__ == "__main__":
    role, scope, task, base, pw, keep = sys.argv[1:]
    print(json.dumps(sync_extra_vars(role, scope, task, base, pw, keep)))
