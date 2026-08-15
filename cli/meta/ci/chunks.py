"""Split the ordered discovery rows into the serial chunks of one sweep.

A *sweep* is one orchestrator run. It deploys its rows in serial chunk
blocks, each small enough that its last runner wave still starts inside the
queue window (:mod:`cli.meta.ci.slots` sizes them). Two rules shape the split:

* **Priority first, never mixed.** Priority rows sort to the head of the list
  and the split forces a chunk boundary at the priority/regular seam, so a
  chunk is either all priority or all regular. The seam chunk stays short
  rather than being topped up with regular rows -- that is what guarantees
  every priority row is done before the first regular one starts. Priority is
  never subject to the sweep offset: it leads every sweep.

* **The regular tail rotates.** A sweep cannot always afford every row (the
  run job cap bounds it), so the regular rows start at an offset that
  advances by the sweep's own capacity. Consecutive sweeps therefore walk the
  whole list instead of re-testing the same head forever. The offset is a
  closed form over the sweep number, so no state is carried between runs.

The rotation deliberately does NOT apply when every regular row fits: with
nothing to leave behind there is nothing to rotate to, and a stable order
keeps the plan output comparable between runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TypeVar

    T = TypeVar("T")


def slice_chunks(rows: Sequence[T], size: int) -> list[list[T]]:
    """Cut *rows* into consecutive blocks of at most *size*."""
    if size < 1:
        raise ValueError(f"chunk size must be >= 1, got {size}")
    return [list(rows[start : start + size]) for start in range(0, len(rows), size)]


def offset(count: int, capacity: int, sweep: int) -> int:
    """Where a sweep starts reading the regular rows.

    Args:
        count: regular rows available.
        capacity: regular rows this sweep can afford.
        sweep: sweep number; consecutive numbers walk the list.

    Returns:
        the start index, or 0 when the whole list fits (nothing is left
        behind, so there is nothing to rotate towards).
    """
    if count < 1 or capacity < 1 or capacity >= count:
        return 0
    return (sweep * capacity) % count


def plan(
    priority: Sequence[T],
    regular: Sequence[T],
    *,
    sweep: int,
    size: int,
    blocks: int,
    budget: int,
) -> list[list[T]]:
    """The chunks one sweep deploys, priority blocks first.

    Args:
        priority: rows of the priority line, in query order.
        regular: rows of the regular line, in query order.
        sweep: sweep number, driving the regular rotation.
        size: rows one chunk may hold (``slots.chunk_size``).
        blocks: chunk blocks the workflow declares (``slots.chunk_count``).
        budget: rows the run job cap allows in total (``slots.available``).

    Returns:
        at most *blocks* chunks, none larger than *size*, together holding at
        most *budget* rows. Priority chunks come first and are never topped up
        with regular rows.
    """
    priority_chunks = slice_chunks(priority[:budget], size)[:blocks]
    spent = sum(len(chunk) for chunk in priority_chunks)
    capacity = max(min((blocks - len(priority_chunks)) * size, budget - spent), 0)
    if not capacity or not regular:
        return priority_chunks
    start = offset(len(regular), capacity, sweep)
    rotated = [*regular[start:], *regular[:start]]
    return priority_chunks + slice_chunks(rotated[:capacity], size)
