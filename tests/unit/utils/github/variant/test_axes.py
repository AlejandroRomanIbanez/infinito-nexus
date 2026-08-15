from __future__ import annotations

import unittest
import unittest.mock as mock

from utils.github.variant import axes
from utils.roles.display import display_names
from utils.symbol_glossary import to_emoji

_VARIANTS = {
    "web-app-a": [
        {"services": {"tor": {"enabled": True}}},
        {"services": {"tor": {"enabled": False}}},
    ],
    "web-app-b": [{"services": {}}],
}


def _row(name: str, variant: int, modes: tuple[str, ...], **extra) -> dict:
    return {"name": name, "variant": variant, "modes": modes, **extra}


class TestResolveTorMode(unittest.TestCase):
    def test_known_modes_pass_through(self) -> None:
        for mode in axes.TOR_MODES:
            self.assertEqual(axes.resolve_tor_mode(mode), mode)

    def test_unknown_and_empty_fall_back_to_auto(self) -> None:
        self.assertEqual(axes.resolve_tor_mode("nonsense"), "auto")
        self.assertEqual(axes.resolve_tor_mode(""), "auto")


class TestResolveSweep(unittest.TestCase):
    def test_a_number_is_read(self) -> None:
        self.assertEqual(axes.resolve_sweep("7"), 7)

    def test_garbage_reads_as_zero(self) -> None:
        self.assertEqual(axes.resolve_sweep("x"), 0)
        self.assertEqual(axes.resolve_sweep(""), 0)


class TestTorCapable(unittest.TestCase):
    def test_a_variant_pinning_the_gate_false_is_incapable(self) -> None:
        self.assertFalse(axes.tor_capable("web-app-a", 1, _VARIANTS))

    def test_a_variant_pinning_the_gate_true_is_capable(self) -> None:
        self.assertTrue(axes.tor_capable("web-app-a", 0, _VARIANTS))

    def test_an_unset_gate_counts_as_capable(self) -> None:
        self.assertTrue(axes.tor_capable("web-app-b", 0, _VARIANTS))


class TestPickMode(unittest.TestCase):
    def test_a_single_offer_is_always_taken(self) -> None:
        for position in range(4):
            self.assertEqual(axes.pick_mode(("host",), position, 0), "host")

    def test_two_offers_alternate_by_position(self) -> None:
        offered = ("compose", "swarm")
        picks = [axes.pick_mode(offered, position, 0) for position in range(4)]
        self.assertEqual(picks, ["compose", "swarm", "compose", "swarm"])

    def test_the_sweep_flips_which_offer_leads(self) -> None:
        offered = ("compose", "swarm")
        self.assertEqual(axes.pick_mode(offered, 0, 0), "compose")
        self.assertEqual(axes.pick_mode(offered, 0, 1), "swarm")

    def test_an_empty_offer_is_a_bug_not_a_fallback(self) -> None:
        with self.assertRaises(ValueError):
            axes.pick_mode((), 0, 0)


class TestAxesDecouple(unittest.TestCase):
    def test_a_row_walks_all_four_combinations_in_four_sweeps(self) -> None:
        offered = ("compose", "swarm")
        seen = {
            (axes.pick_mode(offered, 0, sweep), axes.wants_tor(0, sweep))
            for sweep in range(4)
        }
        self.assertEqual(len(seen), 4)


class TestArtifactSlug(unittest.TestCase):
    def test_the_entry_carries_the_slug_the_reporter_looks_for(self) -> None:
        from cli.meta.ci.report_failures import artifact_name

        rows = [_row("web-app-b", 0, ("compose", "swarm"), priority=True)]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        for entry in entries:
            with self.subTest(entry["label"]):
                self.assertEqual(
                    f"rescue-diagnostics-{entry['artifact']}",
                    artifact_name(
                        entry["mode"],
                        entry["apps"],
                        entry["variant"],
                        entry["tor"] == "true",
                    ),
                )

    def test_the_onion_state_keeps_two_runs_of_one_variant_apart(self) -> None:
        rows = [_row("web-app-b", 0, ("compose",), priority=True)]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        self.assertEqual(len({e["artifact"] for e in entries}), len(entries))

    def test_a_variantless_row_gets_no_dangling_separator(self) -> None:
        self.assertEqual(
            axes.artifact_slug("host", "sys-front-proxy", "", False),
            "host-sys-front-proxy",
        )


class TestTorStates(unittest.TestCase):
    def test_a_capable_tor_mode_covers_both_states_under_auto(self) -> None:
        self.assertEqual(
            axes.tor_states("compose", capable=True, tor_mode="auto"), [True, False]
        )

    def test_an_incapable_row_only_runs_clearnet(self) -> None:
        self.assertEqual(
            axes.tor_states("compose", capable=False, tor_mode="auto"), [False]
        )

    def test_host_carries_no_onion_axis(self) -> None:
        self.assertEqual(
            axes.tor_states("host", capable=True, tor_mode="auto"), [False]
        )

    def test_an_explicit_narrowing_wins_over_full_coverage(self) -> None:
        self.assertEqual(
            axes.tor_states("compose", capable=True, tor_mode="enforced"), [True]
        )
        self.assertEqual(
            axes.tor_states("compose", capable=True, tor_mode="disabled"), [False]
        )

    def test_exclusive_drops_an_incapable_row_entirely(self) -> None:
        self.assertEqual(
            axes.tor_states("compose", capable=False, tor_mode="exclusive"), []
        )


class TestCombinations(unittest.TestCase):
    def test_two_modes_on_the_onion_axis_yield_four_runs(self) -> None:
        self.assertEqual(
            axes.combinations(("compose", "swarm"), capable=True, tor_mode="auto"),
            [
                ("compose", True),
                ("compose", False),
                ("swarm", True),
                ("swarm", False),
            ],
        )

    def test_a_stackless_role_yields_compose_pair_plus_one_host(self) -> None:
        self.assertEqual(
            axes.combinations(("compose", "host"), capable=True, tor_mode="auto"),
            [("compose", True), ("compose", False), ("host", False)],
        )

    def test_an_incapable_variant_halves_the_cross_product(self) -> None:
        self.assertEqual(
            axes.combinations(("compose", "swarm"), capable=False, tor_mode="auto"),
            [("compose", False), ("swarm", False)],
        )


class TestPriorityCoverage(unittest.TestCase):
    def test_a_priority_row_runs_every_combination_in_one_sweep(self) -> None:
        rows = [_row("web-app-b", 0, ("compose", "swarm"), priority=True)]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        self.assertEqual(
            {(e["mode"], e["tor"]) for e in entries},
            {
                ("compose", "true"),
                ("compose", "false"),
                ("swarm", "true"),
                ("swarm", "false"),
            },
        )

    def test_a_regular_row_still_takes_exactly_one_combination(self) -> None:
        rows = [_row("web-app-b", 0, ("compose", "swarm"))]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        self.assertEqual(len(entries), 1)

    def test_priority_coverage_does_not_move_with_the_sweep(self) -> None:
        rows = [_row("web-app-b", 0, ("compose", "swarm"), priority=True)]
        shapes = {
            frozenset(
                (e["mode"], e["tor"])
                for e in axes.assign(
                    rows, sweep=sweep, tor_mode="auto", variants_per_app=_VARIANTS
                )
            )
            for sweep in range(4)
        }
        self.assertEqual(len(shapes), 1)

    def test_every_priority_job_gets_a_distinct_label(self) -> None:
        rows = [_row("web-app-b", 0, ("compose", "swarm"), priority=True)]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        self.assertEqual(len({e["label"] for e in entries}), len(entries))

    def test_an_incapable_priority_variant_skips_its_onion_runs(self) -> None:
        rows = [_row("web-app-a", 1, ("compose", "swarm"), priority=True)]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        self.assertEqual([e["tor"] for e in entries], ["false", "false"])


class TestAssign(unittest.TestCase):
    def test_every_row_becomes_one_entry(self) -> None:
        rows = [
            _row("web-app-a", 0, ("compose", "swarm")),
            _row("web-app-a", 1, ("compose", "swarm")),
        ]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        self.assertEqual([e["variant"] for e in entries], ["0", "1"])

    def test_the_label_opens_with_the_mode_glyph(self) -> None:
        rows = [_row("web-app-a", 0, ("compose",))]
        entry = axes.assign(
            rows, sweep=0, tor_mode="disabled", variants_per_app=_VARIANTS
        )[0]
        self.assertTrue(entry["label"].startswith(to_emoji("compose")))

    def test_a_host_row_carries_no_onion_glyph(self) -> None:
        rows = [_row("web-app-b", 0, ("host",))]
        entry = axes.assign(
            rows, sweep=0, tor_mode="enforced", variants_per_app=_VARIANTS
        )[0]
        self.assertEqual(entry["tor"], "false")
        self.assertNotIn(to_emoji("tor"), entry["label"])
        self.assertNotIn(to_emoji("clearnet"), entry["label"])

    def test_a_priority_row_wears_the_star(self) -> None:
        rows = [_row("web-app-b", 0, ("compose",), priority=True)]
        entry = axes.assign(rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS)[
            0
        ]
        self.assertTrue(entry["label"].endswith(to_emoji("priority")))
        self.assertEqual(entry["priority"], "true")

    def test_enforced_onions_every_capable_row(self) -> None:
        rows = [
            _row("web-app-a", 0, ("compose",)),
            _row("web-app-a", 1, ("compose",)),
        ]
        entries = axes.assign(
            rows, sweep=0, tor_mode="enforced", variants_per_app=_VARIANTS
        )
        self.assertEqual([e["tor"] for e in entries], ["true", "false"])

    def test_disabled_onions_nothing(self) -> None:
        rows = [_row("web-app-a", 0, ("compose",))]
        entries = axes.assign(
            rows, sweep=0, tor_mode="disabled", variants_per_app=_VARIANTS
        )
        self.assertEqual(entries[0]["tor"], "false")
        self.assertEqual(entries[0]["disable"], "tor")

    def test_exclusive_drops_the_rows_that_cannot_take_an_onion(self) -> None:
        rows = [
            _row("web-app-a", 0, ("compose",)),
            _row("web-app-a", 1, ("compose",)),
        ]
        entries = axes.assign(
            rows, sweep=0, tor_mode="exclusive", variants_per_app=_VARIANTS
        )
        self.assertEqual([e["variant"] for e in entries], ["0"])

    def test_a_row_without_tor_disables_the_provider(self) -> None:
        rows = [_row("web-app-a", 1, ("compose",))]
        entry = axes.assign(rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS)[
            0
        ]
        self.assertEqual(entry["disable"], "tor")

    def test_the_provider_row_never_takes_the_clearnet_state(self) -> None:
        provider = axes.tor_provider()
        self.assertIsNotNone(provider)
        for sweep in range(4):
            for tor_mode in axes.TOR_MODES:
                with self.subTest(sweep=sweep, tor_mode=tor_mode):
                    entries = axes.assign(
                        [_row(provider, 0, ("compose", "swarm"), priority=True)],
                        sweep=sweep,
                        tor_mode=tor_mode,
                    )
                    self.assertEqual(
                        [e["disable"] for e in entries], [""] * len(entries)
                    )
                    self.assertNotIn("false", [e["tor"] for e in entries])


class TestParseLabel(unittest.TestCase):
    def _title(self, mode: str, app: str, variant: str, **kw) -> str:
        rows = [_row(app, int(variant), (mode,), **kw)]
        return axes.assign(
            rows, sweep=0, tor_mode="enforced", variants_per_app=_VARIANTS
        )[0]["label"]

    def test_a_label_round_trips_through_the_parser(self) -> None:
        for mode in ("compose", "swarm", "host"):
            with self.subTest(mode):
                title = self._title(mode, "web-app-a", "0")
                label = axes.parse_label(title)
                self.assertIsNotNone(label)
                self.assertEqual(label.mode, mode)
                self.assertEqual(label.variant, "0")
                self.assertEqual(display_names().decode(label.name), "web-app-a")

    def test_the_onion_state_survives_the_round_trip(self) -> None:
        rows = [_row("web-app-b", 0, ("compose",), priority=True)]
        entries = axes.assign(
            rows, sweep=0, tor_mode="auto", variants_per_app=_VARIANTS
        )
        parsed = {axes.parse_label(e["label"]).tor for e in entries}
        self.assertEqual(parsed, {True, False})

    def test_a_host_label_reads_back_as_clearnet(self) -> None:
        title = self._title("host", "web-app-a", "0")
        self.assertFalse(axes.parse_label(title).tor)

    def test_the_priority_star_does_not_bleed_into_the_name(self) -> None:
        title = self._title("compose", "web-app-a", "0", priority=True)
        label = axes.parse_label(title)
        self.assertEqual(display_names().decode(label.name), "web-app-a")

    def test_a_reusable_workflow_prefix_is_tolerated(self) -> None:
        title = "🎶 Orchestrate CI / test-deploy-chunk-1 / " + self._title(
            "swarm", "web-app-a", "0"
        )
        self.assertEqual(axes.parse_label(title).mode, "swarm")

    def test_a_non_deploy_job_yields_nothing(self) -> None:
        self.assertIsNone(axes.parse_label("🎲 Pick distro(s)"))
        self.assertIsNone(axes.parse_label("🧹 Lint"))


class TestEnvironmentReads(unittest.TestCase):
    def test_the_sweep_comes_from_the_environment(self) -> None:
        with mock.patch.dict("os.environ", {"INFINITO_CI_SWEEP": "3"}):
            self.assertEqual(axes.resolve_sweep(), 3)

    def test_the_tor_mode_comes_from_the_environment(self) -> None:
        with mock.patch.dict("os.environ", {"INFINITO_TOR": "exclusive"}):
            self.assertEqual(axes.resolve_tor_mode(), "exclusive")


if __name__ == "__main__":
    unittest.main()
