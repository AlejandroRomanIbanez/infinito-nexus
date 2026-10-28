from __future__ import annotations

import os
import shutil
import subprocess
import time

from utils import PROJECT_ROOT
from utils.env.runtime import (
    mem_available_mb,
    mem_stall_pct,
    mem_total_mb,
    pressure_pct,
)

DISK_FLOOR_MB = 6 * 2**10
MEM_FLOOR_RATIO = 0.06
TOP_EVERY_TICKS = 20
TOP_ROWS = 12


def _abort(proc: subprocess.Popen[bytes], banner: str, probe: list[str]) -> int:
    print(banner, flush=True)
    subprocess.run(probe, check=False)
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return 75


def top_processes(rows: int = TOP_ROWS) -> list[str]:
    """Return the busiest processes of the runner over a 3 s window.

    The lab nodes are containers on the runner's kernel, so this sees every
    nested container process too. The first ``top`` frame averages over each
    process's lifetime; only the second frame covers the window.

    Args:
        rows: how many process lines to return.

    Returns:
        ``"<%CPU> <command>"`` lines, busiest first; empty when ``top`` fails.
    """
    try:
        out = subprocess.run(
            ["top", "-b", "-n", "2", "-d", "3", "-o", "%CPU", "-w", "200"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    frame = out.rsplit("\n\n", 2)[-1].splitlines()
    header = next((i for i, line in enumerate(frame) if "%CPU" in line), None)
    if header is None:
        return []
    columns = frame[header].split()
    cpu, command = columns.index("%CPU"), columns.index("COMMAND")
    lines = []
    for line in frame[header + 1 :]:
        fields = line.split(None, command)
        if len(fields) > command:
            lines.append(f"{fields[cpu]} {fields[command]}")
        if len(lines) == rows:
            break
    return lines


def run_step(cmd: list[str], *, env: dict[str, str], label: str) -> int:
    """Announce a matrix step, run it, and report what it cost.

    Args:
        cmd: argv of the step.
        env: environment the step runs with.
        label: phase name for the banners.

    Returns:
        The step's exit code.
    """
    print(f"=== swarm-matrix: {label} ===", flush=True)
    started = time.monotonic()
    rc = run_watched(cmd, env=env)
    print(
        f"=== swarm-matrix: {label} took {time.monotonic() - started:.0f}s (rc={rc}) ===",
        flush=True,
    )
    return rc


def run_watched(cmd: list[str], *, env: dict[str, str]) -> int:
    """Run a step, aborting visibly before the runner disk or RAM fills.

    The Actions Worker dies silently on ENOSPC while writing its own logs, so
    a full disk truncates the job without diagnostics; terminating the step at
    DISK_FLOOR_MB keeps enough room for rescue artifacts and the log upload.

    Args:
        cmd: argv of the step.
        env: environment the step runs with.

    Returns:
        The step's exit code, or the abort code when a floor was hit.
    """
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env)
    ticks = 0
    while True:
        try:
            return int(proc.wait(timeout=30))
        except subprocess.TimeoutExpired:
            ticks += 1
            if ticks % TOP_EVERY_TICKS == 0:
                print(
                    "=== swarm-matrix: top cpu " + " | ".join(top_processes()) + " ===",
                    flush=True,
                )
            free_mb = shutil.disk_usage("/").free // 2**20
            if free_mb < DISK_FLOOR_MB:
                return _abort(
                    proc,
                    "=== swarm-matrix: DISK EXHAUSTION IMMINENT "
                    f"(<{DISK_FLOOR_MB}M free on /) - aborting step ===",
                    ["df", "-h", "/"],
                )
            avail = mem_available_mb()
            total = mem_total_mb()
            stall = mem_stall_pct()
            print(
                f"=== swarm-matrix: host mem {avail}M/{total}M available, "
                f"disk {free_mb}M free on /, stall60 {stall:.1f}%, "
                f"cpu60 {pressure_pct('cpu', 'some'):.1f}%, "
                f"io60 {pressure_pct('io', 'some'):.1f}%, "
                f"load1 {os.getloadavg()[0]:.1f}/{os.cpu_count()} ===",
                flush=True,
            )
            if total and avail < total * MEM_FLOOR_RATIO:
                return _abort(
                    proc,
                    "=== swarm-matrix: MEMORY EXHAUSTION IMMINENT "
                    f"({avail}M available, below {MEM_FLOOR_RATIO:.0%} of RAM)"
                    " - aborting step ===",
                    ["free", "-m"],
                )
