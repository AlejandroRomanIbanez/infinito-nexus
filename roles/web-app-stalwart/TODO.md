# web-app-stalwart — open items

## Playwright persona flows are blocked (PERSONA_*_BLOCKED=true)

`templates/playwright.env.j2` declares `PERSONA_ADMINISTRATOR_BLOCKED`,
`PERSONA_BIBER_BLOCKED` and `PERSONA_GUEST_BLOCKED` as `true`.

**Why:** the shared persona journeys (`runGuestFlow`/`runBiberFlow`/`runAdminFlow`)
navigate via the dashboard/SSO Account menu, which depends on the Stalwart OIDC
chain. That chain is not wired yet, so the journeys cannot complete.

**Path back to runnable:** wire the OIDC chain (below), confirm Keycloak SSO login
to the WebAdmin + Roundcube works on a `.test` deploy, then flip the three
`PERSONA_*_BLOCKED` flags to `false` (or dashboard-conditional, as web-app-mailu does).

## OIDC chain (the remaining Mailu-parity gap)

The `sso: {flavor: oidc}` block is declared, so Stalwart auto-joins the shared
Keycloak client (redirect URIs include `webmail.<domain>`). Still to do, validated
on a `.test` deploy:

- **Stalwart side:** additive `x:OidcDirectory` (issuerUrl = `OIDC.CLIENT.ISSUER_URL`,
  claimUsername = `preferred_username`) for token validation — WITHOUT switching
  `x:Authentication.directoryId` (that would break the internal admin/mail-bot accounts).
- **Roundcube side:** OAuth2 config → Keycloak + XOAUTH2 to Stalwart.
- Then the `safeSkipUnlessEnabled("sso")` bespoke scenarios run instead of skip.

## Submission port

Stalwart's default submission listener is `465` (implicit TLS); it does not bind
`587`. The compose maps `587` but nothing serves it. Consider adding a `587`
submission listener (standard for desktop clients) or dropping the unused map.
