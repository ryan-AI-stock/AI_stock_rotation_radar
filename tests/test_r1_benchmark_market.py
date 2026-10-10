import unittest
from unittest.mock import patch

import pandas as pd

from r1.benchmark_market import build_snapshot


class BenchmarkMarketTest(unittest.TestCase):
    def test_requires_exact_date_for_all_three_tickers(self):
        frame = pd.DataFrame([
            {"ticker": ticker, "date": "2026-10-10", "close": close}
            for ticker, close in (("00631", 100), ("2308", 900), ("2317", 250))
        ])
        with patch("r1.benchmark_market.load_official_prices_and_turnover",
                   return_value=(frame, pd.DataFrame())):
            result = build_snapshot(date="2026-10-10")
        self.assertEqual(result["actual_ticker_count"], 3)
        self.assertFalse(result["gaps"])


if __name__ == "__main__":
    unittest.main()
