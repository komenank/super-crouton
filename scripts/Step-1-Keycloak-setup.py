#!/usr/bin/env python3
"""
Step 1 — Keycloak setup
Generates keycloak/.env from user input.

After running this script:
  1. cd keycloak && docker compose up -d
  2. Wait for Keycloak to finish starting up
  3. Log in to https://<your-hostname>/admin  with username 'admin'
  4. Create your realm and the rdpgw OIDC client
  5. Run  scripts/Step-2-Rdpgw-setup.py
"""

import getpass
import os
import sys

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(SCRIPT_DIR)
KC_ENV_PATH = os.path.join(REPO_ROOT, "keycloak", ".env")


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

def confirm_overwrite(path, label):
    if os.path.exists(path):
        answer = input(f"\n  {label} already exists. Overwrite? [y/N]: ").strip().lower()
        return answer == "y"
    return True


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("\nStep 1 of 2 — Keycloak setup")
    print("This will generate keycloak/.env for your deployment.")

    # ── 1. Hostname ───────────────────────────────────────────────────────────
    header("1 / 3  —  Hostname")

    kc_hostname = prompt(
        "Keycloak public hostname",
        hint=(
            "The public domain name your Keycloak instance will be reachable on,\n"
            "e.g. auth.example.com  (no https://, no trailing slash).\n"
            "This must match your Cloudflare Tunnel (or reverse-proxy) hostname."
        ),
    )

    # ── 2. Database credentials ───────────────────────────────────────────────
    header("2 / 3  —  Database Credentials")

    print(
        "\n  Keycloak uses two separate database credentials:\n"
        "    POSTGRES_PASSWORD  — the PostgreSQL superuser/owner password\n"
        "    KC_DB_PASSWORD     — the password Keycloak uses to connect to the DB\n"
        "  They can be the same value, but different values are more secure."
    )

    postgres_password = prompt(
        "PostgreSQL password (POSTGRES_PASSWORD)",
        hint="\nSet a strong password for the PostgreSQL database owner.",
        secret=True,
    )

    kc_db_password = prompt(
        "Keycloak DB password (KC_DB_PASSWORD)",
        hint=(
            "\nPassword Keycloak uses to connect to PostgreSQL.\n"
            "Press Enter to reuse the PostgreSQL password above."
        ),
        default=postgres_password,
        secret=True,
    )

    # ── 3. Admin credentials ──────────────────────────────────────────────────
    header("3 / 3  —  Bootstrap Admin")

    kc_admin_password = prompt(
        "Keycloak bootstrap admin password (KC_BOOTSTRAP_ADMIN_PASSWORD)",
        hint=(
            "Password for the initial 'admin' account created on first startup.\n"
            "You will use this to log in to the Keycloak admin console at:\n"
            f"  https://{kc_hostname}/admin\n"
            "\nNote: this password is only used on the very first startup to create\n"
            "the admin account. After that you can manage users through the console."
        ),
        secret=True,
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    header("Summary")
    print(f"\n  Hostname         : {kc_hostname}")
    print(f"  Postgres password: {'*' * len(postgres_password)}")
    print(f"  KC DB password   : {'*' * len(kc_db_password)}")
    print(f"  Admin password   : {'*' * len(kc_admin_password)}")
    print()
    confirm = input("  Write keycloak/.env? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("  Aborted — no files written.")
        sys.exit(0)

    if not confirm_overwrite(KC_ENV_PATH, "keycloak/.env"):
        print("  Skipping keycloak/.env.")
    else:
        content = (
            f"KC_HOSTNAME={kc_hostname}\n"
            f"\n"
            f"# Database credentials\n"
            f"POSTGRES_PASSWORD={postgres_password}\n"
            f"KC_DB_PASSWORD={kc_db_password}\n"
            f"\n"
            f"# Bootstrap admin (only used on first startup)\n"
            f"KC_BOOTSTRAP_ADMIN_PASSWORD={kc_admin_password}\n"
        )
        with open(KC_ENV_PATH, "w") as f:
            f.write(content)
        print("  Written: keycloak/.env")

    print()
    print("  Next steps:")
    print("    1. cd keycloak && docker compose up -d")
    print(f"   2. Wait for Keycloak to start, then open https://{kc_hostname}/admin")
    print("    3. Log in as 'admin' with the password you just set")
    print("    4. Create your realm and the rdpgw OIDC client")
    print("    5. Run  scripts/Step-2-Rdpgw-setup.py")
    print()


if __name__ == "__main__":
    main()
