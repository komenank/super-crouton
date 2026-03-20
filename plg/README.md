# PLG — Promtail + Loki + Grafana

Log aggregation and visualization stack for Super-Crouton.  
Collects logs from **all Docker containers** on the host (Keycloak, rdpgw, Postgres, and itself) and makes them searchable and visual in Grafana.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Docker host                                             │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐             │
│  │ keycloak │  │  rdpgw   │  │ keycloak-db│  ...        │
│  └────┬─────┘  └────┬─────┘  └─────┬──────┘             │
│       │              │              │     container logs  │
│       ▼              ▼              ▼                     │
│  ┌──────────────────────────────────────┐                │
│  │          Promtail                     │                │
│  │  (reads /var/lib/docker/containers)   │                │
│  └──────────────┬───────────────────────┘                │
│                 │  push                                   │
│                 ▼                                         │
│  ┌──────────────────────┐                                │
│  │        Loki           │                                │
│  │   localhost:3100      │                                │
│  └──────────┬───────────┘                                │
│             │  query                                      │
│             ▼                                             │
│  ┌──────────────────────┐                                │
│  │       Grafana         │                                │
│  │   localhost:13000     │                                │
│  └──────────────────────┘                                │
└──────────────────────────────────────────────────────────┘
```

## Quick start

```bash
# 1. Create your .env from the example
cp .env.example .env
# Edit .env — at minimum change GF_ADMIN_PASSWORD

# 2. Start the stack
cd plg && docker compose up -d

# 3. Open Grafana
#    http://localhost:13000
#    Login with the credentials from .env
```

Grafana comes pre-provisioned with:
- **Loki datasource** — no manual setup needed
- **RDP Session Monitor dashboard** — under the *Super-Crouton* folder

## What gets collected

Promtail auto-discovers every running Docker container via the Docker socket.  
Each log line is labelled with:

| Label     | Source                             | Example            |
|-----------|------------------------------------|--------------------|
| `container` | Container name                   | `rdpgw`            |
| `service`   | Compose service name             | `keycloak`         |
| `project`   | Compose project name             | `keycloak`, `rdpgw`|

The Promtail pipeline also extracts the **log level** from Keycloak and rdpgw log formats into a `level` label, so you can filter with `{service="rdpgw", level="error"}`.

## Pre-built dashboard

The **RDP Session Monitor** dashboard ships with six panels:

1. **Error & Warning rate** — bar chart across all services
2. **RDP Session Events** — disconnect / connection events from rdpgw
3. **Keycloak Token Events** — token grants vs auth failures
4. **rdpgw Logs** — live log panel, filterable
5. **Keycloak Logs** — live log panel, filterable
6. **All Logs** — unified stream across all services

## Useful LogQL queries

```logql
# All rdpgw errors
{service="rdpgw"} |~ `(?i)error`

# Session disconnects
{service="rdpgw"} |~ `(?i)(disconnect|session closed|EOF|broken pipe|reset by peer)`

# Keycloak token refresh failures (common cause of RDP drops)
{service="keycloak"} |~ `(?i)(REFRESH_TOKEN_ERROR|invalid_grant)`

# Everything from the last hour, all services
{project=~"keycloak|rdpgw"}
```

## Retention

Loki is configured to retain logs for **30 days**. Change `retention_period` in `config/loki-config.yml` to adjust.

## Exposing via Cloudflare Tunnel (optional)

If you want to access Grafana remotely, add a tunnel entry:

| Public hostname           | Service URL               |
|---------------------------|---------------------------|
| `logs.<your-domain>`      | `http://localhost:13000`  |

Then set `GF_ROOT_URL=https://logs.<your-domain>` in `.env` and restart.
