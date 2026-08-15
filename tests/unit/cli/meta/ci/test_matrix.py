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
