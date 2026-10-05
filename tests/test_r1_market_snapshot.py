import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from r1.market_snapshot import _load_universe, _ratio, _return, load_exact_complete_snapshot


class R1MarketSnapshotTest(unittest.TestCase):
    def test_return_uses_exact_trading_day_offset(self):
        series = pd.Series([100.0, 101.0, 102.0, 105.0, 110.0, 120.0])
        self.assertAlmostEqual(_return(series, 5), 0.20)

    def test_insufficient_return_history_is_missing(self):
        self.assertIsNone(_return(pd.Series([100.0, 101.0]), 5))

    def test_bias_is_ratio_not_percentage_points(self):
        self.assertAlmostEqual(_ratio(110.0, 100.0), 0.10)
        self.assertIsNone(_ratio(100.0, float("nan")))

    def test_reuses_only_exact_complete_snapshot(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            tickers = ["2330", "2327", "2344", "2376", "2454", "3037", "6488",
                       "2408", "2303", "3363", "3081", "3711", "2308", "2379"]
            path.write_text(json.dumps({
                "date": "2026-10-02", "requested_ticker_count": 14, "actual_ticker_count": 14,
                "gaps": [], "rows": [{"ticker": ticker, "raw_close": 1} for ticker in tickers],
            }), encoding="utf-8")
            self.assertIsNotNone(load_exact_complete_snapshot(
                output=path, target="2026-10-02", config_path="config/r1.json"))
            self.assertIsNone(load_exact_complete_snapshot(
                output=path, target="2026-10-03", config_path="config/r1.json"))

    def test_theme_universe_is_independent_and_complete(self):
        universe = _load_universe(
            config_path="config/r1.json", theme_path="config/r1_v02_themes.json")
        self.assertEqual(len(universe), 50)
        self.assertIn("2330", universe)
        self.assertIn("3131", universe)

    def test_theme_universe_does_not_change_original_r1_universe(self):
        original = _load_universe(config_path="config/r1.json")
        themed = _load_universe(
            config_path="config/r1.json", theme_path="config/r1_v02_themes.json")
        self.assertEqual(len(original), 14)
        self.assertEqual(len(themed), 50)


if __name__ == "__main__":
    unittest.main()
