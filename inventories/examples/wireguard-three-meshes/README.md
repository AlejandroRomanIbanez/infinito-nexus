# WireGuard: three meshes around one hub

An inventory that declares **three** WireGuard meshes, to show that the number
of meshes and the hosts in them belong to the deployment rather than to this
repository. Nothing here is special-cased: the same CLI, role and planner
serve it.

## The topology

| mesh | subnet | port | hub | spokes |
|---|---|---|---|---|
| `alpha` | `10.100.10.0/24` | 51830 | `mesh-hub-01` | `svc-swarm-node` |
| `beta` | `10.100.11.0/24` | 51831 | `mesh-hub-01` | `svc-storage-nfs-server` |
| `gamma` | `10.100.12.0/24` | 51832 | `mesh-hub-01` | every `svc-bkp-` group |

`mesh-hub-01` is the hub of all three, which is what lets a spoke of one reach
a spoke of another: every spoke routes `routed_range` — the whole
`NETWORK_MESH_POOL` — through its hub. Two meshes with no host in common
cannot reach each other, by design.

## Running it

The mesh is written by one cross-host pass before the play, never by the role:

```bash
python3 -m cli.administration.inventory.mesh \
  --inventory   inventories/examples/wireguard-three-meshes/inventory.yml \
  --group-vars-file inventories/examples/wireguard-three-meshes/meshes.yml \
  --host-vars-dir <your host_vars dir> \
  --vault-password-file <your password file>
```

That writes each host's own block, and rewrites
`roles/svc-net-wireguard/meta/meshes.yml` from these declarations — the role
contract is generated, because the inventory validator refuses a key the role's
meta tree does not declare and these mesh names are not ones the repository
ships.

## What it does not show

Membership is resolved from inventory groups, and every group a host belongs to
must be a role (`tasks/stages/01_constructor.yml` asserts it). Two hosts of the
same role therefore join the same meshes: this example cannot put one
`svc-swarm-node` in `alpha` and another in `beta`. Splitting hosts that share a
role needs membership groups that are not roles, which is a decision about that
assertion rather than about the mesh.
