from __future__ import annotations

import unittest

from r1.yahoo_target_prices import parse_targets


class YahooTargetPricesTest(unittest.TestCase):
    def test_parses_anonymous_aggregate_as_non_scoreable(self) -> None:
        row = parse_targets(
            {"current": 100, "low": 90, "mean": 130, "median": 125, "high": 160},
            ticker="2330", symbol="2330.TW", retrieved_at="2026-10-19",
        )
        self.assertEqual(row["status"], "READY_AGGREGATE_ONLY")
        self.assertFalse(row["scoreable"])
        self.assertAlmostEqual(row["mean_upside"], 0.3)

    def test_accepts_missing_range_as_partial_but_not_scoreable(self) -> None:
        row = parse_targets(
            {"current": 100, "mean": 130, "median": 125, "high": 160},
            ticker="2330", symbol="2330.TW", retrieved_at="2026-10-19",
        )
        self.assertEqual(row["status"], "READY_AGGREGATE_PARTIAL")
        self.assertIsNone(row["target_low"])
        self.assertFalse(row["scoreable"])

    def test_rejects_missing_central_estimate(self) -> None:
        with self.assertRaisesRegex(ValueError, "median_target_missing"):
            parse_targets(
                {"current": 100, "low": 90, "mean": 130, "high": 160},
                ticker="2330", symbol="2330.TW", retrieved_at="2026-10-19",
            )


if __name__ == "__main__":
    unittest.main()
