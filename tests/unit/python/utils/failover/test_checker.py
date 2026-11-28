from __future__ import annotations

import unittest

from utils.failover.checker import (
    acks_between,
    audit,
    lost_window_s,
    max_write_gap_s,
    parse_checker_output,
    parse_probe_output,
)

_LOG = """\
start run-1 0
ack 1 1000
fail 2 1200
ack 3 1400
noise from the engine client
ack 4 5400
present 1
present 3
present 4
present 9
done
"""


class TestParse(unittest.TestCase):
    def test_parses_acks_fails_and_present(self):
        run = parse_checker_output(_LOG)
        self.assertEqual(run.acks, {1: 1000, 3: 1400, 4: 5400})
        self.assertEqual(run.fails, {2: 1200})
        self.assertEqual(run.present, {1, 3, 4, 9})
        self.assertTrue(run.done)

    def test_unfinished_run_is_not_done(self):
        self.assertFalse(parse_checker_output("ack 1 10\n").done)

    def test_service_log_prefixes_are_ignored(self):
        run = parse_checker_output("svc.1.abc@node    | ack 7 70\n")
        self.assertEqual(run.acks, {7: 70})


class TestAudit(unittest.TestCase):
    def test_every_acked_sequence_present_passes(self):
        self.assertEqual(audit(parse_checker_output(_LOG)), [])

    def test_missing_acked_sequences_are_reported_sorted(self):
        run = parse_checker_output("ack 5 1\nack 2 2\nack 3 3\npresent 3\ndone\n")
        self.assertEqual(audit(run), [2, 5])

    def test_unacked_writes_may_be_missing(self):
        run = parse_checker_output("fail 1 1\nack 2 2\npresent 2\ndone\n")
        self.assertEqual(audit(run), [])


class TestWriteGap(unittest.TestCase):
    def test_gap_is_longest_span_between_acks(self):
        self.assertAlmostEqual(max_write_gap_s(parse_checker_output(_LOG)), 4.0)

    def test_fewer_than_two_acks_spans_the_whole_run(self):
        run = parse_checker_output("start r 0\nack 1 3000\nfail 2 9000\ndone\n")
        self.assertAlmostEqual(max_write_gap_s(run), 6.0)

    def test_no_acks_is_infinite(self):
        run = parse_checker_output("start r 0\nfail 1 100\n")
        self.assertEqual(max_write_gap_s(run), float("inf"))


class TestLostWindow(unittest.TestCase):
    def test_slow_acks_widen_the_window_beyond_count_times_interval(self):
        log = "".join(f"ack {seq} {seq * 400}\n" for seq in range(1, 31)) + "done\n"
        run = parse_checker_output(log)
        lost = audit(run)
        self.assertEqual(len(lost), 30)
        self.assertAlmostEqual(lost_window_s(run, lost), 11.6)

    def test_an_old_lost_write_stretches_the_window(self):
        run = parse_checker_output(
            "ack 1 1000\nack 2 60000\nack 3 60200\npresent 2\ndone\n"
        )
        self.assertAlmostEqual(lost_window_s(run, audit(run)), 59.2)

    def test_nothing_lost_is_an_empty_window(self):
        self.assertEqual(lost_window_s(parse_checker_output(_LOG), []), 0.0)


class TestAcksBetween(unittest.TestCase):
    def test_window_is_inclusive_and_sorted(self):
        run = parse_checker_output(_LOG)
        self.assertEqual(acks_between(run, 1000, 1400), [1, 3])
        self.assertEqual(acks_between(run, 1401, 5399), [])


class TestProbeOutput(unittest.TestCase):
    def test_records_and_done_are_parsed_through_log_prefixes(self):
        done, records = parse_probe_output(
            "svc.1.x@w1    | probe ddl ok\nnoise\nprobe marker found\nprobe-done\n"
        )
        self.assertTrue(done)
        self.assertEqual(records, {"ddl": "ok", "marker": "found"})

    def test_a_detail_record_keeps_its_whole_text(self):
        _, records = parse_probe_output(
            "probe idle fail\nprobe idle-detail server closed the connection \nprobe-done\n"
        )
        self.assertEqual(records["idle-detail"], "server closed the connection")

    def test_unfinished_probe_is_not_done(self):
        self.assertEqual(parse_probe_output("probe idle ok\n"), (False, {"idle": "ok"}))


if __name__ == "__main__":
    unittest.main()
