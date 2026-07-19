import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_old_ai7_deferred_6669_close_fill import load_authority


class OldAi7Deferred6669CloseFillTest(unittest.TestCase):
    def test_authority_requires_one_exact_deferred_key(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"
            pd.DataFrame([{"ticker": "6669", "date": "2019-04-16"}]).to_csv(path, index=False)
            self.assertEqual(load_authority(path)["role"], "sell")


if __name__ == "__main__":
    unittest.main()
