# Super-Crouton

A self-hosted Docker stack combining an nginx reverse proxy, [Kasm Workspaces](https://kasmweb.com/) (browser-based virtual desktops), and [Outline](https://www.getoutline.com/) (collaborative wiki).

## Architecture

```
Internet
   │
   ▼  :80 / :443
 ┌────────────────────────────────────────┐
 │           nginx (reverse proxy)        │
 └────────────┬───────────────────────────┘
              │
   ┌──────────┴──────────┐
   ▼                     ▼
kasm.{NGINX_HOST}   outline.{NGINX_HOST}
   │                     │
   ▼                     ▼
 kasm_proxy          outline:3000
 (Kasm internal     (Outline wiki)
  nginx, no public
  port binding)
```

| Public URL | Routes to |
|---|---|
| `http://*` | Redirected to HTTPS |
| `https://kasm.{NGINX_HOST}` | Kasm Workspaces |
| `https://outline.{NGINX_HOST}` | Outline wiki |

## Services

| Service | Image | Purpose |
|---|---|---|
| `nginx` | `nginx:alpine` | Reverse proxy, TLS termination |
| `kasm_init` | built from `./kasm` | One-shot init — downloads & installs Kasm files, then exits |
| `kasm_db` | `kasmweb/postgres:1.18.1` | Kasm's database |
| `kasm_api` | `kasmweb/api:1.18.1` | Kasm API server |
| `kasm_manager` | `kasmweb/manager:1.18.1` | Kasm session manager |
| `kasm_agent` | `kasmweb/agent:1.18.1` | Kasm workspace agent |
| `kasm_guac` | `kasmweb/kasm-guac:1.18.1` | Guacamole gateway (RDP/VNC) |
| `kasm_rdp_gateway` | `kasmweb/rdp-gateway:1.18.1` | Native RDP gateway (port 3389) |
| `kasm_rdp_https_gateway` | `kasmweb/rdp-https-gateway:1.18.1` | RDP-over-HTTPS gateway |
| `kasm_proxy` | `kasmweb/proxy:1.18.1` | Kasm internal proxy (not publicly exposed) |
| `outline` | `outlinewiki/outline:latest` | Wiki |
| `postgres` | `postgres:15-alpine` | Outline database |
| `redis` | `redis:7-alpine` | Outline cache / queues |

## Project structure

```
super-crouton/
├── certs/                          # TLS certificate files (git-ignored)
│   ├── fullchain.pem               # ← add your cert here
│   └── privkey.pem                 # ← add your key here
├── kasm/
│   ├── Dockerfile                  # Init container image
│   └── init.sh                     # Downloads Kasm installer, runs --no-start
├── nginx/
│   ├── nginx.conf                  # Main nginx config
│   └── templates/
│       ├── default.conf.template   # HTTP → HTTPS redirect
│       ├── kasm.conf.template      # kasm.{NGINX_HOST} vhost
│       └── outline.conf.template   # outline.{NGINX_HOST} vhost
├── .env                            # Environment variables (git-ignored)
├── .gitignore
└── docker-compose.yml
```

## Prerequisites

- Docker Engine 24+
- Docker Compose v2
- A domain and DNS records pointing to this host (see options below)
- TLS certificate and key (see options below)

### DNS records

You have two options. Either works — the wildcard approach requires fewer changes as you add new services.

**Option A — Wildcard (recommended)**

Add a single A record that covers all subdomains:

| Type | Host | Data |
|---|---|---|
| A | `*` | `<your server IP>` |
| A | `@` | `<your server IP>` |

**Option B — Per-subdomain records**

Add one A record per service:

| Type | Host | Data |
|---|---|---|
| A | `kasm` | `<your server IP>` |
| A | `outline` | `<your server IP>` |

### TLS certificates

A wildcard DNS record does **not** automatically give you a wildcard TLS cert. Pick the option that matches your DNS choice above.

**Option A — Multi-domain cert (simplest, pairs with either DNS option)**

Uses HTTP challenge — no extra DNS steps required:

```bash
certbot certonly --standalone \
  -d kasm.yourdomain.com \
  -d outline.yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem certs/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   certs/
```

**Option B — Wildcard cert (pairs with wildcard DNS, covers future subdomains)**

Requires a DNS TXT challenge. Certbot will prompt you to temporarily add a `_acme-challenge` TXT record in your DNS provider:

```bash
certbot certonly --manual --preferred-challenges dns \
  -d "*.yourdomain.com"
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem certs/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   certs/
```

## Setup

### 1. Configure environment variables

Edit `.env` and fill in all required values:

| Variable | Description |
|---|---|
| `NGINX_HOST` | Your base domain, e.g. `example.com` |
| `KASM_UID` / `KASM_GID` | Host UID/GID for Kasm processes — run `id -u && id -g` |
| `KASM_DB_PASSWORD` | Password for Kasm's internal PostgreSQL database |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Outline's PostgreSQL credentials |
| `SECRET_KEY` | Outline secret — generate with `openssl rand -hex 32` |
| `UTILS_SECRET` | Outline utils secret — generate with `openssl rand -hex 32` |

Outline also requires at least one **authentication provider** (Slack, Google, or OIDC). Uncomment and fill in the relevant block in `.env`. See the [Outline auth docs](https://docs.getoutline.com/s/hosting/doc/authentication-7ViKRmRY5o).

### 2. Add TLS certificates

Place your certificate and private key in the `certs/` folder:

```
certs/
├── fullchain.pem
└── privkey.pem
```

For a Let's Encrypt certificate:

```bash
certbot certonly --standalone -d kasm.example.com -d outline.example.com
cp /etc/letsencrypt/live/example.com/fullchain.pem certs/
cp /etc/letsencrypt/live/example.com/privkey.pem   certs/
```

### 3. Start the stack

```bash
docker compose up -d
```

On first run, `kasm_init` will download the Kasm 1.18.1 release and run the installer in file-generation mode (`--no-start`), populating `/opt/kasm/1.18.1/` on the host. All other Kasm services wait for this to complete before starting. Subsequent restarts skip this step automatically.

## Ports

| Port | Protocol | Purpose |
|---|---|---|
| `80` | TCP | HTTP (redirects to HTTPS) |
| `443` | TCP | HTTPS — nginx reverse proxy |
| `3389` | TCP | RDP (Kasm native RDP gateway) |

## Upgrading Kasm

1. Update `KASM_VERSION` in `docker-compose.yml` (the `kasm_init` build arg and all image tags).
2. Remove the sentinel to force re-initialization: `sudo rm -rf /opt/kasm/<old_version>`
3. `docker compose up -d --build`

## Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f nginx
docker compose logs -f kasm_proxy
docker compose logs -f outline
```

## Stopping

```bash
docker compose down        # stop and remove containers
docker compose down -v     # also remove volumes (destructive)
```