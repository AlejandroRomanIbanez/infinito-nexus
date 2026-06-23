# Roundtrip Loop

Use this page for validating one or more roles across **every deploy mode in order** (compose, then swarm) as a breadth-first cross-mode parity gate, rather than a focused single-mode debug session.
For debugging the compose deploy of one role, see [Role Loop](role.md); for the swarm / Act side, see [Workflow Loop](workflow.md); for spec-level inner-loop iteration, see [Playwright Spec Loop](playwright.md).

## When to use

- Use the roundtrip loop to **confirm parity**: a role (or a set of roles) must come up green in compose AND swarm. It is the end-of-change regression sweep, not the place to debug a fresh failure.
- While you are actively debugging one mode, use the focused loops instead: [Role Loop](role.md) for the compose deploy, [Workflow Loop](workflow.md) plus the `act-swarm-*` targets for the swarm deploy. Return to the roundtrip once both modes pass in isolation.

## Rules

- Invoke with `make roundtrip apps="<app> [app...]"`. Each app is taken through the mode sequence in order, and the run stops at the first failure (fail-fast).
- With no `apps=`, the loop defaults to **every application, most-complex first** (the `complexity` CLI: `infinito meta roles applications complexity --sort total --order desc --format string`). That is a large run (one compose plus one swarm deploy per app), so narrow it with `apps=` while iterating.
- The mode sequence defaults to `compose swarm` and is overridable with `modes="compose swarm"`. The order is always compose first, so the cheaper mode fails fast before the expensive swarm rebuild. Append `k8s` here once that mode exists.
- Per step the output is streamed to `${TMPDIR:-/tmp}/roundtrip-<app>-<mode>.log`. Tell the operator the exact `tail -f` path for the running step.
- The compose step runs `compose-deploy mode=reinstall apps=<app> full_cycle=true variant=0`; the swarm step runs `act-swarm-zombie app=<app>`, so the cluster is named `<app>-swarm-mgr-01` etc. via the mandatory `SWARM_NAME` (the app id is the default cluster id). Each validated swarm cluster is released afterwards unless you pass `keep=true`.
- `make autoformat` and `make test` MUST be green before a roundtrip; the loop does not re-run them per app.

## Debugging a failed step

The roundtrip is a gate, not a debugger: when a step goes red it stops and leaves the evidence in place. Do NOT just re-run the roundtrip; drop into the matching focused loop.

- Read `${TMPDIR:-/tmp}/roundtrip-<app>-<mode>.log` to see which app and mode failed, and the first error.
- If the **compose** step failed, switch to the [Role Loop](role.md): reproduce with `make compose-deploy mode=update apps=<app>`, inspect via `make compose-exec` / `make compose-inner-run`, apply the real fix in the repository, then re-run the roundtrip.
- If the **swarm** step failed, the cluster is left up (fail-fast skips the release). Inspect it with `make act-swarm-exec node=<app>-swarm-mgr-01 cmd='...'` or `make act-swarm-shell name=<app>` per the [Workflow Loop](workflow.md), confirm the fix on the live cluster, then re-run. Release it manually with `make act-swarm-down name=<app>` when done.
- Validate every candidate fix on live state BEFORE the next roundtrip; a swarm rebuild costs tens of minutes (same rule as the focused loops). In-cluster edits are validation only, the repo change is the real fix.
- Once the failing mode is green in its focused loop, re-run the full roundtrip to re-confirm parity across all modes.

## Gotchas

- On a recent Docker engine the swarm step can abort at job setup; run `make act-runner-image` once and prefix the run with `ACT_PLATFORM_IMAGE=local/act-runner-fixed:latest` (see [Workflow Loop](workflow.md)).
- A swarm step killed mid-NFS-setup can wedge the host kernel NFS server: the privileged DinD nodes get stuck in kernel D-state and survive `docker rm -f` and even `systemctl restart docker`, so the next swarm step hangs at `Reload NFS exports`. Clearing it needs a host-level `umount -f -l /var/lib/infinito` + `exportfs -ua` + `docker rm -f`, or a reboot. No make target can kill a D-state process.
- Distinct `SWARM_NAME` per app means several apps can keep their clusters in parallel under `keep=true`; release each one with `make act-swarm-down name=<app>`.
