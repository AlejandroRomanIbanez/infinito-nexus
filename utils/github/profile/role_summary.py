"""Parse an Ansible log produced with the ``profile_roles`` callback and write the
top-N slowest roles to ``$GITHUB_STEP_SUMMARY`` as a Markdown table.

Usage: ``role_summary.py <ansible-log-path>``

Env:
  INFINITO_PROFILE_TOP_N  Top-N role rows to emit (default: 20)
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_TOP_N = 20
TOP_N_ENV_KEY = "INFINITO_PROFILE_TOP_N"  # nocheck: CI-only top-N knob for the role-summary step; not part of infra env
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LINE_RE = re.compile(r"^(?P<name>.+?)\s-{2,}\s+(?P<seconds>\d+(?:\.\d+)?)s\s*$")


def _strip_ansi(line: str) -> str:
    return ANSI_RE.sub("", line)


def parse_role_times(log_path: Path) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = _strip_ansi(raw).rstrip()
            match = LINE_RE.match(line)
            if not match:
                continue
            name = match.group("name").strip()
            if not name or name.lower() == "total" or " : " in name:
                continue
            try:
                seconds = float(match.group("seconds"))
            except ValueError:
                continue
            totals[name] += seconds
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def _format_table(rows: list[tuple[str, float]], top_n: int) -> str:
    header = [
        "## ⏱️ Top role runtimes",
        "",
        "| # | Role | Duration |",
        "|---|------|---------:|",
    ]
    body = [
        f"| {idx} | `{name}` | {seconds:.2f}s |"
        for idx, (name, seconds) in enumerate(rows[:top_n], start=1)
    ]
    return "\n".join(header + body) + "\n"


def _read_top_n() -> int:
    raw = os.environ.get(TOP_N_ENV_KEY)
    if not raw:
        return DEFAULT_TOP_N
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TOP_N
    return value if value > 0 else DEFAULT_TOP_N


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: role_summary.py <ansible-log>", file=sys.stderr)
        return 2
    log_path = Path(argv[1])
    if not log_path.is_file():
        print(f"[role_summary] log not found: {log_path}", file=sys.stderr)
        return 0
    rows = parse_role_times(log_path)
    if not rows:
        print("[role_summary] no profile_roles entries found", file=sys.stderr)
        return 0
    top_n = _read_top_n()
    table = _format_table(rows, top_n)
    print(table)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as fh:
            fh.write(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
