import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_strict_bear_cash_incremental_close_fill import exact_rows, load_authority


class StrictBearCashIncrementalCloseFillTest(unittest.TestCase):
    def test_current_authority_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "a.csv"; pd.DataFrame({"ticker": ["00631L"] * 3, "date": ["2018-05-21", "2018-11-19", "2022-10-31"]}).to_csv(path, index=False)
            self.assertEqual(len(load_authority(path)), 3)

    def test_exact_rows_filters_month(self):
        rows = exact_rows({"rows": [{"date": "2022-10-31", "close": 101.0}, {"date": "2022-10-28", "close": 100.0}]}, {"2022-10-31"}, "test")
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["close"], 101.0)


if __name__ == "__main__": unittest.main()
