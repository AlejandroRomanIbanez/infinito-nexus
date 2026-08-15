from __future__ import annotations

import unittest

from cli.meta.ci import chunks


class TestSliceChunks(unittest.TestCase):
    def test_rows_are_cut_into_consecutive_blocks(self) -> None:
        self.assertEqual(chunks.slice_chunks([0, 1, 2, 3, 4], 2), [[0, 1], [2, 3], [4]])

    def test_an_empty_list_yields_no_block(self) -> None:
        self.assertEqual(chunks.slice_chunks([], 3), [])

    def test_a_zero_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            chunks.slice_chunks([1], 0)


class TestOffset(unittest.TestCase):
    def test_a_list_that_fits_is_never_rotated(self) -> None:
        self.assertEqual(chunks.offset(10, 10, 5), 0)
        self.assertEqual(chunks.offset(10, 20, 5), 0)

    def test_consecutive_sweeps_walk_the_list(self) -> None:
        self.assertEqual(
            [chunks.offset(256, 160, sweep) for sweep in range(3)], [0, 160, 64]
        )

    def test_every_row_is_covered_within_two_sweeps(self) -> None:
        count, capacity = 256, 160
        covered = set()
        for sweep in (0, 1):
            start = chunks.offset(count, capacity, sweep)
            covered |= {(start + i) % count for i in range(capacity)}
        self.assertEqual(covered, set(range(count)))


class TestPlan(unittest.TestCase):
    def test_priority_gets_its_own_short_chunk(self) -> None:
        plan = chunks.plan(
            list(range(5)),
            list(range(100, 300)),
            sweep=0,
            size=80,
            blocks=3,
            budget=211,
        )
        self.assertEqual([len(c) for c in plan], [5, 80, 80])
        self.assertEqual(plan[0], list(range(5)))

    def test_the_seam_chunk_is_never_topped_up_with_regular_rows(self) -> None:
        plan = chunks.plan(
            list(range(5)),
            list(range(100, 300)),
            sweep=0,
            size=80,
            blocks=3,
            budget=211,
        )
        self.assertTrue(all(row < 5 for row in plan[0]))

    def test_without_priority_the_first_chunk_is_regular(self) -> None:
        plan = chunks.plan([], list(range(200)), sweep=0, size=80, blocks=3, budget=211)
        self.assertEqual([len(c) for c in plan], [80, 80, 40])

    def test_the_block_count_bounds_the_sweep(self) -> None:
        plan = chunks.plan([], list(range(500)), sweep=0, size=80, blocks=2, budget=500)
        self.assertEqual(len(plan), 2)

    def test_the_job_budget_bounds_the_sweep(self) -> None:
        plan = chunks.plan([], list(range(500)), sweep=0, size=80, blocks=3, budget=100)
        self.assertEqual(sum(len(c) for c in plan), 100)

    def test_priority_alone_may_fill_every_block(self) -> None:
        plan = chunks.plan(
            list(range(300)), list(range(50)), sweep=0, size=80, blocks=3, budget=300
        )
        self.assertEqual([len(c) for c in plan], [80, 80, 80])

    def test_priority_never_moves_with_the_sweep_offset(self) -> None:
        for sweep in range(4):
            plan = chunks.plan(
                list(range(5)),
                list(range(100, 300)),
                sweep=sweep,
                size=80,
                blocks=3,
                budget=211,
            )
            self.assertEqual(plan[0], list(range(5)), f"sweep {sweep}")

    def test_the_regular_tail_rotates_between_sweeps(self) -> None:
        heads = []
        for sweep in range(3):
            plan = chunks.plan(
                [], list(range(256)), sweep=sweep, size=80, blocks=2, budget=256
            )
            heads.append(plan[0][0])
        self.assertEqual(len(set(heads)), 3)

    def test_an_empty_selection_yields_no_chunk(self) -> None:
        self.assertEqual(
            chunks.plan([], [], sweep=0, size=80, blocks=3, budget=211), []
        )


if __name__ == "__main__":
    unittest.main()
