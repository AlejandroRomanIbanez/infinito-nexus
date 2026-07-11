"""Filesystem SPOT for the Python side, read from group_vars/all/05_paths.yml.

``group_vars/all/05_paths.yml`` is the single source of truth for host paths.
The env layer (utils/env/handlers, exported by scripts/meta/env/load.sh) derives
the ``INFINITO_*`` env keys from it; a set env wins so callers can override.
When a tool runs outside that layer, e.g. a bare ``subprocess`` that does not
inherit the env build, the value is read straight from the group_vars SPOT, so
there is still no hardcoded literal default. Only plain-string values can be
read this way; a Jinja expression in the SPOT is a hard error.
"""

from __future__ import annotations

import os
from pathlib import Path

from utils import PROJECT_ROOT
from utils.cache.yaml import load_yaml

_GROUP_PATHS_FILE = str(PROJECT_ROOT / "group_vars" / "all" / "05_paths.yml")


def read_group_path(key: str) -> str:
    """Plain-string path value from the group_vars paths SPOT.

    Args:
        key: top-level variable name in group_vars/all/05_paths.yml.

    Returns:
        The literal string value.

    Raises:
        KeyError: the key is not defined in the SPOT.
        ValueError: the value is not a plain string (e.g. a Jinja template).
    """
    value = load_yaml(_GROUP_PATHS_FILE).get(key)
    if value is None:
        raise KeyError(f"{key} not defined in {_GROUP_PATHS_FILE}")
    if not isinstance(value, str) or "{{" in value:
        raise ValueError(
            f"{key} in {_GROUP_PATHS_FILE} must be a plain string, got: {value!r}"
        )
    return value


def _dir_var_lib() -> str:
    env = os.environ.get("INFINITO_DIR_VAR_LIB")
    if env:
        return env
    return read_group_path("DIR_VAR_LIB")


DIR_VAR_LIB = Path(_dir_var_lib())
DIR_SECRETS = DIR_VAR_LIB / "secrets"
FILE_TOKENS = DIR_SECRETS / "tokens.yml"
FILE_DATABASE_SECRETS = DIR_SECRETS / "databases.csv"
