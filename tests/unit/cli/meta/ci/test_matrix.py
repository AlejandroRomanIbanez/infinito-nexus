from __future__ import annotations

import unittest
import unittest.mock as mock

from cli.meta.ci import matrix


def _entry(app: str, variant: str, mode: str, *, priority: bool = False) -> dict:
    return {
        "apps": app,
        "variant": variant,
        "mode": mode,
        "tor": "false",
        "priority": "true" if priority else "false",
    }


class TestChunksOf(unittest.TestCase):
    def _chunks(self, entries: list[dict], *, size: int) -> list[list[dict]]:
        with (
            mock.patch.object(matrix.slots, "chunk_size", return_value=size),
            mock.patch.object(matrix.slots, "chunk_count", return_value=4),
            mock.patch.object(matrix.slots, "available", return_value=99),
        ):
            return matrix.chunks_of(entries, 0)

    def test_a_chunk_is_sorted_by_name_then_variant(self) -> None:
        entries = [
            _entry("web-app-b", "1", "compose"),
            _entry("web-app-a", "1", "compose"),
            _entry("web-app-a", "0", "compose"),
        ]
        chunk = self._chunks(entries, size=9)[0]
        self.assertEqual(
            [(e["apps"], e["variant"]) for e in chunk],
            [("web-app-a", "0"), ("web-app-a", "1"), ("web-app-b", "1")],
        )

    def test_the_split_still_follows_the_discovery_ranking(self) -> None:
        entries = [
            _entry("web-app-z", "0", "compose"),
            _entry("web-app-a", "0", "compose"),
        ]
        chunks = self._chunks(entries, size=1)
        self.assertEqual(
            [chunk[0]["apps"] for chunk in chunks], ["web-app-z", "web-app-a"]
        )

    def test_priority_chunks_are_sorted_on_their_own(self) -> None:
        entries = [
            _entry("web-app-z", "0", "compose", priority=True),
            _entry("web-app-a", "0", "compose", priority=True),
            _entry("web-app-b", "0", "compose"),
        ]
        chunks = self._chunks(entries, size=9)
        self.assertEqual([e["apps"] for e in chunks[0]], ["web-app-a", "web-app-z"])
        self.assertEqual([e["apps"] for e in chunks[1]], ["web-app-b"])


if __name__ == "__main__":
    unittest.main()


_REGULAR = [
    _entry("web-app-a", "0", "compose"),
    _entry("web-app-b", "1", "swarm"),
    _entry("web-app-b", "2", "compose"),
]


class TestOffsetIndex(unittest.TestCase):
    def test_nothing_given_starts_at_the_head(self) -> None:
        for raw in (None, "", 0, "0"):
            with self.subTest(raw=raw):
                self.assertEqual(matrix.offset_index(raw, _REGULAR), 0)

    def test_a_number_is_a_row_count(self) -> None:
        self.assertEqual(matrix.offset_index("2", _REGULAR), 2)

    def test_a_negative_count_reads_as_the_head(self) -> None:
        self.assertEqual(matrix.offset_index("-5", _REGULAR), 0)

    def test_a_role_token_starts_at_its_first_row(self) -> None:
        self.assertEqual(matrix.offset_index("web-app-b", _REGULAR), 1)

    def test_a_pinned_variant_starts_at_that_variant(self) -> None:
        self.assertEqual(matrix.offset_index("web-app-b#2", _REGULAR), 2)

    def test_a_pinned_mode_picks_the_row_of_that_mode(self) -> None:
        self.assertEqual(matrix.offset_index("web-app-b#1@swarm", _REGULAR), 1)

    def test_a_token_naming_no_regular_row_aborts(self) -> None:
        with self.assertRaises(SystemExit):
            matrix.offset_index("web-app-gone#3", _REGULAR)
