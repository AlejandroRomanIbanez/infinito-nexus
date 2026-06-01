# 024 - ERPNext Role with OIDC SSO

## User Story

As a platform administrator of Infinito.Nexus, I want ERPNext (Frappe Framework) integrated as a `web-app-erpnext` role with OpenID Connect identity provider integration so that users can access the ERP through the same Single Sign-On (SSO) mechanism used across the Infinito.Nexus ecosystem, reusing the platform's central database and cache services.

## Background

ERPNext is an open-source ERP suite built on the [Frappe Framework](https://frappeframework.com/). Upstream ships a multi-container deployment ([frappe_docker](https://github.com/frappe/frappe_docker)) consisting of:

- **`frappe`** (Gunicorn) — Python web backend
- **`socketio`** — Node real-time WebSocket service
- **`scheduler`** — periodic-job dispatcher (`bench schedule`)
- **Workers**: `queue-short`, `queue-default`, `queue-long` — background jobs
- **Nginx** (frontend) — static assets + reverse proxy onto Frappe / SocketIO
- Data plane: **MariaDB** (primary), **Redis** (three logical roles: `cache`, `queue`, `socketio`)

Two of those data-plane dependencies have a central Infinito.Nexus service equivalent — [`svc-db-mariadb`](../../roles/svc-db-mariadb/) and [`svc-db-redis`](../../roles/svc-db-redis/) — and MUST be reused per the central-service convention. Frappe's three Redis logical roles are served by a single central Redis instance using distinct DB numbers (Frappe supports that out of the box via `redis_cache` / `redis_queue` / `redis_socketio` config entries).

Frappe ships native OAuth 2.0 / OpenID Connect client support via the built-in **"Social Login Key"** record (see [Frappe docs: Social Login Key](https://docs.frappe.io/framework/user/en/guides/integration/social_login_key)). The integration uses Frappe's own OIDC client against the Infinito Keycloak IdP — no `oauth2-proxy` sidecar. The role therefore uses the `services.sso.flavor: oidc` schema (post-[021](README.md#archive) unified SSO contract), aligned with [`web-app-odoo`](../../roles/web-app-odoo/meta/services.yml).

The closest existing analogues in this repo are [`web-app-odoo`](../../roles/web-app-odoo/) (ERP shape, OIDC + LDAP variants, central MariaDB consumer pattern omitted — odoo uses Postgres) and [`web-app-zammad`](../../roles/web-app-zammad/) (central-service reuse pattern, OIDC-direct flavor, three-variant matrix).

## Proposed Decisions

These decisions are the **agent's first-pass proposal**; the operator MUST review and confirm/reject each before implementation starts. Tracking the table here so iteration on the requirement happens in one place.

| # | Decision | Rationale |
|---|---|---|
| 1 | Canonical hostname: `next.erp.{{ DOMAIN_PRIMARY }}`. No alias on first iteration. | Mirrors the `odoo.erp.{{ DOMAIN_PRIMARY }}` convention used by [`web-app-odoo`](../../roles/web-app-odoo/meta/server.yml); both ERPs sit under the `.erp.` subdomain. |
| 2 | SSO flavor is **OIDC-direct** (`services.sso.flavor: oidc`), NOT oauth2-proxy. The role uses Frappe's built-in Social Login Key. | Frappe supports OIDC natively as an OAuth client; an oauth2-proxy sidecar would be redundant and break the Frappe "Login with X" UX. |
| 3 | Use the unified post-[021](README.md#archive) `services.sso.*` schema (matches [`web-app-odoo`](../../roles/web-app-odoo/meta/services.yml)). | [021](README.md#archive) is merged. New roles MUST land on the unified schema directly, not on the legacy `services.oidc.*` shape. |
| 4 | The Keycloak OIDC client for ERPNext is **auto-provisioned** via `web-app-keycloak`, consistent with every other OIDC-consuming role in the repo. | No manual operator step on deploy. |
| 5 | Keycloak group → ERPNext role mapping is in scope. Target: `roles/web-app-erpnext/administrator` → Frappe `System Manager`, `roles/web-app-erpnext/manager` → Frappe `Sales User` + `Purchase User` + `Stock User` + `Accounts User`, default → Frappe `Customer`. Mapping is applied via Frappe's `User Type` + role-profile API on first login (a post-start `bench` call from `tasks/`). | Operator-confirmable; Frappe's Social Login Key alone does NOT consume group claims, so the role MUST reconcile via API. |
| 6 | Image strategy: **upstream `frappe/erpnext`** (the official image from [frappe_docker](https://github.com/frappe/frappe_docker)), pinned to the **latest stable major.minor** in `meta/services.yml` (no `:latest`, no `:edge`). Bump path follows the same convention as other upstream-pinned roles. | Self-built image (à la [015 Moodle](README.md#archive)) explicitly out of scope. |
| 7 | External-service reuse: **`svc-db-mariadb`** for MariaDB (primary DB), **`svc-db-redis`** for all three Frappe Redis logical roles (separated by DB number: `cache=0`, `queue=1`, `socketio=2`). Nginx frontend stays bundled in-role (Frappe-aware reverse-proxy config). | Operator-confirmable; matches the convention codified in [022 Zammad Decision #7](README.md#archive). No `svc-db-` role exists for Nginx frontend because it is Frappe-coupled, not a general-purpose service. |
| 8 | Email integration is in scope: SMTP outbound (notifications) via `sys-svc-mail-smtp` / `web-app-mailu`, IMAP inbound (Frappe's "Email Account" → "Communication" feature) auto-wired when `web-app-mailu` is in `group_names`. The first inbound channel is auto-created against the ERPNext-owned mailbox provisioned in Mailu. | Matches the Zammad pattern ([022 Decision #8](README.md#archive)); Frappe's `Email Account` doctype supports IMAP inbound natively. |
| 9 | The Frappe site-setup wizard is **bypassed** on first deploy via auto-bootstrap: `bench new-site` with `--admin-password`, `--db-name`, `--mariadb-user-host-login-scope=%` arguments, plus `bench install-app erpnext`, plus a post-start API call from the role's `tasks/` to mark the wizard as completed (`frappe.db.set_default('setup_complete', '1')`). A fresh deploy lands directly on the ERPNext desk. | Matches the Zammad wizard-bypass pattern ([022 Decision #9](README.md#archive)); avoids a manual UI step on every fresh box. |
| 10 | Playwright coverage per [019](README.md#archive): both `biber` and `administrator` personas ship as part of THIS requirement (not deferred). | Mirrors the Zammad rollout ([022 Decision #10](README.md#archive)). |
| 11 | `meta/variants.yml` defines three variants, mirroring the [`web-app-kix`](../../roles/web-app-kix/meta/variants.yml) / [`web-app-zammad`](../../roles/web-app-zammad/meta/variants.yml) pattern: (V1) `sso` + `ldap` both enabled, (V2) all dynamic services flags `false`, (V3) `ldap` only. | Standard variant matrix across helpdesk / ERP roles. |
| 12 | Multi-tenancy / multi-site (Frappe's `bench --site`) is **out of scope** for v1. The role provisions exactly one site (`{{ canonical_domain }}`) and a single ERPNext app install. | Keeps v1 surface small; multi-site can land in a follow-up requirement if needed. |
| 13 | Backup hook: `bench backup --with-files` is wired into the standard `svc-bkp-` flow as the role-specific pre-backup hook (so MariaDB-level dumps + Frappe site-files tarball land together). | Frappe's recommended backup path; aligns with `svc-bkp-` role contract. |

## Target Schema

### Role layout

```
roles/web-app-erpnext/
├── README.md
├── files/
│   └── playwright/test-*.js
├── meta/
│   ├── main.yml
│   ├── info.yml
│   ├── server.yml
│   ├── services.yml
│   ├── schema.yml
│   ├── users.yml
│   ├── variants.yml
│   └── volumes.yml
├── tasks/
│   ├── main.yml
│   ├── 01_core.yml
│   └── 02_bench_bootstrap.yml          # new-site + install-app + wizard-bypass
├── templates/
│   ├── docker-compose.yml.j2
│   ├── env.j2
│   ├── common_site_config.json.j2
│   └── playwright.env.j2
└── vars/
    └── main.yml
```

### `meta/services.yml` excerpt

```yaml
---
sso:
  enabled: "{{ 'web-app-keycloak' in group_names }}"
  shared:  "{{ 'web-app-keycloak' in group_names }}"
  flavor:  oidc
ldap:
  enabled: "{{ 'svc-db-openldap' in group_names }}"
  shared:  "{{ 'svc-db-openldap' in group_names }}"
email:
  enabled: "{{ 'web-app-mailu' in group_names }}"
  shared:  "{{ 'web-app-mailu' in group_names }}"
logout:
  enabled: "{{ 'web-svc-logout' in group_names }}"
  shared:  "{{ 'web-svc-logout' in group_names }}"
dashboard:
  enabled: "{{ 'web-app-dashboard' in group_names }}"
  shared:  "{{ 'web-app-dashboard' in group_names }}"
matomo:
  enabled: "{{ 'web-app-matomo' in group_names }}"
  shared:  "{{ 'web-app-matomo' in group_names }}"
prometheus:
  enabled: "{{ 'web-app-prometheus' in group_names }}"
  shared:  "{{ 'web-app-prometheus' in group_names }}"
# nocheck: playwright-service-flag — DB engine, covered by role-local integration tests
mariadb:
  enabled: true                         # nocheck: dynamic-flag
  shared:  "{{ 'svc-db-mariadb' in group_names }}"
# nocheck: playwright-service-flag — cache/queue/socketio buses, covered by role-local integration tests
redis:
  enabled: true                         # nocheck: dynamic-flag
  shared:  "{{ 'svc-db-redis' in group_names }}"

erpnext:
  backup:
    no_stop_required: false             # Frappe's bench backup requires a quiesced site
  image:  frappe/erpnext
  version: "X.Y.Z"                      # latest stable semver at the time of the PR
  name:   erpnext
  min_storage: 15GB
  ports:
    local:
      http:      <free port>            # nginx frontend
      socketio:  <free port>
  run_after:
    - svc-db-mariadb
    - svc-db-redis
    - web-app-keycloak
    - web-app-mailu
  lifecycle: alpha
  cpus: "2.0"
  mem_reservation: 2g
  mem_limit: 4g
  pids_limit: 2048
```

### `meta/variants.yml` (three variants per Decision #11)

```yaml
---
# V1: sso + ldap together (everything that can be true, is true)
- services:
    sso:
      enabled: true
      shared:  true
    ldap:
      enabled: true
      shared:  true
    email:
      enabled: true
      shared:  true
    # … all other dynamic flags true …

# V2: no auth — everything false
- services:
    sso:
      enabled: false
      shared:  false
    ldap:
      enabled: false
      shared:  false
    email:
      enabled: false
      shared:  false
    # … all other dynamic flags false …

# V3: ldap only
- services:
    sso:
      enabled: false
      shared:  false
    ldap:
      enabled: true
      shared:  true
    email:
      enabled: false
      shared:  false
    # … all other dynamic flags false …
```

### Frappe site config (Decision #7 — Redis DB-number split)

The role MUST template `sites/{{ canonical_domain }}/site_config.json` (or the equivalent common-site-config layer) so Frappe's three Redis logical roles all point at the shared `svc-db-redis` instance with distinct DB numbers:

```json
{
  "redis_cache":    "redis://<svc-db-redis-host>:<port>/0",
  "redis_queue":    "redis://<svc-db-redis-host>:<port>/1",
  "redis_socketio": "redis://<svc-db-redis-host>:<port>/2"
}
```

DB numbers (0 / 1 / 2) are stable for v1; if `svc-db-redis` later partitions tenants, this requirement gets swept by the same migration.

## Acceptance Criteria

### Routing & TLS

- [ ] `next.erp.{{ DOMAIN_PRIMARY }}` resolves through `sys-svc-proxy` to the ERPNext Nginx frontend and returns HTTP 200 on `GET /` with a Frappe-served HTML body (`<title>` contains `ERPNext`).
- [ ] WebSocket upgrade to the SocketIO container succeeds (`wss://next.erp.{{ DOMAIN_PRIMARY }}/socket.io/` returns `101 Switching Protocols`).
- [ ] CSP `connect-src` whitelist includes the canonical host and its `wss://` variant (mirrors the [`web-app-odoo`](../../roles/web-app-odoo/meta/server.yml) precedent).

### Role layout & image

- [ ] `roles/web-app-erpnext/` exists with the layout in the [Target Schema](#role-layout) above.
- [ ] `meta/services.yml` pins `frappe/erpnext` to a concrete stable semver (no `:latest`, no `:edge`).
- [ ] `meta/info.yml`, `meta/server.yml`, `meta/main.yml`, `meta/schema.yml`, `meta/users.yml`, `meta/volumes.yml` exist and pass the repo's standard role-meta lint (per [008](README.md#archive)).

### Central-service reuse (Decision #7)

- [ ] When `svc-db-mariadb` is in `group_names`, ERPNext uses it as its primary database (no role-internal MariaDB container is spawned). Frappe's `db_host` / `db_port` / `db_name` / `db_user` / `db_password` resolve to the central instance.
- [ ] When `svc-db-redis` is in `group_names`, ERPNext uses it for `cache`, `queue`, and `socketio` (DB numbers 0 / 1 / 2). No role-internal Redis container is spawned.
- [ ] When `svc-db-mariadb` is NOT in `group_names`, the role refuses to deploy with a clear error message (MariaDB is mandatory for Frappe; no in-role bundling is provided).

### SSO / OIDC (Decisions #4, #5)

- [ ] When `web-app-keycloak` is in `group_names`, a Keycloak OIDC client for ERPNext is auto-provisioned via the `web-app-keycloak` role (no manual operator step).
- [ ] Frappe's Social Login Key record for the Keycloak provider is auto-created via a post-start `bench` API call from `tasks/` (issuer, client ID, client secret, redirect URI, `provider_name=keycloak`).
- [ ] End-to-end login: a fresh user signs in at `next.erp.{{ DOMAIN_PRIMARY }}` via the "Login with Keycloak" button, lands authenticated in the Frappe desk, and the resulting Frappe `User` record is auto-created with the email + full name from the OIDC `id_token`.
- [ ] **Group mapping (Decision #5)**: Keycloak group claim → Frappe role mapping is reconciled on each login via a post-login hook (`hooks.py` `on_session_creation`) that calls Frappe's User-role API. Admin / Manager / Customer mapping per Decision #5 is verified end-to-end.

### LDAP (V3 variant + V1 dual)

- [ ] When `svc-db-openldap` is in `group_names` AND OIDC is disabled (variant V3), Frappe's built-in LDAP Settings doctype is auto-configured against the central LDAP, and users authenticate against it.
- [ ] When both are in `group_names` (variant V1), the role deploys cleanly. OIDC is the primary login button; LDAP is configured as a fallback authentication path. Behaviour is documented in `roles/web-app-erpnext/README.md`.

### Email (Decision #8)

- [ ] When `web-app-mailu` is in `group_names`, ERPNext's outbound `Email Account` (outgoing) is auto-configured to use the central SMTP endpoint so notification / password-reset / document emails leave the box.
- [ ] When `web-app-mailu` is in `group_names`, an ERPNext inbound `Email Account` (incoming, IMAP) is auto-created against the ERPNext-owned mailbox provisioned in Mailu. Mail sent to that address arrives in Frappe as a `Communication` record within ≤ 60s.
- [ ] When `web-app-mailu` is NOT in `group_names`, the role deploys cleanly without email; no outbound or inbound Email Account record is seeded.

### First-admin bootstrap (Decision #9)

- [ ] A fresh deploy on a clean volume produces a ready-to-use ERPNext instance: NO setup wizard is presented at `next.erp.{{ DOMAIN_PRIMARY }}/app/setup-wizard`; visiting `/login` shows the login form directly, and the desk (`/app`) is reachable after authentication.
- [ ] An admin user (`Administrator`) is seeded with the role's standard admin-bootstrap email and a password from the role's standard secret-bootstrap convention. The admin can log in via local credentials as a break-glass path even when OIDC is unavailable.
- [ ] `bench install-app erpnext` has completed against the new site at the end of `tasks/02_bench_bootstrap.yml`; visiting `/app/erpnext` resolves the ERPNext desk page (not the bare Frappe desk).

### Variants (Decision #11)

- [ ] `meta/variants.yml` defines exactly three variants in this order: V1 sso+ldap, V2 all-false, V3 ldap-only.
- [ ] All three variants deploy cleanly on a fresh box (`make deploy-fresh-purged-apps INFINITO_FULL_CYCLE=true` succeeds end-to-end for each).

### Backup (Decision #13)

- [ ] A `svc-bkp-` pre-backup hook is wired so `bench --site {{ canonical_domain }} backup --with-files` runs against the running site and the resulting `*.sql.gz` + `*-files.tar` + `*-private-files.tar` land in the standard backup target.
- [ ] Restore is documented in `roles/web-app-erpnext/README.md` as the inverse: `bench --site … restore` + central-MariaDB import.

### Playwright (Decision #10, per [019](README.md#archive))

- [ ] `roles/web-app-erpnext/files/playwright/biber/` contains the biber-persona spec, exercising a customer-style "sign in via SSO and view a quote" path against ERPNext's portal.
- [ ] `roles/web-app-erpnext/files/playwright/administrator/` contains the administrator-persona spec, exercising an "open desk, create a Customer, log out" path.
- [ ] Both specs gate on `SSO_SERVICE_ENABLED` / `LDAP_SERVICE_ENABLED` etc. per the standard `service-gating.js` helper, so they skip-correctly under variant V2.
- [ ] `templates/playwright.env.j2` emits the standard service-flag set per [019 Rule 6](README.md#archive).

### Health & quality

- [ ] ERPNext's compose stack is healthy on a fresh deploy: every container (`frappe`, `socketio`, `scheduler`, three workers, `nginx`) reports `healthy` (or, if upstream ships no healthcheck for that image, no `Restarting` loop within 10 min of `up`).
- [ ] No `ERROR` / `FATAL` log lines in any ERPNext container in the first 10 min after `up`, except known-benign upstream noise documented in `roles/web-app-erpnext/README.md`.
- [ ] `make test` is green tree-wide (the role passes role-meta lints, services contract lints, and any playwright-services-parity lints).

### Documentation

- [ ] `roles/web-app-erpnext/README.md` documents: image source + bump policy, the central-MariaDB and central-Redis (3-DB-number split) consumer pattern, the OIDC group-mapping reconciliation, the variant matrix, the wizard-bypass bootstrap path, and the backup / restore flow.
- [ ] This requirement file is cross-linked from the implementing PR (per [docs/contributing/requirements.md#cross-linking](../contributing/requirements.md#cross-linking)).

## Validation Apps

The role MUST deploy cleanly under all three variants on a fresh box. V1 (sso + ldap) and V3 (ldap-only) additionally MUST pass the biber + administrator Playwright personas.

```bash
INFINITO_APPS="web-app-erpnext" \
  make deploy-fresh-purged-apps INFINITO_FULL_CYCLE=true
```

End-to-end smoke after deploy:

1. Visit `https://next.erp.{{ DOMAIN_PRIMARY }}/` — Frappe / ERPNext login page renders, no wizard.
2. Click the "Login with Keycloak" SSO button — Keycloak login flow completes, user lands on the ERPNext desk (`/app`).
3. Open `/app/erpnext` — ERPNext landing page renders (not bare Frappe desk).
4. (V1 / mail variant) Send an email to the ERPNext-owned mailbox in Mailu — within 60s a new `Communication` record appears under the configured Email Account inbox.
5. (V1 / SSO + group mapping) An OIDC user in the `roles/web-app-erpnext/administrator` group has the `System Manager` Frappe role assigned after first login.

## Prerequisites

Before starting any implementation work, the agent MUST read [AGENTS.md](../../AGENTS.md) and follow all instructions in it.

## Implementation Strategy

The agent MUST execute this requirement **autonomously** once Proposed Decisions are confirmed. Open clarifications only when a decision is genuinely ambiguous and would otherwise block progress; default to the intent already captured in this document and proceed. Avoid back-and-forth questions on choices already resolved in [Proposed Decisions](#proposed-decisions) after operator sign-off.

1. Read [Role Loop](../agents/action/iteration/role.md) before starting.
2. Scaffold the role using [`roles/web-app-odoo/`](../../roles/web-app-odoo/) as the structural template (closest analogue: ERP-shaped, OIDC + LDAP variants, central-service consumer pattern, dual HTTP + WebSocket vhost).
3. Wire the upstream `frappe/erpnext` image into the compose template, plus the SocketIO, scheduler, three worker, and Nginx frontend containers (per [frappe_docker](https://github.com/frappe/frappe_docker)).
4. Template `common_site_config.json` with the central MariaDB endpoint and the three Redis URLs split by DB number.
5. Implement `tasks/02_bench_bootstrap.yml`: `bench new-site` → `bench install-app erpnext` → wizard-bypass API call → Social Login Key seeding.
6. Add Keycloak client auto-provisioning in `web-app-keycloak` for the new ERPNext consumer.
7. Add the biber + administrator Playwright specs.
8. Wire the `svc-bkp-` pre-backup hook (`bench backup --with-files`).
9. Iterate `make test` until green, then run the Validation deploys.

## Commit Policy

- The agent MUST NOT create any git commit until every Acceptance Criterion in this document is checked off (`- [x]`).
- A single commit (or a tight, related sequence) lands the whole role addition; no half-scaffolded intermediate commits.
- When all ACs are met, `make test` is green, and the three variants deploy cleanly, the agent instructs the operator to run `git-sign-push` outside the sandbox (per [CLAUDE.md](../../CLAUDE.md)). The agent MUST NOT push.

## Context

- Upstream framework: <https://frappeframework.com/>
- Upstream product docs: <https://docs.frappe.io/erpnext>
- Upstream container reference: <https://github.com/frappe/frappe_docker>
- Closest in-repo analogue for layout: [`roles/web-app-odoo/`](../../roles/web-app-odoo/)
- Central-service reuse precedent: [022 Zammad](README.md#archive)
- Playwright coverage parity contract: [019](README.md#archive)
- Role meta layout contract: [008](README.md#archive)
- Unified SSO schema: [021](README.md#archive)
