import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sleeve_internal_timing_close_fill import exact_rows, load_authority


class SleeveInternalTimingCloseFillTest(unittest.TestCase):
    def test_authority_requires_97_exact_00631l_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            pd.DataFrame({"ticker": ["00631L"] * 97, "date": [f"2020-01-{day:02d}" for day in range(1, 98)]}).to_csv(path, index=False)
            self.assertEqual(len(load_authority(path)), 97)

    def test_exact_rows_filters_dates(self):
        rows = exact_rows({"rows": [{"date": "2022-10-31", "close": 101.0}, {"date": "2022-10-28", "close": 100.0}]}, {"2022-10-31"}, "test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 101.0)


if __name__ == "__main__":
    unittest.main()
