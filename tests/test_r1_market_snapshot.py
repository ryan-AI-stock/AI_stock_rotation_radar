import unittest

import pandas as pd

from r1.market_snapshot import _ratio, _return


class R1MarketSnapshotTest(unittest.TestCase):
    def test_return_uses_exact_trading_day_offset(self):
        series = pd.Series([100.0, 101.0, 102.0, 105.0, 110.0, 120.0])
        self.assertAlmostEqual(_return(series, 5), 0.20)

    def test_insufficient_return_history_is_missing(self):
        self.assertIsNone(_return(pd.Series([100.0, 101.0]), 5))

    def test_bias_is_ratio_not_percentage_points(self):
        self.assertAlmostEqual(_ratio(110.0, 100.0), 0.10)
        self.assertIsNone(_ratio(100.0, float("nan")))


if __name__ == "__main__":
    unittest.main()
