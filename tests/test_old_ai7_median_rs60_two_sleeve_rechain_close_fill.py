import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_old_ai7_median_rs60_two_sleeve_rechain_close_fill import load_authority


class OldAi7MedianRs60TwoSleeveRechainCloseFillTest(unittest.TestCase):
    def test_authority_requires_two_exact_00631l_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            pd.DataFrame([{"ticker": "00631L", "date": "2019-04-02"}, {"ticker": "00631L", "date": "2023-05-26"}]).to_csv(path, index=False)
            self.assertEqual(len(load_authority(path)), 2)


if __name__ == "__main__":
    unittest.main()
