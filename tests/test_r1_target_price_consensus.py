from __future__ import annotations

import unittest

from r1.target_price_consensus import TargetPriceRecord, build_consensus, build_snapshot


def row(institution: str, price: float, available: str = "2026-10-01") -> TargetPriceRecord:
    return TargetPriceRecord("2330", institution, price, "12M", available, "https://example.test/report")


class R1TargetPriceConsensusTest(unittest.TestCase):
    def test_three_institutions_use_median_not_highest_target(self) -> None:
        result = build_consensus(
            records=[row("A", 300), row("B", 330), row("C", 1000)],
            ticker="2330", current_price=200, as_of_date="2026-10-10",
        )
        self.assertEqual(result["consensus_target_price"], 330)
        self.assertAlmostEqual(result["consensus_upside"], 0.65)
        self.assertEqual(result["status"], "READY")

    def test_single_broker_is_display_only(self) -> None:
        result = build_consensus(
            records=[row("A", 1000)], ticker="2330", current_price=200,
            as_of_date="2026-10-10",
        )
        self.assertEqual(result["status"], "DATA_MISSING")
        self.assertFalse(result["scoreable"])

    def test_future_and_stale_records_are_rejected(self) -> None:
        result = build_consensus(
            records=[row("future", 300, "2026-10-11"), row("stale", 300, "2026-01-01")],
            ticker="2330", current_price=200, as_of_date="2026-10-10",
        )
        self.assertEqual(result["institution_count"], 0)
        self.assertEqual({item["error"] for item in result["rejected"]}, {"future_data", "stale"})

    def test_snapshot_keeps_incomplete_ticker_explicit(self) -> None:
        result = build_snapshot(
            date="2026-10-10", tickers=["2330", "2454"], evidence_path="missing.csv",
            market={"rows": [{"ticker": "2330", "raw_close": 1000}, {"ticker": "2454", "raw_close": 1500}]},
        )
        self.assertEqual(result["ready_ticker_count"], 0)
        self.assertEqual([row["status"] for row in result["rows"]], ["DATA_MISSING", "DATA_MISSING"])


if __name__ == "__main__":
    unittest.main()
