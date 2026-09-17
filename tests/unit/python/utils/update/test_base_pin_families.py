"""Immutable tags the updater could not order before.

Two shapes reach the repository that name a fixed release yet failed the semver
gate, so the bump job skipped them and nothing could tell whether a newer one
existed: a vendor patch counter such as ``2.4.0p32`` and a five-component
version such as ``26.04.2.1.1``.
"""

from __future__ import annotations

import unittest

from utils.update.base import (
    is_semver,
    latest_semver,
    version_depth,
    version_flavor,
    version_key,
)


def _latest(current: str, tags: list[str]) -> str | None:
    return latest_semver(tags, version_depth(current), version_flavor(current))


class TestPatchCounterTags(unittest.TestCase):
    def test_a_patch_counter_is_orderable(self):
        self.assertTrue(is_semver("2.4.0p32"))

    def test_it_bumps_within_its_own_counter(self):
        self.assertEqual(_latest("2.4.0p32", ["2.4.0p32", "2.4.0p33"]), "2.4.0p33")

    def test_the_counter_orders_numerically_not_lexically(self):
        self.assertEqual(_latest("2.4.0p9", ["2.4.0p9", "2.4.0p10"]), "2.4.0p10")

    def test_a_later_release_wins_over_a_later_counter(self):
        self.assertEqual(_latest("2.4.0p32", ["2.4.0p99", "2.4.1p1"]), "2.4.1p1")

    def test_it_never_crosses_into_a_four_component_version(self):
        self.assertEqual(
            _latest("2.4.0p32", ["2.4.0p32", "2.4.0.99"]),
            "2.4.0p32",
            "2.4.0.99 is a different tag family and bumping into it would "
            "silently change what the role deploys",
        )

    def test_the_counter_letter_keeps_families_apart(self):
        self.assertEqual(version_flavor("2.4.0p32"), "p")
        self.assertEqual(version_flavor("2.4.0.32"), "")
        self.assertNotEqual(version_depth("2.4.0p32"), version_depth("2.4.0.32"))

    def test_a_plain_release_does_not_bump_into_a_counter(self):
        self.assertEqual(_latest("2.4.0", ["2.4.0", "2.4.0p1"]), "2.4.0")


class TestFiveComponentTags(unittest.TestCase):
    def test_five_components_are_orderable(self):
        self.assertTrue(is_semver("26.04.2.1.1"))
        self.assertEqual(version_depth("26.04.2.1.1"), 5)

    def test_it_bumps_within_its_own_depth(self):
        self.assertEqual(
            _latest("26.04.2.1.1", ["26.04.2.1.1", "26.04.2.1.2"]), "26.04.2.1.2"
        )

    def test_it_never_crosses_into_a_shorter_version(self):
        self.assertEqual(
            _latest("26.04.2.1.1", ["26.04.2.1.1", "27.0.0.0"]), "26.04.2.1.1"
        )


class TestNothingElseChanged(unittest.TestCase):
    """The shapes the updater already handled must keep their family key."""

    def test_known_shapes_keep_their_classification(self):
        cases = {
            "1.2.3": (True, 3, "", (1, 2, 3, 0)),
            "v1.12.27": (True, 3, "", (1, 12, 27, 0)),
            "16": (True, 1, "", (16, 0, 0, 0)),
            "5.4.5-php8.3-apache": (True, 3, "-php8.3-apache", (5, 4, 5, 0)),
        }

        for tag, (semver, depth, flavor, key) in cases.items():
            self.assertEqual(is_semver(tag), semver, tag)
            self.assertEqual(version_depth(tag), depth, tag)
            self.assertEqual(version_flavor(tag), flavor, tag)
            self.assertEqual(version_key(tag), key, tag)

    def test_moving_names_are_still_refused(self):
        for tag in ("latest", "stable", "lts", "alpine", "main"):
            self.assertFalse(is_semver(tag), tag)

    def test_a_flavored_tag_still_refuses_a_different_runtime(self):
        self.assertEqual(
            _latest("5.4.5-php8.3-apache", ["5.4.6-php8.4-apache", "5.4.6"]),
            None,
        )


if __name__ == "__main__":
    unittest.main()
