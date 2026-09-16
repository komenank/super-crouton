#!/usr/bin/env bash
# Verifies the anjoscode login theme against a disposable Keycloak container.
# Touches nothing in the running stack: its own container, its own port, its own
# in-memory database.
set -euo pipefail

IMAGE="quay.io/keycloak/keycloak:26.6.2"
NAME="kc-theme-test"
PORT="18099"
BASE="http://127.0.0.1:${PORT}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEMES_DIR="${REPO_ROOT}/keycloak/themes"
WORK="$(mktemp -d)"

PASS=0
FAIL=0

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }

# assert_contains <file> <needle> <description>
assert_contains() {
  if grep -qF -- "$2" "$1"; then ok "$3"; else bad "$3 (missing: $2)"; fi
}

# assert_status <url> <expected> <description>
assert_status() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$1")"
  if [ "$code" = "$2" ]; then ok "$3"; else bad "$3 (got HTTP $code, want $2)"; fi
}

kcadm() { docker exec "$NAME" /opt/keycloak/bin/kcadm.sh "$@"; }

mkdir -p "$THEMES_DIR"

echo "==> Starting disposable Keycloak on ${PORT}"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" \
  -p "127.0.0.1:${PORT}:8080" \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  -v "${THEMES_DIR}:/opt/keycloak/themes:ro" \
  "$IMAGE" start-dev \
    --spi-theme-cache-themes=false \
    --spi-theme-cache-templates=false \
    --spi-theme-static-max-age=-1 >/dev/null

echo "==> Waiting for readiness"
curl -sf --retry 90 --retry-delay 2 --retry-all-errors --retry-connrefused \
  -o /dev/null "${BASE}/realms/master/.well-known/openid-configuration"

echo "==> Configuring master realm"
kcadm config credentials --server http://localhost:8080 \
  --realm master --user admin --password admin >/dev/null
kcadm update realms/master -s loginTheme=anjoscode -s resetPasswordAllowed=true >/dev/null

# A client WITH a display name, and one WITHOUT, to exercise the fallback chain.
kcadm create clients -r master -s clientId=wiki-test -s name=Wiki \
  -s enabled=true -s publicClient=true -s 'redirectUris=["http://localhost/*"]' >/dev/null
kcadm create clients -r master -s clientId=nameless-test \
  -s enabled=true -s publicClient=true -s 'redirectUris=["http://localhost/*"]' >/dev/null

auth_url() {
  printf '%s/realms/master/protocol/openid-connect/auth?client_id=%s&response_type=code&scope=openid&redirect_uri=http%%3A%%2F%%2Flocalhost%%2Fcb' \
    "$BASE" "$1"
}

echo "==> Fetching pages"
curl -s --max-time 20 -c "${WORK}/cookies.txt" "$(auth_url wiki-test)" -o "${WORK}/login.html"
curl -s --max-time 20 "$(auth_url nameless-test)" -o "${WORK}/nameless.html"

echo
echo "==> Assertions"

# --- the theme resolves at all ---
assert_status "$(auth_url wiki-test)" "200" "sign-in page renders"
assert_contains "${WORK}/login.html" "/login/anjoscode/" "page loads anjoscode theme resources"

# --- inherited base styling is not lost ---
assert_contains "${WORK}/login.html" "css/styles.css"    "parent stylesheet still linked"
assert_contains "${WORK}/login.html" "css/anjoscode.css" "theme stylesheet linked"

# --- upstream head machinery survived the override ---
assert_contains "${WORK}/login.html" "passwordVisibility.js" "password visibility script intact"
assert_contains "${WORK}/login.html" "authChecker.js"        "session polling script intact"
assert_contains "${WORK}/login.html" "importmap"             "import map intact"

# --- the form itself still works ---
assert_contains "${WORK}/login.html" 'name="username"' "username field present"
assert_contains "${WORK}/login.html" 'name="password"' "password field present"

# --- hero panel ---
assert_contains "${WORK}/login.html" "kc-hero"          "hero panel present"
assert_contains "${WORK}/login.html" "super-crouton"    "mascot image referenced"

# --- per-application context ---
assert_contains "${WORK}/login.html" \
  "Continuing to <strong>Wiki</strong>" "named client shows its display name in the hero"
assert_contains "${WORK}/nameless.html" \
  "Continuing to <strong>nameless-test</strong>" "nameless client falls back to clientId in the hero"

# --- stylesheet is actually served ---
CSS_PATH="$(grep -o '/resources/[^"]*/login/anjoscode/css/anjoscode.css' "${WORK}/login.html" | head -1 || true)"
if [ -n "$CSS_PATH" ]; then
  curl -s --max-time 15 "${BASE}${CSS_PATH}" -o "${WORK}/theme.css"
  assert_contains "${WORK}/theme.css" "#627293" "stylesheet served with palette"
else
  bad "stylesheet URL not found in page"
fi

# --- unhappy paths inherit the same shell ---
RESET_PATH="$(grep -o '/realms/master/login-actions/reset-credentials[^"]*' "${WORK}/login.html" | head -1 | sed 's/&amp;/\&/g' || true)"
if [ -n "$RESET_PATH" ]; then
  curl -s --max-time 20 "${BASE}${RESET_PATH}" -o "${WORK}/reset.html"
  assert_contains "${WORK}/reset.html" "kc-hero" "forgot-password page inherits hero"
else
  bad "forgot-password link not found in page"
fi

curl -s --max-time 20 "$(auth_url does-not-exist)" -o "${WORK}/error.html"
assert_contains "${WORK}/error.html" "kc-hero" "error page inherits hero"

# --- invalid credentials: the alert region renders inside the themed shell ---
LOGIN_ACTION="$(grep -o 'action="[^"]*login-actions/authenticate[^"]*"' "${WORK}/login.html" \
  | head -1 | sed 's/^action="//; s/"$//; s/&amp;/\&/g' || true)"
if [ -n "$LOGIN_ACTION" ]; then
  curl -s --max-time 20 -b "${WORK}/cookies.txt" -c "${WORK}/cookies.txt" \
    -X POST "$LOGIN_ACTION" \
    --data-urlencode "username=nobody-here" \
    --data-urlencode "password=definitely-wrong" \
    -o "${WORK}/invalid.html"
  # keycloak.v2 renders a bad login as a FIELD-level error, not a global
  # pf-v5-c-alert block. Assert on the user-visible message instead.
  assert_contains "${WORK}/invalid.html" "Invalid username or password" \
    "invalid credentials render the error message"
  assert_contains "${WORK}/invalid.html" "kc-hero"       "invalid-credentials page keeps hero"
else
  bad "login form action not found in page"
fi

echo
printf 'passed: %d  failed: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
