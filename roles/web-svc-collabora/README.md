# Collabora

## Description

This Ansible role deploys Collabora Online (CODE) in Docker to enable real-time, in-browser document editing for Nextcloud. It automates the setup of the Collabora CODE container, NGINX reverse proxy configuration, network isolation via Docker networks, and environment variable management.

## Overview

* **Dockerized Collabora CODE:** Uses the official `collabora/code` image.
* **NGINX Reverse Proxy:** Configures a public-facing proxy with TLS termination and WebSocket support for `/cool/` paths.
* **Docker Network Management:** Creates an isolated `/28` subnet for Collabora and connects containers securely.
* **Environment Configuration:** Generates a `.env` file with domain, credentials, and extra parameters for Collabora's WOPI server.

## Cosmos

The diagram places Collabora in the Infinito.Nexus cosmos: the components it deploys (capabilities), the central services it consumes (dependencies), and its outward reach (federation and bridged external networks).

```mermaid
flowchart LR
    subgraph deps [Dependencies]
        dep_svc_db_redis["svc-db-redis 🐳🐝"]
        dep_web_app_matomo["web-app-matomo 🐳🐝"]
        dep_web_app_prometheus["web-app-prometheus 🐳🐝"]
    end
    subgraph role [web-svc-collabora 🐳🐝]
        svc_matomo["matomo"]
        svc_redis["redis"]
        svc_collabora["collabora"]
        svc_prometheus["prometheus"]
    end
    subgraph dependents [Dependents]
        dpt_web_app_bigbluebutton["web-app-bigbluebutton 🐳🐝"]
        dpt_web_app_nextcloud["web-app-nextcloud 🐳🐝"]
    end
    dep_svc_db_redis -.-> svc_redis
    dep_web_app_matomo -.-> svc_matomo
    dep_web_app_prometheus -.-> svc_prometheus
    svc_matomo -.-> dpt_web_app_bigbluebutton
    svc_matomo -.-> dpt_web_app_nextcloud
```

## Features

* Automatic creation of a dedicated Docker network for Collabora.
* Proxy configuration template for NGINX with long timeouts and WebSocket upgrades.
* Customizable domain names and ports via Ansible variables.
* Support for SSL termination at the proxy level.
* Integration hooks to restart NGINX and recreate Docker Compose stacks on changes.

## Quick Setup

### Development

Clone, set up the workstation, and deploy Collabora onto the local stack:

```bash
git clone https://github.com/infinito-nexus/core.git
cd core
make onboard
make compose-deploy mode=reinstall apps=web-svc-collabora full_cycle=false
```

### Production

Run the published image to provision the inventory and deploy Collabora to a managed server (the mounted volume persists the inventory between the two runs):

```bash
docker run --rm -it \
  -v "$PWD/inventories:/etc/infinito.nexus/inventories" \
  ghcr.io/infinito-nexus/core/debian \
  infinito administration inventory provision /etc/infinito.nexus/inventories/prod \
  --inventory-file /etc/infinito.nexus/inventories/prod/devices.yml \
  --host <your-server> \
  --vars-file inventories/<env>/default.yml \
  --include 'web-svc-collabora'

docker run --rm -it \
  -v "$PWD/inventories:/etc/infinito.nexus/inventories" \
  ghcr.io/infinito-nexus/core/debian \
  infinito administration deploy dedicated /etc/infinito.nexus/inventories/prod/devices.yml \
  --password-file /etc/infinito.nexus/inventories/prod/.password \
  --id web-svc-collabora \
  --diff \
  -vv
```

## Further Resources

* [Official Collabora CODE website](https://www.collaboraoffice.com/code/)

## Credits

Implemented by **[Kevin Veen-Birkenbach](https://www.veen.world)**.
Part of the [Infinito.Nexus Project](https://s.infinito.nexus/code) and maintained by [Kevin Veen-Birkenbach](https://www.veen.world).
Licensed under the [Infinito.Nexus Community License (Non-Commercial)](https://s.infinito.nexus/license).
