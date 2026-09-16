# Keycloak Login Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brand the `anjoscode` realm's login flow with a split-screen layout — mascot hero panel beside the form — that names the application the user is signing in to.

**Architecture:** A FreeMarker theme at `keycloak/themes/anjoscode/`, bind-mounted read-only into the Keycloak container. It overrides exactly one template, `template.ftl`, which is the shell 23 of the 31 login templates render through. The override is upstream's file verbatim plus a hero `<aside>` and one wrapper element, so the entire `<head>` and every `<#nested>` hook stay untouched and upgrade diffs stay small.

**Tech Stack:** Keycloak 26.6.2, FreeMarker, PatternFly v5 (inherited from `keycloak.v2`), Docker Compose, bash + curl for verification.

**Spec:** `docs/superpowers/specs/2026-09-15-keycloak-login-theme-design.md`

## Global Constraints

- Keycloak version is **26.6.2** (`quay.io/keycloak/keycloak:26.6.2`). All upstream file extraction and all verification uses this exact tag.
- Theme name is **`anjoscode`**, matching the realm name.
- Parent theme is **`keycloak.v2`**. Never `keycloak` (that is the v1 look) and never `base`.
- `theme.properties` **must** declare `styles=css/styles.css css/anjoscode.css`. The `styles` key replaces the parent's value rather than appending; omitting `css/styles.css` removes all base form styling.
- `darkMode=false`. The palette is a fixed warm light scheme.
- Palette, sampled from `images/super-crouton.png`: dusty blue `#627293`, warm tan `#a87a63`, dark brown `#48312b`, cream `#f7f3eb`, light tan `#d2b7a0`, muted mauve `#6e5f67`.
- The theme mount is **read-only** (`:ro`).
- **No task changes the live realm's login theme.** Activation is a manual step performed by the repo owner. Verification happens exclusively against a disposable container.
- The live `keycloak` container is never stopped, restarted, or recreated by any task in this plan.

---

### Task 1: Verification harness

Builds the test before the thing it tests. The harness starts a throwaway Keycloak with the theme mounted, points the master realm at it, and asserts the rendered HTML. It is also the regression test for future Keycloak upgrades.

**Files:**
- Create: `scripts/test-login-theme.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/test-login-theme.sh`, runnable with no arguments, exit code 0 on pass and non-zero on any failed assertion. Later tasks re-run it unchanged.

- [ ] **Step 1: Write the failing test**

Create `scripts/test-login-theme.sh`:

```bash
#!/usr/bin/env bash
# Verifies the anjoscode login theme against a disposable Keycloak container.
# Touches nothing in the running stack: its own container, its own port, its own
# in-memory database.
set -euo pipefail

# --keep leaves the container running so the themed pages can be browsed by
# hand. Bind address is overridable for remote/SSH setups; the default keeps
# the port off the network (forward it over SSH, or set KC_TEST_BIND).
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

IMAGE="quay.io/keycloak/keycloak:26.6.2"
NAME="kc-theme-test"
PORT="18099"
BIND="${KC_TEST_BIND:-127.0.0.1}"
BASE="http://127.0.0.1:${PORT}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEMES_DIR="${REPO_ROOT}/keycloak/themes"
WORK="$(mktemp -d)"

PASS=0
FAIL=0

cleanup() {
  if [ "$KEEP" = "1" ]; then
    echo
    echo "--keep: container '${NAME}' left running."
    echo "  Sign-in page: ${BASE}/realms/master/protocol/openid-connect/auth?client_id=wiki-test&response_type=code&scope=openid&redirect_uri=http%3A%2F%2Flocalhost%2Fcb"
    echo "  Stop it with: docker rm -f ${NAME}"
  else
    docker rm -f "$NAME" >/dev/null 2>&1 || true
  fi
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
  -p "${BIND}:${PORT}:8080" \
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
```

- [ ] **Step 2: Make it executable and run it to verify it fails**

```bash
chmod +x scripts/test-login-theme.sh
./scripts/test-login-theme.sh
```

Expected: the container starts, then `kcadm update realms/master -s loginTheme=anjoscode` succeeds (Keycloak accepts an unknown theme name) but every rendering assertion fails — no `anjoscode` resources, no `kc-hero`, no mascot — because `keycloak/themes/` does not exist yet. The mount of a non-existent host path also causes Docker to create it as an empty directory owned by root; if that happens, remove it with `sudo rmdir keycloak/themes` before Task 2, or create the directory first.

- [ ] **Step 3: Commit**

```bash
git add scripts/test-login-theme.sh
git commit -m "test: add disposable-container harness for login theme"
```

---

### Task 2: Theme skeleton and compose mount

Gets the theme recognised by Keycloak with no visual change yet: correct inheritance, assets in place, upstream baseline vendored, and the mount wired into compose.

**Files:**
- Create: `keycloak/themes/anjoscode/login/theme.properties`
- Create: `keycloak/themes/anjoscode/login/template.ftl` (verbatim upstream copy)
- Create: `keycloak/themes/anjoscode/login/template.ftl.upstream` (identical, frozen baseline)
- Create: `keycloak/themes/anjoscode/login/resources/img/super-crouton.png`
- Create: `keycloak/themes/anjoscode/login/resources/css/anjoscode.css` (empty placeholder with palette comment)
- Modify: `keycloak/docker-compose.yml` — add the themes volume to the `keycloak` service

**Interfaces:**
- Consumes: `scripts/test-login-theme.sh` from Task 1.
- Produces: theme directory `keycloak/themes/anjoscode/login/`; `template.ftl` defining macro `registrationLayout(bodyClass, displayInfo, displayMessage, displayRequiredFields)`; stylesheet served at `css/anjoscode.css`; image at `img/super-crouton.png`.

- [ ] **Step 1: Create the directory tree and extract the upstream template**

```bash
mkdir -p keycloak/themes/anjoscode/login/resources/css
mkdir -p keycloak/themes/anjoscode/login/resources/img

docker create --name kc-extract quay.io/keycloak/keycloak:26.6.2
docker cp kc-extract:/opt/keycloak/lib/lib/main/org.keycloak.keycloak-themes-26.6.2.jar /tmp/kc-themes.jar
docker rm kc-extract

python3 - <<'PY'
import zipfile
z = zipfile.ZipFile("/tmp/kc-themes.jar")
t = z.read("theme/keycloak.v2/login/template.ftl")
for p in ("keycloak/themes/anjoscode/login/template.ftl",
          "keycloak/themes/anjoscode/login/template.ftl.upstream"):
    open(p, "wb").write(t)
print("wrote", len(t), "bytes to both files")
PY

cp images/super-crouton.png keycloak/themes/anjoscode/login/resources/img/super-crouton.png
```

- [ ] **Step 2: Write theme.properties**

Create `keycloak/themes/anjoscode/login/theme.properties`:

```properties
parent=keycloak.v2
import=common/keycloak

# NOTE: `styles` REPLACES the parent's value rather than appending to it.
# keycloak.v2 declares `styles=css/styles.css`; dropping it here would strip
# all inherited form styling.
styles=css/styles.css css/anjoscode.css

# Fixed warm palette: do not let PatternFly's dark tokens take over.
darkMode=false
```

- [ ] **Step 3: Create the placeholder stylesheet**

Create `keycloak/themes/anjoscode/login/resources/css/anjoscode.css`:

```css
/* anjoscode login theme
 * Palette sampled from images/super-crouton.png:
 *   #627293 dusty blue   — hero background
 *   #a87a63 warm tan     — primary button
 *   #48312b dark brown   — body text
 *   #f7f3eb cream        — form panel
 *   #d2b7a0 light tan    — input borders
 *   #6e5f67 muted mauve  — secondary text
 * Styling lands in Task 4.
 */
```

- [ ] **Step 4: Mount the theme in compose**

In `keycloak/docker-compose.yml`, in the `keycloak` service, directly after the `environment:` block and before `ports:`, add:

```yaml
    volumes:
      - ./themes:/opt/keycloak/themes:ro
```

The relative path resolves against `keycloak/`, the directory holding this included compose file.

- [ ] **Step 5: Validate compose without touching the running stack**

```bash
docker compose config keycloak | grep -A4 'volumes:'
```

Expected: a bind mount with `source: /home/kkomenan/development/super-crouton/keycloak/themes`, `target: /opt/keycloak/themes`, `read_only: true`. Do **not** run `docker compose up`.

- [ ] **Step 6: Run the harness**

```bash
./scripts/test-login-theme.sh
```

Expected: theme-resolution, inherited-styling, head-machinery and form assertions now PASS. Still failing: `kc-hero`, `super-crouton`, `Wiki`, `nameless-test`, palette, and both unhappy-path assertions.

- [ ] **Step 7: Commit**

```bash
git add keycloak/themes keycloak/docker-compose.yml
git commit -m "feat: add anjoscode theme skeleton and mount it into Keycloak"
```

---

### Task 3: Hero panel and per-application context

Adds the split-screen structure. Upstream's file stays byte-identical except for one wrapper element and one `<aside>`.

**Files:**
- Modify: `keycloak/themes/anjoscode/login/template.ftl`

**Interfaces:**
- Consumes: the theme skeleton from Task 2.
- Produces: markup hooks the stylesheet targets in Task 4 — `.kc-split` (flex row wrapper), `.kc-hero` (left panel), `.kc-hero__mascot`, `.kc-hero__word`, `.kc-hero__tagline`, `.kc-hero__app`.

- [ ] **Step 1: Add the hero panel**

In `keycloak/themes/anjoscode/login/template.ftl`, find the opening of the body:

```ftl
<body id="keycloak-bg" class="${properties.kcBodyClass!}" data-page-id="login-${pageId}">
<div class="${properties.kcLogin!}">
```

Replace those two lines with:

```ftl
<body id="keycloak-bg" class="${properties.kcBodyClass!}" data-page-id="login-${pageId}">
<div class="kc-split">
<aside class="kc-hero">
  <img class="kc-hero__mascot" src="${url.resourcesPath}/img/super-crouton.png" alt="" aria-hidden="true">
  <div class="kc-hero__word">anjoscode</div>
  <p class="kc-hero__tagline">One account for everything here.</p>
  <#assign appName = ((client.name)!(client.clientId)!'')?trim>
  <#if appName?has_content>
    <p class="kc-hero__app">Continuing to <strong>${kcSanitize(appName)?no_esc}</strong></p>
  </#if>
</aside>
<div class="${properties.kcLogin!}">
```

- [ ] **Step 2: Close the wrapper**

At the very end of the body, find:

```ftl
    </main>
  </div>
</div>
</body>
```

Replace with:

```ftl
    </main>
  </div>
</div>
</div>
</body>
```

The extra `</div>` closes `.kc-split`. Everything between the two edits is untouched upstream markup.

- [ ] **Step 3: Confirm the diff is exactly these two edits**

```bash
diff keycloak/themes/anjoscode/login/template.ftl.upstream \
     keycloak/themes/anjoscode/login/template.ftl
```

Expected: one insertion block of 10 lines near `<body>`, one added `</div>` at the end. Nothing else. If anything else differs, revert and redo — a small diff is the entire upgrade strategy.

- [ ] **Step 4: Run the harness**

```bash
./scripts/test-login-theme.sh
```

Expected now PASSING: `kc-hero`, `super-crouton`, `Wiki`, `nameless-test`, forgot-password and error pages inherit the hero. Still failing: the palette assertion, since the stylesheet is still a comment.

- [ ] **Step 5: Commit**

```bash
git add keycloak/themes/anjoscode/login/template.ftl
git commit -m "feat: add hero panel with per-application context to login shell"
```

---

### Task 4: Stylesheet

Turns the structure into the Option A design: dusty-blue hero, cream form panel, tan button.

**Files:**
- Modify: `keycloak/themes/anjoscode/login/resources/css/anjoscode.css`

**Interfaces:**
- Consumes: the class hooks produced by Task 3.
- Produces: the finished visual design. No later task depends on specific selectors here.

- [ ] **Step 1: Write the stylesheet**

Replace the contents of `keycloak/themes/anjoscode/login/resources/css/anjoscode.css` with:

```css
/* anjoscode login theme
 * Palette sampled from images/super-crouton.png.
 */
:root {
  --ajc-blue:   #627293;
  --ajc-blue-d: #4a5673;
  --ajc-tan:    #a87a63;
  --ajc-tan-d:  #8f6552;
  --ajc-brown:  #48312b;
  --ajc-cream:  #f7f3eb;
  --ajc-border: #d2b7a0;
  --ajc-mauve:  #6e5f67;
}

/* Drop PatternFly's stock background so the split can own the viewport. */
body#keycloak-bg {
  background: var(--ajc-cream) !important;
  margin: 0;
}

.kc-split {
  display: flex;
  min-height: 100vh;
}

/* ---------- hero ---------- */
.kc-hero {
  flex: 0 0 46%;
  background: linear-gradient(160deg, var(--ajc-blue) 0%, var(--ajc-blue-d) 100%);
  color: var(--ajc-cream);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 3rem 2.5rem;
  gap: 0.35rem;
}
.kc-hero__mascot {
  width: min(260px, 60%);
  height: auto;
  border-radius: 14px;
  margin-bottom: 1.25rem;
}
.kc-hero__word {
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.kc-hero__tagline {
  font-size: 0.95rem;
  color: rgba(247, 243, 235, 0.72);
  margin: 0;
}
.kc-hero__app {
  margin: 1.5rem 0 0;
  font-size: 0.9rem;
  color: rgba(247, 243, 235, 0.85);
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 999px;
  padding: 0.4rem 1rem;
}

/* ---------- form side ----------
 * keycloak.v2 sets properties.kcLogin=pf-v5-c-login, so this is the element
 * template.ftl emits directly after the hero.
 */
.kc-split > .pf-v5-c-login {
  flex: 1 1 54%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ajc-cream);
  padding: 2rem;
}

.kc-split .pf-v5-c-login__main,
.kc-split .pf-v5-c-login__container {
  background: transparent;
  box-shadow: none;
  width: 100%;
  max-width: 24rem;
}

/* Keycloak's own header/brand block is redundant beside the hero. */
.kc-split #kc-header { display: none; }

.kc-split h1#kc-page-title {
  color: var(--ajc-brown);
  font-size: 1.4rem;
  font-weight: 700;
}

.kc-split label,
.kc-split .pf-v5-c-form__label-text {
  color: var(--ajc-brown);
}

.kc-split .pf-v5-c-form-control,
.kc-split input[type="text"],
.kc-split input[type="email"],
.kc-split input[type="password"] {
  background: #fff;
  border: 1px solid var(--ajc-border);
  border-radius: 8px;
  color: var(--ajc-brown);
}
.kc-split .pf-v5-c-form-control:focus-within,
.kc-split input:focus {
  outline: 2px solid var(--ajc-blue);
  outline-offset: 1px;
}

.kc-split .pf-v5-c-button.pf-m-primary {
  background: var(--ajc-tan);
  border-radius: 8px;
  font-weight: 700;
}
.kc-split .pf-v5-c-button.pf-m-primary:hover {
  background: var(--ajc-tan-d);
}

.kc-split a { color: var(--ajc-mauve); }
.kc-split a:hover { color: var(--ajc-brown); }

/* ---------- responsive ---------- */
@media (max-width: 860px) {
  .kc-split { flex-direction: column; min-height: 100vh; }
  .kc-hero {
    flex: 0 0 auto;
    padding: 2rem 1.5rem;
  }
  .kc-hero__mascot { width: 128px; margin-bottom: 0.75rem; }
  .kc-hero__word { font-size: 1.35rem; }
  .kc-hero__tagline { display: none; }
}

@media (prefers-reduced-motion: no-preference) {
  .kc-split .pf-v5-c-button.pf-m-primary { transition: background 0.15s ease; }
}
```

- [ ] **Step 2: Run the harness**

```bash
./scripts/test-login-theme.sh
```

Expected: **all assertions pass**, including `stylesheet served with palette`.

- [ ] **Step 3: Eyeball the rendered page**

No headless browser is installed on this host, so the harness grew a `--keep`
flag instead: it skips teardown and prints a sign-in URL.

```bash
./scripts/test-login-theme.sh --keep
# browse the printed URL, then:
docker rm -f kc-theme-test
```

The port binds to `127.0.0.1` by default. Forward it over SSH, or set
`KC_TEST_BIND=0.0.0.0` to reach it from the LAN.

- [ ] **Step 4: Commit**

```bash
git add keycloak/themes/anjoscode/login/resources/css/anjoscode.css scripts/test-login-theme.sh
git commit -m "feat: style the login theme with the mascot palette"
```

---

### Task 5: Documentation and upgrade procedure

Makes the theme maintainable by someone who was not here, and records the activation steps the owner performs by hand.

**Files:**
- Create: `keycloak/themes/README.md`
- Modify: `README.md` — add Keycloak's theme to the services section

**Interfaces:**
- Consumes: everything above.
- Produces: no code interfaces.

- [ ] **Step 1: Write the theme README**

Create `keycloak/themes/README.md`:

```markdown
# Keycloak themes

## anjoscode (login)

Brands the `anjoscode` realm's login flow: a mascot hero panel beside the sign-in
form, naming the application the user is signing in to.

Design: `docs/superpowers/specs/2026-09-15-keycloak-login-theme-design.md`

### How it is wired

The directory is bind-mounted read-only at `/opt/keycloak/themes` by
`keycloak/docker-compose.yml`. Mounting it does nothing on its own — the theme
only takes effect once a realm or client selects it.

### Activating it

Realm-wide:

    Admin console -> realm `anjoscode` -> Realm settings -> Themes
      -> Login theme -> anjoscode -> Save

One application first (recommended before going realm-wide):

    Admin console -> realm `anjoscode` -> Clients -> <client> -> Settings
      -> Login theme -> anjoscode -> Save

### Rolling back

Set Login theme back to `keycloak.v2`. It applies immediately: no restart, no
redeploy. The theme is scoped to the `anjoscode` realm, so the master realm's
admin console is unaffected and a broken theme cannot lock anyone out.

### Only one template is overridden

`template.ftl` is the shell that 23 of the 31 `keycloak.v2` login templates
render through, via `@layout.registrationLayout`. Overriding it restyles the
whole flow — sign-in, password reset, OTP, consent, error, identity-provider
linking — from one file.

Our copy is upstream's file verbatim plus two edits: a `.kc-split` wrapper with
the `.kc-hero` aside after `<body>`, and the matching `</div>` at the end. Keep
it that way; the small diff is what makes upgrades cheap.

### Upgrading Keycloak

`template.ftl.upstream` is the pristine 26.6.2 shell. On each upgrade:

1. Extract the new shell from the upgraded image:

       docker create --name kc-extract quay.io/keycloak/keycloak:<NEW>
       docker cp kc-extract:/opt/keycloak/lib/lib/main/org.keycloak.keycloak-themes-<NEW>.jar /tmp/kc-themes.jar
       docker rm kc-extract
       python3 -c "import zipfile; open('/tmp/template-new.ftl','wb').write(zipfile.ZipFile('/tmp/kc-themes.jar').read('theme/keycloak.v2/login/template.ftl'))"

2. See what upstream changed:

       diff template.ftl.upstream /tmp/template-new.ftl

3. Apply those changes to `template.ftl`, then replace `template.ftl.upstream`
   with the new baseline.
4. Re-run `scripts/test-login-theme.sh` against the new image tag (update `IMAGE`
   at the top of the script).

Also re-check `theme.properties`: if upstream changes `keycloak.v2`'s own
`styles` value, our `styles=css/styles.css css/anjoscode.css` must be updated to
match, because that key replaces rather than appends.

### Testing

    ./scripts/test-login-theme.sh

Starts a disposable Keycloak on port 18099 with its own in-memory database,
asserts the rendered HTML, and tears it down. It never touches the running stack.
```

- [ ] **Step 2: Update the main README**

In `README.md`, in the Services table, the `keycloak` row's Purpose cell currently reads `OIDC identity provider`. Change it to:

```
OIDC identity provider (custom `anjoscode` login theme)
```

Then immediately after the table's trailing note block, add:

```markdown
> The Keycloak login page uses a custom theme in `keycloak/themes/anjoscode`.
> See [keycloak/themes/README.md](keycloak/themes/README.md) for activation and
> upgrade steps.
```

- [ ] **Step 3: Verify the harness still passes**

```bash
./scripts/test-login-theme.sh
```

Expected: all assertions pass. Documentation changes must not affect it.

- [ ] **Step 4: Commit**

```bash
git add keycloak/themes/README.md README.md
git commit -m "docs: document the anjoscode login theme and its upgrade procedure"
```

---

## Manual activation (owner, not an implementation task)

Deliberately excluded from every task above, because it changes live
authentication for every application in the stack:

1. `docker compose up -d keycloak` from the **repo root** — never from `keycloak/`,
   which would create a second compose project clashing on `container_name`.
   This recreates the container to pick up the themes mount; expect a short SSO
   interruption.
2. Admin console → realm `anjoscode` → Clients → `outline` → Login theme →
   `anjoscode`. Sign in to the Wiki to confirm.
3. Once satisfied: Realm settings → Themes → Login theme → `anjoscode`, and clear
   the per-client override.
4. To roll back at any point, set the theme back to `keycloak.v2`.
