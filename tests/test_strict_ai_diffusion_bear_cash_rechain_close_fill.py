import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_strict_ai_diffusion_bear_cash_rechain_close_fill import EXPECTED_DATES, extract_exact, load_authority


class StrictAiDiffusionBearCashRechainCloseFillTest(unittest.TestCase):
    def test_authority_scope_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "authority.csv"; pd.DataFrame({"ticker": ["00631L"] * 4, "date": EXPECTED_DATES}).to_csv(path, index=False)
            self.assertEqual(load_authority(path)["date"].tolist(), EXPECTED_DATES)

    def test_extract_exact_close_only(self):
        rows = extract_exact({"rows": [{"date": "2022-08-22", "close": 90.0}, {"date": "2022-08-23", "close": 91.0}]}, {"2022-08-22"})
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["date"], "2022-08-22"); self.assertEqual(rows[0]["close"], 90.0)


if __name__ == "__main__": unittest.main()
