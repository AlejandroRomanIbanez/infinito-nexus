"""Node.js runtime provisioning for the JavaScript unit suite.

``make test-unit-javascript`` runs ``node --test``; the runtime is a hard
requirement of that target, not an optional extra, so a host that cannot
install it fails loudly instead of silently skipping the suite.
"""

from __future__ import annotations

import shutil

from utils.install.primitives import log
from utils.install.system_pkg import install_command_via_pkg


def ensure_node_present() -> None:
    """Install the Node.js runtime through the system package manager.

    Raises:
        RuntimeError: node is still absent after the install attempt.
    """
    if shutil.which("node") is not None:
        return

    log("node missing; attempting Node.js install via system package manager.")
    install_command_via_pkg("node")

    if shutil.which("node") is None:
        raise RuntimeError("node not found and could not be installed")


if __name__ == "__main__":
    ensure_node_present()
