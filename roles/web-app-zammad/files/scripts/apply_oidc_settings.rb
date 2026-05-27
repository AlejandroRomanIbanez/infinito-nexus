# Idempotently apply Zammad's post-bootstrap fqdn/http_type + OIDC settings,
# and pre-create the bootstrap administrator with a local password + Admin
# role so Basic-auth REST-API access works (the OIDC-created user is
# password-less by design — `source: "openid_connect"`).
#
# Expects the following ENV vars (set by the calling shell):
#
#   ZAMMAD_FQDN          - public hostname (e.g. helpdesk.infinito.example)
#   ZAMMAD_HTTP_TYPE     - "https" or "http"
#   OIDC_BUTTON_TEXT     - display label for the login button
#   OIDC_CLIENT_ID       - shared Keycloak client id (= SOFTWARE_DOMAIN)
#   OIDC_CLIENT_SECRET   - shared Keycloak client secret
#   OIDC_ISSUER_URL      - Keycloak realm issuer URL
#   API_BOT_LOGIN        - login for the API-only bot user used by Basic-auth
#                          REST-API regression tests (separate from the
#                          OIDC-managed admin to avoid email-clash on first
#                          OIDC sign-in)
#   API_BOT_EMAIL        - bot email (must NOT match the OIDC admin's email)
#   API_BOT_PASSWORD     - bot local password (Basic-auth secret)

UserInfo.current_user_id = 1

Setting.set("fqdn",      ENV.fetch("ZAMMAD_FQDN"))
Setting.set("http_type", ENV.fetch("ZAMMAD_HTTP_TYPE"))

Setting.set("auth_openid_connect", true)
Setting.set("auth_openid_connect_credentials", {
  "display_name"                 => ENV.fetch("OIDC_BUTTON_TEXT"),
  "identifier"                   => ENV.fetch("OIDC_CLIENT_ID"),
  "secret"                       => ENV.fetch("OIDC_CLIENT_SECRET"),
  "issuer"                       => ENV.fetch("OIDC_ISSUER_URL"),
  "scope"                        => "openid email profile",
  # Use the human-readable Keycloak username (e.g. "administrator") as the
  # Zammad user.login, so the pre-created bootstrap admin below matches on
  # first OIDC sign-in. The default `sub` yields a UUID that would not
  # match — leading to a 422 email-already-used clash on user create.
  "uid_field"                    => "preferred_username",
  "send_scope_to_token_endpoint" => true,
})

# Ensure an API-only bot user exists with a LOCAL password + Admin role for
# Basic-auth REST-API regression tests. Kept separate from the OIDC-managed
# `administrator` user (different login + email) so OIDC's first-sign-in
# user creation does not clash with this pre-seeded user's email
# (`Validation failed: Email address … is already used for another user.`
# 422 from Zammad). The OIDC user stays password-less / source=openid_connect;
# this bot is the one Basic auth talks to.
api_bot = User.find_or_initialize_by(login: ENV.fetch("API_BOT_LOGIN"))
api_bot.email     = ENV.fetch("API_BOT_EMAIL")
api_bot.firstname = "Infinito"
api_bot.lastname  = "API Bot"
api_bot.password  = ENV.fetch("API_BOT_PASSWORD")
api_bot.active    = true
api_bot.roles     = Role.where(name: %w[Admin Agent])
api_bot.save!

# Grant the api bot full access to the default `Users` group so it can
# create / read / change tickets via the REST API. Without an explicit group
# membership, `ticket.agent` permission alone yields 403 on POST /tickets.
users_group = Group.find_or_create_by!(name: "Users") { |g| g.active = true }
api_bot.group_names_access_map = { users_group.name => "full" }
api_bot.save!
