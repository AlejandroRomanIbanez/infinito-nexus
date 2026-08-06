import unittest

from utils.cache.files import read_text
from utils.roles.mapping import ROLE_FILE_PLAYWRIGHT_SPEC

from . import PROJECT_ROOT

ENV_TEMPLATE_REL = "templates/playwright.env.j2"  # nocheck: role-file-spot
_RULE = "playwright-env-template"


class TestWebAppRolesHavePlaywrightEnvTemplate(unittest.TestCase):
    def test_web_app_roles_have_playwright_env_template(self):
        """
        Every roles/web-app-* role that ships a Playwright spec MUST also
        ship ``templates/playwright.env.j2``.

        The template is not decoration: it is the discovery marker. The
        runner builds its role list from ``rglob("templates/playwright.env.j2")``
        (roles/test-e2e-playwright/filter_plugins/discover_playwright_roles.py),
        so a spec without it is staged nowhere and executed never. Its
        sibling lint ``test_has_spec.py`` makes the spec mandatory for the
        same reason this makes the template mandatory -- without both halves
        the deploy reports a role as covered while nothing ran.

        Opt out per role with ``# nocheck: playwright-env-template`` on the
        first line of the spec, and say why the role is deliberately
        unverified.
        """
        roles_dir = PROJECT_ROOT / "roles"
        self.assertTrue(
            roles_dir.is_dir(), f"'roles' directory not found at: {roles_dir}"
        )

        missing: list[str] = []
        for role_path in sorted(roles_dir.iterdir()):
            if not (role_path.is_dir() and role_path.name.startswith("web-app-")):
                continue

            spec_file = role_path / ROLE_FILE_PLAYWRIGHT_SPEC
            if not spec_file.is_file():
                continue
            if _RULE in read_text(str(spec_file)).split("\n", 1)[0]:
                continue

            if not (role_path / ENV_TEMPLATE_REL).is_file():
                missing.append(role_path.name)

        if missing:
            self.fail(
                f"Playwright spec present but never executed -- missing "
                f"{ENV_TEMPLATE_REL} in:\n  - " + "\n  - ".join(missing)
            )


if __name__ == "__main__":
    unittest.main()
