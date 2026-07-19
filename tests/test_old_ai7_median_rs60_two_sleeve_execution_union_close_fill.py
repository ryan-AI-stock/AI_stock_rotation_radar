import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_old_ai7_median_rs60_two_sleeve_execution_union_close_fill import load_authority


class OldAi7MedianRs60TwoSleeveExecutionUnionCloseFillTest(unittest.TestCase):
    def test_authority_requires_34_exact_00631l_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            dates = pd.date_range("2020-01-01", periods=34, freq="B").strftime("%Y-%m-%d")
            pd.DataFrame({"ticker": "00631L", "date": dates}).to_csv(path, index=False)
            self.assertEqual(len(load_authority(path)), 34)


if __name__ == "__main__":
    unittest.main()
