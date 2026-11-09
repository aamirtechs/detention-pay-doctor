"""Tests for detention_pay_doctor. Standard library only."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detention_pay_doctor import (  # noqa: E402
    LoadError,
    build_report,
    compute_load,
    main,
    parse_timestamp,
)

DEFAULTS = {
    "free_hours": Decimal("2"),
    "rate": Decimal("75"),
    "increment": Decimal("15"),
    "cap": None,
}


def load(**overrides):
    entry = {
        "id": "L-1",
        "arrival": "2026-11-02T08:00:00",
        "departure": "2026-11-02T10:00:00",
    }
    entry.update(overrides)
    return entry


class TestComputeLoad(unittest.TestCase):
    def test_free_time_not_exceeded_pays_zero(self):
        result = compute_load(
            load(departure="2026-11-02T09:30:00"), DEFAULTS)
        self.assertEqual(result["total_wait_hours"], 1.5)
        self.assertEqual(result["billable_hours"], 0.0)
        self.assertEqual(result["amount"], 0.0)

    def test_free_time_exactly_met_pays_zero(self):
        result = compute_load(load(), DEFAULTS)
        self.assertEqual(result["billable_hours"], 0.0)
        self.assertEqual(result["amount"], 0.0)

    def test_partial_increment_rounds_up(self):
        # Wait 3h10m, free 2h, excess 70 min, rounds up to 75 min.
        result = compute_load(
            load(departure="2026-11-02T11:10:00"), DEFAULTS)
        self.assertEqual(result["billable_minutes"], 75.0)
        self.assertEqual(result["billable_hours"], 1.25)
        self.assertEqual(result["amount"], 93.75)

    def test_exact_increment_not_rounded_up(self):
        # Excess exactly 60 min at a 15 min increment stays 60 min.
        result = compute_load(
            load(departure="2026-11-02T11:00:00"), DEFAULTS)
        self.assertEqual(result["billable_minutes"], 60.0)
        self.assertEqual(result["amount"], 75.0)

    def test_cap_applied(self):
        result = compute_load(
            load(arrival="2026-11-02T07:00:00",
                 departure="2026-11-02T19:00:00", cap_amount=300),
            DEFAULTS)
        self.assertEqual(result["billable_hours"], 10.0)
        self.assertEqual(result["amount"], 300.0)
        self.assertTrue(result["capped"])

    def test_cap_not_applied_below_cap(self):
        result = compute_load(
            load(departure="2026-11-02T11:00:00", cap_amount=300),
            DEFAULTS)
        self.assertEqual(result["amount"], 75.0)
        self.assertFalse(result["capped"])

    def test_overnight_wait(self):
        result = compute_load(
            load(arrival="2026-11-02T22:00:00",
                 departure="2026-11-03T06:30:00"), DEFAULTS)
        self.assertEqual(result["total_wait_hours"], 8.5)
        self.assertEqual(result["billable_hours"], 6.5)
        self.assertEqual(result["amount"], 487.50)

    def test_date_and_time_pairs(self):
        entry = {
            "id": "L-9",
            "arrival_date": "2026-11-02",
            "arrival_time": "08:00",
            "departure_date": "2026-11-02",
            "departure_time": "11:10",
        }
        result = compute_load(entry, DEFAULTS)
        self.assertEqual(result["billable_hours"], 1.25)
        self.assertEqual(result["amount"], 93.75)

    def test_iso_z_suffix(self):
        result = compute_load(
            load(arrival="2026-11-02T08:00:00Z",
                 departure="2026-11-02T11:10:00Z"), DEFAULTS)
        self.assertEqual(result["amount"], 93.75)

    def test_cents_rounding_half_up(self):
        # 1 hour at $33.335 rounds to $33.34, not $33.33.
        result = compute_load(
            load(departure="2026-11-02T11:00:00", rate_per_hour="33.335"),
            DEFAULTS)
        self.assertEqual(result["amount"], 33.34)

    def test_cli_defaults_override(self):
        defaults = dict(DEFAULTS, free_hours=Decimal("1"),
                        rate=Decimal("100"),
                        increment=Decimal("30"))
        result = compute_load(load(departure="2026-11-02T10:00:00"), defaults)
        # Wait 2h, free 1h, excess 60 min, 30 min increment: 1h at $100.
        self.assertEqual(result["billable_hours"], 1.0)
        self.assertEqual(result["amount"], 100.0)

    def test_missing_departure_raises(self):
        entry = load()
        del entry["departure"]
        with self.assertRaises(LoadError):
            compute_load(entry, DEFAULTS)

    def test_missing_arrival_raises(self):
        entry = load()
        del entry["arrival"]
        with self.assertRaises(LoadError):
            compute_load(entry, DEFAULTS)

    def test_missing_id_raises(self):
        entry = load()
        del entry["id"]
        with self.assertRaises(LoadError):
            compute_load(entry, DEFAULTS)

    def test_departure_before_arrival_raises(self):
        with self.assertRaises(LoadError):
            compute_load(load(departure="2026-11-02T07:00:00"), DEFAULTS)

    def test_unparseable_timestamp_raises(self):
        with self.assertRaises(LoadError):
            compute_load(load(arrival="not a time"), DEFAULTS)

    def test_negative_rate_raises(self):
        with self.assertRaises(LoadError):
            compute_load(load(rate_per_hour=-5), DEFAULTS)

    def test_zero_increment_raises(self):
        with self.assertRaises(LoadError):
            compute_load(load(billing_increment_minutes=0), DEFAULTS)


class TestReportAndCli(unittest.TestCase):
    def test_json_output_shape(self):
        report = build_report(
            [load(), load(id="L-2", departure="2026-11-02T11:10:00")],
            DEFAULTS)
        self.assertIn("loads", report)
        self.assertIn("totals", report)
        self.assertIn("errors", report)
        self.assertEqual(len(report["loads"]), 2)
        for item in report["loads"]:
            for key in ("id", "arrival", "departure", "total_wait_hours",
                        "free_hours", "billable_hours", "amount"):
                self.assertIn(key, item)
        self.assertEqual(report["totals"]["loads"], 2)
        self.assertEqual(report["totals"]["total_amount"], 93.75)
        self.assertEqual(report["errors"], [])

    def test_invalid_entries_collected_not_fatal(self):
        bad = load()
        del bad["departure"]
        report = build_report([load(), bad], DEFAULTS)
        self.assertEqual(len(report["loads"]), 1)
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("L-1", report["errors"][0])

    def test_check_exits_zero_on_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "loads.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([load()], handle)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([path, "--check"]), 0)

    def test_check_exits_one_on_bad_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "loads.json")
            bad = load()
            del bad["departure"]
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([bad], handle)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([path, "--check"]), 1)

    def test_check_exits_zero_without_flag_even_with_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "loads.json")
            bad = load()
            del bad["departure"]
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([bad], handle)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([path]), 0)

    def test_json_flag_emits_parseable_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "loads.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([load()], handle)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main([path, "--json"])
            self.assertEqual(code, 0)
            report = json.loads(buffer.getvalue())
            self.assertEqual(report["totals"]["loads"], 1)

    def test_text_output_contains_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "loads.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([load(departure="2026-11-02T11:10:00")], handle)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main([path])
            self.assertIn("total amount $93.75", buffer.getvalue())

    def test_parse_timestamp_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_timestamp("tomorrow-ish")


if __name__ == "__main__":
    unittest.main()
