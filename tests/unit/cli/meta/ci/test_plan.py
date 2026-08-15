from __future__ import annotations

import unittest

from cli.meta.ci import plan
from utils.symbol_glossary import to_emoji


def _entry(app: str, variant: str, mode: str, *, priority: bool = False) -> dict:
    return {
        "apps": app,
        "variant": variant,
        "mode": mode,
        "tor": "true" if variant == "0" else "false",
        "disable": "",
        "priority": "true" if priority else "false",
        "weight": "42",
        "label": f"{to_emoji(mode)}{app} {variant}",
    }


_PRIORITY = [_entry("web-app-a", "0", "compose", priority=True)]
_REGULAR = [
    _entry("web-app-b", "0", "swarm"),
    _entry("web-app-b", "1", "compose"),
]
_ENTRIES = _PRIORITY + _REGULAR


class TestCells(unittest.TestCase):
    def test_a_row_in_a_chunk_reports_that_chunk(self) -> None:
        rows = plan.cells(
            _ENTRIES, [_PRIORITY, _REGULAR], distros="debian", current=None
        )
        self.assertEqual([row[0] for row in rows], ["0", "1", "1"])

    def test_a_priority_row_is_starred_not_ticked(self) -> None:
        rows = plan.cells(
            _ENTRIES, [_PRIORITY, _REGULAR], distros="debian", current=None
        )
        self.assertEqual(rows[0][-1], to_emoji("priority"))
        self.assertEqual(rows[1][-1], to_emoji("enabled"))

    def test_a_row_outside_the_sweep_is_marked_disabled(self) -> None:
        rows = plan.cells(_ENTRIES, [_PRIORITY], distros="debian", current=None)
        self.assertEqual(rows[1][-1], to_emoji("disabled"))
        self.assertEqual(rows[1][0], "")

    def test_the_current_chunk_is_marked(self) -> None:
        rows = plan.cells(_ENTRIES, [_PRIORITY, _REGULAR], distros="debian", current=1)
        self.assertEqual(rows[0][0], "0")
        self.assertEqual(rows[1][0], f"1{to_emoji('skip')}")

    def test_the_mode_is_rendered_as_its_glyph(self) -> None:
        rows = plan.cells(
            _ENTRIES, [_PRIORITY, _REGULAR], distros="debian", current=None
        )
        self.assertEqual(rows[0][5], to_emoji("compose"))
        self.assertEqual(rows[1][5], to_emoji("swarm"))

    def test_the_tor_state_is_rendered_as_its_glyph(self) -> None:
        rows = plan.cells(
            _ENTRIES, [_PRIORITY, _REGULAR], distros="debian", current=None
        )
        self.assertEqual(rows[0][-2], to_emoji("tor"))
        self.assertEqual(rows[2][-2], to_emoji("clearnet"))

    def test_every_row_carries_the_distro_list(self) -> None:
        rows = plan.cells(
            _ENTRIES, [_PRIORITY, _REGULAR], distros="debian arch", current=None
        )
        self.assertTrue(all(row[6] == "debian arch" for row in rows))


class TestRender(unittest.TestCase):
    def _rows(self) -> list[tuple[str, ...]]:
        return plan.cells(_ENTRIES, [_PRIORITY, _REGULAR], distros="debian", current=0)

    def test_markdown_is_one_table_with_a_chunk_column(self) -> None:
        out = plan.render_markdown("sweep 0", self._rows())
        self.assertEqual(out.count("| ---"), 0)
        self.assertEqual(out.count("\n|---"), 1)
        self.assertIn(f"{to_emoji('chunk')} Chunk", out)
        self.assertIn("web-app-a", out)

    def test_markdown_keeps_one_line_per_row(self) -> None:
        out = plan.render_markdown("sweep 0", self._rows())
        body = [line for line in out.splitlines() if line.startswith("| web")]
        self.assertEqual(len(body), 0)
        self.assertEqual(len([ln for ln in out.splitlines() if ln.startswith("| ")]), 4)

    def test_cli_pads_to_display_width(self) -> None:
        out = plan.render_cli("sweep 0", self._rows())
        lines = out.splitlines()
        self.assertEqual(lines[0], "sweep 0")
        self.assertTrue(lines[2].startswith("---"))
        self.assertEqual(len(lines), 3 + len(_ENTRIES))


if __name__ == "__main__":
    unittest.main()
