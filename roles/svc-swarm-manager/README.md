# Docker Swarm Manager

## Description

[Docker Swarm](https://docs.docker.com/engine/swarm/) groups Docker
hosts into a single virtual host. Managers run the Raft store and accept
service-API calls. This group holds 1 host, or an odd number of at least 3
for Raft-quorum HA.
The first host is `STACK_HOST`; listing an existing worker here promotes it on
the next run. No run demotes or removes a manager except `make swarm-forget-node`.

## Overview

This role is a group-name tag. It exists so the project's inventory
validator accepts `svc-swarm-manager` as a legitimate
application_id. The actual swarm-init logic lives in `svc-swarm-node`
and dispatches on `'svc-swarm-manager' in group_names`.

## Cosmos

The diagram places Docker Swarm Manager in the Infinito.Nexus cosmos: the components it deploys (capabilities), the central services it consumes (dependencies), and its outward reach (federation and bridged external networks).

```mermaid
flowchart LR
    subgraph deps [Dependencies]
        dep_svc_swarm_node["svc-swarm-node 💻"]
    end
    subgraph role [svc-swarm-manager 💻]
        svc_node["node"]
        svc_manager["manager"]
    end
    dep_svc_swarm_node -. "0..1" .-> svc_node
```

Solid `1:1` edges are fixed relationships; dashed `0..1` edges are conditional (enabled only in matching deployments); red `0..0` edges are turned off in this role. Node markers show the role's deploy modes (💻 host, 🐳 compose, 🐝 swarm); ❌ marks a service that is explicitly turned off, and ⚙️ an Ansible role dependency declared in `meta/main.yml`.

## Features

- **Marker role:** Carries no tasks; selects which `svc-swarm-node`
  member runs the manager-init flow.

## Forgetting a Lost Node

A partition looks the same as a dead node, so declaring a node permanently
gone is an administrator decision. Remove the host from every inventory group
(reorder `svc-swarm-manager` if it was the first manager), then run:

```bash
make swarm-forget-node host=<name> inventory=<file> args="--password-file <file>"
```

The target refuses while the host is still in the inventory, and refuses
unless Swarm reports the node `Down`; there is no force option. It then chains
into the normal swarm deploy (`infinito administration deploy swarm <file>
-e SWARM_FORGET_NODE=<name>`), whose first manager demotes the node if it was
a manager, runs `docker node rm`, removes its etcd member and runs
`SENTINEL RESET *` on the Redis Sentinels. The same run removes the instance
services of every host that left an engine group with an explicit
`docker service rm`.

There is no self-healing and no node reaper. Between a loss and its
replacement each engine runs 2 of 3 instances, and the HA promise covers the
first loss only. Getting back to 3 instances always means listing a host in
the engine group and re-running the deploy: the new instance clones itself,
and a new etcd member is registered and joins the running cluster.

## Quick Setup

### Development

Clone, set up the workstation, and deploy Docker Swarm Manager onto the local stack:

```bash
git clone https://github.com/infinito-nexus/core.git
cd core
make onboard
make compose-deploy mode=reinstall apps=svc-swarm-manager full_cycle=false
```

### Production

Install Docker Swarm Manager directly onto the target machine: clone the repository, install the OS prerequisites and the repository toolchain, then deploy against localhost over a local connection (no SSH, no container):

```bash
git clone https://github.com/infinito-nexus/core.git
cd core
bash scripts/install/package.sh
make install
source scripts/meta/env/load.sh

APP=svc-swarm-manager
DOMAIN=<your-domain>
TLS_MODE=self_signed
SSH_PUBLIC_KEY="<your-ssh-public-key>"
INVENTORY=inventories/production
infinito administration inventory provision "$INVENTORY" \
  --inventory-file "$INVENTORY/devices.yml" \
  --host localhost \
  --include "$APP" \
  --vars "{\"TLS_MODE\": \"$TLS_MODE\", \"DOMAIN_PRIMARY\": \"$DOMAIN\", \"users\": {\"administrator\": {\"authorized_keys\": [\"$SSH_PUBLIC_KEY\"]}}}"
infinito administration deploy dedicated "$INVENTORY/devices.yml" \
  --password-file "$INVENTORY/.password" \
  --diff -vv
```

## Credits

Implemented by **[Kevin Veen-Birkenbach](https://www.veen.world)**.
Part of the [Infinito.Nexus Project](https://s.infinito.nexus/code) and maintained by [Kevin Veen-Birkenbach](https://www.veen.world).
Licensed under the [Infinito.Nexus Community License (Non-Commercial)](https://s.infinito.nexus/license).
