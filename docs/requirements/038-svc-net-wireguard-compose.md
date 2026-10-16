# 038 - svc-net-wireguard: Full-Mesh WireGuard for Compose Deployments

## User Story

As an operator running Compose deployments on several hosts, I want those hosts joined by full-mesh WireGuard networks that each role opts into from the inventory, so that host-to-host traffic is tunnelled without a swarm manager and without WireGuard hardcoded into any role.

## Acceptance Criteria

- [x] Every role that ships a container stack carries `networks.meshes` in its `meta/networks.yml`, empty, and a lint fails a stack role without it.
- [x] With no `svc-swarm-manager` host in the inventory, `cli.administration.inventory.mesh` plans every declared mesh as a full mesh: each member lists every other member as a peer, with that peer's `/32` as `AllowedIPs`.
- [x] With no `svc-swarm-manager` host, the CLI reads the declared meshes from every host that declares any, and refuses hosts that declare different meshes.
- [x] In a full mesh, every member listens on the mesh port and dials every peer with a keepalive.
- [x] In a full mesh, the gate waits for a handshake with every peer and probes the MTU against each of them.
- [x] With a `svc-swarm-manager` host in the inventory, the host_vars the CLI writes and the `wg.conf` the role renders are unchanged.
- [x] Under `auto`, the `vpn` axis rotates on Compose rows of a role's smallest variant, and only there; `enforced` and `disabled` hold those rows on one side.
- [x] A Compose row of a role's smallest variant carries 🚇 or 🛣️ in its title, and every other Compose title is unchanged.
- [ ] A Compose row with `vpn` on deploys `svc-net-wireguard` beside the role, and the CLI test of `svc-net-wireguard` runs in that deploy.
- [x] The CLI test builds three throwaway hosts from one inventory with two full meshes. Host II joins both, and the membership comes from role fields.
- [x] The CLI test deploys `playbook-mesh.yml` onto those hosts, and the role installs WireGuard there; the image ships none.
- [x] The CLI test proves that I and II reach each other, that II and III reach each other, and that I and III do not.
- [x] The role README describes Compose use and what it means in production.
- [ ] A Compose CI row with `vpn` on passes, and its log shows the CLI test's three reachability assertions.
