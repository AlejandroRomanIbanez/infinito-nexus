"""Filesystem SPOT for the Python side, mirroring group_vars/all/05_paths.yml.

Reads the ``INFINITO_DIR_VAR_LIB`` env SPOT. The env layer
(scripts/meta/env/load.sh, sourced via BASH_ENV by every Make recipe) provides
it at runtime. When a tool runs outside that layer — e.g. the compose-deploy
inventory validator, spawned as a bare ``subprocess`` that does not inherit the
env build — the value is read straight from its source of truth, ``default.env``,
so there is still no hardcoded literal default."""

from __future__ import annotations

import os
from pathlib import Path

from utils import PROJECT_ROOT


def _dir_var_lib() -> str:
    env = os.environ.get("INFINITO_DIR_VAR_LIB")
    if env:
        return env
    prefix = "INFINITO_DIR_VAR_LIB="
    # Plain read (not utils.cache.read_text) to avoid a utils.paths -> utils.cache
    # -> utils.paths import cycle: utils.cache.base binds FILE_TOKENS at import.
    for line in (PROJECT_ROOT / "default.env").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip().strip('"').strip("'")
    raise KeyError("INFINITO_DIR_VAR_LIB")


DIR_VAR_LIB = Path(_dir_var_lib())
DIR_SECRETS = DIR_VAR_LIB / "secrets"
FILE_TOKENS = DIR_SECRETS / "tokens.yml"
FILE_DATABASE_SECRETS = DIR_SECRETS / "databases.csv"
