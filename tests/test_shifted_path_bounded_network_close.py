from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_p1_p2_ma_slope_cd50_shifted_path_bounded_network_close import join_exact_close_values


class ShiftedPathBoundedNetworkCloseTest(unittest.TestCase):
    def test_existing_empty_close_column_does_not_create_unreadable_merge_suffix(self) -> None:
        authority = pd.DataFrame([{
            "period": "P1", "ticker": "2330", "date": "2020-01-02",
            "adjusted_analysis_close": None, "source_quality": None,
        }])
        values = pd.DataFrame([{
            "ticker": "2330", "date": "2020-01-02", "adjusted_analysis_close": 100.5,
            "source_quality": "trusted_test",
        }])

        joined = join_exact_close_values(authority, values, "adjusted_analysis_close")

        self.assertEqual(joined.loc[0, "adjusted_analysis_close"], 100.5)
        self.assertNotIn("adjusted_analysis_close_x", joined.columns)
        self.assertNotIn("adjusted_analysis_close_y", joined.columns)

    def test_raw_market_lineage_comes_from_exact_value_source(self) -> None:
        authority = pd.DataFrame([{
            "period": "P2", "ticker": "2303", "date": "2023-03-15",
            "official_raw_close": None, "market": "TWSE",
        }])
        values = pd.DataFrame([{
            "ticker": "2303", "date": "2023-03-15", "official_raw_close": 56.0,
            "market": "TWSE", "source_quality": "official_test",
        }])

        joined = join_exact_close_values(authority, values, "official_raw_close")

        self.assertEqual(joined.loc[0, "official_raw_close"], 56.0)
        self.assertEqual(joined.loc[0, "market"], "TWSE")


if __name__ == "__main__":
    unittest.main()
