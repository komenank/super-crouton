#!/usr/bin/env bash
set -euo pipefail

KASM_VERSION="${KASM_VERSION:-1.18.1}"
INSTALL_DIR="/opt/kasm/${KASM_VERSION}"
SENTINEL="${INSTALL_DIR}/conf/database/data.sql"

# ── Idempotency check ─────────────────────────────────────────────────────────
if [ -f "${SENTINEL}" ]; then
  echo "[kasm_init] Kasm ${KASM_VERSION} already initialized at ${INSTALL_DIR}. Skipping."
  exit 0
fi

echo "[kasm_init] Starting Kasm ${KASM_VERSION} installation (files only)..."

# ── Download ──────────────────────────────────────────────────────────────────
RELEASE_URL="https://kasm-static-content.s3.amazonaws.com/kasm_release_${KASM_VERSION}.tar.gz"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "[kasm_init] Downloading ${RELEASE_URL}..."
curl -fsSL "${RELEASE_URL}" -o "${TMP_DIR}/kasm_release.tar.gz"

echo "[kasm_init] Extracting..."
tar -xf "${TMP_DIR}/kasm_release.tar.gz" -C "${TMP_DIR}"

# ── Install ───────────────────────────────────────────────────────────────────
# -e  = accept EULA non-interactively
# --no-start = generate all configs/certs/sql but do NOT launch any containers
echo "[kasm_init] Running installer..."
bash "${TMP_DIR}/kasm_release/install.sh" \
  --accept-eula \
  --no-start \
  --database-password "${KASM_DB_PASSWORD}"

echo "[kasm_init] Kasm ${KASM_VERSION} initialized successfully."
