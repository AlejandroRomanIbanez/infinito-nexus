"""Whether GitLab announces SMTP AUTH, and on which listener.

Ruby's ``net/smtp`` authenticates whenever a ``user_name`` or ``password`` is
present, falling back to its default auth type — ``authentication: nil`` does
NOT switch it off. So on the provider's SSO relay, where port 25 offers no
AUTH at all, leaving the credentials in the hash makes every send die with
``503 5.5.1 AUTH not allowed`` while GitLab still reports the mail as queued.
The credentials therefore have to be omitted, not merely unaccompanied by an
auth type.

``tls`` and ``enable_starttls_auto`` are the other half: they are mutually
exclusive in ActionMailer, implicit TLS on 465 or STARTTLS on the relay.
"""

from __future__ import annotations

import re
import unittest

from jinja2 import Environment, StrictUndefined

from utils.cache.files import read_text

from . import PROJECT_ROOT

TEMPLATE = (
    PROJECT_ROOT
    / "roles"
    / "web-app-gitlab"
    / "templates"
    / "config"
    / "smtp_settings.rb.j2"
)

RELAY = {
    "host": "mail.infinito.test",
    "port": 25,
    "username": "no-reply@infinito.test",
    "password": "s3cr3t",
    "domain": "infinito.test",
    "auth": False,
    "start_tls": True,
    "tls": False,
}
SUBMISSION = dict(RELAY, port=465, auth=True, start_tls=False, tls=True)


def _render(email: dict, ca_file: str = "", onion_relay: bool = False) -> str:
    env = Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        autoescape=False,  # noqa: S701 - a Ruby config file, and Ansible's templar does not escape either
    )
    env.filters["bool"] = bool
    env.filters["ruby_dq"] = lambda value: '"' + str(value).replace('"', '\\"') + '"'
    return env.from_string(read_text(TEMPLATE)).render(
        GITLAB_EMAIL=email,
        GITLAB_EMAIL_CA_FILE=ca_file,
        GITLAB_EMAIL_ONION_RELAY=onion_relay,
    )


class TestGitlabSmtpSettings(unittest.TestCase):
    def test_a_clearnet_relay_keeps_full_certificate_verification(self):
        rendered = _render(RELAY)
        self.assertNotIn("openssl_verify_mode", rendered)
        self.assertNotIn("ca_file", rendered)

    def test_an_onion_relay_stops_verifying_a_name_no_certificate_can_carry(self):
        """Net::SMTP dies with "certificate verify failed" against a .onion
        relay, and the send is dropped after three silent retries."""
        rendered = _render(dict(RELAY, host="mail.abc.onion"), onion_relay=True)
        self.assertIn('openssl_verify_mode: "none"', rendered)

    def test_our_own_ca_is_trusted_rather_than_skipping_verification(self):
        rendered = _render(
            dict(RELAY, host="mail.abc.onion"),
            ca_file="/tmp/infinito/ca/root-ca.crt",  # noqa: S108 - container path
            onion_relay=True,
        )
        self.assertIn('ca_file: "/tmp/infinito/ca/root-ca.crt"', rendered)
        self.assertNotIn("openssl_verify_mode", rendered)

    def test_the_relay_carries_no_credentials_at_all(self):
        rendered = _render(RELAY)
        self.assertNotIn("user_name", rendered)
        self.assertNotIn("password", rendered)
        self.assertNotIn("s3cr3t", rendered)

    def test_the_relay_announces_no_auth_type(self):
        self.assertNotIn("authentication", _render(RELAY))

    def test_authenticated_submission_still_sends_credentials(self):
        rendered = _render(SUBMISSION)
        self.assertIn('user_name: "no-reply@infinito.test"', rendered)
        self.assertIn("authentication: :login", rendered)

    def test_tls_and_starttls_are_never_both_on(self):
        for email in (RELAY, SUBMISSION):
            rendered = _render(email)
            tls = re.search(r"^\s*tls:\s*(\w+)", rendered, re.MULTILINE).group(1)
            starttls = re.search(
                r"^\s*enable_starttls_auto:\s*(\w+)", rendered, re.MULTILINE
            ).group(1)
            self.assertNotEqual((tls, starttls), ("true", "true"))

    def test_the_relay_uses_starttls_and_the_submission_port_implicit_tls(self):
        self.assertIn("enable_starttls_auto: true", _render(RELAY))
        self.assertIn("tls: false", _render(RELAY))
        self.assertIn("tls: true", _render(SUBMISSION))

    def test_the_hash_stays_syntactically_valid_without_credentials(self):
        rendered = _render(RELAY).strip()
        self.assertTrue(rendered.endswith("}"))
        self.assertNotIn(",\n}", rendered)


if __name__ == "__main__":
    unittest.main()
