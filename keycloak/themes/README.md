# Keycloak themes

## anjoscode (login)

Brands the `anjoscode` realm's login flow: a mascot hero panel beside the sign-in
form, naming the application the user is signing in to.

Design: [`docs/superpowers/specs/2026-09-15-keycloak-login-theme-design.md`](../../docs/superpowers/specs/2026-09-15-keycloak-login-theme-design.md)

### How it is wired

The directory is bind-mounted read-only at `/opt/keycloak/themes` by
`keycloak/docker-compose.yml`. Mounting it does nothing on its own — the theme
only takes effect once a realm or client selects it.

### Activating it

One application first (recommended before going realm-wide):

    Admin console -> realm `anjoscode` -> Clients -> <client> -> Settings
      -> Login theme -> anjoscode -> Save

Realm-wide:

    Admin console -> realm `anjoscode` -> Realm settings -> Themes
      -> Login theme -> anjoscode -> Save

Picking up the mount requires recreating the container, which briefly interrupts
SSO for every application:

    docker compose up -d keycloak     # from the REPO ROOT, never from keycloak/

Running it from `keycloak/` would create a separate compose project that clashes
on `container_name`.

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

    diff template.ftl.upstream template.ftl

That should show only those two edits. If it shows more, the upgrade story has
quietly gotten more expensive.

### Per-application context

The hero reads the requesting client:

    ((client.name)!(client.clientId)!'')

The chain is parenthesized deliberately. FreeMarker's `!` default operator throws
if the chain's *root* is undefined, and `client` is undefined on the error page —
without the parentheses that page returns a 500.

`client.attributes.logoUri` is available too, if you ever want each application's
own logo in the hero. It is a per-client field in the admin console, so
applications added later need no theme change.

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
4. Update `IMAGE` at the top of `scripts/test-login-theme.sh` to the new tag and
   re-run it.

Also re-check `theme.properties`: if upstream changes `keycloak.v2`'s own
`styles` value, our `styles=css/styles.css css/anjoscode.css` must be updated to
match, because that key replaces rather than appends.

### Testing

    ./scripts/test-login-theme.sh

Starts a disposable Keycloak on port 18099 with its own in-memory database,
asserts the rendered HTML across the sign-in, forgot-password, error and
invalid-credentials pages, then tears it down. It never touches the running
stack.

To look at the pages by hand:

    ./scripts/test-login-theme.sh --keep

leaves the container up and prints a sign-in URL. Stop it with
`docker rm -f kc-theme-test`. The port binds to `127.0.0.1` by default; forward
it over SSH, or set `KC_TEST_BIND=0.0.0.0` to reach it from the LAN.
