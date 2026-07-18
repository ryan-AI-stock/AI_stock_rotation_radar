import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_strict_bear_cash_incremental_close_fill import exact_rows, load_authority


class StrictBearCashIncrementalCloseFillTest(unittest.TestCase):
    def test_current_authority_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "a.csv"; pd.DataFrame({"ticker": ["00631L"] * 9, "date": ["2018-07-02", "2019-01-02", "2019-04-01", "2020-04-20", "2022-05-16", "2022-08-29", "2022-10-11", "2022-11-28", "2022-12-12"]}).to_csv(path, index=False)
            self.assertEqual(len(load_authority(path)), 9)

    def test_exact_rows_filters_month(self):
        rows = exact_rows({"rows": [{"date": "2022-10-31", "close": 101.0}, {"date": "2022-10-28", "close": 100.0}]}, {"2022-10-31"}, "test")
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["close"], 101.0)


if __name__ == "__main__": unittest.main()
