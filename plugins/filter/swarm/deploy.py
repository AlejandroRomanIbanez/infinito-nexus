"""Filters ``swarm_deploy_replicas`` and ``swarm_deploy``: the swarm ``deploy:`` block of one service.

``roles/sys-svc-container/templates/deploy.yml.j2`` gathers the values (lookups,
``resource_filter`` reads and the caller's template variables) and these
filters decide what the block holds: replicas, labels, placement, rolling
update, restart policy and resources.
"""

from __future__ import annotations

from typing import Any

from plugins.filter.swarm.placement import swarm_placement_constraints


def swarm_deploy_replicas(ctx: dict[str, Any]) -> Any:
    """Return what ``lookup('compose_replicas')`` receives, ``''`` for the topology default.

    Args:
        ctx: the inputs ``deploy.yml.j2`` gathers; reads ``db_instance``,
            ``replicas_forced`` (None when the caller forces none) and
            ``replicas_declared`` (the service's ``replicas``, ``''`` if unset).
    """
    if ctx["db_instance"]:
        return 1
    if ctx["replicas_forced"] is not None:
        return ctx["replicas_forced"]
    return ctx["replicas_declared"]


def _labels(ctx: dict[str, Any]) -> list[str]:
    labels = []
    if ctx["db_instance"] and ctx["seeded_after_converge"] is True:
        labels.append(ctx["seed_wait_label"])
    if ctx["db_endpoint"]:
        labels.append(ctx["db_endpoint_label"])
    return labels


def _constraints(ctx: dict[str, Any]) -> list[str]:
    placement = (ctx["placement"] or "").strip()
    constraints = []
    if ctx["db_instance"]:
        constraints.append(
            f"node.labels.{ctx['host_id_label']} == {ctx['db_instance']['host']}"
        )
    elif ctx["max_replicas_per_node"] is not None:
        pass
    elif placement:
        constraints.extend(
            swarm_placement_constraints(
                placement, ctx["managers"], ctx["stack_host_label"]
            )
        )
    elif ctx["manager_placed"]:
        constraints.extend(
            swarm_placement_constraints(
                "manager", ctx["managers"], ctx["stack_host_label"]
            )
        )
    if ctx["arch"] != "":
        constraints.append(f"node.platform.arch == {ctx['arch']}")
    if ctx["kata_group"]:
        operator = "==" if ctx["kata_enabled"] else "!="
        constraints.append(f"node.labels.{ctx['sandbox_label']} {operator} true")
    return constraints


def swarm_deploy(ctx: dict[str, Any], replicas_line: str) -> str:
    """Render the ``deploy:`` block, indented for a service under ``services:``.

    Args:
        ctx: the inputs ``deploy.yml.j2`` gathers, see its keys there.
        replicas_line: what ``lookup('compose_replicas')`` returned.

    Returns:
        The block without its final newline.
    """
    lines = ["    deploy:", f"      {replicas_line}"]
    labels = _labels(ctx)
    if labels:
        lines.append("      labels:")
        lines.extend(f'        {label}: "true"' for label in labels)
    constraints = _constraints(ctx)
    if constraints or ctx["max_replicas_per_node"] is not None:
        lines.append("      placement:")
        if ctx["max_replicas_per_node"] is not None:
            lines.append(
                f"        max_replicas_per_node: {ctx['max_replicas_per_node']}"
            )
        if constraints:
            lines.append("        constraints:")
            lines.extend(f"          - {constraint}" for constraint in constraints)
    delay = "0s" if replicas_line == "replicas: 1" else ctx["update_delay"]
    lines += [
        "      update_config:",
        f"        parallelism: {ctx['update_parallelism']}",
        f"        delay: {delay}",
        "        failure_action: continue",
    ]
    if ctx["update_order"] is not None:
        lines.append(f"        order: {ctx['update_order']}")
    resources = ctx["resources"]
    lines += [
        "      restart_policy:",
        f"        condition: {ctx['restart_condition']}",
        "      resources:",
        "        limits:",
        f'          cpus: "{resources["cpus"]}"',
        f"          memory: {resources['mem_limit']}",
        f"          pids: {resources['pids_limit']}",
    ]
    if ctx["runtime"] != "github":
        lines += [
            "        reservations:",
            f"          memory: {resources['mem_reservation']}",
        ]
    return "\n".join(lines)


class FilterModule:
    def filters(self) -> dict[str, Any]:
        return {
            "swarm_deploy_replicas": swarm_deploy_replicas,
            "swarm_deploy": swarm_deploy,
        }
