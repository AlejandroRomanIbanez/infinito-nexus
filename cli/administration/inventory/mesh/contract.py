"""Keep the role contract in step with the declared meshes.

``compare_application_keys`` refuses any ``applications.<app>.<key>`` a host
carries that the role's meta tree does not declare, and the mesh block is
generated rather than authored. Enumerating the mesh names in the contract by
hand means stating them twice: once where they are declared and once here, and
the copy that drifts is found at the rotation gate, after a pass has already
run. The contract is written from the declarations instead, so a deployment
may declare whatever meshes it likes.

Values stay empty because the writer supplies them; only the shape is the
contract. ``peers`` is a list, which the validator does not walk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.cache.yaml import dump_yaml, load_yaml_any

if TYPE_CHECKING:
    from pathlib import Path

    from .model import MeshSpec


def _shape() -> dict[str, object]:
    """One mesh's empty block.

    Built per call rather than copied from a constant: a shared ``peers`` list
    is one object under two keys, and the dumper writes the second as a YAML
    alias to the first.
    """
    return {
        "host": "",
        "address": "",
        "subnet": "",
        "listen_port": 0,
        "is_hub": False,
        "primary": False,
        "public_key": "",
        "peers": [],
    }


def contract_of(specs: list[MeshSpec]) -> dict[str, dict]:
    """The contract the given meshes require, keyed by mesh name."""
    return {spec.name: _shape() for spec in sorted(specs, key=lambda s: s.name)}


def write_contract(specs: list[MeshSpec], path: Path) -> bool:
    """Write the contract for *specs*, reporting whether it changed.

    Args:
        specs: the declared meshes.
        path: the role's ``meta/meshes.yml``.

    Returns:
        True when the file on disk did not already match.
    """
    wanted = contract_of(specs)
    if path.is_file() and load_yaml_any(str(path), default_if_missing=None) == wanted:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(str(path), wanted)
    return True
