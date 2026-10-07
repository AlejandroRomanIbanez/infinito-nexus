# 037 - Database Cluster on Kubernetes

## User Story

As a platform administrator, I want Infinito.Nexus to run its central Postgres, MariaDB, Redis and OpenLDAP engines as highly available database clusters on Kubernetes, so that losing any one node loses no acknowledged database write and stops writes for at most 90 seconds, without changing a single application role.

## Context

Today every central engine (`svc-db-postgres`, `svc-db-mariadb`, `svc-db-redis`, `svc-db-openldap`) runs as one container on one host, in compose and in swarm mode alike. Each role's `meta/services.yml` already says it stays "single-node until replication is in scope". Swarm cannot close that gap without writing our own operators. Kubernetes can, because mature operators exist for three of the four engines. The fourth, OpenLDAP, needs only a small writer-election helper inside the slapd image the project already builds.

This requirement brings in `kubernetes` as the third deployment mode (`compose → swarm → kubernetes`, see [023](023-docker-swarm-nfs.md)) and uses it for the data tier only:

1. **A Kubernetes foundation**, sized to what the data tier needs:
   - the mode trigger and the inventory shape;
   - a reference cluster that Infinito.Nexus bootstraps itself (k3s);
   - an engine-local storage class;
   - an operator install layer;
   - cluster add-ons: cert-manager, K8up for file-level backups, and a node reaper that finishes forgetting a dead node for every engine;
   - an image path.
2. **One database cluster per engine:**
   - CloudNativePG for Postgres;
   - mariadb-operator for MariaDB;
   - the OT redis-operator for Redis with Sentinel;
   - a self-rendered syncrepl StatefulSet for OpenLDAP, with writer election inside each pod.
3. **Cross-cutting pieces:** backups to a write-only target outside the cluster, NetworkPolicy and Pod Security, and an acceptance suite that proves failover under real faults.

**The seam stays unchanged.** Applications keep consuming `lookup('database')` and `lookup('engine')`. In kubernetes mode only `host` changes: it becomes the database cluster's write endpoint. Real applications arrive with the Kubernetes render backend in a later requirement. Until then, the acceptance suite's test client is the only consumer.

**Terms used below:**

| Term | Meaning |
|---|---|
| **Database cluster** | The HA form of one central engine on Kubernetes: several instances on different nodes behind one write endpoint that follows failover. Its goal is HA, not horizontal scale. |
| **Write endpoint** | The one Service that always points at the current primary and follows failover (`postgres-rw`, `mariadb-primary`, `redis-master`, and `openldap`, which follows writer election). |
| **Writer election** | How a database cluster without an operator (OpenLDAP) keeps exactly one instance taking writes. The instances compete for a Lease, the winner becomes the writer behind the write endpoint, and an instance that loses or cannot renew the Lease makes itself read-only. |
| **Standalone form** | An engine rendered with one instance and no replication, for the 1-node lab. It is documented as non-HA. |
| **Residual step** | An imperative step that no operator resource covers. It runs through the Kubernetes API inside the pod behind the write endpoint. |
| **API host** | The one inventory host that holds the kubeconfig and runs every `kubernetes.core` task. It is the stack host in kubernetes mode. |
| **Reference cluster** | The k3s cluster that Infinito.Nexus bootstraps itself, for the lab, CI and self-hosters who bring no cluster. |
| **BYO cluster** | Any conformant Kubernetes cluster the administrator already runs, reached only through its API. |
| **Server** | A reference-cluster node that holds a control-plane and etcd member and also runs workloads. |
| **Engine-local class** | The volume class for database cluster data: one node-local volume per instance, with no storage-level replication. |
| **Forgetting a node** | Declaring a lost node permanently gone by deleting its Node from the cluster. The administrator makes that one decision, because a partition looks the same as a dead node. Everything after it is automatic: the node reaper discards the engine-local volumes pinned to that node, and each database cluster re-clones the lost instance onto a healthy node. |
| **Node reaper** | The shared cluster add-on that finishes forgetting a node: once a Node is deleted, or found missing when it reconciles, it discards the engine-local volumes that were pinned to it. It never acts on a node that is only unreachable. |
| **Backup target** | The write-only object store outside the cluster that receives every backup. |
| **Cluster add-on** | A cluster-wide prerequisite that a decided consumer needs (here: cert-manager, K8up and the node reaper). It is installed through the API, in its own role, on the same pattern as the operators. |

## Acceptance Criteria

### Mode selection and inventory

- [ ] `DEPLOYMENT_MODE` resolves to `kubernetes` when the inventory has hosts in `svc-k3s-node` or `svc-k8s-api`; to `swarm` when it has more than one host in `svc-swarm-node`; and to `compose` otherwise.
- [ ] An inventory with both swarm groups and Kubernetes groups fails at inventory-validation time. One inventory runs exactly one mode.
- [ ] In kubernetes mode, `STACK_HOST` is the API host, and `IS_STACK_HOST` is true only there.
  - **Reference cluster:** the API host is the first host in `svc-k3s-server`, using `/etc/rancher/k3s/k3s.yaml`.
  - **BYO:** the API host is the one host in `svc-k8s-api`, which carries a kubeconfig path and context. It MAY be the controller itself (`ansible_connection: local`).
- [ ] Kubernetes support is opt-in in role meta.
  - A missing `modes.kubernetes` entry means disabled.
  - Only the four `svc-db-*` roles and the platform roles introduced here set `modes.kubernetes.enabled: true`.
  - A kubernetes-mode inventory that names any other stack role fails at validation. Host-level roles (`sys-*`, `desk-*`, ...) are unaffected.
- [ ] In kubernetes mode, instance counts come from role config (`services.<engine>.instances`), never from host groups.
- [ ] The mode set is closed. Any lookup or filter without a `kubernetes` arm raises in kubernetes mode instead of falling back to compose. The unit tests that assert the compose fallback are updated to assert the raise.
- [ ] `IS_BACKUP_HOST` keeps its meaning: membership of an `svc-bkp-*` group, outside the cluster.

### Role: `svc-k3s-node` (reference cluster)

- [ ] A new role at `roles/svc-k3s-node/` follows the role-meta layout. It installs k3s with embedded etcd, using the official install script and a pinned `INSTALL_K3S_VERSION` (an exact release such as `v1.36.5+k3s1`, never a channel).
  - The first host in `svc-k3s-server` initialises the cluster with `--cluster-init`.
  - The other servers join as servers. Hosts in `svc-k3s-node` but not in `svc-k3s-server` join as agents.
  - The join token is a pre-generated Infinito credential.
- [ ] The number of servers is 1, or an odd number of at least 3. Any other count fails fast. HA is claimed only with 3 or more servers.
- [ ] Servers run workloads; no control-plane taints are applied.
- [ ] Bundled components:
  - **Disabled:** Traefik, ServiceLB and the Helm controller.
  - **Kept:** local-storage, metrics-server, CoreDNS, the network-policy controller and kube-proxy.
  - `prefer-bundled-bin: true` is set on every distribution.
- [ ] `flannel-backend: wireguard-native` and `secrets-encryption: true` are set from bootstrap. On BYO both are documented recommendations.
- [ ] `tls-san` lists every server name and IP. There is no control-plane VIP in v1.
- [ ] `resolv-conf` is set when the host resolver is a loopback address.
- [ ] The role writes `/etc/rancher/k3s/registries.yaml`. Its mirrors point at the project's GHCR `mirror/` copies by default, or at an `svc-registry-cache` host when the inventory has one.
- [ ] etcd snapshots keep the k3s defaults (every 12 h, 5 kept, local) and are also shipped through `etcd-s3` to the backup target's etcd bucket, with write-only credentials.
- [ ] After every run, the role asserts that the etcd member count equals the server count.
- [ ] Upgrades are role-driven and rolling (`serial: 1`, servers first). For each node, the role:
  1. drains the node, respecting PDBs;
  2. re-runs the installer with the new pin;
  3. waits until the node is Ready, etcd is healthy, and every database cluster passes the shared health wait.

  The role refuses to skip a Kubernetes minor version.
- [ ] The minimum documented node size for the HA claim is 4 vCPU, 16 GiB RAM and SSD or NVMe per server. The role's README shows the per-server memory arithmetic.

### Forgetting a node and the node reaper

- [ ] Forgetting a dead server or agent is one administrator action: deleting its Node. It is exposed as one documented playbook or `make` target, which:
  1. asserts that the host is removed from the inventory;
  2. deletes the Node (`kubectl delete node`).

  Nothing else is manual. There is no runbook of PVC deletes. The one open exception is MariaDB's empty-replica recovery (see [Risks to Settle During Implementation](#risks-to-settle-during-implementation)).
- [ ] A new role at `roles/svc-k8s-node-reaper/` (working name) installs the node reaper as a cluster add-on, on the same pattern as the operator roles. It is always installed in kubernetes mode, on the reference cluster and on BYO alike.
  - It runs 2 replicas with leader election through its own Lease. Like the operators, it has required pod anti-affinity on `kubernetes.io/hostname` and a PDB.
  - Its namespace equals its role id.
  - It is written in Python with the `kubernetes` client. Its code lives under the role's `files/` and ships as its own image on GHCR (see [Images](#images)); the role meta pins the exact image version. Its pytest unit tests live in the repo's test tree, under `tests/unit/python/roles/`.
- [ ] The node reaper acts only on a Node that is gone, never on one that is merely unhealthy. For every engine, it deletes each PVC whose PV belongs to the engine-local StorageClass (`infinito-engine-local` on the reference cluster, or whatever `KUBERNETES_STORAGE_CLASSES` maps `engine-local` to on BYO) and is pinned to a deleted node, plus any pod of that PVC left behind. It finds such nodes in two ways:
  1. **Node delete events,** which it watches.
  2. **Reconciliation,** at startup and then periodically, every few minutes: it deletes every engine-local PVC pinned to a node that no longer exists. A missing Node is the same proof as a delete event, so a delete that happened while no reaper replica was running is still finished.

  - It never acts on a NotReady node. A partition cannot be told apart from a dead node, so that decision stays with the administrator.
  - It never touches any other StorageClass or any application volume.
- [ ] Each database cluster then re-clones the lost instance on a healthy node on its own: CNPG through pg_basebackup, MariaDB through replica recovery, Redis through a full resync, and OpenLDAP through a syncrepl refresh. A re-cloned OpenLDAP pod configures itself from its ConfigMap, with no Ansible run.
- [ ] Cluster size:
  - The HA minimum stays at 3 nodes, and the required hostname anti-affinity of every engine stays.
  - With 3 nodes, the third instance comes back only once a replacement node joins.
  - 4 nodes are documented as the self-healing size: there, deleting the Node is enough to get every database cluster back to its instance count.

### Engine-local storage

- [ ] Role meta asks for the abstract class `engine-local`. The data volume entry in each `svc-db-*` role's `meta/volumes.yml` gains `kubernetes: {class: engine-local, size: <n>}`.
  - The default sizes are Postgres 20Gi, MariaDB 20Gi, Redis 2Gi and OpenLDAP 2Gi.
  - The inventory can override each size.
- [ ] An inventory map `KUBERNETES_STORAGE_CLASSES` resolves `engine-local` to a real StorageClass name.
- [ ] On the reference cluster, the platform layer creates the StorageClass `infinito-engine-local`: provisioner `rancher.io/local-path`, `volumeBindingMode: WaitForFirstConsumer`, `reclaimPolicy: Delete`.
- [ ] The BYO documentation states three things:
  - the class MUST be RWO;
  - `WaitForFirstConsumer` and no storage-level replication are recommended;
  - TopoLVM is a better local class where one is available.
- [ ] The documentation warns that local-path does not enforce sizes, so disk headroom must be planned.

### Operators and applying resources

- [ ] Each operator has its own role, which installs it through `kubernetes.core.helm` from its first-party chart at an exact pinned chart version:
  - `svc-k8s-operator-cnpg`;
  - `svc-k8s-operator-mariadb`, which installs the `mariadb-operator-crds` chart first;
  - `svc-k8s-operator-redis`.

  The kubernetes arm of each `svc-db-*` role pulls in its operator role, which runs once per play.
- [ ] Every operator runs 2 replicas with leader election, required pod anti-affinity on `kubernetes.io/hostname`, and a PDB.
  - For mariadb-operator this applies to the operator, the webhook and the cert-controller.
- [ ] The namespace of every engine and every operator equals its role id (`svc-db-postgres`, `svc-k8s-operator-cnpg`, ...).
- [ ] Every CR, StatefulSet, Deployment, ConfigMap, Secret, RBAC object and NetworkPolicy is applied through `kubernetes.core.k8s` with server-side apply (`field_manager: infinito`), from Jinja templates inside the role. Every task runs on the API host.
- [ ] One shared wait helper is used after every apply, with a strategy per kind:
  - **Kinds whose status carries `observedGeneration`:** wait for `observedGeneration == metadata.generation` plus Ready or applied.
  - **CNPG `Cluster` and `MariaDB`, after a changing apply:** wait in two steps:
    1. wait a bounded time for the resource to leave its healthy state, tolerating no transition;
    2. wait for Ready and `readyInstances == instances`, plus `currentPrimary == targetPrimary` for CNPG.
  - **OT:** `status.masterNode` is non-empty, and the StatefulSet rollouts of the replication and the Sentinel are complete.
  - **The OpenLDAP StatefulSet:** the native rollout wait, then exactly one pod carrying the writer label.

  The same helper is the database-cluster health gate for k3s upgrades.
- [ ] A role leaving the inventory deletes nothing. Removal is only an explicit purge task, which deletes the CR, then the PVCs, then the namespace.
- [ ] Three cluster add-ons are installed in kubernetes mode:
  - **cert-manager:** the role `svc-k8s-addon-cert-manager` installs it through Helm, because the Barman Cloud plugin requires it. On BYO, an existing cert-manager install is detected and reused.
  - **K8up:** a new role at `roles/svc-k8s-k8up/` (working name) installs it on the same pattern as the operator roles: `kubernetes.core.helm` from its first-party chart at an exact pinned chart version, 2 replicas with leader election, required pod anti-affinity on `kubernetes.io/hostname`, a PDB, and a namespace equal to its role id. It is always installed, on the reference cluster and on BYO alike. It runs the OpenLDAP backups (see [Backups](#backups)), and it is the backup tool that application volumes will reuse once applications render on Kubernetes.
  - **The node reaper** (see [Forgetting a node and the node reaper](#forgetting-a-node-and-the-node-reaper)). It ships its own manifests, not a Helm chart.
- [ ] Operator chart and engine image bumps are deliberate pull requests. They are merged only with the acceptance suite green. CNPG MUST stay inside its upstream support window.

### Images

- [ ] The project builds exactly two images for kubernetes mode:
  - **slapd,** from `roles/svc-db-openldap/files/Dockerfile`. It gains `python3`, the `kubernetes` client and the writer elector, whose code lives in `roles/svc-db-openldap/files/elector/`. Its version is the upstream slapd version plus a build suffix.
  - **The node reaper,** from its role's `files/`. Its version is the reaper's own version.
- [ ] Both images follow one tag rule: every build is published under a git-sha tag and a version tag. The role meta of `svc-db-openldap` and of the node reaper role pins the exact version tag.
- [ ] A new CI workflow builds both images for amd64 and arm64 and publishes them to GHCR under the project namespace.
- [ ] An inventory override `KUBERNETES_IMAGE_REGISTRY` rewrites the prefix of every data-tier image, the node reaper's included, for air-gapped or private mirrors.
- [ ] The BYO contract requires pull access to GHCR or to that override. Push access is never required.
- [ ] `k3s ctr images import` MAY be used in the lab to test an unpublished Dockerfile change. It is never used by a deploy.

### Shared conventions

- [ ] The kubernetes arm of `lookup('database')` and `lookup('engine')` changes only `host`, to `<write Service>.<engine role id>.svc`.
  - The short `.svc` form is used, so a custom cluster domain still resolves.
  - `url_jdbc`, `url_full` and `url` are built from it.
  - `port` keeps the engine default.
- [ ] In kubernetes mode, the compose-only keys are absent, and any access raises: `address`, `container`, `service_name`, `reach_host`, `network`, `env`, `realign_*`, `initdb_dir`, `build_dir`, `volume`, `image`, and the engine `container`. An embedded engine (`shared: false`) raises.
- [ ] `library/database_query.py` raises "no kubernetes arm" in kubernetes mode.
- [ ] Every credential is an inventory-owned `kubernetes.io/basic-auth` Secret (keys `username` and `password`) in the engine namespace, applied with `no_log`.
  - One Secret per consumer: `<name>-credentials`.
  - One Secret per engine that needs it: `<engine>-superuser`.
  - Labels: `app.kubernetes.io/managed-by: infinito` and `infinito.nexus/consumer: <application_id>`.
- [ ] Rotating a password means changing the inventory value and re-running the deploy. The Secret is re-applied, and the operator updates the role.
- [ ] Every engine defaults to 3 instances, set in its `meta/services.yml`, with required pod anti-affinity on `kubernetes.io/hostname`.
  - 1 instance renders the standalone form and warns "non-HA".
  - 2 instances are allowed but documented as having no drain safety.
- [ ] Resources are Burstable:
  - `requests.memory` is `mem_reservation`, and `limits.memory` is `mem_limit`;
  - `limits.cpu` is `cpus`, and `requests.cpu` is `cpus / 4`.
- [ ] Provisioning keeps today's entry point: `database_init: true` through `sys-svc-rdbms` or `sys-svc-engine`.
  - In kubernetes mode, `00_core.yml` applies the engine CR.
  - `01_init.yml` dispatches to a kubernetes file that applies the consumer's Secret and CRs, named `<name>`, in the engine namespace.
- [ ] Every consumer CR sets its retain policy explicitly. Deleting a CR never drops data. Dropping a database is only ever an explicit purge task.
- [ ] Residual steps run through `kubernetes.core.k8s_exec`, inside the pod behind the write endpoint, using the engine's password-less local admin path. A password never appears in argv.
- [ ] In-cluster TLS keeps each operator's defaults and is not enforced in v1:
  - Postgres and MariaDB serve TLS but still accept plaintext;
  - Redis and OpenLDAP are plaintext.

### Postgres: `svc-db-postgres` on CloudNativePG

- [ ] The kubernetes arm renders a CNPG `Cluster` named `postgres` on CNPG 1.30.x, with image `ghcr.io/cloudnative-pg/postgis:18-3-standard-trixie` pinned to an exact tag. The project builds no Postgres image for kubernetes mode.
- [ ] The write endpoint is `postgres-rw`, so `host` is `postgres-rw.svc-db-postgres.svc`.
- [ ] Durability is `synchronous: {method: any, number: 1, dataDurability: preferred}`. At 1 instance, no `synchronous` block is rendered.
- [ ] The initdb locale (`UTF8`, `C`) maps to `bootstrap.initdb`. The parameters from `compose.yml.j2` map to `spec.postgresql.parameters`.
- [ ] `enableSuperuserAccess` stays `false`, and no superuser Secret is applied. Residual steps use peer authentication over the socket.
- [ ] `primaryUpdateMethod` is `restart`.
- [ ] CNPG's default `app` database, owner and Secret are accepted and documented as unused.
- [ ] Each consumer applies a `DatabaseRole` (password from `<name>-credentials`, `LOGIN`) and a `Database` owned by it, both with the retain reclaim policy.
  - The extensions from the consumer's `meta/services.yml` `postgres.extensions` are rendered into `Database.spec.extensions` with `ensure: present`.
  - The `GRANT ALL ON ALL TABLES IN SCHEMA public` and `ALTER DEFAULT PRIVILEGES` steps of `01_init.yml` have no kubernetes counterpart. Ownership covers the database, the `public` schema and every table the consumer creates.

### MariaDB: `svc-db-mariadb` on mariadb-operator

- [ ] The kubernetes arm renders a `MariaDB` CR named `mariadb` with the official `mariadb` image, on MariaDB 12.3 LTS.
  - The version comes from a kubernetes-mode version key in role meta.
  - Compose and swarm keep their own pin.
- [ ] Replication is on with `semiSyncWaitPoint: AfterSync` (semi-sync stays on) and `primary.autoFailover: true`. Galera and MaxScale are not used.
- [ ] The write endpoint is `mariadb-primary`, so `host` is `mariadb-primary.svc-db-mariadb.svc`.
- [ ] The CR references `mariadb-superuser` through `rootPasswordSecretKeyRef`.
- [ ] Each consumer applies a `Database`, a `User` and a `Grant`, all with `cleanupPolicy: Skip`.
  - `Database.characterSet` and `collate` come from `MARIADB_ENCODING` and `MARIADB_COLLATION`.
  - `User.host` is `%`. The `Grant` gives `ALL PRIVILEGES` on `<db>.*`.
- [ ] Replica recovery is enabled: `replication.replica.recovery.enabled`, with `replica.bootstrapFrom` pointing at a PhysicalBackup template using `PreferReplica`.
- [ ] The standalone form has replication off and 1 replica. If no `-primary` Service exists in that form, the lookup returns `mariadb` as the Service at 1 instance.

### Redis: `svc-db-redis` on the OT redis-operator

- [ ] The kubernetes arm renders a `RedisReplication` named `redis` with the stock `redis:8.10.x` image, used under its AGPLv3 licence option. The operator runs with the `GenerateConfigInInitContainer` feature gate on.
- [ ] A separate `RedisSentinel` CR runs 3 Sentinels with quorum 2, `downAfterMilliseconds` 5000 and `failoverTimeout` 10000. Each Sentinel requests 32Mi and 50m CPU.
- [ ] The write endpoint is `redis-master`, so `host` is `redis-master.svc-db-redis.svc`. Clients keep a plain `redis://` URL.
- [ ] Authentication uses `redisSecret` from `redis-superuser`. Consumers keep the shared `default` user. No per-consumer ACL user or Secret is applied.
- [ ] RDB and AOF persistence stay on. `maxmemory` is 80 % of the memory limit, with `allkeys-lru`.
- [ ] Replication is async, with no `min-replicas-to-write`. Redis keeps `backup.disabled: true`.
- [ ] The standalone form is a `RedisReplication` of size 1 without Sentinel, if the operator accepts that size. Otherwise it is a `Redis` CR, and the lookup returns `redis` at 1 instance.

### OpenLDAP: `svc-db-openldap` as a StatefulSet with writer election

OpenLDAP has no maintained operator, so the role renders its own StatefulSet. All pods replicate the data tree as multi-provider peers, but only one of them takes writes at a time. That is the OpenLDAP admin guide's mirror mode (in 2.6, `olcMirrorMode` is an alias of `olcMultiProvider`) stretched to 3 nodes, with the "external frontend" being a Kubernetes Service. A small writer-election helper inside the slapd image moves the writer automatically, in the way Patroni does for Postgres: each pod competes for a Lease, the winner labels itself, and the write Service selects that label.

This is deliberately not an operator. A central controller cannot fence a writer that is partitioned away from it; only a process inside the pod can make slapd read-only without the network. An operator would therefore still need the same in-pod helper, plus thousands of lines of controller code and a CRD API to maintain.

- [ ] The kubernetes arm renders a 3-pod StatefulSet of the project's slapd image. All pods replicate the data tree through N-way syncrepl:
  - `olcServerID` is derived from the pod ordinal;
  - `olcMultiProvider: TRUE`;
  - each pod runs syncrepl to every peer.
- [ ] `cn=config` is not replicated. Each pod builds its own `cn=config` at boot from a ConfigMap of rendered LDIF:
  - the schemas, including those that `ldapsm` creates today, shipped as static LDIF;
  - the memberof and refint overlays;
  - the syncrepl stanzas to every peer;
  - `olcServerID` from the pod's ordinal;
  - the data database with `olcReadOnly: TRUE`, so slapd always boots read-only;
  - `olcAccess` rules on `cn=config` and on the data database that grant `manage` to the local peercred identity the container runs as, so that the elector and the residual steps work over `ldapi:///` with EXTERNAL.

  A re-cloned pod therefore configures itself, with no Ansible run. A change to the ConfigMap rolls the StatefulSet through a checksum annotation; restarting the writer costs a few seconds of writes (estimated 2–4 s).
- [ ] Each pod runs a writer elector next to slapd:
  - It competes for the Lease `openldap-writer` in the `svc-db-openldap` namespace, and only while its pod is Ready.
  - **On winning the Lease,** in this order: it sets `olcReadOnly: FALSE` on the data database over `ldapi`, removes the label `infinito.nexus/ldap-role=writer` from every other pod, and adds that label to its own pod.
  - **On losing the Lease, missing the renew deadline, or receiving SIGTERM,** in this order: it sets `olcReadOnly: TRUE` locally over `ldapi`, removes its own label as a best effort, and releases the Lease.
  - Its timings are the control plane's defaults: a Lease duration of 15 s, a renew deadline of 10 s and a retry period of 2 s.
- [ ] The elector fails closed. It runs as a second process in the slapd container, under the image's existing `tini` entrypoint. If the elector exits, slapd stops and the container restarts, and slapd comes back read-only. A separate sidecar container is not used, because slapd would keep its last mode if the sidecar crashed.
- [ ] The elector is Python with the `kubernetes` client: a Lease loop of our own of roughly 300 lines, in `roles/svc-db-openldap/files/elector/`, with pytest unit tests under `tests/unit/python/roles/svc-db-openldap/`.
- [ ] The write endpoint `openldap` selects `infinito.nexus/ldap-role=writer`, so `host` stays `openldap.svc-db-openldap.svc`. The Service maps port 389 to 1389.
  - There is no read Service in v1. Reads and binds also go to the writer, so logins fail during a write gap as well. This is accepted for v1.
  - Keycloak's LDAP `connection_pooling` stays `false` (`roles/web-app-keycloak/meta/services.yml`), so every operation opens a new connection to the current writer.
- [ ] Expected write gaps at these timings (estimates, measured by the acceptance suite):
  - writer node crash: about 15–20 s;
  - writer partitioned: the old writer turns read-only about 10 s after its last renewal, and the new writer takes over about 15–17 s after it;
  - writer pod delete or rolling change: about 2–4 s.
- [ ] Fencing a demoted writer rests on three layers, in order:
  1. its own read-only switch at the renew deadline, which needs no network;
  2. the new writer removing the old pod's label through the API, which needs nothing from the old node;
  3. node NotReady at 50 s, which removes the old pod from every Service.

  The README documents the accepted residual risk: a frozen old writer (a paused process or node) may still accept writes for a few seconds. Those writes merge through replication, and conflicts on the same entry resolve last-writer-wins by `entryCSN`. Node power fencing is not part of v1.
- [ ] Each pod runs its own memberof and refint overlays, and nothing switches at failover. `olcMemberOfAddCheck: TRUE` is set, and `memberOf` stays excluded from replication.
- [ ] ppolicy and `olcLastBind` MUST NOT be enabled while more than one pod serves. Both turn binds into internal writes that bypass `olcReadOnly`. The README documents why.
- [ ] slapd and the elector run as a non-root user, and slapd listens on 1389.
- [ ] A pod is Ready only when slapd answers and its initial syncrepl refresh is complete, meaning its contextCSN is present and equal to a peer's. A pod that is not Ready never competes for the Lease.
- [ ] Data provisioning runs as residual steps against the writer:
  - Ansible first waits until exactly one pod carries the writer label;
  - each rendered data LDIF is copied into that pod with `kubernetes.core.k8s_cp` and applied with `k8s_exec` (`ldapmodify` / `ldapadd -Y EXTERNAL -H ldapi:///`), tolerating the same return codes as today;
  - this covers OUs, users and groups. Configuration and schemas live in the ConfigMap instead.
- [ ] The standalone form is 1 pod without syncrepl. The elector runs there too, on the same code path, and the single pod wins the Lease within about 2 s.

#### Alternatives considered

- **All pods take writes (true multi-provider writes through a Service over every pod):** rejected for production. Keycloak federates LDAP in `WRITABLE` mode, so writes are frequent, and concurrent writes on different pods can cross under a partition, which the OpenLDAP admin guide warns against and which leaves dangling `member` values that refint cannot repair.
- **An operator of our own** (kubebuilder or operator-sdk in Go, kopf in Python, or hooks on shell-operator or Metacontroller): rejected because a central controller cannot fence a partitioned writer, so it would still need the in-pod elector, plus a product of its own to maintain (or one more add-on to install and pin).
- **2 providers plus 1 read-only consumer:** rejected because it drops to one writer candidate after the first node loss, needs a second config shape, needs the same elector, and gains no consistency, since both layouts send writes to one node.
- **slaptain** (a community OpenLDAP operator): rejected because it writes to all pods, is an alpha (`v1alpha1`) maintained by a single contributor, and defaults to OpenLDAP 2.7, while Debian trixie ships 2.6.10.

### Backups

- [ ] The backup target is an S3 endpoint outside the cluster, configured through `KUBERNETES_BACKUP_S3` (endpoint, bucket prefix, credentials).
  - **Documented default:** `web-app-seaweedfs` in compose mode on the backup host, with versioning, object lock and SSE-S3 enabled.
  - **Buckets:** one per engine, plus one for etcd.
  - **Credentials:** the cluster holds write-only credentials (a bucket policy without delete). Retention and pruning run on the backup host.
- [ ] **Postgres:** the CNPG Barman Cloud plugin, installed in the CNPG operator namespace:
  - continuous WAL archiving;
  - a daily base backup;
  - 30 days of retention;
  - TLS to the endpoint.
- [ ] **MariaDB:**
  - a `PhysicalBackup` (mariadb-backup) every 6 h, 30 days retained, with SSE-C using a key from a Secret;
  - a logical `Backup` per database every day, so one database can be restored on its own.
- [ ] **OpenLDAP:** the K8up add-on (`svc-k8s-k8up`) runs `slapcat -n0` and `slapcat -n1` daily through its `backupcommand` annotation on the OpenLDAP pods, with restic client-side encryption, to the same target.
  - `slapcat` is safe on any pod, so the annotation does not follow the writer label.
  - A plain `slapcat` CronJob is not used, because it would rebuild restic's scheduling and retention.
- [ ] **Redis** is not backed up.
- [ ] Before applying a changed engine CR, the deploy creates an on-demand `Backup` (CNPG) or `PhysicalBackup` (MariaDB), waits for it to complete, and aborts on failure.
- [ ] In kubernetes mode, `databases.csv` and `baudolo-seed` are not used.
- [ ] Each engine's README carries a manual disaster-recovery runbook:
  - Postgres recovers through `bootstrap.recovery` into a new `Cluster`. A single database is restored by recovering into a scratch cluster, then `pg_dump`/`pg_restore` into the live cluster.
  - MariaDB recovers through `bootstrapFrom` or a logical `Restore`.
  - OpenLDAP recovers from the K8up dump.

### Security

- [ ] Every engine namespace, every operator namespace, K8up's namespace and the node reaper's namespace has default-deny NetworkPolicies for ingress and egress.
- [ ] Explicit ingress allows:
  - replication and Sentinel traffic inside the engine namespace;
  - the operator's namespace to its instances on CNPG 8000/5432, mariadb-operator 3306/5555/5566, and OT 6379/26379;
  - webhook port 9443 into each operator namespace, from any source;
  - consumers, from namespaces labelled `infinito.nexus/consumes-<engine>: "true"`.
- [ ] Explicit egress allows:
  - DNS to kube-system;
  - traffic inside the namespace;
  - the API server (the node IPs on 6443). `svc-db-openldap`, where the elector talks to the API, and the node reaper's namespace each carry this rule explicitly;
  - the backup target, as an ipBlock.
- [ ] The elector and the node reaper each run under their own ServiceAccount with only these rights:
  - **Elector:** a namespaced Role in `svc-db-openldap` with `leases` get, create and update, and `pods` get, list and patch.
  - **Node reaper:** a ClusterRole to list and watch nodes, list PVs, and delete PVCs and pods. Listing nodes is what its periodic reconciliation needs.
- [ ] Pod Security Admission enforces `restricted` on every engine namespace, every operator namespace, K8up's namespace and the node reaper's namespace. The elector runs inside the slapd container and complies with the same security context.
  - mariadb-operator (operator, webhook, cert-controller, MariaDB, agent, init and backup Job containers) and OT (operator, Redis, Sentinel, init and exporter containers) get explicit security contexts that comply.
  - Any component that provably cannot comply drops its namespace to `baseline`, and the exception is documented in that role's README.
- [ ] The BYO contract requires a network plugin that enforces NetworkPolicy.
- [ ] The BYO documentation defines a minimal ClusterRole for the deploy identity. It covers namespaces, CRDs, the Helm installs of the operators and of K8up, the engine CRs, K8up's backup resources, Secrets, ConfigMaps, StatefulSets, the node reaper's Deployment, ServiceAccounts, Roles and ClusterRoles with their bindings, `pods/exec` and NetworkPolicies. Because Kubernetes only lets an identity grant rights it holds itself, it also includes the elector's and the node reaper's rights listed above: list and watch nodes, list PVs, delete PVCs and pods, `leases` get, create and update, and `pods` patch.

### Acceptance suite

- [ ] A new GitHub Actions workflow runs the acceptance suite on a GitHub-hosted `ubuntu-latest` runner.
  - It uses the repo's privileged systemd-container lab running the real `svc-k3s-node` role on 3 servers. k3d is not used.
  - It runs nightly on the default branch, on pull requests that touch data-tier paths, and on manual dispatch.
  - The same suite runs locally through `make test-k8s-data`.
  - It is separate from `make test` and from the existing deploy tests, and it writes JUnit output.
- [ ] The 4-node lab, the self-healing size, runs locally only in v1: `make test-k8s-data-lab` brings it up and runs the full re-clone scenario. It is run by hand before each release. Hosted CI stays at 3 servers, because 4 nodes plus every engine would strain a 16 GB hosted runner. A self-hosted runner for the 4-node lab comes later.
- [ ] A preflight raises `fs.inotify.max_user_instances` on the lab host.
- [ ] Each engine has a write-continuity checker pod.
  - It runs on a node the suite never kills, in a namespace carrying the consumer label.
  - It reads `host` and its credentials from a Secret that Ansible renders from `lookup('database')` or `lookup('engine')`.
  - It opens a new connection every 200 ms with a 1 s timeout and writes one sequence number per connection.
  - Afterwards it audits that every acknowledged sequence number exists.
- [ ] The suite runs these scenarios against every engine:
  1. delete the primary pod;
  2. crash the primary's node (`docker kill`);
  3. hang the primary's node (`docker pause`);
  4. partition the primary (`docker network disconnect`);
  5. crash the node running the operator leader. OpenLDAP has no operator, so for OpenLDAP this crashes the node holding the `openldap-writer` Lease while the node reaper's leader runs there too: the worst case, in which the writer and the reaper leader are lost together;
  6. apply a rolling, restart-requiring change;
  7. forget a dead node by deleting its Node, and re-clone to full strength (for MariaDB, from an empty replica); where this runs is set by the node reaper scenario below;
  8. back up, restore into a scratch instance, and assert a seeded marker;
  9. run consumer DDL and DML as the consumer role (Postgres and MariaDB);
  10. check the standalone shape at 1 instance.
- [ ] The suite also runs these scenarios for writer election and the node reaper:
  1. On each fault, the OpenLDAP writer label moves within the target time.
  2. A demoted OpenLDAP pod rejects writes with `unwillingToPerform`.
  3. `memberOf` matches across the OpenLDAP pods after a re-clone.
  4. After a Node delete, every engine re-clones back to its instance count. This runs on the local 4-node lab (`make test-k8s-data-lab`). The hosted 3-server CI run checks only that the node reaper deletes the engine-local PVCs (and any pod left behind) pinned to the deleted node.
  5. During a partition, the OpenLDAP writer label never stays on two pods for longer than the renew deadline.
- [ ] The targets, at default Kubernetes timings:
  - **Postgres and MariaDB:** 0 acknowledged writes lost on every single-node fault.
  - **Every engine:** a write gap of ≤ 90 s on a node crash, hang or partition; ≤ 30 s on a pod delete; ≤ 5 s on a rolling change.
  - **Redis and OpenLDAP:** losses are reported, and the run fails only above 10 s worth of writes.
  - **Re-clone:** full strength within 15 minutes on the 4-node lab.
- [ ] The workflow reports `failure` when any assertion fails.

### Tests and documentation

- [ ] `make test` passes with every new role, schema entry and lint change in place.
- [ ] Each new role and each changed `svc-db-*` role ships a README covering the kubernetes arm, its configuration surface and its failure modes.
- [ ] A design page under [docs/contributing/design/](../contributing/design/) documents three things:
  - the kubernetes mode and its opt-in rule;
  - the BYO contract (Kubernetes 1.35–1.36, an RWO engine-local class, an enforcing network plugin, image pull access, an S3 backup target, the always-installed K8up and node reaper add-ons, the minimal ClusterRole);
  - the reference cluster's sizing, with 3 nodes as the HA minimum and 4 nodes as the self-healing size.
- [ ] This requirement is cross-linked from the implementing pull request, and the pull request is cross-linked back here per [requirements.md](../contributing/requirements.md).

## Risks to Settle During Implementation

Primary-source research could not settle these points. The acceptance suite MUST settle each one, and the outcome MUST be recorded in the affected role's README:

- **MariaDB standalone Service:** whether mariadb-operator exposes a `-primary` Service when replication is off.
- **Redis standalone form:** whether the OT operator accepts a `RedisReplication` of size 1.
- **Empty-replica recovery:** whether mariadb-operator's replica recovery triggers for an empty replica while the primary still has its binlogs. Bug #1857 (copy-back misses dotfiles) is open upstream. Until this passes, forgetting a node includes a manual PhysicalBackup restore for MariaDB.
- **OT stock image:** whether the stock Redis image runs correctly under the `GenerateConfigInInitContainer` gate. If it does not, the fallback is the OT image, never a project build.
- **CNPG stale Ready:** CNPG's `Ready` condition lacks `observedGeneration` (upstream PR #11560 is open). Once it merges, the wait helper switches CNPG to the generation-correct strategy.
- **`olcReadOnly` scope:** the OpenLDAP 2.6 source enforces `olcReadOnly` for client operations, counts the Password Modify extended operation as an update, and never applies the check to syncrepl. The lab must confirm both halves: a demoted pod rejects Password Modify (Keycloak's password path), and it keeps receiving replication.
- **Elector timing:** the write-gap figures for OpenLDAP are estimates. The lab must confirm that the Python Lease loop honours the 15 s / 10 s / 2 s timings under API latency, and record the measured gaps for node crash, partition, and pod delete.
- **Dual-write window:** a frozen old OpenLDAP writer may accept writes for a few seconds before it notices the lost Lease. This window is accepted; the suite measures its length and the README records it.
- **Node reaper coverage:** the hosted 3-server CI run checks only that the node reaper deletes the right PVCs. The full re-clone back to instance count is proven only on the local 4-node lab (`make test-k8s-data-lab`, run by hand before each release), and the latest result is recorded in the node reaper role's README.

## Future Extensions

Explicitly out of scope for this requirement, and tracked for later:

- **Application rendering on Kubernetes,** the edge, application storage, and the kubernetes arm of `database_query` and the other exec callers. This is a separate requirement for the render backend.
- **Migrating data** from existing compose or swarm installs. v1 is greenfield.
- **Embedded engines** and the engines without v1 HA (Elasticsearch, RabbitMQ, Qdrant, Typesense, SeaweedFS, Memcached).
- **Database HA on swarm or compose,** and any bridge that lets swarm or compose apps use a database cluster.
- **Sharding,** including Redis Cluster mode.
- **The shared storage tier** (replicated and shared volume classes), a sibling feature.
- **Enforced in-cluster TLS** as a per-engine opt-in: `hostnossl … reject` for Postgres, `tls.required` for MariaDB, a project CA for Redis and OpenLDAP, and TLS fields in the lookup. It is blocked on apps that hard-code `sslmode=disable` or `DB_SSL=false`.
- **MariaDB point-in-time recovery** through binlog archiving, once mariadb-operator bug #1815 is fixed.
- **Redis per-consumer ACL users** and key isolation.
- **OpenLDAP dynamic memberOf** through dynlist.
- **Shorter failure detection** by tuning the node-monitor grace period and the tolerations.
- **Automatic node replacement without a Node delete:** a NotReady-timeout trigger that replaces a lost instance without the administrator forgetting the node. It is safe only for OpenLDAP, whose old pod has fenced itself read-only, and it pays off only with 4 or more nodes.
- **An OpenLDAP read or bind Service,** so that logins survive the write gap. It changes the lookup seam, and a password changed moments earlier may not yet have replicated to the pod that answers.
- **STONITH and node power fencing** (for example the medik8s remediation operators), which would close the few-second window in which a frozen old OpenLDAP writer still accepts writes.
- **Postgres image-volume extensions,** once the k3s containerd version is confirmed to be at least 2.1.
- **A self-hosted runner for the 4-node lab,** so that the full re-clone scenario runs in CI instead of by hand before releases.
- **Application volume backups through K8up,** reusing the add-on installed here, once applications render on Kubernetes.
- **Monitoring and alerting** for the database clusters (operator metrics, failover and replica-lag alerts).
- **A control-plane VIP** and multi-replica edge.
- **Autoscaling.**

## Procedure

The implementation follows the [Compose Loop](../agents/action/iteration/compose.md) for role changes and the [Workflow Loop](../agents/action/iteration/workflow.md) for workflow changes, in this order:

1. The foundation: mode trigger, `svc-k3s-node`, the engine-local class, the operator layer, the wait helper, the node reaper with the image workflow that publishes it, and the acceptance workflow skeleton.
2. Postgres, as the pilot engine, with its acceptance scenarios green.
3. MariaDB, then Redis, then OpenLDAP (including the slapd image and its writer elector), each with its scenarios green.
4. Backups, including the K8up add-on, and the restore drill.
5. NetworkPolicy and Pod Security, re-running the full suite.

The following rules apply for the entire run:

- [ ] Clarifying questions are raised once, at the start, in a single batched round. Ambiguities found mid-run are resolved by the agent, recorded in the affected README, and revisited at review.
- [ ] Every failure is fixed at its root within the run. Skips, retry-until-green loops and "follow-up" deferrals are not used.
- [ ] No intermediate commits. All changes and the ticked checkboxes in this document land in one commit, once every criterion is checked, `make test` is green, and the acceptance workflow is green. The agent does not push; the operator runs `git-sign-push` outside the sandbox per [AGENTS.md](../../AGENTS.md).

## See Also

- [023 - Docker Swarm Deployment with NFS-backed Shared Volumes](023-docker-swarm-nfs.md)
- [Compose Loop](../agents/action/iteration/compose.md)
- [Workflow Loop](../agents/action/iteration/workflow.md)
- [Per-Role Meta Layout](../contributing/design/role/services/layout.md)
- [requirements.md (contributor guide)](../contributing/requirements.md)
- [requirements.md (agent guide)](../agents/action/requirements.md)
