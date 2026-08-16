"""Turn a run's deploy jobs back into selection tokens.

A deploy job title carries the whole row it deployed -- role, variant, mode,
onion state -- and :mod:`utils.github.variant.selection` is the grammar that
writes it back down. Reading the tokens out of a finished run is what lets a
retrigger replay exactly what failed and start the regular line where that run
stopped, instead of aggregating to role ids and guessing the rest.
"""

from __future__ import annotations

from utils.github.variant import axes, selection

from .runs import _effective, _iter_deploy_jobs


def failed_selections(jobs: list[dict], *, strict: bool = False) -> list[str]:
    """The selection tokens that reproduce exactly what did not pass.

    A role aggregated to its id loses what actually broke: the retrigger then
    redeploys every variant of it, in whatever mode and onion state the sweep
    rotation happens to pick, and the combination that failed may not be among
    them. Each failed job therefore contributes its own
    ``role#variant@mode+tor`` token (:mod:`utils.github.variant.selection`), so
    the priority line replays that job and nothing else.

    Every mode is read; there is no scope to narrow to. A run that failed in
    swarm and in compose comes back as two tokens for the same role.

    Args:
        jobs: the source run's jobs.
        strict: only hard failures (❌) count; cancelled, timed out and still
            running are left out.

    Returns:
        sorted, deduplicated tokens.
    """
    tokens = set()
    for app, _mode, job in _iter_deploy_jobs(jobs):
        state = _effective(job)
        if state == "success" or (strict and state != "failure"):
            continue
        label = axes.parse_label(str(job.get("name", "")))
        tokens.add(
            selection.describe(
                selection.Pin(
                    app,
                    tuple(int(part) for part in label.variant.split(",") if part),
                    label.mode,
                    label.tor,
                )
            )
        )
    return sorted(tokens)


def deployed_selections(jobs: list[dict]) -> set[str]:
    """Every selection the source run actually deployed, green or red.

    The verdict is irrelevant here: what matters is that the run reached the
    row at all, because that is what a retrigger no longer has to repeat.
    """
    return {
        selection.describe(
            selection.Pin(
                app,
                tuple(int(part) for part in label.variant.split(",") if part),
                label.mode,
                label.tor,
            )
        )
        for app, _mode, job in _iter_deploy_jobs(jobs)
        if (label := axes.parse_label(str(job.get("name", "")))) is not None
    }


def resume_offset(regular: list[dict[str, str]], deployed: set[str]) -> str:
    """Where a retrigger should pick the regular line up again.

    The source run deployed a window of the ranking and stopped at its budget.
    Everything inside that window has a verdict -- the red rows come back on
    the priority line anyway -- so the regular line has no reason to walk it a
    second time. The answer is the last row of the leading run of deployed
    rows, as a selection token: a token still names the same row after the
    ranking shifts, a row count does not.

    Stops at the first gap. A hole inside the window means that row was
    filtered out, not that the run got further, and resuming past it would skip
    whatever follows.

    Args:
        regular: the regular line of the retrigger's own discovery, in ranking
            order.
        deployed: tokens the source run deployed (:func:`deployed_selections`).

    Returns:
        the token to resume at, or ``''`` when the source run deployed nothing
        of this line -- then the retrigger starts at the head, as it would
        without an offset.
    """
    resume = ""
    for entry in regular:
        token = selection.describe(
            selection.Pin(
                entry["apps"],
                tuple(
                    int(part)
                    for part in str(entry.get("variant", "")).split(",")
                    if part
                ),
                entry["mode"],
                entry["tor"] == "true",
            )
        )
        if token not in deployed:
            break
        resume = token
    return resume
