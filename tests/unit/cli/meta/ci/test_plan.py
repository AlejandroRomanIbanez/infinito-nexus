from __future__ import annotations

import unittest

from cli.meta.ci import plan


class TestCells(unittest.TestCase):
    def test_keeps_query_order_and_expands_variants(self) -> None:
        rows = [("svc-prio", "⭐"), ("web-app-a", "✅"), ("web-app-b", "❌")]
        cells = plan._cells(
            rows,
            {"svc-prio": 5, "web-app-a": 10, "web-app-b": 7},
            {"svc-prio": 2, "web-app-a": 1, "web-app-b": 1},
            priority="svc-prio",
            distros="debian",
        )
        self.assertEqual(
            cells,
            [
                ("svc-prio", "5", "⭐", "0", "debian", "⭐"),
                ("svc-prio", "5", "⭐", "1", "debian", "⭐"),
                ("web-app-a", "10", "", "0", "debian", "✅"),
                ("web-app-b", "7", "", "0", "debian", "❌"),
            ],
        )


class TestRender(unittest.TestCase):
    def setUp(self) -> None:
        self.sections = [
            (
                "compose",
                54,
                [
                    ("web-app-a", "10", "", "0", "debian", "✅"),
                    ("web-app-b", "7", "", "0", "debian", "❌"),
                ],
            ),
            ("host", 10, [("svc-x", "3", "", "0", "debian", "✅")]),
        ]

    def test_markdown_has_one_section_per_mode_and_no_legend(self) -> None:
        out = plan.render_markdown(self.sections)
        self.assertIn("### 🐳 compose (max jobs: 54)", out)
        self.assertIn("### 💻 host (max jobs: 10)", out)
        self.assertIn(
            "| 📛 Name | 📊 Weight | ⭐ Priority | 🎯 Variant | 🐧 Distros "
            "| ✅ Triggered |",
            out,
        )
        self.assertIn("| web-app-b | 7 |  | 0 | debian | ❌ |", out)
        self.assertNotIn("priority line", out)

    def test_cli_renders_fixed_width_sections(self) -> None:
        out = plan.render_cli(self.sections)
        self.assertIn("🐳 compose (max jobs: 54)", out)
        self.assertIn("💻 host (max jobs: 10)", out)
        header_line = next(
            line for line in out.splitlines() if line.startswith("📛 Name")
        )
        rule_line = next(line for line in out.splitlines() if line.startswith("---"))
        self.assertEqual(len(rule_line), len(rule_line.rstrip()))
        self.assertIn("web-app-a", out)
        self.assertTrue(header_line)


if __name__ == "__main__":
    unittest.main()
