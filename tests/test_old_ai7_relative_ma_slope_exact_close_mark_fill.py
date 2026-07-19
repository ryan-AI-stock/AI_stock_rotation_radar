import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_old_ai7_relative_ma_slope_exact_close_mark_fill import factor_continuity_mark, exact_official_rows, load_mark_authority, load_raw_authority


class OldAi7RelativeExactCloseMarkFillTest(unittest.TestCase):
    def test_raw_authority_requires_exact_five_ticker_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "raw.csv"
            rows = ([{"ticker": "00631L", "date": f"2020-01-{index:02d}"} for index in range(1, 68)]
                    + [{"ticker": "2308", "date": "2015-09-29"}, {"ticker": "2382", "date": "2020-09-10"}]
                    + [{"ticker": "2454", "date": "2023-01-13"}, {"ticker": "2454", "date": "2023-03-01"}]
                    + [{"ticker": "6669", "date": "2021-11-12"}])
            pd.DataFrame(rows).to_csv(path, index=False)
            self.assertEqual(len(load_raw_authority(path)), 72)

    def test_mark_authority_requires_one_exact_key(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mark.csv"
            pd.DataFrame([{"date": "2025-08-01", "ticker": "2308"}]).to_csv(path, index=False)
            self.assertEqual(len(load_mark_authority(path)), 1)

    def test_exact_official_rows_filters_target_dates(self):
        rows = exact_official_rows({"rows": [{"date": "2022-10-31", "close": 101.0}, {"date": "2022-10-28", "close": 100.0}]}, "00631L", {"2022-10-31"}, "test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 101.0)

    def test_2308_factor_continuity_is_not_raw_as_adjusted(self):
        mark, audit = factor_continuity_mark("2025-08-01", 588.0)
        self.assertIsNotNone(mark)
        self.assertNotEqual(mark["adjusted_analysis_mark"], 588.0)
        self.assertFalse(audit["raw_used_as_adjusted"])


if __name__ == "__main__":
    unittest.main()
