# OpenBao secrets manager — design

**Date:** 2026-09-17
**Status:** Draft, awaiting review
**Scope:** An OpenBao 2.6.2 instance in the `super-crouton` stack, plus Outline as its pilot consumer

## Problem

Secrets for homelab projects are created ad hoc and live in scattered, git-ignored `.env` files.
There is no single place to store them, nothing controls which service can read what, rotating a
secret means hand-editing files, and there is no record of who read a secret.

## Goal

A self-hosted secrets manager that:

1. Services fetch secrets from **at runtime**, surviving a host reboot with no human involved.
2. Works for **off-the-shelf images** (the majority of consumers) and for **our own code**.
3. Serves consumers on this host now, and on **a second machine on the private network** soon.
4. Lets humans administer it through the existing Keycloak single sign-on.

Explicitly **not** goals: high availability, dynamic secrets (database credentials, PKI), automatic
restart of consumers when a secret rotates, or moving Keycloak's own secrets into OpenBao.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Consumer | Machines first (humans administer) | Services must fetch secrets at runtime |
| Unseal | `static` seal, key file on this host | Unattended reboot with zero extra infrastructure |
| Storage | Integrated Raft, single node | Recommended backend; consistent snapshots; the path to a future second node |
| Machine network | Private only: Docker network now, TLS listener on LAN/Tailscale later | The API never gets a public hostname |
| Human access | UI at `https://vault.anjoscode.com` via Cloudflare Tunnel + Access, OIDC login via Keycloak | Matches Outline and Portainer |
| Machine auth | AppRole, one role + one policy per app | Works identically for sidecars and our own code |
| Secrets engine | KV v2 at `secret/`, path `secret/<app>/<name>` | Versioned; simple per-app policy boundary |
| Off-the-shelf delivery | OpenBao Agent sidecar renders `/secrets/.env`; entrypoint wrapper sources it | Consumer images stay unmodified |
| Own-code delivery | App authenticates with AppRole and reads KV directly | No sidecar needed when we control the code |
| Pilot consumer | Outline | Real off-the-shelf image already in this repo; exercises the whole pattern |

### Rejected alternatives

- **Manual unseal.** Any reboot takes every dependent service down until a human intervenes.
- **Cloud KMS unseal.** Keeps the key off this disk, but adds an internet dependency at boot and a
  cloud account for no gain against the realistic threat (root on this host).
- **Transit unseal from a second OpenBao.** Correct end state, but needs a second machine that does
  not exist yet. **Deferred** — see [Deferred work](#deferred-work).
- **API exposed through Cloudflare Tunnel.** Every client would need Access service-token headers
  (poorly supported by agent tooling), and the most sensitive service would get a public hostname.
- **Render secrets to host disk at deploy time.** Plaintext on disk, and rotation means a redeploy.
- **Compose `env_file:` pointing at the rendered file.** Does not work: compose reads `env_file` on
  the host at `up` time, before the sidecar has rendered anything inside a volume.
- **Moving Keycloak onto OpenBao.** Circular: OpenBao's human login depends on Keycloak.

## Threat model

The static seal key sits on the same host as the encrypted Raft data. **Root on this host can read
every secret** — this design does not defend against that, and neither would Cloud KMS for a running
instance. What the seal key *does* protect is data that leaves the host: Raft snapshots and a stolen
disk image, provided the key is never stored alongside them. Hence the hard rule that the key never
enters `backups/`, and its only other copy lives in the password manager.

## Architecture

```
                 Cloudflare Tunnel + Access
                            │ https://vault.anjoscode.com  (humans, UI)
                            ▼
                     127.0.0.1:18200
                            │
┌───────────────────────────┴───────────────────────────────┐
│ openbao  (openbao/openbao:2.6.2)                          │
│   listener :8200  HTTP   — Docker network + loopback      │
│   listener :8201  TLS    — LAN/Tailscale (disabled now)   │
│   storage raft  → volume openbao_openbao-data             │
│   seal static   → /openbao/seal/unseal.key (ro)           │
│   audit file    → volume openbao_openbao-audit            │
└───────────────────────────┬───────────────────────────────┘
                            │ network: openbao
              ┌─────────────┴──────────────┐
              ▼                            ▼
      outline-openbao-agent          (own-code apps:
      AppRole: outline               AppRole login,
      renders /secrets/.env          read KV directly)
              │ tmpfs volume
              ▼
          outline  (entrypoint sources /secrets/.env, then execs Node)
```

### Layout

```
openbao/
├── docker-compose.yml          # included from the root docker-compose.yml
├── config/openbao.hcl          # server config (committed)
├── unseal.key                  # 32 random bytes — git-ignored, chmod 600
├── policies/
│   ├── admin.hcl
│   └── outline.hcl             # read secret/data/outline/*
├── agent/
│   ├── agent.hcl.template      # reusable sidecar config
│   └── env.ctmpl.template      # reusable .env template
└── README.md                   # bootstrap, onboarding, backup, recovery runbook
outline/openbao/
├── agent.hcl
├── env.ctmpl
├── role_id                     # git-ignored
└── secret_id                   # git-ignored, chmod 600
```

Run compose from the repo root only, like every other included service.

### Server

- Image pinned to `openbao/openbao:2.6.2`, command `server -config=/openbao/config/openbao.hcl`.
- `storage "raft"` on named volume `openbao_openbao-data`, `node_id = "openbao-1"`.
- `seal "static"` with `current_key_id = "<yyyymmdd>-1"` and
  `current_key = "file:///openbao/seal/unseal.key"`. The key is generated with
  `openssl rand -out openbao/unseal.key 32`. Rotation later uses `previous_key`/`previous_key_id`.
- Because the seal is automatic, `bao operator init` produces **recovery keys**, not unseal keys.
  They and the initial root token go into the password manager and nowhere else.
- `audit "file"` declared in the config file (not enabled through the API), writing to volume
  `openbao_openbao-audit`.
- `disable_mlock = true` (the recommended setting with Raft storage).
- `ui = true`, `api_addr`/`cluster_addr` set to the Docker network name.
- Healthcheck: `bao status` exit code (0 = unsealed).

### Network

1. **Docker network `openbao`** — consumers on this host reach `http://openbao:8200`.
2. **`127.0.0.1:18200:8200`** — the Cloudflare Tunnel ingress for `vault.anjoscode.com` (behind
   Access) and the `bao` CLI on this host.
3. **TLS listener on `:8201`** — declared in the config but not published until a second machine
   exists. Publishing it means binding to the chosen LAN or Tailscale interface address and providing
   a certificate from `certs/`. It is never bound to `0.0.0.0` on a public interface.

### Human authentication

- Keycloak realm `anjoscode` gets a confidential client `openbao` with redirect URIs
  `https://vault.anjoscode.com/v1/auth/oidc/*`,
  `https://vault.anjoscode.com/ui/vault/auth/oidc/oidc/callback`, and
  `http://localhost:8250/oidc/callback` (CLI).
- A Keycloak group `openbao-admins` with a group-membership mapper emitting a `groups` claim.
- OpenBao `oidc` auth method with `oidc_discovery_url = https://auth.anjoscode.com/realms/anjoscode`
  and role `admin`: `user_claim = "sub"`, `groups_claim = "groups"`,
  `bound_claims = { groups = ["openbao-admins"] }`, `policies = ["admin"]`.
  **Without the group binding, every realm user would get admin.**
- Once OIDC admin login is verified, the root token is revoked. Emergency access regenerates one
  from the recovery keys (`bao operator generate-root`).

### Machine authentication and policy

- `approle` auth method. Per app: policy `<app>` granting `read` on `secret/data/<app>/*`, and role
  `<app>` bound to that policy with short token TTLs (`token_ttl=1h`, `token_max_ttl=24h`) and
  `secret_id_ttl=0` (no expiry — a documented homelab tradeoff; rotate by issuing a new one).
- **Secret zero:** `role_id` and `secret_id` are written to `<app>/openbao/` on this host,
  git-ignored, `chmod 600`, mounted read-only into the agent. This is the one credential not held
  in OpenBao, and it only unlocks that app's own path.

### Agent sidecar pattern (off-the-shelf images)

For each consumer `<app>`:

- Service `<app>-openbao-agent` (same `openbao/openbao:2.6.2` image, command `agent -config=...`)
  on the `openbao` network. `auto_auth` via AppRole reads the `role_id`/`secret_id` files; a
  `template` stanza renders `env.ctmpl` to `/secrets/.env` with mode `0400`.
- `/secrets` is a named volume backed by **tmpfs** (`driver_opts: type=tmpfs, device=tmpfs`) so
  rendered secrets never touch disk.
- Agent healthcheck: `test -s /secrets/.env`. The app declares
  `depends_on: <app>-openbao-agent: condition: service_healthy`, and the agent declares
  `depends_on: openbao: condition: service_healthy`.
- The app's entrypoint is overridden with a wrapper that preserves the image's original entrypoint
  and command:
  `sh -c 'set -a; . /secrets/.env; set +a; exec <original entrypoint> <original cmd>'`.
  Requires a shell in the image; distroless images need a different approach (out of scope).
- **Rotation:** the agent re-renders on change, but the app only picks up new values on restart.

### Own-code pattern

Apps we write authenticate with AppRole directly (same role/policy shape) and read
`secret/data/<app>/*` with a client library, renewing their token themselves. No sidecar. The
README documents the pattern; no own-code app is migrated in this work.

### Pilot: Outline

- Outline's image entrypoint is `docker-entrypoint.sh`, command `node build/server/index.js`, and it
  has `sh` — confirmed on the running container. The wrapper becomes
  `exec docker-entrypoint.sh node build/server/index.js`.
- Secrets move to `secret/outline/*`: `SECRET_KEY`, `UTILS_SECRET`, `DATABASE_URL`,
  `POSTGRES_PASSWORD`, `OIDC_CLIENT_SECRET`, `SMTP_PASSWORD`. Non-secret settings (`URL`, ports,
  `OIDC_*_URI`, `SMTP_HOST`…) stay in `outline/.env`.
- `outline-postgres` gets **no** sidecar and drops `POSTGRES_PASSWORD` from its environment: the
  official image only reads it when initialising an empty data directory, and its healthcheck
  (`pg_isready`) needs no password. The password's single source of truth becomes
  `secret/outline/POSTGRES_PASSWORD` (also embedded in `DATABASE_URL`). Re-initialising from an empty
  volume means passing it in temporarily; rotating it means `ALTER USER outline PASSWORD ...` plus
  updating both KV entries.
- **Rollback:** the current `outline/.env` is backed up (`backups/outline-env-pre-openbao-<ts>`)
  and kept until Outline has run cleanly from OpenBao through at least one host reboot. Reverting is
  restoring that file and the previous compose definition.
- **Operational coupling:** Outline is now down whenever OpenBao is sealed or broken. The OpenBao
  recovery runbook therefore lives in `openbao/README.md` and the password manager — **never only
  in Outline**.

## Backup and recovery

- `bao operator raft snapshot save` into `backups/openbao-<ts>.snap` (already git-ignored), run by a
  script in `scripts/`. Snapshots are encrypted by the seal key, so they are useless without it —
  and the key is never written to `backups/`.
- Restore drill, documented in `openbao/README.md`: fresh volume → start with the same
  `unseal.key` → `bao operator raft snapshot restore -force`.
- Recovery keys, root-token regeneration, and the unseal key copy all live in the password manager.

## Testing

Mirroring `scripts/test-login-theme.sh`, a disposable harness `scripts/test-openbao.sh` that never
touches the live stack:

1. Starts a throwaway OpenBao with a temporary static key and volume on a non-live port.
2. Initialises, enables KV v2 + AppRole, loads the committed policies.
3. **Unattended unseal:** restarts the container and asserts it comes back unsealed.
4. **Policy boundary:** an `outline` AppRole token can read `secret/outline/*` and is denied
   `secret/other/*`.
5. **Sidecar:** runs the agent with the committed template and asserts `/secrets/.env` renders
   with the expected keys, and that a stub container using the wrapper sees them as env vars.
6. **Backup:** snapshot → wipe volume → restore → secret still readable.

Live verification (manual, after cut-over): `bao status` via `127.0.0.1:18200`; OIDC login to
`vault.anjoscode.com` as an `openbao-admins` member succeeds and a non-member is refused; Outline
login still works; `docker compose restart` of the host stack (and one real reboot) leaves OpenBao
unsealed and Outline healthy; audit log shows the agent's reads.

## Deferred work

- **Transit auto-unseal from a second OpenBao.** Trigger: a second machine joins the stack. Migrate
  the seal from `static` to `transit` (using `disabled = "true"` on the static stanza during seal
  migration), after which the static key file is destroyed.
- **Cross-machine TLS listener.** Trigger: the first consumer on another machine. Pick LAN vs
  Tailscale, provision a certificate, publish `:8201` on that interface only.
- **Orchestration.** This design assumes Docker Compose. A move to Kubernetes/MicroK8s (under
  discussion) would replace the sidecar/wrapper pattern with the Agent injector or CSI provider;
  server config, policies, and the KV layout carry over unchanged.
