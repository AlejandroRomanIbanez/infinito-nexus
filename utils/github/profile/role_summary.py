"""Parse an Ansible `profile_roles` log and write the per-role runtimes to `$GITHUB_STEP_SUMMARY`.

When the log carries the matrix-deploy round markers emitted by
`cli.administration.deploy.development.deploy` (one `=== matrix-deploy: round
R/M ... PASS N (sync|async) ===` line per playbook run), the runtimes are split
into one table per variant round + pass. Without those markers (a plain,
non-matrix deploy) a single combined table is emitted.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LINE_RE = re.compile(
    r"^(?:.*\bINFO\|\s+)?(?P<name>\S.*?)\s-{2,}\s+(?P<seconds>\d+(?:\.\d+)?)s\s*$"
)
SEGMENT_RE = re.compile(
    r"matrix-deploy: round (?P<round>\d+)/(?P<rounds>\d+).*?"
    r"PASS (?P<pass>\d+) \((?P<mode>sync|async)\)"
)


def _strip_ansi(line: str) -> str:
    return ANSI_RE.sub("", line)


def _role_time(line: str) -> tuple[str, float] | None:
    """Return (role, seconds) for a profile_roles summary line, else None.

    Drops the `total` line and `<role> : <task>` profile_tasks entries so only
    real per-role rows survive.
    """
    match = LINE_RE.match(line)
    if not match:
        return None
    name = match.group("name").strip()
    if not name or name.lower() == "total" or " : " in name:
        return None
    try:
        return name, float(match.group("seconds"))
    except ValueError:
        return None


def _sorted_rows(totals: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def parse_role_times(log_path: Path) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            row = _role_time(_strip_ansi(raw).rstrip())
            if row:
                totals[row[0]] += row[1]
    return _sorted_rows(totals)


def parse_segments(log_path: Path) -> list[tuple[str, list[tuple[str, float]]]]:
    """Split the log by matrix-deploy round/pass markers.

    Returns a list of (label, rows) in encounter order. Lines before the first
    marker belong to no variant and are ignored. Returns [] when the log has no
    markers at all (caller falls back to a single combined table).
    """
    segments: list[tuple[str, dict[str, float]]] = []
    current: dict[str, float] | None = None
    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = _strip_ansi(raw).rstrip()
            marker = SEGMENT_RE.search(line)
            if marker:
                label = (
                    f"Round {marker.group('round')}/{marker.group('rounds')} · "
                    f"PASS {marker.group('pass')} ({marker.group('mode')})"
                )
                current = defaultdict(float)
                segments.append((label, current))
                continue
            if current is None:
                continue
            row = _role_time(line)
            if row:
                current[row[0]] += row[1]
    return [(label, _sorted_rows(totals)) for label, totals in segments]


def _format_table(
    rows: list[tuple[str, float]], *, title: str = "## ⏱️ Role runtimes"
) -> str:
    header = [
        title,
        "",
        "| # | Role | Duration |",
        "|---|------|---------:|",
    ]
    body = [
        f"| {idx} | `{name}` | {seconds:.2f}s |"
        for idx, (name, seconds) in enumerate(rows, start=1)
    ]
    return "\n".join(header + body) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: role_summary.py <ansible-log>", file=sys.stderr)
        return 2
    log_path = Path(argv[1])
    if not log_path.is_file():
        print(f"[role_summary] log not found: {log_path}", file=sys.stderr)
        return 0

    segments = [(label, rows) for label, rows in parse_segments(log_path) if rows]
    if segments:
        parts = ["## ⏱️ Role runtimes per variant (matrix round)", ""]
        parts.extend(_format_table(rows, title=f"### {label}") for label, rows in segments)
        table = "\n".join(parts) + "\n"
    else:
        rows = parse_role_times(log_path)
        if not rows:
            print("[role_summary] no profile_roles entries found", file=sys.stderr)
            return 0
        table = _format_table(rows)

    print(table)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as fh:
            fh.write(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
