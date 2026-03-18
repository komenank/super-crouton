<p align="center">
  <img src="../images/super-crouton.png" alt="Super-Crouton" width="120" />
</p>

# Cloudflare Tunnels Setup

This guide walks through installing `cloudflared`, creating a tunnel, and configuring the two public hostnames required by super-crouton.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Install cloudflared](#install-cloudflared)
- [Authenticate with Cloudflare](#authenticate-with-cloudflare)
- [Create a Tunnel](#create-a-tunnel)
- [Configure Public Hostnames](#configure-public-hostnames)
- [Run as a System Service](#run-as-a-system-service)
- [Verify](#verify)

---

## Prerequisites

- A Cloudflare account (free tier is sufficient)
- A domain whose DNS is managed by Cloudflare
- A Linux host where the super-crouton stack will run

---

## Install cloudflared

**Debian / Ubuntu:**

```sh
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list

sudo apt update && sudo apt install cloudflared
```

**Other platforms:** see the [official cloudflared install docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

Verify the installation:

```sh
cloudflared --version
```

---

## Authenticate with Cloudflare

```sh
cloudflared tunnel login
```

This opens a browser window. Select the domain you want to use. A certificate file will be saved to `~/.cloudflared/cert.pem`.

---

## Create a Tunnel

```sh
cloudflared tunnel create super-crouton
```

This creates a tunnel and saves its credentials to `~/.cloudflared/<tunnel-id>.json`. Note the tunnel ID printed in the output — you will need it in the next step.

---

## Configure Public Hostnames

Create a config file at `~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-id>
credentials-file: /home/<your-user>/.cloudflared/<tunnel-id>.json

ingress:
  # Keycloak — plain HTTP internally, Cloudflare handles TLS
  - hostname: auth.<your-domain>
    service: http://localhost:18080

  # rdpgw — HTTPS internally (self-signed cert)
  - hostname: rdp.<your-domain>
    service: https://localhost:19443
    originRequest:
      noTLSVerify: true

  # Catch-all — required by cloudflared
  - service: http_status:404
```

Replace `<tunnel-id>`, `<your-user>`, and `<your-domain>` with your actual values.

> **Why `noTLSVerify: true` for rdpgw?**  
> rdpgw terminates its own TLS connection using a self-signed certificate. Cloudflare cannot verify a self-signed cert, so we tell `cloudflared` to skip verification for that origin. Traffic between the user and Cloudflare is still fully encrypted via Cloudflare's certificate.

---

## Route DNS to the Tunnel

```sh
cloudflared tunnel route dns super-crouton auth.<your-domain>
cloudflared tunnel route dns super-crouton rdp.<your-domain>
```

This creates `CNAME` records in your Cloudflare DNS pointing both hostnames to the tunnel. You can verify them in the Cloudflare dashboard under **DNS → Records**.

---

## Run as a System Service

Install and enable `cloudflared` as a systemd service so it starts automatically on boot:

```sh
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

Check the status:

```sh
sudo systemctl status cloudflared
```

---

## Verify

Once the service is running and the super-crouton stack is up, test both hostnames:

```sh
curl -o /dev/null -s -w "%{http_code}\n" https://auth.<your-domain>
curl -o /dev/null -s -w "%{http_code}\n" https://rdp.<your-domain>
```

- `auth.<your-domain>` should return `200` or `303` (Keycloak login redirect)
- `rdp.<your-domain>` should return `200` (rdpgw web UI)

If a hostname returns a Cloudflare error page (520–527), check `sudo systemctl status cloudflared` and confirm the corresponding Docker container is running with `docker ps`.
