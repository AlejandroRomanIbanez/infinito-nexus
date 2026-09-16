"""Compare the pinned Galaxy requirements against what is on disk."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def _installed_version(collections_dir: Path, namespace: str, name: str) -> str | None:
    """The version recorded in a collection's manifest, or None when absent.

    Args:
        collections_dir: the ``-p`` target ansible-galaxy installs into.
        namespace: collection namespace, the part before the dot.
        name: collection name, the part after the dot.
    """
    manifest = (
        collections_dir / "ansible_collections" / namespace / name / "MANIFEST.json"
    )
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = payload.get("collection_info", {}).get("version")
    return str(version) if version else None


def unsatisfied(requirements_file: Path, collections_dir: Path) -> list[str]:
    """Requirements that COLLECTIONS_DIR does not already hold at the pinned version.

    An entry without a pinned version can never be confirmed from disk and is
    always reported, so the caller falls through to a real install.

    Args:
        requirements_file: the requirements.galaxy.yml to read.
        collections_dir: the ``-p`` target ansible-galaxy installs into.
    """
    declared = yaml.safe_load(requirements_file.read_text(encoding="utf-8")) or {}
    missing: list[str] = []
    for entry in declared.get("collections") or []:
        if not isinstance(entry, dict):
            missing.append(str(entry))
            continue
        fqcn = str(entry.get("name", ""))
        pinned = entry.get("version")
        if not fqcn or "." not in fqcn or not pinned:
            missing.append(fqcn or repr(entry))
            continue
        namespace, _, name = fqcn.partition(".")
        if _installed_version(collections_dir, namespace, name) != str(pinned):
            missing.append(f"{fqcn}:{pinned}")
    return missing


def main() -> int:
    """Exit 0 when every pinned collection is present at its pinned version.

    Args:
        argv[1]: path to requirements.galaxy.yml.
        argv[2]: path to the collections directory.
    """
    missing = unsatisfied(Path(sys.argv[1]), Path(sys.argv[2]))
    if missing:
        print(" ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
