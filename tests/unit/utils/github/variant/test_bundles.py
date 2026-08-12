"""Unit tests for :mod:`utils.github.variant.bundles`."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from humanfriendly import parse_size

from utils.github.variant import bundles as vb


class TestChunkIndices(unittest.TestCase):
    def test_splits_into_consecutive_bundles(self) -> None:
        self.assertEqual(vb.chunk_indices(5, 3), [[0, 1, 2], [3, 4]])
        self.assertEqual(vb.chunk_indices(6, 3), [[0, 1, 2], [3, 4, 5]])
        self.assertEqual(vb.chunk_indices(3, 3), [[0, 1, 2]])
        self.assertEqual(vb.chunk_indices(1, 3), [[0]])


class TestResolveBundleSize(unittest.TestCase):
    def test_default_when_unset(self) -> None:
        self.assertEqual(vb.resolve_bundle_size(""), vb.DEFAULT_BUNDLE_SIZE)

    def test_explicit_value(self) -> None:
        self.assertEqual(vb.resolve_bundle_size("2"), 2)

    def test_zero_or_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vb.resolve_bundle_size("0")

    def test_non_numeric_rejected_cleanly(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            vb.resolve_bundle_size("three")


class TestExpandApps(unittest.TestCase):
    VARIANTS = {  # noqa: RUF012
        "web-app-single": [{}],
        "web-app-three": [{}, {}, {}],
        "web-app-five": [{}, {}, {}, {}, {}],
    }

    def test_role_within_bundle_size_shows_all_variants(self) -> None:
        self.assertEqual(
            vb.expand_apps(["web-app-three"], self.VARIANTS, 3),
            [{"apps": "web-app-three", "variant": "0,1,2", "variant_slug": "0-1-2"}],
        )

    def test_missing_variants_treated_as_single(self) -> None:
        self.assertEqual(
            vb.expand_apps(["web-app-unknown"], self.VARIANTS, 3),
            [{"apps": "web-app-unknown", "variant": "", "variant_slug": ""}],
        )

    def test_per_app_bundle_size_override_wins(self) -> None:
        self.assertEqual(
            vb.expand_apps(
                ["web-app-three"],
                self.VARIANTS,
                3,
                bundle_size_per_app={"web-app-three": 1},
            ),
            [
                {"apps": "web-app-three", "variant": "0", "variant_slug": "0"},
                {"apps": "web-app-three", "variant": "1", "variant_slug": "1"},
                {"apps": "web-app-three", "variant": "2", "variant_slug": "2"},
            ],
        )

    def test_per_app_override_leaves_other_apps_bundled(self) -> None:
        self.assertEqual(
            vb.expand_apps(
                ["web-app-three", "web-app-five"],
                self.VARIANTS,
                3,
                bundle_size_per_app={"web-app-five": 2},
            ),
            [
                {"apps": "web-app-three", "variant": "0,1,2", "variant_slug": "0-1-2"},
                {"apps": "web-app-five", "variant": "0,1", "variant_slug": "0-1"},
                {"apps": "web-app-five", "variant": "2,3", "variant_slug": "2-3"},
                {"apps": "web-app-five", "variant": "4", "variant_slug": "4"},
            ],
        )

    def test_role_over_bundle_size_is_split(self) -> None:
        self.assertEqual(
            vb.expand_apps(["web-app-five"], self.VARIANTS, 3),
            [
                {"apps": "web-app-five", "variant": "0,1,2", "variant_slug": "0-1-2"},
                {"apps": "web-app-five", "variant": "3,4", "variant_slug": "3-4"},
            ],
        )

    def test_mixed_list_preserves_app_order(self) -> None:
        out = vb.expand_apps(["web-app-single", "web-app-five"], self.VARIANTS, 3)
        self.assertEqual(
            out,
            [
                {"apps": "web-app-single", "variant": "0", "variant_slug": "0"},
                {"apps": "web-app-five", "variant": "0,1,2", "variant_slug": "0-1-2"},
                {"apps": "web-app-five", "variant": "3,4", "variant_slug": "3-4"},
            ],
        )

    def test_storage_cap_splits_within_bundle_size(self) -> None:
        gb = 1_000_000_000
        out = vb.expand_apps(
            ["web-app-three"],
            self.VARIANTS,
            3,
            storages_per_app={"web-app-three": [300 * gb, 300 * gb, 300 * gb]},
            max_storage_bytes=400 * gb,
        )
        self.assertEqual(
            out,
            [
                {"apps": "web-app-three", "variant": "0", "variant_slug": "0"},
                {"apps": "web-app-three", "variant": "1", "variant_slug": "1"},
                {"apps": "web-app-three", "variant": "2", "variant_slug": "2"},
            ],
        )


class TestBundleIndices(unittest.TestCase):
    def test_count_only_matches_chunk_indices(self) -> None:
        self.assertEqual(vb.bundle_indices(6, 3), [[0, 1, 2], [3, 4, 5]])
        self.assertEqual(vb.bundle_indices(5, 3), [[0, 1, 2], [3, 4]])
        self.assertEqual(vb.bundle_indices(3, 3), [[0, 1, 2]])

    def test_storage_cap_opens_new_bundle_early(self) -> None:
        gb = 1_000_000_000
        storages = [206 * gb, 150 * gb, 159 * gb, 148 * gb, 164 * gb, 143 * gb]
        self.assertEqual(
            vb.bundle_indices(6, 3, storages, 400 * gb),
            [[0, 1], [2, 3], [4, 5]],
        )

    def test_single_variant_over_cap_stands_alone(self) -> None:
        gb = 1_000_000_000
        self.assertEqual(
            vb.bundle_indices(2, 3, [500 * gb, 100 * gb], 400 * gb),
            [[0], [1]],
        )

    def test_none_storage_falls_back_to_count(self) -> None:
        self.assertEqual(
            vb.bundle_indices(4, 3, [None, None, None, None], 400_000_000_000),
            [[0, 1, 2], [3]],
        )


class TestResolveMaxStorage(unittest.TestCase):
    def test_default_when_unset(self) -> None:
        self.assertEqual(vb.resolve_max_storage(""), int(parse_size("350GB")))

    def test_explicit_value(self) -> None:
        self.assertEqual(vb.resolve_max_storage("200GB"), int(parse_size("200GB")))

    def test_zero_disables_cap(self) -> None:
        self.assertIsNone(vb.resolve_max_storage("0"))

    def test_invalid_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vb.resolve_max_storage("huge")


class TestMain(unittest.TestCase):
    def test_reads_argv_and_prints_json(self) -> None:
        with (
            patch.object(vb, "get_variants", return_value={"web-app-five": [{}] * 5}),
            patch.object(vb, "app_variant_storages", return_value={}),
            patch.dict(
                "os.environ",
                {
                    "INFINITO_VARIANT_BUNDLE_SIZE": "3",
                    "INFINITO_DEPLOY_MODE": "",
                    "INFINITO_TOR": "disabled",
                },
            ),
            patch("builtins.print") as mock_print,
        ):
            rc = vb.main(['["web-app-five"]'])
        self.assertEqual(rc, 0)
        printed = json.loads(mock_print.call_args.args[0])
        self.assertEqual(
            printed,
            [
                {
                    "apps": "web-app-five",
                    "variant": "0,1,2",
                    "variant_slug": "0-1-2",
                    "tor": "false",
                    "disable": "tor",
                    "label": "web-app-five 0,1,2",
                },
                {
                    "apps": "web-app-five",
                    "variant": "3,4",
                    "variant_slug": "3-4",
                    "tor": "false",
                    "disable": "tor",
                    "label": "web-app-five 3,4",
                },
            ],
        )

    def test_empty_input_yields_empty_list(self) -> None:
        with (
            patch.object(vb, "get_variants", return_value={}),
            patch.object(vb, "app_variant_storages", return_value={}),
            patch("builtins.print") as mock_print,
        ):
            rc = vb.main([""])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(mock_print.call_args.args[0]), [])

    def test_non_list_json_rejected(self) -> None:
        with (
            patch.object(vb, "get_variants", return_value={}),
            patch.object(vb, "app_variant_storages", return_value={}),
            self.assertRaises(SystemExit),
        ):
            vb.main(['"web-app-five"'])


class TestSwarmMode(unittest.TestCase):
    def _run_swarm(self, apps_json, variants):
        with (
            patch.object(vb, "get_variants", return_value=variants),
            patch.dict(
                "os.environ",
                {"INFINITO_DEPLOY_MODE": "swarm", "INFINITO_TOR": "disabled"},
            ),
            patch("builtins.print") as mock_print,
        ):
            rc = vb.main([apps_json])
        self.assertEqual(rc, 0)
        return json.loads(mock_print.call_args.args[0])

    def test_one_variant_per_runner(self) -> None:
        printed = self._run_swarm(
            '["web-app-five"]',
            {"web-app-five": [{}] * 5},
        )
        self.assertEqual(
            printed,
            [
                {
                    "apps": "web-app-five",
                    "variant": str(i),
                    "variant_slug": str(i),
                    "tor": "false",
                    "disable": "tor",
                    "label": f"\U0001f310web-app-five {i}",
                }
                for i in range(5)
            ],
        )

    def test_every_variant_runs_including_all_off(self) -> None:
        printed = self._run_swarm(
            '["web-app-bbb"]',
            {"web-app-bbb": [{}, {}]},
        )
        self.assertEqual(
            printed,
            [
                {
                    "apps": "web-app-bbb",
                    "variant": "0",
                    "variant_slug": "0",
                    "tor": "false",
                    "disable": "tor",
                    "label": "\U0001f310web-app-bbb 0",
                },
                {
                    "apps": "web-app-bbb",
                    "variant": "1",
                    "variant_slug": "1",
                    "tor": "false",
                    "disable": "tor",
                    "label": "\U0001f310web-app-bbb 1",
                },
            ],
        )

    def test_variant_tokens_map_one_to_one_without_expansion(self) -> None:
        printed = self._run_swarm(
            '["web-app-five#3", "web-app-five#0", "web-app-bare"]',
            {"web-app-five": [{}] * 5, "web-app-bare": [{}, {}]},
        )
        self.assertEqual(
            printed,
            [
                {
                    "apps": "web-app-five",
                    "variant": "3",
                    "variant_slug": "3",
                    "tor": "false",
                    "disable": "tor",
                    "label": "\U0001f310web-app-five 3",
                },
                {
                    "apps": "web-app-five",
                    "variant": "0",
                    "variant_slug": "0",
                    "tor": "false",
                    "disable": "tor",
                    "label": "\U0001f310web-app-five 0",
                },
                {
                    "apps": "web-app-bare",
                    "variant": "0",
                    "variant_slug": "0",
                    "tor": "false",
                    "disable": "tor",
                    "label": "\U0001f310web-app-bare 0",
                },
                {
                    "apps": "web-app-bare",
                    "variant": "1",
                    "variant_slug": "1",
                    "tor": "false",
                    "disable": "tor",
                    "label": "\U0001f310web-app-bare 1",
                },
            ],
        )

    def test_compose_mode_keeps_bundling_and_all_variants(self) -> None:
        with (
            patch.object(vb, "get_variants", return_value={"web-app-bbb": [{}, {}]}),
            patch.object(vb, "app_variant_storages", return_value={}),
            patch.dict(
                "os.environ",
                {"INFINITO_DEPLOY_MODE": "compose", "INFINITO_TOR": "disabled"},
                clear=False,
            ),
            patch("builtins.print") as mock_print,
        ):
            rc = vb.main(['["web-app-bbb"]'])
        self.assertEqual(rc, 0)
        self.assertEqual(
            json.loads(mock_print.call_args.args[0]),
            [
                {
                    "apps": "web-app-bbb",
                    "variant": "0,1",
                    "variant_slug": "0-1",
                    "tor": "false",
                    "disable": "tor",
                    "label": "\U0001f310web-app-bbb 0,1",
                }
            ],
        )


class TestResolveTorMode(unittest.TestCase):
    def test_known_modes_pass_through(self) -> None:
        for raw in ("auto", "ENFORCED", " disabled ", "Exclusive"):
            self.assertEqual(vb.resolve_tor_mode(raw), raw.strip().lower())

    def test_unknown_and_empty_fall_back_to_auto(self) -> None:
        for raw in ("", None, "yes", "tor", "enabled"):
            self.assertEqual(vb.resolve_tor_mode(raw), "auto")


class TestTorCapable(unittest.TestCase):
    def _role(self, root, app, body):
        path = root / app / "meta"
        path.mkdir(parents=True)
        (path / "services.yml").write_text(body)

    def test_reads_the_literal_flag_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._role(root, "web-app-off", "tor:\n  enabled: false\n")
            self._role(root, "web-app-on", "tor:\n  enabled: true\n")
            self._role(
                root,
                "web-app-reactive",
                "tor:\n  enabled: \"{{ 'svc-net-tor' in group_names }}\"\n",
            )
            self._role(root, "web-app-silent", "sso:\n  enabled: true\n")
            with patch.object(vb, "ROLES_DIR", root):
                self.assertFalse(vb.tor_capable("web-app-off"))
                self.assertTrue(vb.tor_capable("web-app-on"))
                self.assertTrue(vb.tor_capable("web-app-reactive"))
                self.assertTrue(vb.tor_capable("web-app-silent"))
                self.assertTrue(vb.tor_capable("web-app-absent"))


TOR_VARIANTS = {
    "web-app-rotating": [
        {"services": {"tor": {"enabled": True}}},
        {"services": {"tor": {"enabled": False}}},
        {"services": {"tor": {"enabled": False}}},
    ],
    "web-app-reactive": [
        {"services": {"tor": {"enabled": "{{ 'svc-net-tor' in group_names }}"}}},
    ],
    "web-app-silent": [{"services": {"sso": {"enabled": True}}}],
}


class TestTorCapableVariants(unittest.TestCase):
    """Roles pin the tor gate true in variant 0 and false in the rest, so the
    entry's own variants decide capability — not the base services.yml."""

    def test_a_variant_pinning_the_gate_off_is_not_capable(self) -> None:
        self.assertFalse(vb.tor_capable("web-app-rotating", "1", TOR_VARIANTS))
        self.assertFalse(vb.tor_capable("web-app-rotating", "2", TOR_VARIANTS))

    def test_the_baseline_variant_is_capable(self) -> None:
        self.assertTrue(vb.tor_capable("web-app-rotating", "0", TOR_VARIANTS))

    def test_a_bundle_is_capable_when_any_of_its_variants_is(self) -> None:
        self.assertTrue(vb.tor_capable("web-app-rotating", "0,1,2", TOR_VARIANTS))
        self.assertFalse(vb.tor_capable("web-app-rotating", "1,2", TOR_VARIANTS))

    def test_a_reactive_flag_stays_capable(self) -> None:
        self.assertTrue(vb.tor_capable("web-app-reactive", "0", TOR_VARIANTS))

    def test_a_variant_without_a_tor_gate_stays_capable(self) -> None:
        self.assertTrue(vb.tor_capable("web-app-silent", "0", TOR_VARIANTS))

    def test_an_out_of_range_index_falls_back_to_the_base_config(self) -> None:
        with patch.object(vb, "_base_tor_capable", return_value=False) as base:
            self.assertFalse(vb.tor_capable("web-app-rotating", "9", TOR_VARIANTS))
        base.assert_called_once_with("web-app-rotating")


class TestAssignTor(unittest.TestCase):
    """The axis decides which entries deploy behind the node onion."""

    APPS = ("a", "b", "c", "d")
    INCAPABLE = "c"

    def _assign(self, mode, run):
        entries = [{"apps": app, "variant": ""} for app in self.APPS]
        with patch.object(vb, "tor_capable", lambda app, *_: app != self.INCAPABLE):
            vb.assign_tor(entries, mode, run)
        return {entry["apps"]: entry for entry in entries}

    def test_enforced_gives_tor_to_every_capable_entry(self) -> None:
        by_app = self._assign("enforced", 0)
        self.assertEqual(
            {app: by_app[app]["tor"] for app in self.APPS},
            {"a": "true", "b": "true", "c": "false", "d": "true"},
        )

    def test_disabled_gives_tor_to_none(self) -> None:
        by_app = self._assign("disabled", 0)
        self.assertEqual(
            {by_app[app]["tor"] for app in self.APPS},
            {"false"},
        )

    def test_auto_alternates_over_the_capable_entries_only(self) -> None:
        even = self._assign("auto", 0)
        self.assertEqual(
            {app: even[app]["tor"] for app in self.APPS},
            {"a": "true", "b": "false", "c": "false", "d": "true"},
        )

    def test_auto_flips_with_the_run_parity(self) -> None:
        odd = self._assign("auto", 1)
        self.assertEqual(
            {app: odd[app]["tor"] for app in self.APPS},
            {"a": "false", "b": "true", "c": "false", "d": "false"},
        )

    def test_two_consecutive_runs_cover_both_states_per_capable_entry(self) -> None:
        even, odd = self._assign("auto", 0), self._assign("auto", 1)
        for app in self.APPS:
            if app == self.INCAPABLE:
                continue
            self.assertEqual(
                {even[app]["tor"], odd[app]["tor"]},
                {"true", "false"},
                f"{app} never sees both states",
            )

    def test_an_entry_without_tor_disables_the_provider(self) -> None:
        by_app = self._assign("auto", 0)
        for entry in by_app.values():
            self.assertEqual(entry["disable"], "" if entry["tor"] == "true" else "tor")


class TestKeepTorVariants(unittest.TestCase):
    """``exclusive`` narrows each entry to the variants that can use the onion."""

    def _entry(self, app, variant):
        return {
            "apps": app,
            "variant": variant,
            "variant_slug": variant.replace(",", "-"),
        }

    def test_a_bundle_shrinks_to_its_capable_variants(self) -> None:
        kept = vb.keep_tor_variants(
            [self._entry("web-app-rotating", "0,1,2")], TOR_VARIANTS
        )
        self.assertEqual(
            kept, [self._entry("web-app-rotating", "0")], "the bundle must shrink to 0"
        )

    def test_a_gap_in_the_middle_yields_a_non_contiguous_bundle(self) -> None:
        variants = {
            "web-app-holed": [
                {"services": {"tor": {"enabled": True}}},
                {"services": {"tor": {"enabled": False}}},
                {"services": {"tor": {"enabled": True}}},
            ]
        }
        kept = vb.keep_tor_variants([self._entry("web-app-holed", "0,1,2")], variants)
        self.assertEqual(kept, [self._entry("web-app-holed", "0,2")])

    def test_an_entry_without_a_capable_variant_is_dropped(self) -> None:
        self.assertEqual(
            vb.keep_tor_variants(
                [self._entry("web-app-rotating", "1,2")], TOR_VARIANTS
            ),
            [],
        )

    def test_a_capable_entry_survives_untouched(self) -> None:
        entry = self._entry("web-app-reactive", "0")
        self.assertEqual(vb.keep_tor_variants([entry], TOR_VARIANTS), [entry])

    def test_a_variantless_entry_falls_back_to_the_base_config(self) -> None:
        entry = {"apps": "web-app-bare", "variant": "", "variant_slug": ""}
        with patch.object(vb, "_base_tor_capable", return_value=False):
            self.assertEqual(vb.keep_tor_variants([entry], TOR_VARIANTS), [])
        with patch.object(vb, "_base_tor_capable", return_value=True):
            self.assertEqual(vb.keep_tor_variants([entry], TOR_VARIANTS), [entry])


class TestLabelGlyphs(unittest.TestCase):
    """A job name states which of the two networks it tested."""

    ONION = "\U0001f9c5"
    GLOBE = "\U0001f310"

    def _labels(self, deploy_mode, tor_mode):
        with (
            patch.object(vb, "get_variants", return_value={"web-app-bbb": [{}, {}]}),
            patch.object(vb, "app_variant_storages", return_value={}),
            patch.dict(
                "os.environ",
                {"INFINITO_DEPLOY_MODE": deploy_mode, "INFINITO_TOR": tor_mode},
            ),
            patch("builtins.print") as mock_print,
        ):
            vb.main(['["web-app-bbb"]'])
        return [e["label"] for e in json.loads(mock_print.call_args.args[0])]

    def test_an_onion_entry_wears_the_onion(self) -> None:
        for label in self._labels("swarm", "enforced"):
            self.assertTrue(label.startswith(self.ONION), label)

    def test_a_clearnet_entry_wears_the_globe(self) -> None:
        for label in self._labels("swarm", "disabled"):
            self.assertTrue(label.startswith(self.GLOBE), label)

    def test_compose_is_marked_too(self) -> None:
        for label in self._labels("compose", "disabled"):
            self.assertTrue(label.startswith(self.GLOBE), label)

    def test_host_wears_neither(self) -> None:
        for label in self._labels("host", "enforced"):
            self.assertFalse(label.startswith((self.ONION, self.GLOBE)), label)


if __name__ == "__main__":
    unittest.main()
