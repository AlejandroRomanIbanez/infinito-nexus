from __future__ import annotations

import unittest

from utils.github.variant import selection
from utils.symbol_glossary import to_emoji


def _row(name: str, variant: int) -> dict:
    return {"name": name, "variant": variant}


class TestParseAscii(unittest.TestCase):
    def test_a_bare_role_pins_nothing(self) -> None:
        pin = selection.parse("web-app-a")
        self.assertEqual(pin, selection.Pin("web-app-a"))
        self.assertFalse(pin.pinned)

    def test_every_axis_is_read(self) -> None:
        self.assertEqual(
            selection.parse("web-app-a#0,2@swarm+tor"),
            selection.Pin("web-app-a", (0, 2), "swarm", True),
        )

    def test_clearnet_is_the_other_onion_state(self) -> None:
        self.assertFalse(selection.parse("web-app-a@compose+clearnet").tor)

    def test_a_role_id_ending_in_tor_is_not_read_as_an_axis(self) -> None:
        self.assertEqual(selection.parse("svc-net-tor"), selection.Pin("svc-net-tor"))

    def test_an_unknown_mode_aborts(self) -> None:
        with self.assertRaises(SystemExit):
            selection.parse("web-app-a@swrm")

    def test_an_unknown_onion_state_aborts(self) -> None:
        with self.assertRaises(SystemExit):
            selection.parse("web-app-a+onion")

    def test_an_unparsable_token_aborts(self) -> None:
        with self.assertRaises(SystemExit):
            selection.parse("web-app-a#zwei")


class TestParseLabel(unittest.TestCase):
    def _label(self, mode: str, tor: str) -> str:
        return f"{to_emoji(mode)}{to_emoji(tor)}web-app-a#2"

    def test_the_glyphs_carry_mode_and_onion(self) -> None:
        self.assertEqual(
            selection.parse(self._label("swarm", "tor")),
            selection.Pin("web-app-a", (2,), "swarm", True),
        )

    def test_the_clearnet_glyph_pins_the_clearnet_state(self) -> None:
        self.assertFalse(selection.parse(self._label("compose", "clearnet")).tor)

    def test_the_priority_star_is_not_part_of_the_name(self) -> None:
        pasted = f"{self._label('compose', 'tor')} {to_emoji('priority')}"
        self.assertEqual(selection.parse(pasted).app, "web-app-a")

    def test_a_host_label_pins_the_mode_only(self) -> None:
        pasted = f"{to_emoji('host')}{to_emoji('test_host')}web-app-a"
        self.assertEqual(
            selection.parse(pasted), selection.Pin("web-app-a", (), "host")
        )

    def test_the_two_spellings_may_not_contradict_each_other(self) -> None:
        with self.assertRaises(SystemExit):
            selection.parse(f"{to_emoji('swarm')}web-app-a@compose")


class TestNames(unittest.TestCase):
    def test_the_query_filters_on_role_ids_only(self) -> None:
        pins = selection.parse_list("web-app-a#0@swarm web-app-b+tor")
        self.assertEqual(selection.names(pins), "web-app-a web-app-b")

    def test_a_role_pinned_twice_is_named_once(self) -> None:
        pins = selection.parse_list("web-app-a#0 web-app-a#1")
        self.assertEqual(selection.names(pins), "web-app-a")


_ROWS = [_row("web-app-a", 0), _row("web-app-a", 1), _row("web-app-b", 0)]


class TestApply(unittest.TestCase):
    def test_no_selection_keeps_every_row_untouched(self) -> None:
        self.assertEqual(selection.apply(_ROWS, []), _ROWS)

    def test_a_pinned_variant_drops_the_other_variants(self) -> None:
        kept = selection.apply(_ROWS, selection.parse_list("web-app-a#1"))
        self.assertEqual([row["variant"] for row in kept], [1])

    def test_the_pinned_axes_ride_along_on_the_row(self) -> None:
        kept = selection.apply(_ROWS, selection.parse_list("web-app-a#0@swarm+tor"))
        self.assertEqual(kept[0]["pin_mode"], "swarm")
        self.assertTrue(kept[0]["pin_tor"])

    def test_an_unpinned_row_carries_open_axes(self) -> None:
        kept = selection.apply(_ROWS, selection.parse_list("web-app-b"))
        self.assertEqual([kept[0]["pin_mode"], kept[0]["pin_tor"]], [None, None])

    def test_one_variant_that_failed_in_two_modes_comes_back_twice(self) -> None:
        kept = selection.apply(
            _ROWS,
            selection.parse_list("web-app-a#0@compose+tor web-app-a#0@swarm+tor"),
        )
        self.assertEqual(
            [(row["variant"], row["pin_mode"], row["pin_tor"]) for row in kept],
            [(0, "compose", True), (0, "swarm", True)],
        )

    def test_the_same_narrowing_written_twice_stays_one_deploy(self) -> None:
        kept = selection.apply(
            _ROWS,
            selection.parse_list("web-app-a#0@swarm+tor web-app-a#0@swarm+tor"),
        )
        self.assertEqual(len(kept), 1)

    def test_a_bare_role_loses_to_a_token_that_narrows_the_same_row(self) -> None:
        kept = selection.apply(
            _ROWS, selection.parse_list("web-app-a web-app-a#0@swarm+tor")
        )
        self.assertEqual(
            [(row["variant"], row["pin_mode"]) for row in kept],
            [(0, "swarm"), (1, None)],
        )

    def test_two_pins_on_one_role_keep_their_own_axes(self) -> None:
        kept = selection.apply(
            _ROWS, selection.parse_list("web-app-a#0@swarm web-app-a#1@compose")
        )
        self.assertEqual([row["pin_mode"] for row in kept], ["swarm", "compose"])

    def test_the_query_order_survives_the_selection(self) -> None:
        kept = selection.apply(_ROWS, selection.parse_list("web-app-b web-app-a"))
        self.assertEqual([row["name"] for row in kept], [row["name"] for row in _ROWS])

    def test_a_pin_that_matches_nothing_aborts_instead_of_running_empty(self) -> None:
        with self.assertRaises(SystemExit):
            selection.apply(_ROWS, selection.parse_list("web-app-b#7"))

    def test_a_bare_role_that_matches_nothing_is_tolerated(self) -> None:
        self.assertEqual(selection.apply(_ROWS, selection.parse_list("web-app-c")), [])


if __name__ == "__main__":
    unittest.main()
