#!/usr/bin/env python3
"""
Step 2 — rdpgw setup
Generates rdpgw/.env and rdpgw/config/rdpgw.yaml from user input.

Prerequisites:
  - Keycloak is up and running  (run Step-1-Keycloak-setup.py first)
  - You have created a realm and an OIDC client for rdpgw in Keycloak
  - Your Cloudflare Tunnel (or reverse-proxy) for the RDP gateway is configured
"""

import getpass
import os
import secrets
import sys

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT     = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(REPO_ROOT, "rdpgw", "config", "rdpgw.yaml.template")
OUTPUT_YAML   = os.path.join(REPO_ROOT, "rdpgw", "config", "rdpgw.yaml")
OUTPUT_ENV    = os.path.join(REPO_ROOT, "rdpgw", ".env")


# ── helpers ──────────────────────────────────────────────────────────────────

def header(text):
    width = 60
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)

def prompt(label, hint=None, default=None, required=True, secret=False):
    if hint:
        for line in hint.splitlines():
            print(f"  {line}")
    display_default = f"  [default: {default}]" if default else ""
    while True:
        if secret:
            value = getpass.getpass(f"  {label}{display_default}: ").strip()
        else:
            value = input(f"  {label}{display_default}: ").strip()
        if not value and default:
            return default
        if not value and required:
            print("  This field is required.")
            continue
        return value

def prompt_hosts():
    print(
        "\n  Enter the RDP hosts that users can connect to.\n"
        "  Use the format  hostname:port  or  ip:port  (e.g. gaming:3389).\n"
        "  Note: hostnames work better than raw IPs with the Windows RDP client.\n"
        "  Press Enter with no input when you are done."
    )
    hosts = []
    while True:
        entry = input(f"  Host {len(hosts) + 1} (or Enter to finish): ").strip()
        if not entry:
            if not hosts:
                print("  You must add at least one host.")
                continue
            break
        if ":" not in entry:
            print("  Please include the port, e.g. gaming:3389")
            continue
        hosts.append(entry)
    return hosts

def generate_hex_key(length=16):
    return secrets.token_hex(length)

def confirm_overwrite(path, label):
    if os.path.exists(path):
        answer = input(f"\n  {label} already exists. Overwrite? [y/N]: ").strip().lower()
        return answer == "y"
    return True


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("\nStep 2 of 2 — rdpgw setup")
    print("This will generate rdpgw/.env and rdpgw/config/rdpgw.yaml.")
    print("\n  Make sure Keycloak is running and your OIDC client is configured")
    print("  before proceeding. Run Step-1-Keycloak-setup.py first if you haven't.")

    # ── 1. Gateway ────────────────────────────────────────────────────────────
    header("1 / 4  —  RDP Gateway")

    gateway_address = prompt(
        "Public gateway hostname",
        hint=(
            "The public domain name your users will reach this gateway on,\n"
            "e.g. rdp.example.com  (no https://, no trailing slash).\n"
            "This must match your Cloudflare Tunnel (or reverse-proxy) hostname."
        ),
    )

    rdpgw_port = prompt(
        "Local listen port",
        hint=(
            "\nThe host port Docker will bind to, e.g. 19443.\n"
            "Your Cloudflare Tunnel should point to  https://localhost:<this port>."
        ),
        default="19443",
    )

    # ── 2. RDP Hosts ─────────────────────────────────────────────────────────
    header("2 / 4  —  RDP Hosts")
    hosts = prompt_hosts()

    # ── 3. OpenID Connect ────────────────────────────────────────────────────
    header("3 / 4  —  OpenID Connect (Keycloak)")

    print(
        "\n  You need a Keycloak client configured for rdpgw.\n"
        "  To find or create it:\n"
        "    1. Log in to your Keycloak admin console  (https://<keycloak-hostname>/admin)\n"
        "    2. Select your realm\n"
        "    3. Go to  Clients  →  rdpgw  (create it if it doesn't exist yet)\n"
        "       - Set  Client authentication  to ON\n"
        "       - Enable  Standard flow\n"
        f"      - Add the redirect URI:  https://{gateway_address}/callback\n"
        "    4. Get the client secret from:  Clients → rdpgw → Credentials → Client secret"
    )

    oidc_provider_url = prompt(
        "OIDC provider URL",
        hint=(
            "\nThe full Keycloak realm URL, e.g.:\n"
            "  https://auth.example.com/realms/my-realm"
        ),
    )

    oidc_client_id = prompt(
        "OIDC client ID",
        hint=(
            "\nFound in Keycloak → Clients → your client → Settings → Client ID.\n"
            "Typically:  rdpgw"
        ),
        default="rdpgw",
    )

    oidc_client_secret = prompt(
        "OIDC client secret",
        hint=(
            "\nFound in Keycloak → Clients → rdpgw → Credentials → Client secret.\n"
            "Click 'Regenerate' if no secret is shown yet, then copy the value."
        ),
        secret=True,
    )

    # ── 4. Security keys ─────────────────────────────────────────────────────
    header("4 / 4  —  Security Keys  (auto-generated)")

    print(
        "\n  The following cryptographic keys will be randomly generated for this\n"
        "  deployment. Keep them stable — changing them will invalidate active sessions."
    )

    session_key            = generate_hex_key()
    session_encryption_key = generate_hex_key()
    paa_encryption_key     = generate_hex_key()
    paa_signing_key        = generate_hex_key()

    print(f"  SessionKey            : {session_key}")
    print(f"  SessionEncryptionKey  : {session_encryption_key}")
    print(f"  PAATokenEncryptionKey : {paa_encryption_key}")
    print(f"  PAATokenSigningKey    : {paa_signing_key}")

    # ── Summary ───────────────────────────────────────────────────────────────
    header("Summary")
    print(f"\n  Gateway address  : {gateway_address}")
    print(f"  Local port       : {rdpgw_port}")
    print(f"  RDP hosts        : {', '.join(hosts)}")
    print(f"  OIDC provider    : {oidc_provider_url}")
    print(f"  OIDC client ID   : {oidc_client_id}")
    print(f"  OIDC secret      : {'*' * len(oidc_client_secret)}")
    print()
    confirm = input("  Write these files? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("  Aborted — no files written.")
        sys.exit(0)

    # ── Write rdpgw/.env ──────────────────────────────────────────────────────
    if not confirm_overwrite(OUTPUT_ENV, "rdpgw/.env"):
        print("  Skipping rdpgw/.env.")
    else:
        env_content = (
            f"RDPGW_PORT={rdpgw_port}\n"
            f"\n"
            f"# OIDC configuration\n"
            f"OIDC_ISSUER={oidc_provider_url}\n"
            f"OIDC_CLIENT_ID={oidc_client_id}\n"
            f"OIDC_CLIENT_SECRET={oidc_client_secret}\n"
        )
        with open(OUTPUT_ENV, "w") as f:
            f.write(env_content)
        print("  Written: rdpgw/.env")

    # ── Write rdpgw/config/rdpgw.yaml ─────────────────────────────────────────
    if not confirm_overwrite(OUTPUT_YAML, "rdpgw/config/rdpgw.yaml"):
        print("  Skipping rdpgw/config/rdpgw.yaml.")
    else:
        with open(TEMPLATE_PATH) as f:
            template = f.read()

        hosts_yaml = "\n".join(f"    - {h}" for h in hosts)

        yaml_content = (
            template
            .replace("{{GATEWAY_ADDRESS}}", gateway_address)
            .replace("{{SESSION_KEY}}", session_key)
            .replace("{{SESSION_ENCRYPTION_KEY}}", session_encryption_key)
            .replace("{{HOSTS}}", hosts_yaml)
            .replace("{{OIDC_PROVIDER_URL}}", oidc_provider_url)
            .replace("{{OIDC_CLIENT_ID}}", oidc_client_id)
            .replace("{{OIDC_CLIENT_SECRET}}", oidc_client_secret)
            .replace("{{PAA_ENCRYPTION_KEY}}", paa_encryption_key)
            .replace("{{PAA_SIGNING_KEY}}", paa_signing_key)
        )

        with open(OUTPUT_YAML, "w") as f:
            f.write(yaml_content)
        print("  Written: rdpgw/config/rdpgw.yaml")

    print()
    print("  Done! Start rdpgw with:")
    print("    cd rdpgw && docker compose up -d")
    print()


if __name__ == "__main__":
    main()
