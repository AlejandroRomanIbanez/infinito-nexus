"""PHP toolchain provisioning for the PHP unit suite."""

from __future__ import annotations

import subprocess

from utils import PROJECT_ROOT
from utils.install.primitives import log
from utils.install.system_pkg import ensure_command_present

_PHPUNIT = PROJECT_ROOT / "vendor" / "bin" / "phpunit"


def ensure_php_toolchain() -> None:
    """Install the PHP interpreter and Composer.

    Raises:
        RuntimeError: php or composer is still absent afterwards.
    """
    ensure_command_present("php")
    ensure_command_present("composer")


def ensure_php_present() -> None:
    """Install the PHP toolchain and the Composer vendor tree.

    Raises:
        RuntimeError: php, composer or phpunit is still absent afterwards.
        subprocess.CalledProcessError: ``composer install`` failed.
    """
    ensure_php_toolchain()

    if not _PHPUNIT.is_file():
        log("phpunit missing; running composer install.")
        subprocess.run(
            ["composer", "install", "--no-interaction", "--no-progress"],
            cwd=PROJECT_ROOT,
            check=True,
        )

    if not _PHPUNIT.is_file():
        raise RuntimeError(f"{_PHPUNIT} missing after composer install")


if __name__ == "__main__":
    ensure_php_present()
