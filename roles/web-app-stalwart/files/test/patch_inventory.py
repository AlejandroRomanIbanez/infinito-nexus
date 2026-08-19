#!/usr/bin/env python3
"""Patch a copied dev inventory for the migration e2e state machine.

Args:
    inventory_dir: inventory copy to patch in place.
    --mail-provider: value for the top-level MAIL_PROVIDER host var.
    --import-mailu:  true|false for
        applications.web-app-stalwart.services.stalwart.migration.import_mailu.

The target file is the host_vars YAML that carries the baked
``applications:`` map (host_vars beat the playbook's group_vars, which is
why the override cannot ride an inventory group_vars file).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utils.cache.yaml import dump_yaml, load_yaml_any


def _candidate_files(inventory_dir: Path) -> list[Path]:
    host_vars = inventory_dir / "host_vars"
    files = sorted(host_vars.glob("*.yml")) if host_vars.is_dir() else []
    return files or sorted(
        p for p in inventory_dir.glob("*.yml") if p.name != "devices.yml"
    )


def _pick_target(files: list[Path]) -> Path:
    for path in files:
        data = load_yaml_any(str(path), default_if_missing={})
        if isinstance(data, dict) and "applications" in data:
            return path
    if not files:
        raise SystemExit("patch_inventory: no host_vars YAML found")
    return files[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory_dir")
    parser.add_argument("--mail-provider", required=True)
    parser.add_argument("--import-mailu", required=True, choices=["true", "false"])
    args = parser.parse_args()

    target = _pick_target(_candidate_files(Path(args.inventory_dir)))
    data = load_yaml_any(str(target), default_if_missing={})
    if not isinstance(data, dict):
        raise SystemExit(f"patch_inventory: {target} is not a mapping")

    data["MAIL_PROVIDER"] = args.mail_provider

    node = data.setdefault("applications", {})
    for key in ("web-app-stalwart", "services", "stalwart", "migration"):
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    node["import_mailu"] = args.import_mailu == "true"

    dump_yaml(target, data)
    print(
        f"patched {target}: MAIL_PROVIDER={args.mail_provider} "
        f"import_mailu={args.import_mailu}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
