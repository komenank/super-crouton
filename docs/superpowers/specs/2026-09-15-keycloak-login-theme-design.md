# Keycloak login theme — design

**Date:** 2026-09-15
**Status:** Approved, ready for implementation
**Scope:** The login flow for realm `anjoscode` on Keycloak 26.6.2

## Problem

Every application in the stack — Outline (Wiki), Portainer, and anything added later — delegates
authentication to Keycloak. The login page is therefore the most-seen screen in the whole stack, and
it is currently stock `keycloak.v2`: PatternFly blue, no logo, no indication of which application the
user is signing in to.

## Goal

A branded login page for realm `anjoscode` that:

1. Carries the project's own identity rather than Keycloak's defaults.
2. Tells the user which application they are heading into.
3. Costs as little as possible to carry across Keycloak upgrades.

Explicitly **not** goals: theming the account console, email templates, or the welcome page.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Visual structure | Split-screen: branded hero panel + form | Chosen over a CSS-only reskin; gives room for identity and per-app context |
| Identity | "Crouton" — mascot plus a palette sampled from `images/super-crouton.png` | Already the project's visual identity; warm rather than corporate |
| Authoring | Native FreeMarker | Every upstream doc and example is FreeMarker; a fix needs no toolchain |
| Delivery | Bind-mounted theme directory | Fast iteration; baking into an image later is a pure delivery change with zero rework |
| Application | One realm-wide theme that adapts per client | One theme to maintain; per-app context comes free from the login context |

### Rejected alternatives

- **CSS-only reskin.** Lower maintenance, but cannot produce the hero panel or per-app context.
- **Keycloakify (React/TS).** Better authoring ergonomics, but introduces a Node toolchain into a
  repo that has no build step at all, and permanently diverges from upstream documentation. The
  benefit is priced for teams overriding many templates; this design overrides one.
- **Baked image from the start.** Immutable deploys, but a slow build-and-recreate loop during the
  design phase. Deferred, not rejected — see "Future work".

## Palette

Sampled from `images/super-crouton.png` by frequency, so the theme and the mascot agree:

| Token | Hex | Share | Role |
|---|---|---|---|
| Dusty blue | `#627293` | 28.4% | Hero background |
| Warm tan | `#a87a63` | 18.8% | Primary button |
| Dark brown | `#48312b` | 10.8% | Body text on cream |
| Cream | `#f7f3eb` | 7.0% | Form panel background |
| Light tan | `#d2b7a0` | 6.2% | Input borders |
| Muted mauve | `#6e5f67` | 5.3% | Secondary text, links |

## Architecture

```
keycloak/themes/anjoscode/
└── login/
    ├── theme.properties
    ├── template.ftl              # the only overridden template
    ├── template.ftl.upstream     # pristine 26.6.2 copy, for three-way diffs
    └── resources/
        ├── css/anjoscode.css
        └── img/super-crouton.png
```

### Why one template is enough

23 of the 31 templates in `keycloak.v2/login/` render through `@layout.registrationLayout`, the macro
defined in `template.ftl`. The remaining 8 (`field.ftl`, `buttons.ftl`, `footer.ftl`,
`social-providers.ftl`, `password-commons.ftl`, `password-validation.ftl`, `register-commons.ftl`,
`user-profile-commons.ftl`) are macro partials included by the others, not standalone pages.

Overriding that single shell therefore restyles the entire login flow — sign-in, password reset, OTP,
consent, error, IdP linking — while leaving exactly one file to reconcile at upgrade time.

### theme.properties

```properties
parent=keycloak.v2
import=common/keycloak
styles=css/styles.css css/anjoscode.css
darkMode=false
```

Two non-obvious points:

- **`styles` replaces the parent's value; it does not append.** `keycloak.v2` declares
  `styles=css/styles.css`, so that file must be listed explicitly. Omitting it silently removes all
  base form styling.
- **`keycloak.v2` ships `darkMode=true`.** This design is a fixed warm palette, so dark mode is
  disabled rather than left to fight the cream and tan with PatternFly's dark tokens.

### Per-application context

The login context exposes the requesting client. The hero panel renders:

```ftl
${client.name!client.clientId!''}
```

`client.name` is the display name, falling back to `clientId`, falling back to omitting the line
entirely — so a client with no display name degrades gracefully instead of rendering "Continuing to".

`client.attributes.logoUri` is available as an optional per-client logo. It is a field in the admin
console, so applications added later need no theme change.

### Delivery

In `keycloak/docker-compose.yml`:

```yaml
volumes:
  - ./themes:/opt/keycloak/themes:ro
```

The relative path resolves against `keycloak/`, the directory of the included compose file. The mount
is read-only: Keycloak never writes to it.

Activation is a realm setting — Realm Settings → Themes → Login theme → `anjoscode` — not a
deployment step. Mounting the theme is inert until that setting changes.

## Risk and rollback

A FreeMarker error in `template.ftl` breaks the login page for every application at once. Three
things contain that risk:

1. **Admin access survives.** The theme applies to realm `anjoscode`. The master realm, which hosts
   the admin console, keeps its own theme and stays reachable, so it is not possible to lock yourself
   out with a broken theme.
2. **Rollback is instant.** Reverting the Login theme dropdown to `keycloak.v2` takes effect
   immediately, with no restart and no redeploy.
3. **Staged rollout.** A per-client login theme override (Clients → *client* → Login theme) exercises
   the theme on one application before it is promoted realm-wide.

## Verification

The theme is verified against a **disposable Keycloak container** — same 26.6.2 image, `start-dev`,
its own port, no shared database — so that no verification step touches the live instance.

Because all login pages share the overridden shell, verification covers the unhappy paths too:

| Page | What it proves |
|---|---|
| Sign-in | The shell compiles; hero, form and palette render |
| Invalid credentials | The error/alert region is styled, not orphaned |
| Forgot password | A non-login page inherits the shell correctly |
| Per-app context | `client.name` resolves, and a nameless client degrades gracefully |

## Upgrade procedure

`template.ftl.upstream` holds the pristine 26.6.2 shell. On each Keycloak upgrade:

1. Extract the new `keycloak.v2/login/template.ftl` from the upgraded image.
2. Three-way diff: `template.ftl.upstream` (old upstream) vs the new upstream vs `template.ftl` (ours).
3. Port upstream's changes into ours, then replace `template.ftl.upstream` with the new baseline.

This turns "guess what changed" into a mechanical merge, and belongs alongside the existing Outline
and Portainer upgrade procedures.

## Future work

Not in scope now, deliberately:

- **Bake the theme into an image.** Same theme source, a two-line `COPY` — `kc.sh build` is only
  required for provider JARs, not for theme directories. Worth doing once the design stops changing.
- **Per-client `logoUri` wiring.** Additive; the theme works without it.
- **Account console and email themes.** Separate theme types, separate decisions.
