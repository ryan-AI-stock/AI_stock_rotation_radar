import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from r1.yahoo_consensus import _fetch_estimates_with_retry, parse_estimates


class YahooConsensusTest(unittest.TestCase):
    def test_transport_failure_is_retried_three_times(self):
        ticker = MagicMock()
        ticker.get_earnings_estimate.side_effect = RuntimeError("temporary")
        with patch("r1.yahoo_consensus.yf.Ticker", return_value=ticker) as factory:
            with patch("r1.yahoo_consensus.time.sleep"):
                with self.assertRaises(RuntimeError):
                    _fetch_estimates_with_retry("2330.TW")
        self.assertEqual(factory.call_count, 3)
        self.assertEqual(ticker.get_earnings_estimate.call_count, 3)

    def test_parses_only_current_and_next_annual_estimates(self):
        table = pd.DataFrame([
            {"period": "0q", "avg": 2, "low": 1, "high": 3, "numberOfAnalysts": 4},
            {"period": "0y", "avg": 10, "low": 8, "high": 12, "numberOfAnalysts": 8},
            {"period": "+1y", "avg": 14, "low": 11, "high": 17, "numberOfAnalysts": 6},
        ]).set_index("period")
        rows = parse_estimates(table, ticker="2330", retrieved_at="2026-10-14")
        self.assertEqual([(r["fiscal_year"], r["mean_eps"]) for r in rows],
                         [("2026", "10"), ("2027", "14")])

    def test_rejects_incomplete_forward_pair(self):
        table = pd.DataFrame([
            {"period": "0y", "avg": 10, "low": 8, "high": 12, "numberOfAnalysts": 8},
        ]).set_index("period")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_estimates(table, ticker="2330", retrieved_at="2026-10-14")


if __name__ == "__main__":
    unittest.main()
