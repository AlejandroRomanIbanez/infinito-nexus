"""Single source of truth for the CI app-discovery query.

Usage:
  python -m cli.meta.ci.query --mode compose|swarm|host [--format json]

Both the production discovery (scripts/meta/resolve/apps.sh) and the
deploy-plan table (cli.meta.ci.plan) resolve role lists through this
module, so the plan shows exactly the query the run executes: the same
filter (mode + INFINITO_WHITELIST + INFINITO_BLACKLIST), the same
INFINITO_DISCOVERY_SORT order, compose's --unique coverage dedup, the
lifecycle envelope, and the INFINITO_MAX_JOBS cap ('auto' resolves per
mode via cli.meta.ci.slots). ``capped=False`` returns the full ordered
candidate list so callers can show what fell behind the budget cut.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from cli.meta.ci import slots
from utils.cache.files import PROJECT_ROOT, read_text

MODES = ("compose", "swarm", "host")


def build_filter(mode: str, whitelist: str = "", blacklist: str = "") -> str:
    parts = [f"test_{mode} == true"]
    include = ",".join(whitelist.split())
    if include:
        parts.append(f"name %% {{{include}}}")
    exclude = ",".join(blacklist.split())
    if exclude:
        parts.append(f"not (name %% {{{exclude}}})")
    return " and ".join(parts)


def _sort_spec() -> str:
    spec = os.environ.get("INFINITO_DISCOVERY_SORT", "")
    if spec.strip():
        return spec
    for line in read_text(str(PROJECT_ROOT / "default.env")).splitlines():
        if line.startswith("INFINITO_DISCOVERY_SORT="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def max_jobs(mode: str) -> int:
    raw = os.environ.get("INFINITO_MAX_JOBS", "auto").strip()
    if raw == "auto" or not raw:
        return slots.mode_slots()[mode]
    return int(raw)


def discover(
    mode: str,
    *,
    whitelist: str = "",
    blacklist: str = "",
    lifecycles: str = "",
    capped: bool = True,
) -> list[str]:
    """The ordered role list the discovery query yields for *mode*."""
    args = [
        sys.executable,
        "-m",
        "cli.meta.roles.applications.complexity",
        "--deploy-mode",
        mode,
        "--filter",
        build_filter(mode, whitelist, blacklist),
        "--sort",
        _sort_spec(),
        "--format",
        "string",
    ]
    if mode == "compose":
        args.append("--unique")
    envelope = lifecycles or os.environ.get("INFINITO_LIFECYCLES", "")
    if envelope.strip():
        args += ["--lifecycles", envelope]
    if capped:
        args += ["--max-jobs", str(max_jobs(mode))]
    out = subprocess.run(
        args, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the CI app-discovery query for one deploy mode."
    )
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--format", choices=("json",), dest="fmt")
    args = parser.parse_args(argv)

    roles = discover(
        args.mode,
        whitelist=os.environ.get("INFINITO_WHITELIST", ""),
        blacklist=os.environ.get("INFINITO_BLACKLIST", ""),
    )
    if args.fmt == "json":
        print(json.dumps(roles))
    else:
        print("\n".join(roles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
