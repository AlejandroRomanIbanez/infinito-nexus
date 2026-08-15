"""Render CI deploy-job display names from their workflow source of truth.

Single point of truth for test fixtures so they cannot drift back to job
names GitHub never emits -- the bug that silently made ``--failed swarm`` a
no-op was masked by fixtures hand-typed as ``🐳 Compose web-app-x``, which no
real job is ever called.

Since the deploy modes collapsed into one workflow, a job's mode is no longer
in the workflow file name but in the row's own label, so the glyph prefix is
built here the same way ``utils.github.variant.axes`` builds it.
"""

from __future__ import annotations

import re

from tests.utils import PROJECT_ROOT
from utils.cache.files import read_text
from utils.github.variant.axes import TOR_DEPLOY_MODES
from utils.roles.display import display_names
from utils.symbol_glossary import to_emoji

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

DEPLOY_WORKFLOW = "call-test-deploy.yml"

_MODE_NAMES = {"docker": "compose", "swarm": "swarm", "host": "host"}

_NAME_RE = re.compile(r"name: (.+)$", re.MULTILINE)


def orchestrator_prefix(chunk: int = 0) -> str:
    """The caller path GitHub prepends to a chunk's nested deploy jobs."""
    return f"🎶 Orchestrate CI / test-deploy-chunk-{chunk} / "


def _template(job_id: str) -> str:
    block = re.search(
        rf"^  {job_id}:\n((?:    .*\n)+)",
        read_text(str(WORKFLOWS / DEPLOY_WORKFLOW)),
        re.MULTILINE,
    )
    assert block, f"job '{job_id}' not found in {DEPLOY_WORKFLOW}"
    name = _NAME_RE.search(block.group(1))
    assert name, f"no name: in job '{job_id}' of {DEPLOY_WORKFLOW}"
    return name.group(1).strip().strip('"').strip("'")


def discover_job_name(chunk: int, distros: str, marker: str = "") -> str:
    """The job display name GitHub emits for a chunk's discover step.

    Args:
        chunk: chunk index the block deploys.
        distros: the distro list the run swept.
        marker: suffix, e.g. ``' ⭐'`` for a priority chunk.
    """
    rendered = _template("discover").replace("${{ inputs.index }}", str(chunk))
    rendered = rendered.replace("${{ inputs.distros }}", distros)
    return rendered.replace("${{ inputs.marker }}", marker)


def row_label(
    mode: str, app: str, variant: str = "", *, tor: bool = False, priority: bool = False
) -> str:
    """The ``matrix.label`` axes assigns to one row: mode glyph, tor glyph on
    the modes that carry the onion axis, display name, and the priority star."""
    deploy_mode = _MODE_NAMES[mode]
    glyphs = to_emoji(deploy_mode)
    if deploy_mode in TOR_DEPLOY_MODES:
        glyphs += to_emoji("tor" if tor else "clearnet")
    label = f"{glyphs}{display_names().encode(app, variant)}"
    return f"{label} {to_emoji('priority')}" if priority else label


def deploy_job_name(
    mode: str,
    app: str,
    variant: str = "",
    *,
    tor: bool = False,
    priority: bool = False,
    chunk: int = 0,
    orchestrated: bool = True,
) -> str:
    """The job display name GitHub emits for an ``app`` deploy in ``mode``.

    Args:
        mode: ``'docker'`` (compose), ``'swarm'`` or ``'host'``.
        app: role id, e.g. ``'web-app-matomo'``.
        variant: the row's variant index, e.g. ``'0'`` (``''`` = none).
        tor: whether the row deploys behind the node onion.
        priority: whether the row belongs to the priority line.
        chunk: chunk index, for the orchestrator prefix.
        orchestrated: include the ci-orchestrator caller prefix (real runs do).
    """
    rendered = _template("deploy").replace(
        "${{ matrix.label }}",
        row_label(mode, app, variant, tor=tor, priority=priority),
    )
    return (orchestrator_prefix(chunk) if orchestrated else "") + rendered
